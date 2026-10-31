"""
读取 GRASP 的原子态 (ASF) 结果，只用 Python 标准库：

  * 混合系数文件 name.m (rmcdhf)、name.cm (rci)、rmix.out —— Fortran 无格式顺序文件：
        'G92MIX'
        nelec, ncftot, nw, nvectot, nvecsiz, nblock
        对每个对称块:  nb, ncf, nev, 2J+1, parity
                       ivec(1..nev)                     能级在块内的序号
                       eav, eval(1..nev)                总能量 = eav + eval
                       evec(1..ncf, 1..nev)             混合系数
  * CSF 列表 name.c —— 文本，每个 CSF 三行，块之间以 "*" 分隔
  * jj2lsj 的 LSJ 组成 name.lsj.lbl —— 文本
"""

import array
import os
import re
import struct

HARTREE_CM = 219474.6313632     # 1 a.u. 能量 = 219474.63 cm⁻¹
HARTREE_EV = 27.211386245988


class Level:
    def __init__(self, block, pos, energy, coeffs):
        self.block, self.pos, self.energy, self.coeffs = block, pos, energy, coeffs

    @property
    def J(self):
        return self.block.J

    @property
    def parity(self):
        return self.block.parity

    def components(self, min_weight=0.0):
        """[(CSF 在块内的序号 (从 1 开始), 系数)]，按权重从大到小。"""
        comps = [(i + 1, c) for i, c in enumerate(self.coeffs) if c * c >= min_weight]
        return sorted(comps, key=lambda t: -t[1] * t[1])

    def leading(self):
        return max(range(len(self.coeffs)), key=lambda i: abs(self.coeffs[i])) + 1


class Block:
    def __init__(self, nb, ncf, twoj1, parity):
        self.nb, self.ncf, self.twoj1, self.parity = nb, ncf, twoj1, parity
        self.levels = []

    @property
    def J(self):
        """J 的字符串，如 1/2、2"""
        twoj = self.twoj1 - 1
        return f"{twoj // 2}" if twoj % 2 == 0 else f"{twoj}/2"

    @property
    def label(self):
        return f"{self.J}{'+' if self.parity > 0 else '-'}"


def _records(data):
    pos = 0
    while pos < len(data):
        size, = struct.unpack_from("<i", data, pos)
        end = pos + 4 + size
        if size < 0 or end + 4 > len(data) or struct.unpack_from("<i", data, end)[0] != size:
            raise ValueError("not a Fortran unformatted file")
        yield data[pos + 4:end]
        pos = end + 4


def read_mix(path):
    """读取混合系数文件，返回 [Block]；各 Block.levels 为 [Level]。"""
    with open(path, "rb") as f:
        recs = _records(f.read())
        try:
            if next(recs)[:6] != b"G92MIX":
                raise ValueError("not a GRASP mixing coefficient file (G92MIX)")
            nelec, ncftot, nw, nvectot, nvecsiz, nblock = struct.unpack("<6i", next(recs)[:24])
            blocks = []
            for _ in range(nblock):
                nb, ncf, nev, twoj1, parity = struct.unpack("<5i", next(recs)[:20])
                block = Block(nb, ncf, twoj1, parity)
                if nev > 0:
                    ivec = struct.unpack(f"<{nev}i", next(recs)[:4 * nev])
                    e = struct.unpack(f"<{nev + 1}d", next(recs)[:8 * (nev + 1)])
                    vec = array.array("d")
                    vec.frombytes(next(recs)[:8 * ncf * nev])
                    for k in range(nev):
                        block.levels.append(Level(block, ivec[k], e[0] + e[k + 1], vec[k * ncf:(k + 1) * ncf]))
                blocks.append(block)
        except StopIteration:
            raise ValueError("truncated mixing coefficient file") from None
    return blocks


def mix_symmetries(path):
    """混合系数文件中各块的 (2J, 宇称)，按块的顺序。"""
    return [(b.twoj1 - 1, b.parity) for b in read_mix(path)]


def _record(body):
    n = struct.pack("<i", len(body))
    return n + body + n


def write_mix_subset(src, dst, keep):
    """只保留 (2J, 宇称) 在 keep 中的块，写出新的混合系数文件；块号重新从 1 编起，
    文件头中的 CSF 总数、能级总数、混合系数总数 (Σ ncf·nev) 和块数随之更新。"""
    with open(src, "rb") as f:
        recs = list(_records(f.read()))
    nelec, ncftot, nw, nvectot, nvecsiz, nblock = struct.unpack("<6i", recs[1][:24])
    blocks, i = [], 2
    for _ in range(nblock):
        nb, ncf, nev, twoj1, parity = struct.unpack("<5i", recs[i][:20])
        n = 4 if nev > 0 else 1
        if (twoj1 - 1, parity) in keep:
            blocks.append((ncf, nev, recs[i:i + n]))
        i += n
    out = [recs[0], struct.pack("<6i", nelec, sum(b[0] for b in blocks), nw, sum(b[1] for b in blocks),
                                sum(b[0] * b[1] for b in blocks), len(blocks)) + recs[1][24:]]
    for nb, (_, _, rs) in enumerate(blocks, 1):
        out.append(struct.pack("<i", nb) + rs[0][4:])
        out += rs[1:]
    with open(dst, "wb") as f:
        f.write(b"".join(_record(r) for r in out))
    return len(blocks)


def write_csf_subset(src, dst, positions):
    """只保留 CSF 文件中第 positions 个块 (从 0 开始，与混合系数文件的块顺序一致)，块之间仍以 " *" 分隔。"""
    with open(src) as f:
        lines = f.read().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("CSF(s):")) + 1
    blocks, cur = [], []
    for ln in lines[start:]:
        if ln.strip() == "*":
            blocks.append(cur)
            cur = []
        else:
            cur.append(ln)
    blocks.append(cur)
    kept = [blocks[i] for i in sorted(positions)]
    body = []
    for k, b in enumerate(kept):
        if k:
            body.append(" *")
        body += b
    with open(dst, "w") as f:
        f.write("\n".join(lines[:start] + body) + "\n")


def read_csfs(path):
    """读取 CSF 文件，返回各块的 CSF 列表 [[(组态, 耦合)]]，与混合系数文件的块一一对应。"""
    with open(path) as f:
        lines = f.read().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("CSF(s):")) + 1
    blocks, current, i = [], [], start
    while i < len(lines):
        if lines[i].strip() == "*":
            blocks.append(current)
            current = []
            i += 1
            continue
        if not lines[i].strip():
            i += 1
            continue
        orbitals = re.sub(r"\s*\(\s*", "(", lines[i].strip())
        orbitals = re.sub(r"\s*\)\s*", ") ", orbitals).strip()
        coupling = " ".join((lines[i + 1].split() if i + 1 < len(lines) else []) +
                            (lines[i + 2].split() if i + 2 < len(lines) else []))
        current.append((orbitals, coupling))
        i += 3
    blocks.append(current)
    return blocks


LEVEL_RE = re.compile(r"^\s*(\d+)\s+(\d+(?:/2)?)\s+([+-])\s+(-?\d+\.\d+)\s+([\d.]+)%")
COMP_RE = re.compile(r"^\s+(-?\d+\.\d+)\s+(\d+\.\d+)\s+(\S+)\s*$")


def read_lsj(path):
    """读取 jj2lsj 的 name.lsj.lbl：返回 [(J, 宇称, 序号, 总能量, 组成百分比, [(系数, 权重, LSJ 标记)])]。"""
    levels = []
    with open(path) as f:
        for line in f:
            m = LEVEL_RE.match(line)
            if m:
                pos, J, par, energy, pct = m.groups()
                levels.append((J, par, int(pos), float(energy), float(pct), []))
                continue
            m = COMP_RE.match(line)
            if m and levels:
                levels[-1][5].append((float(m.group(1)), float(m.group(2)), m.group(3)))
    return levels


# ---------------------------------------------------------------------------
#  按内容识别文件、配对 CSF 列表和 LSJ 结果 (不依赖文件名)
# ---------------------------------------------------------------------------

_sig_cache = {}            # 路径 -> (mtime, 特征)


def _cached(path, fn):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    hit = _sig_cache.get((path, fn))
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        value = fn(path)
    except (OSError, ValueError, StopIteration, struct.error, UnicodeDecodeError, IndexError):
        value = None
    _sig_cache[(path, fn)] = (mtime, value)
    return value


def _head(path, n):
    try:
        with open(path, "rb") as f:
            return f.read(n)
    except OSError:
        return b""


def fortran_tag(path):
    """Fortran 无格式文件第一条记录的 6 字节标识，如 G92MIX、G92RWF；不是时返回 None。"""
    head = _head(path, 10)
    if len(head) == 10 and struct.unpack_from("<i", head)[0] == 6:
        return head[4:10].decode("ascii", "replace")
    return None


def is_csf_file(path):
    return _head(path, 15) == b"Core subshells:"


def _mix_signature(path):
    """(轨道数, ((CSF 数, J, 宇称), ...))，只读文件头和各块的块头。"""
    with open(path, "rb") as f:
        recs = _records(f.read())
    next(recs)
    nelec, ncftot, nw, nvectot, nvecsiz, nblock = struct.unpack("<6i", next(recs)[:24])
    blocks = []
    for _ in range(nblock):
        nb, ncf, nev, twoj1, parity = struct.unpack("<5i", next(recs)[:20])
        b = Block(nb, ncf, twoj1, parity)
        blocks.append((ncf, b.J, "+" if parity > 0 else "-"))
        if nev > 0:
            next(recs), next(recs), next(recs)
    return nw, tuple(blocks)


JP_RE = re.compile(r"(\d+(?:/2)?)([+-])$")


def _csf_signature(path):
    """(轨道数, ((CSF 数, J, 宇称), ...))：轨道数为核心和外层轨道之和，J^π 取自每块第一个 CSF 的第 3 行。"""
    with open(path) as f:
        lines = f.read().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("CSF(s):"))
    nw = sum(len(ln.split()) for ln in lines[:start] if not ln.rstrip().endswith(":"))
    # 与 read_csfs 一样每个 CSF 占 3 行 (第 2 行可能是空行)
    lines = lines[start + 1:] + ["*"]
    blocks, ncf, jp, i = [], 0, None, 0
    while i < len(lines):
        if lines[i].strip() == "*":
            if ncf:
                blocks.append((ncf, *(jp.groups() if jp else ("?", "?"))))
            ncf, jp = 0, None
            i += 1
        elif not lines[i].strip():
            i += 1
        else:
            if not ncf:
                jp = JP_RE.search(lines[i + 2].strip()) if i + 2 < len(lines) else None
            ncf += 1
            i += 3
    return nw, tuple(blocks)


def csf_orbitals(path):
    """CSF 文件用到的全部轨道 (核心和外层)，如 ["1s", "2s", "2p-", "2p"]。"""
    with open(path) as f:
        lines = f.read().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("CSF(s):"))
    return [t for ln in lines[:start] if not ln.rstrip().endswith(":") for t in ln.split()]


def mix_signature(path):
    return _cached(path, _mix_signature)


def csf_signature(path):
    return _cached(path, _csf_signature)


def find_csf_for(mix_path):
    """找与混合系数文件对应的 CSF 文件：特征 (轨道数、各块的 CSF 数与 J^π) 必须一致。
    先试同名的 .c，再试 rcsf.inp / rcsf.out，最后在目录中所有 CSF 文件里找 (新的优先)。"""
    sig = mix_signature(mix_path)
    if not sig:
        return None
    d, base = os.path.split(mix_path)
    stem = os.path.splitext(base)[0]
    first = [os.path.join(d, stem + ".c"), os.path.join(d, "rcsf.inp"), os.path.join(d, "rcsf.out")]
    try:
        others = sorted((os.path.join(d, n) for n in os.listdir(d)), key=os.path.getmtime, reverse=True)
    except OSError:
        others = []
    seen = set()
    for p in first + others:
        if p in seen or not os.path.isfile(p):
            continue
        seen.add(p)
        if is_csf_file(p) and csf_signature(p) == sig:
            return p
    return None


def find_lsj_for(mix_path, blocks):
    """找与混合系数文件对应的 jj2lsj 结果：按能级的 J^π 和能量匹配，先试同名的 .lsj.lbl，
    再试目录中其他 *.lsj.lbl；返回 (路径, {(块号, 序号): LSJ 条目})，匹配最多者优先。"""
    d, base = os.path.split(mix_path)
    stem = os.path.splitext(base)[0]
    same = os.path.join(d, stem + ".lsj.lbl")
    try:
        names = sorted(n for n in os.listdir(d) if n.endswith(".lsj.lbl"))
    except OSError:
        names = []
    nlev = sum(len(b.levels) for b in blocks)
    best = (None, {})
    for p in [same] + [os.path.join(d, n) for n in names if os.path.join(d, n) != same]:
        entries = _cached(p, read_lsj) if os.path.isfile(p) else None
        if not entries:
            continue
        matched = match_lsj(blocks, entries)
        if len(matched) > len(best[1]):
            best = (p, matched)
        if len(matched) == nlev:
            break
    return best


def match_lsj(blocks, lsj_levels, tol=1e-6):
    """把 LSJ 组成按 J、宇称和能量对应到能级上：返回 {(块号, 序号): LSJ 条目}。

    同名的 .m 与 .cm 共用一个 .lsj.lbl，只有能量一致时才对应。
    """
    out = {}
    for J, par, pos, energy, pct, comps in lsj_levels:
        for b in blocks:
            if b.J == J and (b.parity > 0) == (par == "+"):
                for lv in b.levels:
                    if lv.pos == pos and abs(lv.energy - energy) < tol * max(1.0, abs(energy)):
                        out[(b.nb, lv.pos)] = (pct, comps)
    return out


# ---------------------------------------------------------------------------
#  能级的组态和谱项 (用于导出)
# ---------------------------------------------------------------------------

L_LETTERS = "SPDFGHIKLMNOQRTUV"
LSJ_SEGMENT = re.compile(r"^(\d+[a-z])(?:\((\d+)\))?(?:\d[A-Z]\d?)?(?:_(\d+[A-Z]))?$")
JJ_SUBSHELL = re.compile(r"(\d+[a-z])-?\((\d+)\)")


def parse_lsj_label(label):
    """jj2lsj 的 LSJ 标记，如 2s(2).2p(6).3s_2S.3p_1P、1s(2).2s(2).2p(3)2D3_2D：
    返回 ([(nl, 占据数)], 总谱项如 "1P")；格式不认识时返回 (None, None)。
    各段之间以 "." 分隔：nl、(占据数)、子壳层谱项 (2S+1、L、辛弱数)、"_" 后为耦合到此的谱项。"""
    config, term = [], None
    for seg in label.split("."):
        m = LSJ_SEGMENT.match(seg)
        if not m:
            return None, None
        config.append((m.group(1), int(m.group(2) or 1)))
        term = m.group(3) or term
    return config, term


def nonrel_config(jj_orbitals):
    """jj 耦合的 CSF 组态 (如 "2s(2) 2p-(2) 2p(4) 3s(1)") 合并为非相对论组态 [(nl, 占据数)]，如 2p- 与 2p 相加。"""
    out = {}
    for nl, occ in JJ_SUBSHELL.findall(jj_orbitals):
        out[nl] = out.get(nl, 0) + int(occ)
    return [(nl, occ) for nl, occ in out.items() if occ > 0]


def csf_core(path):
    """CSF 文件中的核心轨道 (Core subshells，全部占满)，合并为非相对论组态 [(nl, 占据数)]：
    nl- (j = l - 1/2) 可容纳 2l 个电子，nl (j = l + 1/2) 可容纳 2l + 2 个。"""
    lines = []
    with open(path) as f:                    # 只读文件头 (CSF 列表可能很大)
        for ln in f:
            if ln.startswith("CSF(s):"):
                break
            lines.append(ln.rstrip())
    try:
        start = lines.index("Core subshells:") + 1
        end = next(i for i in range(start, len(lines)) if lines[i].endswith(":"))
    except (ValueError, StopIteration):
        return []
    out = {}
    for tok in " ".join(lines[start:end]).split():
        m = re.match(r"(\d+)([a-z])(-?)$", tok)
        if not m:
            continue
        l = "spdfghiklmnoqrtuv".index(m.group(2))
        nl = m.group(1) + m.group(2)
        out[nl] = out.get(nl, 0) + (2 * l if m.group(3) else 2 * l + 2)
    return list(out.items())


# 默认的组态缩写：惰性气体原子实
NOBLE_GAS_CORES = [
    ["[He]", "1s2"],
    ["[Ne]", "1s2.2s2.2p6"],
    ["[Ar]", "1s2.2s2.2p6.3s2.3p6"],
    ["[Kr]", "1s2.2s2.2p6.3s2.3p6.3d10.4s2.4p6"],
    ["[Xe]", "1s2.2s2.2p6.3s2.3p6.3d10.4s2.4p6.4d10.5s2.5p6"],
    ["[Rn]", "1s2.2s2.2p6.3s2.3p6.3d10.4s2.4p6.4d10.5s2.5p6.4f14.5d10.6s2.6p6"],
]


def parse_config(text):
    """组态文字 (如 1s2.2s2.2p6、1s2 2s2 2p6、1s(2)) -> [(nl, 占据数)]；看不懂时返回 None。"""
    out = []
    for tok in re.split(r"[\s.]+", text.strip()):
        if not tok:
            continue
        m = re.match(r"^(\d+[a-z])(?:\((\d+)\)|(\d*))$", tok)
        if not m:
            return None
        out.append((m.group(1), int(m.group(2) or m.group(3) or 1)))
    return out


def abbreviate(config, rules):
    """按规则 [[缩写, 完整组态], ...] 缩写组态：组态中含有规则的全部子壳层 (占据数相同) 时，
    把它们换成缩写写在最前面 (与子壳层的书写顺序无关)；缩写可以为空，表示省略。
    子壳层多的规则先用，用过的子壳层不再参与。返回 (缩写文字, 剩余组态)。"""
    rest = list(config)
    prefix = ""
    parsed = [(abbr, parse_config(full)) for abbr, full in rules]
    for abbr, need in sorted((r for r in parsed if r[1]), key=lambda r: -len(r[1])):
        if all(rest.count(x) >= need.count(x) for x in need):
            for x in need:
                rest.remove(x)
            prefix += abbr
    return prefix, rest


def config_ascii(config):
    """NIST 原子光谱数据库的写法：2s2.2p6.3s"""
    return ".".join(f"{nl}{occ if occ > 1 else ''}" for nl, occ in config)


def term_ascii(term, parity):
    """NIST 的写法：奇宇称的谱项加 *，如 3P*"""
    return f"{term}{'*' if parity < 0 else ''}" if term else ""


def natural_key(name):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


def is_mix_file(path):
    """文件头是否为 G92MIX (与文件名无关；scatterplot.m 等同扩展名的脚本不是)。"""
    return fortran_tag(path) == "G92MIX"


def is_biorthogonal(name):
    """rbiotransform 写出的 name.bm / name.cbm：双正交变换后的系数，不是 (归一化的) 物理态。
    这两个后缀由 rbiotransform 决定，与用户起的名字无关。"""
    return name.endswith(".bm") or name.endswith(".cbm")


def find_mix_files(directory):
    """目录中所有混合系数文件 (按文件头识别，不看扩展名)，不含双正交变换的 .bm / .cbm。"""
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    files = [n for n in names if not is_biorthogonal(n) and os.path.isfile(os.path.join(directory, n))
             and is_mix_file(os.path.join(directory, n))]
    return sorted(files, key=natural_key)
