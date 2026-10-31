"""
读取 GRASP 径向波函数文件 (name.w、rwfn.out) 并计算轨道性质。只用 Python 标准库。

文件为 Fortran 无格式顺序文件 (每条记录前后各有 4 字节长度)：
    'G92RWF'
    对每个轨道:  n, kappa, energy, npts
                 a0, P(1..npts), Q(1..npts)
                 r(1..npts)
"""

import math
import os
import re
import struct

L_LETTERS = "spdfghiklmnoqrtuv"


class Orbital:
    def __init__(self, n, kappa, energy, a0, r, P, Q):
        self.n, self.kappa, self.energy, self.a0 = n, kappa, energy, a0
        self.r, self.P, self.Q = r, P, Q
        self._grid = exp_grid(r)

    @property
    def l(self):
        return self.kappa if self.kappa > 0 else -self.kappa - 1

    @property
    def name(self):
        """GRASP 写法：2p- 为 j = l - 1/2，2p 为 j = l + 1/2。"""
        return f"{self.n}{L_LETTERS[self.l]}{'-' if self.kappa > 0 else ''}"

    @property
    def sort_key(self):
        return (self.n, self.l, 0 if self.kappa > 0 else 1)

    def density(self):
        return [p * p + q * q for p, q in zip(self.P, self.Q)]

    def integrate(self, values):
        return integrate(values, self.r, self._grid)

    def norm(self):
        return self.integrate(self.density())

    def mean_r(self, k=1):
        """<r^k> = ∫ r^k (P² + Q²) dr"""
        return self.integrate([r ** k * d for r, d in zip(self.r, self.density())])

    def r_peak(self):
        """|P| 最大处的 r"""
        i = max(range(len(self.P)), key=lambda i: abs(self.P[i]))
        return self.r[i]

    def nodes(self, thresh=0.05):
        """大分量 P(r) 的节点数，与 GRASP 的 COUNT (lib9290/count.f90) 相同：
        按变号分成若干段，去掉幅度小于最大幅度 thresh 倍的段 (rmcdhf 默认 0.05)，再数剩余各段之间的变号。"""
        lobes = []                 # 每段的极值
        for p in self.P[1:]:
            if lobes and (p > 0) == (lobes[-1] > 0) or (lobes and p == 0):
                if abs(p) > abs(lobes[-1]):
                    lobes[-1] = p
            else:
                lobes.append(p)
        big = max((abs(x) for x in lobes), default=0.0)
        kept = [x for x in lobes if abs(x) >= thresh * big]
        return sum(1 for a, b in zip(kept, kept[1:]) if (a > 0) != (b > 0))

    def expected_nodes(self):
        return self.n - self.l - 1


def exp_grid(r):
    """GRASP 网格 r_i = RNT (exp((i-1) h) - 1)：返回 (RNT, h)；不是这种网格时返回 None。"""
    if len(r) < 4 or r[1] <= 0 or r[2] / r[1] <= 1:
        return None
    h = math.log(r[2] / r[1] - 1)
    if h <= 0:
        return None
    rnt = r[1] / (math.exp(h) - 1)
    for i in (len(r) // 2, len(r) - 1):
        if abs(rnt * (math.exp(i * h) - 1) - r[i]) > 1e-8 * max(r[i], 1e-30):
            return None
    return rnt, h


def integrate(values, r, grid=None):
    """∫ f dr。指数网格上用均匀变量的 Simpson 公式 (与 GRASP 的精度一致)，否则用梯形公式。"""
    n = len(values)
    if grid:
        rnt, h = grid
        g = [v * (x + rnt) * h for v, x in zip(values, r)]
        m = n - 1 if (n - 1) % 2 == 0 else n - 2
        s = (g[0] + g[m] + 4 * sum(g[1:m:2]) + 2 * sum(g[2:m - 1:2])) / 3
        if m != n - 1:
            s += (g[m] + g[m + 1]) / 2
        return s
    return sum((values[i] + values[i + 1]) / 2 * (r[i + 1] - r[i]) for i in range(n - 1))


def read_w(path):
    """读取 .w 文件，返回按 n、l、κ 排序的 Orbital 列表。格式不对时抛出 ValueError。"""
    with open(path, "rb") as f:
        data = f.read()
    pos = 0

    def record():
        nonlocal pos
        if pos + 4 > len(data):
            raise ValueError("truncated file")
        size, = struct.unpack_from("<i", data, pos)
        end = pos + 4 + size
        if size < 0 or end + 4 > len(data) or struct.unpack_from("<i", data, end)[0] != size:
            raise ValueError("not a Fortran unformatted file")
        body = data[pos + 4:end]
        pos = end + 4
        return body

    if record()[:6] != b"G92RWF":
        raise ValueError("not a GRASP radial wave function file (G92RWF)")
    orbitals = []
    while pos < len(data):
        n, kappa, energy, npts = struct.unpack("<iidi", record())
        pq = record()
        a0, = struct.unpack_from("<d", pq)
        P = struct.unpack_from(f"<{npts}d", pq, 8)
        Q = struct.unpack_from(f"<{npts}d", pq, 8 + 8 * npts)
        r = struct.unpack(f"<{npts}d", record())
        orbitals.append(Orbital(n, kappa, energy, a0, r, P, Q))
    return sorted(orbitals, key=lambda o: o.sort_key)


def orbital_names(path):
    """文件中各轨道的名称 (如 2p-)，只读每个轨道的头记录，不解析 P、Q 数组。"""
    names = []
    with open(path, "rb") as f:
        def record(keep):
            head = f.read(4)
            if len(head) < 4:
                return None
            size, = struct.unpack("<i", head)
            if size < 0:
                raise ValueError("not a Fortran unformatted file")
            body = f.read(size) if keep else f.seek(size, 1)
            f.read(4)
            return body
        if (record(True) or b"")[:6] != b"G92RWF":
            raise ValueError("not a GRASP radial wave function file (G92RWF)")
        while True:
            head = record(True)
            if not head:
                break
            n, kappa = struct.unpack_from("<ii", head)
            l = kappa if kappa > 0 else -kappa - 1
            names.append(f"{n}{L_LETTERS[l]}{'-' if kappa > 0 else ''}")
            record(False)
            record(False)
    return names


def natural_key(name):
    """odd2.w < odd10.w"""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


def is_wfn_file(path):
    """文件头是否为 G92RWF (与文件名无关)。"""
    try:
        with open(path, "rb") as f:
            head = f.read(10)
    except OSError:
        return False
    return len(head) == 10 and struct.unpack_from("<i", head)[0] == 6 and head[4:10] == b"G92RWF"


def find_w_files(directory):
    """目录中所有径向波函数文件 (按文件头识别：name.w、rwfn.inp、rwfn.out 以及改过名的文件)。"""
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    files = [n for n in names if os.path.isfile(os.path.join(directory, n)) and is_wfn_file(os.path.join(directory, n))]
    return sorted(files, key=natural_key)
