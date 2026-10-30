#!/usr/bin/env python3
"""
GRASP 图形界面 (Qt / PySide6)：填写参数 -> 自动生成交互输入 (stdin) -> 在工作目录中运行 GRASP 程序。

每个标签页对应一个 GRASP 程序 (字段与生成规则见 grasp_core.py)。多个步骤可以加入"流程"后
顺序运行 (可选 MPI)，或导出为 shell 脚本 / Slurm 作业脚本。界面支持中文 / English。

用法:  python3 gui/grasp_gui.py [--lang en]
依赖:  pip install pyside6
"""

import json
import os
import queue
import sys
import threading


def fix_wsl_display():
    """WSL 启用 systemd 后 $XDG_RUNTIME_DIR 中常缺少 WSLg 的 wayland 套接字；直接指向它并优先用 Wayland。"""
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    wl = os.environ.get("WAYLAND_DISPLAY")
    if not wl:
        return
    path = wl if os.path.isabs(wl) else os.path.join(os.environ.get("XDG_RUNTIME_DIR", ""), wl)
    wslg = os.path.join("/mnt/wslg/runtime-dir", os.path.basename(wl))
    if not os.path.exists(path) and os.path.exists(wslg):
        os.environ["WAYLAND_DISPLAY"] = path = wslg
    if os.path.exists(path):
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"


fix_wsl_display()

from PySide6.QtCore import Qt, QTimer                               # noqa: E402
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont,    # noqa: E402
                           QFontDatabase, QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox,  # noqa: E402
                               QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QMainWindow, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QSplitter, QTabWidget, QVBoxLayout, QWidget)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grasp_core as core                                           # noqa: E402
from grasp_core import T                                            # noqa: E402

CJK_FONTS = ["Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei", "WenQuanYi Micro Hei",
             "Droid Sans Fallback", "AR PL UMing CN"]


def fixed_font():
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)


def hint_label(text):
    w = QLabel(T(text) if text else "")
    w.setStyleSheet("color: gray;")
    return w


def text_edit(text="", lines=4):
    w = QPlainTextEdit(text)
    w.setFont(fixed_font())
    w.setTabChangesFocus(True)
    w.setFixedHeight(int(w.fontMetrics().lineSpacing() * lines + 14))
    return w


def button(text, slot):
    b = QPushButton(T(text))
    b.clicked.connect(slot)
    return b


# ---------------------------------------------------------------------------
#  表单
# ---------------------------------------------------------------------------

class CsfListsWidget(QWidget):
    """rcsfgenerate 的多个 CSF 列表，每个列表一个标签页。"""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(T("CSF 列表:")))
        bar.addWidget(button("+ 添加列表", lambda: self.add_list(dict(core.CsfLists.EMPTY))))
        bar.addWidget(button("− 删除当前列表", self.del_list))
        bar.addStretch()
        lay.addLayout(bar)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self.lists = []

    def add_list(self, d):
        page = QWidget()
        g = QGridLayout(page)
        lst = {"configs": text_edit(d["configs"], 4)}
        g.addWidget(QLabel(T("参考组态 (每行一个)")), 0, 0, Qt.AlignTop)
        g.addWidget(lst["configs"], 0, 1, 1, 2)
        for r, (key, label, hint) in enumerate(core.CsfLists.LIST_FIELDS, start=1):
            lst[key] = QLineEdit(d[key])
            g.addWidget(QLabel(T(label)), r, 0)
            g.addWidget(lst[key], r, 1)
            g.addWidget(hint_label(hint), r, 2)
        g.setColumnStretch(1, 1)
        self.lists.append(lst)
        self.tabs.addTab(page, T("列表 {n}", n=len(self.lists)))
        self.tabs.setCurrentWidget(page)

    def del_list(self):
        if len(self.lists) <= 1:
            return
        i = self.tabs.currentIndex()
        self.tabs.removeTab(i)
        self.lists.pop(i)
        for k in range(len(self.lists)):
            self.tabs.setTabText(k, T("列表 {n}", n=k + 1))

    def value(self):
        return [dict(configs=l["configs"].toPlainText(),
                     **{k: l[k].text() for k, _, _ in core.CsfLists.LIST_FIELDS}) for l in self.lists]

    def set_value(self, lists):
        self.tabs.clear()
        self.lists = []
        for d in lists:
            self.add_list(d)
        self.tabs.setCurrentIndex(0)


class StepForm(QScrollArea):
    """根据 step.fields 生成的参数表单。"""

    def __init__(self, step, bindir):
        super().__init__()
        self.step = step
        self.setWidgetResizable(True)
        inner = QWidget()
        g = QGridLayout(inner)
        g.setColumnStretch(1, 1)
        self.get, self.put = {}, {}
        r = 0
        for f in step.fields:
            if isinstance(f, core.Note):
                w = QLabel(T(f.text))
                w.setWordWrap(True)
                w.setStyleSheet("color: #555; padding-bottom: 4px;")
                g.addWidget(w, r, 0, 1, 3)
            elif isinstance(f, core.Check):
                w = QCheckBox(T(f.label))
                g.addWidget(w, r, 0, 1, 2)
                g.addWidget(hint_label(f.hint), r, 2)
                self.get[f.key], self.put[f.key] = w.isChecked, w.setChecked
            elif isinstance(f, core.CsfLists):
                w = CsfListsWidget()
                g.addWidget(w, r, 0, 1, 3)
                self.get[f.key], self.put[f.key] = w.value, w.set_value
            else:
                if isinstance(f, core.Entry):
                    w = QLineEdit()
                    self.get[f.key], self.put[f.key] = w.text, w.setText
                elif isinstance(f, core.Text):
                    w = text_edit("", f.lines)
                    self.get[f.key], self.put[f.key] = w.toPlainText, w.setPlainText
                elif isinstance(f, core.Choice):
                    w = QComboBox()
                    for code, desc in f.options:
                        w.addItem(f"{code}   {T(desc)}", code)
                    self.get[f.key] = w.currentData
                    self.put[f.key] = lambda v, w=w: w.setCurrentIndex(max(w.findData(v), 0))
                elif isinstance(f, core.Program):
                    w = QComboBox()
                    w.setEditable(True)
                    if os.path.isdir(bindir):
                        w.addItems(sorted(os.listdir(bindir)))
                    self.get[f.key], self.put[f.key] = w.currentText, w.setCurrentText
                label = QLabel(T(f.label))
                g.addWidget(label, r, 0, Qt.AlignTop if isinstance(f, core.Text) else Qt.AlignVCenter)
                g.addWidget(w, r, 1)
                g.addWidget(hint_label(f.hint), r, 2)
            r += 1
        g.setRowStretch(r, 1)
        self.setWidget(inner)
        self.set_values(step.defaults())

    def values(self):
        return {k: get() for k, get in self.get.items()}

    def set_values(self, d):
        fields = {f.key: f for f in self.step.fields if isinstance(f, core.Field)}
        for k, val in d.items():
            if k in self.put:
                self.put[k](core.normalize(fields[k], val))

    def job(self):
        return self.step.job(self.values())


# ---------------------------------------------------------------------------
#  Slurm 对话框
# ---------------------------------------------------------------------------

class SlurmDialog(QDialog):
    FIELDS = [("job", "作业名", ""), ("partition", "分区 (partition)", "空 = 默认分区"),
              ("nodes", "节点数", ""), ("ntasks", "每节点 MPI 进程数", ""),
              ("time", "时间限制", "如 2-00:00:00 (2 天)"), ("mem", "内存", "如 64G；空 = 不指定"),
              ("bindir", "服务器上的 GRASP bin 目录", ""),
              ("modules", "加载模块等命令", "每行一条，如 module load openmpi"),
              ("mpirun", "MPI 启动命令", ""), ("mpitmp", "MPI 临时目录 (MPI_TMP)", ""),
              ("mail", "邮件通知地址", "空 = 不通知"), ("extra", "其他 #SBATCH 选项", "每行一条，如 --account=xxx")]
    MULTILINE = ("modules", "extra")

    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle(T("Slurm 作业脚本"))
        lay = QVBoxLayout(self)
        note = QLabel(T("把当前流程导出为可直接 sbatch 提交的作业脚本。把脚本和工作目录中的输入文件 "
                        "(isodata, *.c, *.w …) 一起上传到服务器的同一目录，然后运行 sbatch 脚本名。"))
        note.setWordWrap(True)
        lay.addWidget(note)
        g = QGridLayout()
        g.setColumnStretch(1, 1)
        self.w = {}
        for r, (key, label, hint) in enumerate(self.FIELDS):
            if key in self.MULTILINE:
                w = text_edit(settings[key], 3)
            else:
                w = QLineEdit(settings[key])
                w.setMinimumWidth(320)
            self.w[key] = w
            g.addWidget(QLabel(T(label)), r, 0, Qt.AlignTop if key in self.MULTILINE else Qt.AlignVCenter)
            g.addWidget(w, r, 1)
            g.addWidget(hint_label(hint), r, 2)
        lay.addLayout(g)
        bar = QHBoxLayout()
        bar.addStretch()
        ok = button("导出…", self.accept)
        ok.setDefault(True)
        bar.addWidget(ok)
        bar.addWidget(button("取消", self.reject))
        lay.addLayout(bar)

    def settings(self):
        return {k: (w.toPlainText() if isinstance(w, QPlainTextEdit) else w.text()).strip()
                for k, w in self.w.items()}


# ---------------------------------------------------------------------------
#  程序页：上层按功能分组，下层是组内的程序 (每层都能一行放下，无需滚动)
# ---------------------------------------------------------------------------

class StepNav(QWidget):
    def __init__(self, forms):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.groups = QTabWidget()
        self.groups.tabBar().setStyleSheet("QTabBar::tab { font-weight: bold; padding: 5px 18px; }")
        by_key = {f.step.key: f for f in forms}
        self.inner = {}                         # 程序 key -> 所在分组的下层标签页
        for title, keys in core.STEP_GROUPS:
            tabs = QTabWidget()
            tabs.setDocumentMode(True)
            for key in keys:
                tabs.addTab(by_key[key], T(by_key[key].step.name))
                self.inner[key] = tabs
            self.groups.addTab(tabs, T(title).replace("&", "&&"))     # "&" 在标签里是快捷键标记
        lay.addWidget(self.groups)

    def currentWidget(self):
        return self.groups.currentWidget().currentWidget()

    def setCurrentWidget(self, form):
        tabs = self.inner[form.step.key]
        self.groups.setCurrentWidget(tabs)
        tabs.setCurrentWidget(form)

    def setText(self, form, text):
        tabs = self.inner[form.step.key]
        tabs.setTabText(tabs.indexOf(form), text)

    def text(self, form):
        tabs = self.inner[form.step.key]
        return tabs.tabText(tabs.indexOf(form))


# ---------------------------------------------------------------------------
#  主窗口
# ---------------------------------------------------------------------------

TAG_COLORS = {"": QColor("#dcdcdc"), "head": QColor("#6cb6ff"), "info": QColor("#a0d080"), "err": QColor("#ff7070")}


class MainWindow(QMainWindow):
    def __init__(self, workdir=None):
        super().__init__()
        self.resize(1150, 880)
        self.q = queue.Queue()
        self.runner = core.Runner(lambda s, tag: self.q.put((s, tag)))
        self.pipeline = []
        self.busy = False
        self.group = core.GROUPS[0]
        self.groups = {g: core.group_defaults(g) for g in core.GROUPS}
        cfg = core.load_config()
        if not workdir:
            last = cfg.get("workdir", "")
            workdir = last if last and os.path.isdir(last) else os.getcwd()
        self.cur_workdir = os.path.abspath(workdir)
        self.settings = dict(workdir=self.cur_workdir, bindir=core.default_bindir(), np=int(cfg.get("np", 1)),
                             mpirun=cfg.get("mpirun", "mpirun"), mpitmp=cfg.get("mpitmp", "tmp_mpi"),
                             nice=cfg.get("nice", True))
        self.slurm = dict(core.SLURM_DEFAULTS, **cfg.get("slurm", {}))
        self.formats = {}
        for tag, color in TAG_COLORS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            if tag == "head":
                fmt.setFontWeight(QFont.Bold)
            self.formats[tag] = fmt
        self.build()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        core.save_config(workdir=self.cur_workdir)
        self.open_workdir(self.cur_workdir)

    # ---- 布局 ----
    def build(self):
        """创建全部控件；切换语言时重新调用。"""
        app = QApplication.instance()
        fams = set(QFontDatabase.families())
        cjk = next((f for f in CJK_FONTS if f in fams), None)
        if core.LANG == "zh" and cjk:
            font = app.font()
            font.setFamily(cjk)
            app.setFont(font)
        self.setWindowTitle(T("GRASP 图形界面"))
        self.build_menu()

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(self.build_top())
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.build_steps())
        split.addWidget(self.build_bottom())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split)
        self.setCentralWidget(central)
        self.statusBar().showMessage(T("就绪"))

    def build_menu(self):
        mb = self.menuBar()
        mb.clear()
        fm = mb.addMenu(T("文件"))
        for item in [("保存参数…", self.save_params), ("载入参数…", self.load_params), None,
                     ("导出流程为 shell 脚本…", self.export_script),
                     ("导出 Slurm 作业脚本…", self.export_slurm), None, ("退出", self.close)]:
            if item is None:
                fm.addSeparator()
            else:
                fm.addAction(T(item[0])).triggered.connect(item[1])
        lm = mb.addMenu(T("语言") + " / Language" if core.LANG == "zh" else "Language / 语言")
        group = QActionGroup(self)
        for code, label in [("zh", "中文"), ("en", "English")]:
            act = QAction(label, self, checkable=True, checked=core.LANG == code)
            act.triggered.connect(lambda _=False, c=code: self.set_language(c))
            group.addAction(act)
            lm.addAction(act)

    def build_top(self):
        s = self.settings
        g = QGridLayout()
        self.workdir = QLineEdit(s["workdir"])
        self.bindir = QLineEdit(s["bindir"])
        self.workdir.editingFinished.connect(self.workdir_changed)
        for r, (label, edit) in enumerate([("工作目录", self.workdir), ("GRASP bin 目录", self.bindir)]):
            g.addWidget(QLabel(T(label)), r, 0)
            g.addWidget(edit, r, 1)
            g.addWidget(button("浏览…", lambda _=False, e=edit: self.pick_dir(e)), r, 2)
        g.addWidget(button("查看文件", self.list_files), 0, 3)

        mp = QHBoxLayout()
        self.np = QSpinBox()
        self.np.setRange(1, max(os.cpu_count() or 1, 1))
        self.np.setValue(s["np"])
        self.mpirun = QLineEdit(s["mpirun"])
        self.mpitmp = QLineEdit(s["mpitmp"])
        self.nice = QCheckBox(T("降低计算进程优先级 (nice)"))
        self.nice.setChecked(s["nice"])
        for w in [QLabel(T("MPI 进程数")), self.np, QLabel(T("mpirun 命令")), self.mpirun,
                  QLabel("MPI_TMP"), self.mpitmp, self.nice]:
            mp.addWidget(w)
        mp.addStretch()
        g.addLayout(mp, 2, 0, 1, 4)
        hint = hint_label("进程数 > 1 时 rangular / rmcdhf / rci / rbiotransform / rtransition 改用 *_mpi 版本；"
                          "rangular 与 rmcdhf 须使用相同的进程数和 MPI_TMP。")
        hint.setWordWrap(True)
        g.addWidget(hint, 3, 0, 1, 4)
        g.setColumnStretch(1, 1)
        return g

    def build_steps(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        gb = QHBoxLayout()
        gb.addWidget(QLabel(T("态组")))
        self.group_buttons = QButtonGroup(w)
        for g in core.GROUPS:
            b = QPushButton(g)
            b.setCheckable(True)
            b.setChecked(g == self.group)
            b.setStyleSheet("QPushButton { padding: 3px 18px; } "
                            "QPushButton:checked { background: #2d6cdf; color: white; font-weight: bold; }")
            b.clicked.connect(lambda _=False, g=g: self.switch_group(g))
            self.group_buttons.addButton(b)
            gb.addWidget(b)
        self.copy_btn = QPushButton()
        self.copy_btn.clicked.connect(self.copy_group)
        gb.addWidget(self.copy_btn)
        note = hint_label("rcsfgenerate 至 ris4 的参数按态组分别保存；rnucleus、rlevels、rtablevels、rbiotransform、"
                          "rtransition 和自定义页两组共用。")
        note.setWordWrap(True)
        gb.addWidget(note, 1)
        lay.addLayout(gb)

        self.forms = [StepForm(step, self.bindir.text()) for step in core.STEPS]
        self.nav = StepNav(self.forms)
        for f in self.group_forms():
            f.set_values(self.groups[self.group][f.step.key])
        self.update_group_labels()
        lay.addWidget(self.nav)
        bar = QHBoxLayout()
        bar.addWidget(button("预览输入", self.preview))
        bar.addWidget(button("▶ 运行当前程序", self.run_current))
        bar.addWidget(button("加入流程 ↓", self.add_to_pipeline))
        bar.addStretch()
        bar.addWidget(button("■ 停止", self.runner.stop))
        lay.addLayout(bar)
        return w

    def build_bottom(self):
        split = QSplitter(Qt.Horizontal)
        self.btabs = QTabWidget()

        pw = QWidget()
        pl = QHBoxLayout(pw)
        self.plist = QListWidget()
        self.plist.itemDoubleClicked.connect(self.show_job)
        pl.addWidget(self.plist)
        btns = QVBoxLayout()
        for text, slot in [("▶ 运行全部", self.run_pipeline), ("▶ 从选中开始", self.run_from_selected),
                           ("查看", self.show_job), ("上移", lambda: self.move(-1)), ("下移", lambda: self.move(1)),
                           ("删除", self.remove_job), ("清空", self.clear_pipeline),
                           ("导出脚本…", self.export_script), ("导出 Slurm 作业脚本…", self.export_slurm)]:
            btns.addWidget(button(text, slot))
        btns.addStretch()
        pl.addLayout(btns)
        self.btabs.addTab(pw, T("流程"))

        self.prev = QPlainTextEdit()
        self.prev.setFont(fixed_font())
        self.btabs.addTab(self.prev, T("输入预览"))
        split.addWidget(self.btabs)

        ow = QWidget()
        ol = QVBoxLayout(ow)
        ol.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(QLabel(T("程序输出")))
        top.addWidget(hint_label(T("（只显示最后 {n} 行，完整输出请设置日志文件）", n=core.MAX_OUT_LINES)))
        top.addStretch()
        top.addWidget(button("清屏", lambda: self.out.clear()))
        ol.addLayout(top)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(fixed_font())
        self.out.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.out.setMaximumBlockCount(core.MAX_OUT_LINES)   # 超出部分由 Qt 自动丢弃
        self.out.setStyleSheet("QPlainTextEdit { background: #1e1e1e; color: #dcdcdc; }")
        ol.addWidget(self.out)
        split.addWidget(ow)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        self.refresh_list()
        return split

    def closeEvent(self, event):
        if self.busy:
            ans = QMessageBox.question(self, T("运行中"), T("有程序正在运行，退出将终止它。确定退出吗？"))
            if ans != QMessageBox.Yes:
                event.ignore()
                return
            self.runner.kill()
        self.save_session()
        event.accept()

    def pick_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "", edit.text() or os.getcwd())
        if d:
            edit.setText(d)
            if edit is self.workdir:
                self.workdir_changed()

    # ---- 态组 ----
    def group_forms(self):
        return [f for f in self.forms if f.step.key in core.GROUP_STEPS]

    def other_group(self):
        return next(g for g in core.GROUPS if g != self.group)

    def flush_group(self):
        """把表单中当前态组的参数存回 self.groups。"""
        for f in self.group_forms():
            self.groups[self.group][f.step.key] = f.values()

    def load_group(self):
        for f in self.group_forms():
            f.set_values(self.groups[self.group][f.step.key])
        self.update_group_labels()

    def update_group_labels(self):
        for b in self.group_buttons.buttons():
            b.setChecked(b.text() == self.group)
        self.copy_btn.setText(T("复制到 {g}（替换名称）", g=self.other_group()))
        for f in self.forms:
            name = T(f.step.name)
            self.nav.setText(f, f"{name} · {self.group}" if f.step.key in core.GROUP_STEPS else name)

    def switch_group(self, g):
        if g == self.group:
            return
        self.flush_group()
        self.group = g
        self.load_group()
        self.statusBar().showMessage(T("当前态组：{g}", g=g))
        self.save_session()

    def copy_group(self):
        a, b = self.group, self.other_group()
        if QMessageBox.question(self, T("态组"), T("确定用 {a} 组的参数覆盖 {b} 组吗？", a=a, b=b)) != QMessageBox.Yes:
            return
        self.flush_group()
        self.groups[b] = core.rename_group(self.groups[a], a, b)
        self.statusBar().showMessage(
            T("已把 {a} 组的参数复制到 {b} 组 (名称中的 {a} 已替换为 {b})；请检查 {b} 的参考组态、2J 范围和能级。", a=a, b=b))
        self.save_session()

    # ---- 工作目录中的记录 ----
    def workdir_changed(self):
        new = os.path.abspath(self.workdir.text().strip() or ".")
        if new == self.cur_workdir:
            return
        self.save_session()                 # 先保存旧目录的记录
        self.cur_workdir = new
        self.workdir.setText(new)
        core.save_config(workdir=new)
        self.open_workdir(new)

    def open_workdir(self, d):
        if not os.path.isdir(d):
            return
        data = core.load_session(d)
        if data:
            self.apply(data)
            self.statusBar().showMessage(T("已载入此目录上次的记录") + f"  ({os.path.join(d, core.SESSION_FILE)})")
        else:
            self.statusBar().showMessage(T("此目录还没有记录，沿用当前参数"))

    def save_session(self):
        data = self.collect()
        for key in ("workdir", "bindir"):     # 与目录无关的设置不放进目录记录
            data.pop(key)
        core.save_session(self.cur_workdir, data)

    def set_language(self, lang):
        if lang == core.LANG:
            return
        data = self.collect()
        output = self.out.toPlainText()
        core.set_lang(lang)
        core.save_config(lang=lang)
        self.build()
        self.apply(data)
        self.append(output, "")

    # ---- 输出 ----
    def poll(self):
        # 每次把队列中的输出全部取出，合并相同 tag 的连续片段后一次插入
        segs = []
        try:
            while True:
                s, tag = self.q.get_nowait()
                if tag == "done":
                    self.finished(s)
                elif segs and segs[-1][1] == tag:
                    segs[-1][0].append(s)
                else:
                    segs.append(([s], tag))
        except queue.Empty:
            pass
        for parts, tag in segs:
            text = "".join(parts)
            if text.count("\n") > core.MAX_OUT_LINES:
                text = "\n".join(text.split("\n")[-core.MAX_OUT_LINES - 1:])
            self.append(text, tag)

    def append(self, text, tag):
        if not text:
            return
        bar = self.out.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 2
        cur = QTextCursor(self.out.document())
        cur.movePosition(QTextCursor.End)
        cur.insertText(text, self.formats[tag])
        if at_bottom:   # 用户向上翻看时不强行滚到底
            bar.setValue(bar.maximum())

    def write(self, s, tag=""):
        self.q.put((s, tag))

    # ---- 动作 ----
    def current_job(self):
        try:
            return self.nav.currentWidget().job()
        except (ValueError, KeyError) as e:
            QMessageBox.critical(self, T("参数错误"), T("参数格式有误：{e}", e=e))
            return None

    def mpi_prefix(self):
        n = self.np.value()
        return f"{self.mpirun.text().strip()} -np {n}" if n > 1 else ""

    def preview(self):
        job = self.current_job()
        if job:
            self.prev.setPlainText(core.describe(job, self.mpi_prefix()) + "\n")
            self.btabs.setCurrentIndex(1)

    def check_dirs(self):
        cwd = self.workdir.text()
        if not os.path.isdir(cwd):
            QMessageBox.critical(self, T("错误"), T("工作目录不存在：{d}", d=cwd))
            return False
        return True

    def start(self, jobs):
        if self.busy:
            QMessageBox.information(self, T("运行中"), T("已有任务在运行，请等待或先停止。"))
            return
        if not jobs or not self.check_dirs():
            return
        cfg = dict(bindir=self.bindir.text(), cwd=self.workdir.text(), np=self.np.value(),
                   mpirun=self.mpirun.text(), mpitmp=self.mpitmp.text().strip() or "tmp_mpi",
                   nice=self.nice.isChecked())
        core.save_config(np=cfg["np"], mpirun=cfg["mpirun"], mpitmp=cfg["mpitmp"], nice=cfg["nice"],
                         bindir=cfg["bindir"])
        self.save_session()
        self.busy = True
        self.statusBar().showMessage(T("运行中：{n} 个步骤 …", n=len(jobs)))
        threading.Thread(target=self.runner.run_all, daemon=True,
                         args=(jobs, cfg, lambda ok: self.q.put((ok, "done")))).start()

    def finished(self, ok):
        self.busy = False
        self.statusBar().showMessage(T("完成") if ok else T("失败 / 已停止 — 详见输出"))

    def run_current(self):
        job = self.current_job()
        if job:
            self.prev.setPlainText(core.describe(job, self.mpi_prefix()) + "\n")
            self.start([job])

    def add_to_pipeline(self):
        job = self.current_job()
        if job:
            self.pipeline.append(job)
            self.refresh_list()
            self.btabs.setCurrentIndex(0)
            self.save_session()

    def refresh_list(self):
        self.plist.clear()
        self.plist.addItems([f"{i:2d}. {j['title']}" for i, j in enumerate(self.pipeline, 1)])

    def selected(self):
        i = self.plist.currentRow()
        return i if 0 <= i < len(self.pipeline) else None

    def show_job(self, *_):
        i = self.selected()
        if i is not None:
            self.prev.setPlainText(core.describe(self.pipeline[i], self.mpi_prefix()) + "\n")
            self.btabs.setCurrentIndex(1)

    def move(self, d):
        i = self.selected()
        if i is None or not 0 <= i + d < len(self.pipeline):
            return
        p = self.pipeline
        p[i], p[i + d] = p[i + d], p[i]
        self.refresh_list()
        self.plist.setCurrentRow(i + d)
        self.save_session()

    def remove_job(self):
        i = self.selected()
        if i is not None:
            del self.pipeline[i]
            self.refresh_list()
            self.save_session()

    def clear_pipeline(self):
        self.pipeline.clear()
        self.refresh_list()
        self.save_session()

    def run_pipeline(self):
        self.start(list(self.pipeline))

    def run_from_selected(self):
        self.start(self.pipeline[self.selected() or 0:])

    def list_files(self):
        if not self.check_dirs():
            return
        cwd = self.workdir.text()
        names = sorted(os.listdir(cwd))
        self.write("\n" + T("----- {d} ({n} 个文件) -----", d=cwd, n=len(names)) + "\n", "head")
        self.write("  ".join(names) + "\n")

    def need_pipeline(self):
        if not self.pipeline:
            QMessageBox.information(self, T("导出"), T("流程为空：先在各标签页点击“加入流程”。"))
            return False
        return True

    def save_text(self, title, name, text):
        path, _ = QFileDialog.getSaveFileName(self, title, os.path.join(self.workdir.text(), name))
        if not path:
            return
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, 0o755)
        self.statusBar().showMessage(T("已导出 {p}", p=path))

    def export_script(self):
        if self.need_pipeline():
            self.save_text(T("导出 shell 脚本"), "sh_gui",
                           core.shell_script(self.pipeline, self.bindir.text(), self.workdir.text(),
                                             self.mpi_prefix(), self.mpitmp.text().strip()))

    def export_slurm(self):
        if not self.need_pipeline():
            return
        dlg = SlurmDialog(self, self.slurm)
        if dlg.exec() != QDialog.Accepted:
            return
        self.slurm = dlg.settings()
        core.save_config(slurm=self.slurm)
        self.save_text(T("Slurm 作业脚本"), f"{self.slurm['job'] or 'grasp'}.slurm",
                       core.slurm_script(self.pipeline, self.slurm))

    # ---- 参数保存 / 载入 ----
    def collect(self):
        self.flush_group()
        return dict(workdir=self.workdir.text(), bindir=self.bindir.text(), np=self.np.value(),
                    mpirun=self.mpirun.text(), mpitmp=self.mpitmp.text(), nice=self.nice.isChecked(),
                    slurm=self.slurm, steps={f.step.key: f.values() for f in self.forms},
                    groups=self.groups, group=self.group,
                    pipeline=self.pipeline, tab=self.nav.currentWidget().step.key)

    def apply(self, data):
        for key, edit in [("workdir", self.workdir), ("bindir", self.bindir),
                          ("mpirun", self.mpirun), ("mpitmp", self.mpitmp)]:
            if key in data:
                edit.setText(str(data[key]))
        if "workdir" in data:
            self.cur_workdir = os.path.abspath(str(data["workdir"]))
            core.save_config(workdir=self.cur_workdir)
        if "np" in data:
            self.np.setValue(int(data["np"]))
        if "nice" in data:
            self.nice.setChecked(bool(data["nice"]))
        self.slurm.update(data.get("slurm", {}))
        steps = data.get("steps", {})
        for f in self.forms:
            # 兼容旧版本以中文标签页名保存的"自定义"参数
            d = steps.get(f.step.key) or steps.get(f.step.name)
            if d and f.step.key not in core.GROUP_STEPS:
                f.set_values(d)
        saved = data.get("groups")
        if saved is None:
            # 旧版本的参数没有态组：作为 odd 组的参数，even 组用默认值
            saved = {core.GROUPS[0]: {k: steps[k] for k in core.GROUP_STEPS if k in steps}}
        self.groups = {g: {k: dict(v, **saved.get(g, {}).get(k, {})) for k, v in core.group_defaults(g).items()}
                       for g in core.GROUPS}
        self.group = data.get("group") if data.get("group") in core.GROUPS else core.GROUPS[0]
        self.load_group()
        self.pipeline = [dict(j, pre=[tuple(a) for a in j["pre"]], post=[tuple(a) for a in j["post"]])
                         for j in data.get("pipeline", [])]
        self.refresh_list()
        tab = data.get("tab")
        if isinstance(tab, int):                # 旧版本按序号保存
            if 0 <= tab < len(self.forms):
                self.nav.setCurrentWidget(self.forms[tab])
        elif tab:
            for f in self.forms:
                if f.step.key == tab:
                    self.nav.setCurrentWidget(f)

    def save_params(self):
        path, _ = QFileDialog.getSaveFileName(self, T("保存参数"), self.workdir.text(), "JSON (*.json)")
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        with open(path, "w") as f:
            json.dump(self.collect(), f, ensure_ascii=False, indent=1)
        self.statusBar().showMessage(T("参数已保存到 {p}", p=path))

    def load_params(self):
        path, _ = QFileDialog.getOpenFileName(self, T("载入参数"), self.workdir.text(), "JSON (*.json)")
        if not path:
            return
        with open(path) as f:
            self.apply(json.load(f))
        self.statusBar().showMessage(T("已载入 {p}", p=path))


def main():
    args = sys.argv[1:]
    if "--lang" in args and args.index("--lang") + 1 < len(args):
        i = args.index("--lang")
        core.set_lang(args[i + 1])
        core.save_config(lang=core.LANG)
        del args[i:i + 2]
    else:
        core.set_lang(core.load_config().get("lang", "zh"))
    app = QApplication(sys.argv[:1])
    app.setApplicationName("GRASP GUI")
    win = MainWindow(args[0] if args else None)     # 可选参数：要打开的工作目录
    win.show()
    rc = app.exec()
    # 在 WSLg 的 Wayland 下，进程退出时 Qt 的收尾清理会卡住几十秒以上；
    # 参数在操作时已保存，运行中的程序已在 closeEvent 中结束，因此直接退出
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)


if __name__ == "__main__":
    main()
