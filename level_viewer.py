"""
能级与组成查看器：读取混合系数文件 (name.m / name.cm)，按 J^π 分列画出能级图；
鼠标停在能级上显示信息，点击后在右侧列出该原子态 (ASF) 的组成：
jj 耦合下的 CSF 混合系数 (配合 name.c)，以及 jj2lsj 给出的 LSJ 组成 (name.lsj.lbl)。
"""

import os
import struct

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QPushButton, QSplitter,
                               QStyledItemDelegate, QTableWidget, QTableWidgetItem, QTabWidget, QToolTip,
                               QVBoxLayout, QWidget)

import grasp_core as core
import grasp_mix as mix
from grasp_core import T
from wfn_viewer import fmt, nice_ticks

# (下拉框中的名称 (用时再翻译), 表头和坐标轴中的简写, 1 a.u. 折合多少, 显示格式)；第一个为默认单位
UNITS = [("eV", "eV", mix.HARTREE_EV, "{:.5f}"), ("cm⁻¹", "cm⁻¹", mix.HARTREE_CM, "{:.2f}"),
         ("原子单位 (Hartree)", "a.u.", 1.0, "{:.8f}")]


class NumItem(QTableWidgetItem):
    """显示格式化的文字，按数值排序。"""

    def __init__(self, text, value):
        super().__init__(text)
        self.value = value
        self.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def __lt__(self, other):
        return self.value < getattr(other, "value", 0)
PARITY_COLORS = {1: QColor("#1f5fbf"), -1: QColor("#c0392b")}     # 偶宇称蓝色，奇宇称红色
SELECTED = QColor("#f39c12")


class LevelDiagram(QWidget):
    """能级图：每个 (文件, J^π) 一列，横线为能级；滚轮缩放、拖动平移、双击复位，点击选中能级。"""
    levelClicked = Signal(object)

    MARGIN = (78, 12, 46, 30)      # 左、右、上 (列标题)、下

    def __init__(self):
        super().__init__()
        self.columns = []          # dict(file, title, levels=[dict(key, y, label, color, info)])
        self.unit = "cm⁻¹"
        self.yr = None
        self.hover = self.selected = None
        self.drag = None
        self.setMouseTracking(True)
        self.setMinimumHeight(240)

    def set_columns(self, columns, unit):
        self.columns, self.unit = columns, unit
        self.yr = None
        self.hover = None
        self.update()

    def auto_y(self):
        ys = [lv["y"] for c in self.columns for lv in c["levels"]]
        if not ys:
            return (0.0, 1.0)
        lo, hi = min(ys), max(ys)
        pad = (hi - lo) * 0.06 or 1.0
        return (lo - pad, hi + pad)

    def y_range(self):
        return self.yr or self.auto_y()

    def plot_rect(self):
        l, r, t, b = self.MARGIN
        return QRectF(l, t, max(self.width() - l - r, 10), max(self.height() - t - b, 10))

    def to_py(self, y, rect, yr):
        return rect.bottom() - (y - yr[0]) / (yr[1] - yr[0]) * rect.height()

    def geometry_of(self, rect):
        """各列的 (左边界 x, 宽度)：所有列等宽。"""
        n = max(len(self.columns), 1)
        w = rect.width() / n
        return [(rect.left() + i * w, w) for i in range(n)]

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        rect = self.plot_rect()
        yr = self.y_range()
        fm = p.fontMetrics()

        big = yr[1] - yr[0] >= 100          # 如 cm⁻¹：刻度写成整数，不用科学计数法
        for y in nice_ticks(*yr, n=6):
            py = self.to_py(y, rect, yr)
            p.setPen(QPen(QColor("#ececec")))
            p.drawLine(QPointF(rect.left(), py), QPointF(rect.right(), py))
            p.setPen(QColor("#333"))
            label = f"{y:.0f}" if big else fmt(y)
            p.drawText(QPointF(rect.left() - fm.horizontalAdvance(label) - 6, py + fm.ascent() / 2 - 1), label)
        p.save()
        p.translate(14, rect.center().y())
        p.rotate(-90)
        text = T("相对能量 ({u})", u=self.unit)
        p.drawText(QPointF(-fm.horizontalAdvance(text) / 2, 0), text)
        p.restore()
        p.setPen(QColor("#999"))
        p.drawRect(rect)

        geo = self.geometry_of(rect)
        self.draw_headers(p, rect, geo)
        for (x0, w), col in zip(geo, self.columns):
            p.save()
            p.setClipRect(rect)
            # 能级只画横线，组成等信息在鼠标悬停时显示
            lx0, lx1 = x0 + w * 0.15, x0 + w * 0.85
            for lv in col["levels"]:
                py = self.to_py(lv["y"], rect, yr)
                key = lv["key"]
                color = SELECTED if key == self.selected else lv["color"]
                width = 3.2 if key in (self.selected, self.hover) else 1.6
                p.setPen(QPen(color, width))
                p.drawLine(QPointF(lx0, py), QPointF(lx1, py))
            p.restore()

    def draw_headers(self, p, rect, geo):
        """列标题：每个文件的名称居中写在它的几列上方 (放不下时截短)，各列下方写 J^π
        (放不下时用小号字，仍放不下则省略，悬停提示中仍有)。文件之间用实线分隔，同一文件的列之间用虚线。"""
        fm = p.fontMetrics()
        groups = []                # [文件名, 左边界, 右边界]
        for (x0, w), col in zip(geo, self.columns):
            if groups and groups[-1][0] == col["file"]:
                groups[-1][2] = x0 + w
                if x0 > rect.left():
                    p.setPen(QPen(QColor("#ddd"), 1, Qt.DashLine))
                    p.drawLine(QPointF(x0, rect.top()), QPointF(x0, rect.bottom()))
            else:
                groups.append([col["file"], x0, x0 + w])
                if x0 > rect.left():
                    p.setPen(QPen(QColor("#999"), 1))
                    p.drawLine(QPointF(x0, rect.top() - fm.height() - 22), QPointF(x0, rect.bottom()))
        bold = QFont(self.font())
        bold.setBold(True)
        p.setFont(bold)
        bfm = p.fontMetrics()
        p.setPen(QColor("#333"))
        for name, a, b in groups:
            text = bfm.elidedText(name, Qt.ElideMiddle, int(b - a - 6))
            p.drawText(QPointF((a + b) / 2 - bfm.horizontalAdvance(text) / 2, rect.top() - fm.height() - 8), text)
        small = QFont(self.font())
        small.setPointSizeF(self.font().pointSizeF() * 0.78)
        for (x0, w), col in zip(geo, self.columns):
            for font in (self.font(), small):
                p.setFont(font)
                tw = p.fontMetrics().horizontalAdvance(col["title"])
                if tw <= w - 3:
                    p.drawText(QPointF(x0 + w / 2 - tw / 2, rect.top() - 6), col["title"])
                    break
        p.setFont(self.font())

    def level_at(self, pos):
        rect = self.plot_rect()
        yr = self.y_range()
        for (x0, w), col in zip(self.geometry_of(rect), self.columns):
            if x0 <= pos.x() < x0 + w:
                best = None
                for lv in col["levels"]:
                    d = abs(self.to_py(lv["y"], rect, yr) - pos.y())
                    if d < 7 and (best is None or d < best[0]):
                        best = (d, lv)
                return best[1] if best else None
        return None

    def mouseMoveEvent(self, event):
        if self.drag:
            start, yr = self.drag
            rect = self.plot_rect()
            dy = (event.position().y() - start.y()) / rect.height() * (yr[1] - yr[0])
            self.yr = (yr[0] + dy, yr[1] + dy)
            self.update()
            return
        lv = self.level_at(event.position())
        key = lv["key"] if lv else None
        if key != self.hover:
            self.hover = key
            self.update()
        if lv:
            QToolTip.showText(event.globalPosition().toPoint(), lv["info"], self)
            self.setCursor(Qt.PointingHandCursor)
        else:
            QToolTip.hideText()
            self.unsetCursor()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        lv = self.level_at(event.position())
        if lv:
            self.levelClicked.emit(lv["key"])
        else:
            self.drag = (event.position(), self.y_range())

    def mouseReleaseEvent(self, _event):
        self.drag = None

    def mouseDoubleClickEvent(self, _event):
        self.yr = None
        self.update()

    def wheelEvent(self, event):
        rect = self.plot_rect()
        yr = self.y_range()
        y = yr[0] + (rect.bottom() - event.position().y()) / rect.height() * (yr[1] - yr[0])
        f = 0.8 if event.angleDelta().y() > 0 else 1.25
        self.yr = (y + (yr[0] - y) * f, y + (yr[1] - y) * f)
        self.update()

    def leaveEvent(self, _event):
        self.hover = None
        self.update()


class WeightBar(QStyledItemDelegate):
    """权重列：在文字后面画一条与权重成比例的浅色条。"""

    def paint(self, painter, option, index):
        w = index.data(Qt.UserRole) or 0.0
        r = option.rect.adjusted(2, 3, -2, -3)
        painter.fillRect(QRectF(r.left(), r.top(), r.width() * min(max(w, 0.0), 1.0), r.height()),
                         QColor("#cfe3f7"))
        super().paint(painter, option, index)


def table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setWordWrap(False)       # 长标签不折行，过宽时横向滚动
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)     # 列宽在填完后用 resizeColumnsToContents 调整一次
    return t


def item(value, color=None, align=None):
    it = QTableWidgetItem()
    it.setData(Qt.DisplayRole, value)
    if color is not None:
        it.setForeground(color)
    if align is not None:
        it.setTextAlignment(align)
    return it


class LevelViewer(QMainWindow):
    MAX_ROWS = 500

    def __init__(self, workdir):
        super().__init__()
        self.setWindowTitle(T("能级与组成查看器"))
        self.resize(1400, 880)
        self.cache = {}            # 路径 -> (mtime, 数据)
        self.levels = {}           # key -> (文件标签, 路径, Level)
        self.current = None

        central = QWidget()
        lay = QVBoxLayout(central)
        top = QHBoxLayout()
        top.addWidget(QLabel(T("目录")))
        self.dir = QLineEdit(workdir)
        self.dir.editingFinished.connect(self.scan)
        top.addWidget(self.dir, 1)
        for text, slot in [("浏览…", self.pick_dir), ("刷新", self.scan)]:
            b = QPushButton(T(text))
            b.clicked.connect(slot)
            top.addWidget(b)
        top.addSpacing(12)
        top.addWidget(QLabel(T("能量单位")))
        self.unit = QComboBox()
        for label, _, _, _ in UNITS:
            self.unit.addItem(T(label))
        self.unit.setCurrentIndex(min(max(core.load_config().get("level_unit", 0), 0), len(UNITS) - 1))
        self.unit.currentIndexChanged.connect(self.unit_changed)
        top.addWidget(self.unit)
        lay.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel(T("混合系数文件")))
        self.files = QListWidget()
        self.files.itemChanged.connect(self.redraw)
        ll.addWidget(self.files)
        note = QLabel(T("文件按内容识别，与文件名无关：组态取自 CSF 数和 J^π 都对应的 CSF 文件，LSJ 组成取自能量对应的 jj2lsj 结果。"))
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        ll.addWidget(note)
        split.addWidget(left)

        middle = QSplitter(Qt.Vertical)
        dw = QWidget()
        dl = QVBoxLayout(dw)
        dl.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(T("鼠标停在能级上显示信息，点击查看组成；滚轮缩放，拖动平移，双击复位。"))
        hint.setStyleSheet("color: gray;")
        dl.addWidget(hint)
        self.diagram = LevelDiagram()
        self.diagram.levelClicked.connect(self.select)
        dl.addWidget(self.diagram, 1)
        middle.addWidget(dw)
        self.level_table = table([T("文件"), "J^π", T("序号"), T("能量"), T("总能量 (a.u.)"), T("纯度"),
                                  T("主要组成")])
        self.level_table.setSortingEnabled(True)
        self.level_table.cellClicked.connect(lambda row, _c: self.select(self.level_table.item(row, 0).data(Qt.UserRole)))
        middle.addWidget(self.level_table)
        middle.setSizes([560, 260])
        split.addWidget(middle)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel(T("点击能级查看组成"))
        self.title.setWordWrap(True)
        self.title.setTextFormat(Qt.RichText)
        rl.addWidget(self.title)
        fl = QHBoxLayout()
        fl.addWidget(QLabel(T("只显示权重 ≥")))
        self.min_w = QDoubleSpinBox()
        self.min_w.setDecimals(3)
        self.min_w.setRange(0.0, 100.0)
        self.min_w.setValue(0.1)
        self.min_w.setSuffix(" %")
        self.min_w.valueChanged.connect(self.show_composition)
        fl.addWidget(self.min_w)
        fl.addStretch()
        rl.addLayout(fl)
        self.comp_tabs = QTabWidget()
        self.jj_table = table(["#", "CSF", T("系数"), T("权重"), T("组态"), T("耦合 (中间 J、总 J^π)")])
        self.jj_table.setItemDelegateForColumn(3, WeightBar(self.jj_table))
        self.lsj_table = table([T("系数"), T("权重"), T("LSJ 标记")])
        self.lsj_table.setItemDelegateForColumn(1, WeightBar(self.lsj_table))
        self.comp_tabs.addTab(self.jj_table, T("jj 耦合 CSF"))
        self.comp_tabs.addTab(self.lsj_table, T("LSJ 组成"))
        rl.addWidget(self.comp_tabs, 1)
        self.summary = QLabel()
        self.summary.setStyleSheet("color: gray;")
        rl.addWidget(self.summary)
        split.addWidget(right)
        split.setSizes([220, 660, 520])
        lay.addWidget(split, 1)
        self.setCentralWidget(central)
        self.scan()

    # ---- 文件 ----
    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "", self.dir.text())
        if d:
            self.dir.setText(d)
            self.scan()

    def set_dir(self, d):
        if os.path.abspath(d) != os.path.abspath(self.dir.text()):
            self.dir.setText(d)
            self.scan()

    def scan(self):
        """列出混合系数文件；默认勾选 CI 结果 (.cm)，没有时勾选最新的 .m (保留已勾选的)。"""
        d = self.dir.text()
        checked = {self.files.item(i).data(Qt.UserRole) for i in range(self.files.count())
                   if self.files.item(i).checkState() == Qt.Checked}
        paths = [os.path.join(d, n) for n in mix.find_mix_files(d)]
        if not checked & set(paths) and paths:
            cm = [p for p in paths if p.endswith(".cm")]
            checked = set(cm) if cm else {max(paths, key=os.path.getmtime)}
        self.files.blockSignals(True)
        self.files.clear()
        for path in paths:
            it = QListWidgetItem(os.path.basename(path))
            it.setData(Qt.UserRole, path)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if path in checked else Qt.Unchecked)
            self.files.addItem(it)
        self.files.blockSignals(False)
        self.redraw()
        self.statusBar().showMessage(T("{n} 个混合系数文件", n=len(paths)) if paths
                                     else T("此目录中没有混合系数文件"))

    def cached(self, path, reader):
        try:
            mtime = os.path.getmtime(path)
        except OSError as e:
            return e
        hit = self.cache.get((path, reader))
        if hit and hit[0] == mtime:
            return hit[1]
        try:
            data = reader(path)
        except (OSError, ValueError, StopIteration, struct.error) as e:
            data = e
        self.cache[(path, reader)] = (mtime, data)
        return data

    def load(self, path):
        """(blocks, csfs, CSF 文件, {(nb, pos): LSJ}, LSJ 文件)；没有对应文件时为 None / {}。
        CSF 列表和 LSJ 结果按内容配对，不依赖文件名。读不了混合系数文件时返回异常。"""
        blocks = self.cached(path, mix.read_mix)
        if isinstance(blocks, Exception):
            return blocks
        csf_path = mix.find_csf_for(path)
        csfs = self.cached(csf_path, mix.read_csfs) if csf_path else None
        if isinstance(csfs, Exception):
            csfs, csf_path = None, None
        lsj_path, lsj = mix.find_lsj_for(path, blocks)
        return blocks, csfs, csf_path, lsj, lsj_path

    # ---- 能级图与能级列表 ----
    def unit_info(self):
        """(简写, 换算因子, 显示格式)"""
        _, short, factor, efmt = UNITS[self.unit.currentIndex()]
        return short, factor, efmt

    def unit_changed(self):
        core.save_config(level_unit=self.unit.currentIndex())    # 下次打开沿用
        self.redraw()

    def redraw(self, *_):
        unit_label, factor, efmt = self.unit_info()
        data = []
        for i in range(self.files.count()):
            it = self.files.item(i)
            if it.checkState() != Qt.Checked:
                continue
            path = it.data(Qt.UserRole)
            res = self.load(path)
            if isinstance(res, Exception):
                it.setForeground(QColor("#c00"))
                it.setToolTip(T("无法读取：{e}", e=res))
                continue
            it.setForeground(QColor("black"))
            it.setToolTip(path)
            data.append((os.path.basename(path), path, *res))
        energies = [lv.energy for _, _, blocks, *_ in data for b in blocks for lv in b.levels]
        e0 = min(energies) if energies else 0.0

        self.levels = {}
        columns, rows = [], []
        for fname, path, blocks, csfs, csf_path, lsj, lsj_path in data:
            for b in blocks:
                col = dict(file=fname, title=self.jp(b), levels=[])
                for lv in b.levels:
                    key = (path, b.nb, lv.pos)
                    self.levels[key] = (fname, path, lv, csfs, lsj.get((b.nb, lv.pos)), csf_path, lsj_path)
                    label, purity = self.leading(lv, csfs, lsj.get((b.nb, lv.pos)))
                    rel = (lv.energy - e0) * factor
                    info = (f"{fname}   J^π = {self.jp(b)}   #{lv.pos}\n"
                            f"{T('能量')}: {efmt.format(rel)} {unit_label}   ({lv.energy:.9f} a.u.)\n"
                            f"{T('主要组成')}: {label}  ({purity:.1f} %)")
                    col["levels"].append(dict(key=key, y=rel, label=label, color=PARITY_COLORS[b.parity], info=info))
                    rows.append((fname, self.jp(b), lv.pos, rel, lv.energy, purity, label, key))
                if col["levels"]:
                    columns.append(col)
        self.diagram.set_columns(columns, unit_label)
        self.fill_levels(rows, unit_label, efmt)
        if self.current not in self.levels:
            self.current = None
        self.diagram.selected = self.current
        self.show_composition()

    @staticmethod
    def jp(block):
        return f"{block.J}{'⁺' if block.parity > 0 else '⁻'}"

    @staticmethod
    def leading(lv, csfs, lsj):
        """主要组成的标签和权重 (%)：有 LSJ 组成时用 LSJ 标记，否则用权重最大的 CSF。"""
        if lsj and lsj[1]:
            c, w, label = max(lsj[1], key=lambda t: t[1])
            return label, 100 * w
        i = lv.leading()
        c = lv.coeffs[i - 1]
        label = csfs[lv.block.nb - 1][i - 1][0] if csfs else f"CSF {i}"
        return label, 100 * c * c

    def fill_levels(self, rows, unit_label, efmt):
        t = self.level_table
        t.setSortingEnabled(False)
        t.setHorizontalHeaderItem(3, QTableWidgetItem(T("能量 ({u})", u=unit_label)))
        t.setRowCount(len(rows))
        for r, (fname, jp, pos, rel, e, purity, label, key) in enumerate(sorted(rows, key=lambda x: x[3])):
            first = item(fname)
            first.setData(Qt.UserRole, key)
            vals = [first, item(jp), item(pos), NumItem(efmt.format(rel), rel), NumItem(f"{e:.9f}", e),
                    NumItem(f"{purity:.1f}", purity), item(label)]
            for c, it in enumerate(vals):
                t.setItem(r, c, it)
        t.setSortingEnabled(True)
        t.resizeColumnsToContents()

    # ---- 组成 ----
    def select(self, key):
        self.current = key
        self.diagram.selected = key
        self.diagram.update()
        for r in range(self.level_table.rowCount()):
            if self.level_table.item(r, 0).data(Qt.UserRole) == key:
                self.level_table.selectRow(r)
                break
        self.show_composition()

    def show_composition(self, *_):
        for t in (self.jj_table, self.lsj_table):
            t.setRowCount(0)
        if self.current is None:
            self.title.setText(T("点击能级查看组成"))
            self.summary.setText("")
            return
        fname, path, lv, csfs, lsj, csf_path, lsj_path = self.levels[self.current]
        unit_label, factor, efmt = self.unit_info()
        e0 = min(v[2].energy for v in self.levels.values())
        self.title.setText(f"<b>{fname}</b> &nbsp; J<sup>π</sup> = {self.jp(lv.block)} &nbsp; #{lv.pos} &nbsp; "
                           f"{efmt.format((lv.energy - e0) * factor)} {unit_label} &nbsp; ({lv.energy:.9f} a.u.)")
        wmin = self.min_w.value() / 100
        comps = lv.components(wmin)
        shown = comps[:self.MAX_ROWS]
        t = self.jj_table
        t.setRowCount(len(shown))
        names = csfs[lv.block.nb - 1] if csfs else None
        for r, (i, c) in enumerate(shown):
            w = item(f"{100 * c * c:.3f} %", align=Qt.AlignRight | Qt.AlignVCenter)
            w.setData(Qt.UserRole, c * c)
            orb, coup = names[i - 1] if names else ("", "")
            for col, it in enumerate([item(r + 1), item(i), NumItem(f"{c:+.6f}", c), w, item(orb), item(coup)]):
                t.setItem(r, col, it)
        t.resizeColumnsToContents()
        total = sum(c * c for _, c in shown)
        msg = T("显示 {n} / {m} 个 CSF，权重之和 {w:.3f} %", n=len(shown), m=len(lv.coeffs), w=100 * total)
        if names:
            msg += "  " + T("组态取自 {f}", f=os.path.basename(csf_path))
        else:
            msg += "  " + T("(找不到对应的 CSF 文件，只显示 CSF 序号)")
        self.summary.setText(msg)

        lt = self.lsj_table
        comps = [x for x in (lsj[1] if lsj else []) if x[1] >= wmin]
        lt.setRowCount(len(comps))
        for r, (c, wgt, label) in enumerate(comps):
            w = item(f"{100 * wgt:.3f} %", align=Qt.AlignRight | Qt.AlignVCenter)
            w.setData(Qt.UserRole, wgt)
            for col, it in enumerate([NumItem(f"{c:+.6f}", c), w, item(label)]):
                lt.setItem(r, col, it)
        lt.resizeColumnsToContents()
        self.comp_tabs.setTabEnabled(1, bool(lsj))
        self.comp_tabs.setTabToolTip(1, T("LSJ 组成取自 {f}", f=os.path.basename(lsj_path)) if lsj
                                     else T("没有对应的 jj2lsj 结果 (.lsj.lbl)"))
