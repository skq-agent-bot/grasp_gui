"""
能级与组成查看器：读取混合系数文件 (name.m / name.cm)，按 J^π 分列画出能级图；
鼠标停在能级上显示信息，点击后在右侧列出该原子态 (ASF) 的组成：
jj 耦合下的 CSF 混合系数 (配合 name.c)，以及 jj2lsj 给出的 LSJ 组成 (name.lsj.lbl)。
把一个能级连到另一个能级即可计算两者之间的跃迁 (自动运行 rbiotransform 和 rtransition，见 grasp_trans.py)。
"""

import math
import os
import queue
import struct
import threading

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen, QPolygonF, QTextCursor
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QPlainTextEdit,
                               QPushButton, QSplitter,
                               QStyledItemDelegate, QTableWidget, QTableWidgetItem, QTabWidget, QToolTip,
                               QVBoxLayout, QWidget)

import grasp_core as core
import grasp_mix as mix
import grasp_trans as tr
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
ARROW = QColor("#d35400")          # 选中的一对能级之间的跃迁
LINK = QColor("#6c3483")           # 选中能级的其他已算跃迁


class LevelDiagram(QWidget):
    """能级图：每个 (文件, J^π) 一列，横线为能级；滚轮缩放、拖动平移、双击复位，点击选中能级。
    从一个能级拖到另一个能级 (或按住 Shift 点击第二个能级) 选中一对能级，用于计算跃迁。"""
    levelClicked = Signal(object)
    pairSelected = Signal(object, object)

    MARGIN = (78, 12, 46, 30)      # 左、右、上 (列标题)、下

    def __init__(self):
        super().__init__()
        self.columns = []          # dict(file, title, levels=[dict(key, y, label, color, info)])
        self.unit = "cm⁻¹"
        self.yr = None
        self.hover = self.selected = None
        self.drag = None
        self.press = None          # (能级, 按下位置)：拖动超过几个像素即开始连线
        self.linking = None        # 连线时鼠标的位置
        self.pair = None           # (上能级, 下能级)：画一条箭头
        self.links = []            # [(能级, 能级, 强度 0..1)]：选中能级的已算跃迁
        self.centers = {}          # 能级 -> (x, y)，绘制时更新
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
        self.centers = {lv["key"]: (x0 + w / 2, self.to_py(lv["y"], rect, yr))
                        for (x0, w), col in zip(geo, self.columns) for lv in col["levels"]}
        p.save()
        p.setClipRect(rect)
        for k1, k2, strength in self.links:          # 选中能级的已算跃迁，越强越粗越深
            if k1 in self.centers and k2 in self.centers:
                c = QColor(LINK)
                c.setAlphaF(0.25 + 0.6 * strength)
                p.setPen(QPen(c, 0.8 + 2.4 * strength))
                p.drawLine(QPointF(*self.centers[k1]), QPointF(*self.centers[k2]))
        p.restore()
        for (x0, w), col in zip(geo, self.columns):
            p.save()
            p.setClipRect(rect)
            # 能级只画横线，组成等信息在鼠标悬停时显示
            lx0, lx1 = x0 + w * 0.15, x0 + w * 0.85
            for lv in col["levels"]:
                py = self.to_py(lv["y"], rect, yr)
                key = lv["key"]
                in_pair = self.pair and key in self.pair
                color = SELECTED if key == self.selected or in_pair else lv["color"]
                width = 3.2 if key in (self.selected, self.hover) or in_pair else 1.6
                p.setPen(QPen(color, width))
                p.drawLine(QPointF(lx0, py), QPointF(lx1, py))
            p.restore()
        p.save()
        p.setClipRect(rect)
        if self.pair and all(k in self.centers for k in self.pair):
            self.draw_arrow(p, QPointF(*self.centers[self.pair[0]]), QPointF(*self.centers[self.pair[1]]))
        if self.linking and self.press and self.press[0] in self.centers:
            p.setPen(QPen(SELECTED, 2, Qt.DashLine))
            p.drawLine(QPointF(*self.centers[self.press[0]]), self.linking)
        p.restore()

    @staticmethod
    def draw_arrow(p, a, b):
        """从上能级 a 指向下能级 b 的箭头。"""
        p.setPen(QPen(ARROW, 2.4))
        p.drawLine(a, b)
        d = b - a
        length = (d.x() ** 2 + d.y() ** 2) ** 0.5
        if length < 1:
            return
        ux, uy = d.x() / length, d.y() / length
        size = 11
        left = QPointF(b.x() - size * (ux * 0.87 - uy * 0.5), b.y() - size * (uy * 0.87 + ux * 0.5))
        right = QPointF(b.x() - size * (ux * 0.87 + uy * 0.5), b.y() - size * (uy * 0.87 - ux * 0.5))
        p.setBrush(ARROW)
        p.drawPolygon(QPolygonF([b, left, right]))
        p.setBrush(Qt.NoBrush)

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
        if self.press and not self.drag:
            if self.linking or (event.position() - self.press[1]).manhattanLength() > 6:
                self.linking = event.position()
                lv = self.level_at(event.position())
                self.hover = lv["key"] if lv else None
                self.update()
                return
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
            if event.modifiers() & Qt.ShiftModifier and self.selected and lv["key"] != self.selected:
                self.pairSelected.emit(self.selected, lv["key"])
            else:
                self.press = (lv["key"], event.position())
        else:
            self.drag = (event.position(), self.y_range())

    def mouseReleaseEvent(self, event):
        self.drag = None
        if self.press:
            key = self.press[0]
            if self.linking:
                lv = self.level_at(event.position())
                if lv and lv["key"] != key:
                    self.pairSelected.emit(key, lv["key"])
            else:
                self.levelClicked.emit(key)
        self.press = self.linking = None
        self.update()

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


def saved_settings():
    """单独打开查看器时的运行设置：主窗口保存的 GRASP bin 目录和 MPI 设置。"""
    cfg = core.load_config()
    return dict(bindir=core.default_bindir(), np=int(cfg.get("np", 1)), mpirun=cfg.get("mpirun", "mpirun"),
                mpitmp=cfg.get("mpitmp", "tmp_mpi"), nice=cfg.get("nice", True))


class LevelViewer(QMainWindow):
    MAX_ROWS = 500

    def __init__(self, workdir, settings=saved_settings):
        super().__init__()
        self.setWindowTitle(T("能级与组成查看器"))
        self.resize(1400, 880)
        self.settings = settings   # 返回运行设置 (bindir, np, mpirun, mpitmp, nice) 的函数
        self.cache = {}            # 路径 -> (mtime, 数据)
        self.levels = {}           # key -> (文件标签, 路径, Level)
        self.key_by_id = {}        # (绝对路径, 2J, 宇称, 序号) -> key
        self.current = None
        self.pair = None           # (上能级, 下能级)
        self.plan = None           # (Workspace, 要算的跃迁类型)
        self.tr_by_pair = {}       # frozenset(能级, 能级) -> [Transition]
        self.tr_by_level = {}      # 能级 -> [(另一能级, Transition, 本能级是否为上能级)]
        self.runner = core.Runner(lambda text, tag: self.q.put((text, tag)))
        self.q = queue.Queue()
        self.running = None        # (Workspace, 跃迁类型)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)

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
        hint = QLabel(T("鼠标停在能级上显示信息，点击查看组成；从一个能级拖到另一个能级计算跃迁 (或按住 Shift 点击)；"
                        "滚轮缩放，拖动空白处平移，双击复位。"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        dl.addWidget(hint)
        self.diagram = LevelDiagram()
        self.diagram.levelClicked.connect(self.select)
        self.diagram.pairSelected.connect(self.select_pair)
        dl.addWidget(self.diagram, 1)
        middle.addWidget(dw)
        self.level_table = table([T("文件"), "J^π", T("序号"), T("能量"), T("总能量 (a.u.)"), T("纯度"),
                                  T("主要组成")])
        self.level_table.setSortingEnabled(True)
        self.level_table.setSelectionMode(QTableWidget.SingleSelection)
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
        self.tr_tab = self.build_transition_tab()
        self.comp_tabs.addTab(self.tr_tab, T("跃迁"))
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
        self.key_by_id = {}
        self.workspaces = {}
        columns, rows = [], []
        for fname, path, blocks, csfs, csf_path, lsj, lsj_path in data:
            for b in blocks:
                col = dict(file=fname, title=self.jp(b), levels=[])
                for lv in b.levels:
                    key = (path, b.nb, lv.pos)
                    self.levels[key] = (fname, path, lv, csfs, lsj.get((b.nb, lv.pos)), csf_path, lsj_path)
                    self.key_by_id[(os.path.abspath(path), tr.two_j(b), b.parity, lv.pos)] = key
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
        if self.pair and not all(k in self.levels for k in self.pair):
            self.pair = None
        self.diagram.selected = self.current
        self.diagram.pair = self.pair
        self.load_transitions()
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
        self.diagram.links = self.links_of(key)
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
        self.show_transitions()

    # ---- 跃迁 ----
    def build_transition_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.tr_title = QLabel()
        self.tr_title.setWordWrap(True)
        self.tr_title.setTextFormat(Qt.RichText)
        lay.addWidget(self.tr_title)
        self.tr_plan = QLabel()
        self.tr_plan.setWordWrap(True)
        lay.addWidget(self.tr_plan)
        row = QHBoxLayout()
        self.tr_run = QPushButton(T("计算跃迁"))
        self.tr_run.clicked.connect(self.compute)
        self.tr_stop = QPushButton(T("停止"))
        self.tr_stop.clicked.connect(self.runner.stop)
        row.addWidget(self.tr_run)
        row.addWidget(self.tr_stop)
        row.addStretch()
        lay.addLayout(row)
        self.pair_table = table([T("类型"), T("规范"), "A (s⁻¹)", "gf", "S (a.u.)"])
        lay.addWidget(self.pair_table, 1)
        self.level_tr_label = QLabel()
        self.level_tr_label.setWordWrap(True)
        lay.addWidget(self.level_tr_label)
        self.level_tr_table = table([T("另一能级"), "", T("类型"), "λ (Å)", "A (s⁻¹)", "gf", T("分支比")])
        self.level_tr_table.cellClicked.connect(self.level_tr_clicked)
        lay.addWidget(self.level_tr_table, 2)
        self.tr_log = QPlainTextEdit()
        self.tr_log.setReadOnly(True)
        self.tr_log.setMaximumBlockCount(3000)
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono.setPointSizeF(self.font().pointSizeF())
        self.tr_log.setFont(mono)
        self.tr_log.setPlaceholderText(T("GRASP 程序的输出"))
        lay.addWidget(self.tr_log, 1)
        return w

    def level_name(self, key):
        fname, _, lv, *_ = self.levels[key]
        return f"{fname}  {self.jp(lv.block)}  #{lv.pos}"

    def select_pair(self, k1, k2):
        """连上两个能级：能量高者为上能级。"""
        e1, e2 = self.levels[k1][2].energy, self.levels[k2][2].energy
        self.pair = (k1, k2) if e1 >= e2 else (k2, k1)
        self.diagram.pair = self.pair
        self.comp_tabs.setCurrentWidget(self.tr_tab)
        self.select(self.pair[0])          # 组成页和已算跃迁列表显示上能级

    def workspace(self, path1, path2):
        k = tuple(sorted((os.path.abspath(path1), os.path.abspath(path2))))
        if k not in self.workspaces:
            self.workspaces[k] = tr.Workspace(self.dir.text(), *k)
        return self.workspaces[k]

    def load_transitions(self):
        """读取工作目录中已算好的跃迁，按能级建立索引。"""
        self.tr_by_pair, self.tr_by_level = {}, {}
        for roles, transitions in tr.computed(self.dir.text()):
            for t in transitions:
                ku = self.key_by_id.get((roles.get(t.upper[0]),) + t.upper[1:])
                kl = self.key_by_id.get((roles.get(t.lower[0]),) + t.lower[1:])
                if ku is None or kl is None:          # 文件没有勾选
                    continue
                self.tr_by_pair.setdefault(frozenset((ku, kl)), []).append(t)
                self.tr_by_level.setdefault(ku, []).append((kl, t, True))
                self.tr_by_level.setdefault(kl, []).append((ku, t, False))
        self.diagram.links = self.links_of(self.current)
        self.diagram.update()

    def links_of(self, key):
        """能级图上要画的已算跃迁：线的粗细按 A 的对数 (最强的为 1，弱 6 个量级以上的为 0)。"""
        items = self.tr_by_level.get(key, [])
        best = {}
        for other, t, _ in items:
            a = abs(t.main()[0])
            best[other] = max(best.get(other, 0.0), a)
        top = max(best.values(), default=0.0)
        if top <= 0:
            return []
        return [(key, other, min(max((math.log10(a) - math.log10(top) + 6) / 6, 0.0), 1.0) if a > 0 else 0.0)
                for other, a in best.items()]

    def show_transitions(self):
        self.show_pair()
        self.show_level_transitions()

    def show_pair(self):
        busy = self.running is not None
        self.tr_stop.setEnabled(busy)
        self.pair_table.setRowCount(0)
        self.plan = None
        if not self.pair:
            self.tr_title.setText(T("从一个能级拖到另一个能级 (或选中一个能级后按住 Shift 点击另一个)，计算两者之间的跃迁。"))
            self.tr_plan.setText("")
            self.tr_run.setEnabled(False)
            return
        up, low = self.pair
        lu, ll = self.levels[up][2], self.levels[low][2]
        unit_label, factor, efmt = self.unit_info()
        de = lu.energy - ll.energy
        lam = 1e8 / (de * mix.HARTREE_CM) if de > 0 else float("inf")
        self.tr_title.setText(f"<b>{self.level_name(up)}</b> → <b>{self.level_name(low)}</b><br>"
                              f"ΔE = {efmt.format(de * factor)} {unit_label} &nbsp; λ = {lam:.3f} Å")
        kinds = tr.multipoles(tr.two_j(lu.block), lu.parity, tr.two_j(ll.block), ll.parity)
        rows = sorted(self.tr_by_pair.get(frozenset(self.pair), []), key=lambda t: tr.KINDS.index(t.kind)
                      if t.kind in tr.KINDS else 99)
        self.fill_pair(rows)
        self.tr_run.setEnabled(False)
        if not kinds:
            self.tr_plan.setText(T("J = 0 → J = 0：单光子跃迁严格禁戒。"))
            return
        ws = self.workspace(self.levels[up][1], self.levels[low][1])
        done = ws.done_kinds()
        missing = [k for k in kinds if k not in done]
        if not missing:
            self.tr_plan.setText(T("已算出 {k}。结果保存在 {d}", k=", ".join(kinds), d=ws.dir))
            return
        problems = ws.problems()
        if problems:
            text = []
            for what, where in problems:
                if what == "isodata":
                    text.append(T("工作目录中没有 isodata：{d}", d=where))
                elif what == "w?":
                    text.append(T("无法确定与 {f} 对应的波函数文件，候选：{c}。请把对应的 .w 文件命名为与混合系数文件同名 "
                                  "(如 {s}.w)。", f=os.path.basename(where[0]),
                                  c=", ".join(os.path.basename(c) for c in where[1]),
                                  s=os.path.splitext(os.path.basename(where[0]))[0]))
                else:
                    text.append(T("找不到与 {f} 对应的 {what} 文件", f=os.path.basename(where),
                                  what=".c" if what == "CSF" else ".w"))
            self.tr_plan.setText("\n".join(text))
            return
        progs = "rtransition" if ws.manifest().get("bio") or ws.same else "rbiotransform → rtransition"
        note = T("两个能级来自同一个文件，轨道相同，不需要双正交变换。") if ws.same else \
            T("两个能级来自不同的计算，先用 rbiotransform 做双正交变换。")
        files = "; ".join(f"{os.path.basename(s.mix)}: {os.path.basename(s.csf)}, {os.path.basename(s.w)}"
                          for s in ws.sides.values())
        self.tr_plan.setText(T("需要计算 {k} ({p})。", k=", ".join(missing), p=progs) + " " + note + "\n" +
                             T("使用的文件：{f}", f=files) + "\n" +
                             T("rtransition 一次算出这两个文件中所有能级之间的 {k} 跃迁，之后点其他能级对可直接显示。",
                               k=", ".join(missing)))
        self.plan = (ws, missing)
        self.tr_run.setEnabled(not busy)

    def fill_pair(self, rows):
        t = self.pair_table
        out = []
        for x in rows:
            for g in ("B", "C", "M"):
                if g in x.values:
                    a, gf, s = x.values[g]
                    gauge = {"B": T("Babushkin (长度)"), "C": T("Coulomb (速度)"), "M": ""}[g]
                    out.append((x.kind, gauge, a, gf, s))
        t.setRowCount(len(out))
        for r, (kind, gauge, a, gf, s) in enumerate(out):
            for c, it in enumerate([item(kind), item(gauge), NumItem(f"{a:.5e}", a), NumItem(f"{gf:.5e}", gf),
                                    NumItem(f"{s:.5e}", s)]):
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        ratios = [f"{x.kind}: A_C / A_B = {x.gauge_ratio():.4f}" for x in rows if x.gauge_ratio() is not None]
        if ratios:
            t.setToolTip(T("两种规范之比接近 1 说明计算较可靠。") + "\n" + "\n".join(ratios))

    def show_level_transitions(self):
        t = self.level_tr_table
        t.setRowCount(0)
        key = self.current
        items = self.tr_by_level.get(key, []) if key else []
        if not key:
            self.level_tr_label.setText("")
            return
        if not items:
            self.level_tr_label.setText(T("能级 {l} 还没有算出的跃迁。", l=self.level_name(key)))
            return
        decay = sum(abs(x.main()[0]) for _, x, is_up in items if is_up)
        rows = sorted(items, key=lambda i: -abs(i[1].main()[0]))
        t.setSortingEnabled(False)
        t.setRowCount(len(rows))
        for r, (other, x, is_up) in enumerate(rows):
            a, gf, _ = x.main()
            br = abs(a) / decay if is_up and decay else None
            first = item(self.level_name(other))
            first.setData(Qt.UserRole, other)
            vals = [first, item("↓" if is_up else "↑"), item(x.kind), NumItem(f"{x.wavelength:.3f}", x.wavelength),
                    NumItem(f"{a:.4e}", a), NumItem(f"{gf:.4e}", gf),
                    NumItem(f"{100 * br:.2f} %" if br is not None else "", br or 0.0)]
            for c, it in enumerate(vals):
                t.setItem(r, c, it)
        t.setSortingEnabled(True)
        t.resizeColumnsToContents()
        msg = T("能级 {l} 的已算跃迁 ({n} 条；↓ 衰变到更低能级，↑ 从更低能级激发)。", l=self.level_name(key), n=len(rows))
        if decay:
            msg += " " + T("已算衰变的总速率 {a:.4e} s⁻¹，对应寿命 {tau:.4e} s (只计入已算的跃迁)。", a=decay, tau=1 / decay)
        self.level_tr_label.setText(msg)

    def level_tr_clicked(self, row, _col):
        other = self.level_tr_table.item(row, 0).data(Qt.UserRole)
        if self.current and other in self.levels:
            self.select_pair(self.current, other)

    def compute(self):
        if not self.plan or self.running:
            return
        ws, kinds = self.plan
        cfg = dict(self.settings())
        try:
            ws.prepare()
        except OSError as e:
            self.tr_log.appendPlainText(T("\n*** 错误: {e}\n", e=e))
            return
        cfg["cwd"] = ws.dir
        self.tr_log.clear()
        if cfg["np"] > 1 and not ws.mpi_ok(cfg["mpitmp"]):
            cfg["np"] = 1
            self.tr_log.appendPlainText(T("计算目录的路径超过 {n} 个字符，GRASP 的 MPI 版本无法处理，改用串行版本。",
                                          n=tr.MPI_PATH_MAX))
        jobs = ws.jobs(kinds, {s.key: s for s in core.STEPS})
        self.running = (ws, kinds)
        self.statusBar().showMessage(T("正在计算 {k} 跃迁 …", k=", ".join(kinds)))
        self.show_pair()
        threading.Thread(target=self.runner.run_all, daemon=True,
                         args=(jobs, cfg, lambda ok: self.q.put((ok, "done")))).start()

    def poll(self):
        text = []
        try:
            while True:
                s, tag = self.q.get_nowait()
                if tag == "done":
                    if text:
                        self.tr_log.insertPlainText("".join(text))
                        text = []
                    self.finished(s)
                else:
                    text.append(s)
        except queue.Empty:
            pass
        if text:
            self.tr_log.moveCursor(QTextCursor.End)
            self.tr_log.insertPlainText("".join(text))
            self.tr_log.ensureCursorVisible()

    def finished(self, ok):
        ws, kinds = self.running
        self.running = None
        if ok:
            try:
                ws.finish(kinds)
            except (OSError, RuntimeError) as e:
                ok = False
                self.tr_log.appendPlainText(T("\n*** 错误: {e}\n", e=e))
        self.statusBar().showMessage(T("跃迁计算完成") if ok else T("跃迁计算失败，见下方的程序输出"))
        self.load_transitions()
        self.show_transitions()

    def closeEvent(self, event):
        if self.running:
            self.runner.kill()
        super().closeEvent(event)
