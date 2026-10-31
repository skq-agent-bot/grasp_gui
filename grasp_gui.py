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


FONTS_CONF = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <dir>/usr/share/fonts</dir>
  <dir>/usr/local/share/fonts</dir>
  <dir prefix="xdg">fonts</dir>
  <dir>~/.fonts</dir>
  <cachedir>{cache}</cachedir>
  <alias><family>sans-serif</family>
    <prefer><family>Noto Sans</family><family>DejaVu Sans</family><family>Noto Sans CJK SC</family></prefer></alias>
  <alias><family>serif</family>
    <prefer><family>Noto Serif</family><family>DejaVu Serif</family><family>Noto Serif CJK SC</family></prefer></alias>
  <alias><family>monospace</family>
    <prefer><family>DejaVu Sans Mono</family><family>Noto Sans Mono</family><family>Noto Sans Mono CJK SC</family></prefer></alias>
  <match target="font">
    <edit name="antialias" mode="assign"><bool>true</bool></edit>
    <edit name="hinting" mode="assign"><bool>true</bool></edit>
    <edit name="hintstyle" mode="assign"><const>hintslight</const></edit>
  </match>
</fontconfig>
"""


def fix_fontconfig():
    """打包的程序自带构建机器上的 fontconfig 库；系统的 /etc/fonts 若来自更新的 fontconfig，
    旧库读它时会打印大量 "invalid attribute 'xsi:nil'" 之类的错误。因此改用一份只列出字体目录的
    简单配置 (系统和用户字体照常可用；打包的字体在 load_fonts 中直接注册)。"""
    if not getattr(sys, "frozen", False) or os.environ.get("FONTCONFIG_FILE") or os.environ.get("FONTCONFIG_PATH"):
        return
    cache = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "grasp_gui")
    path = os.path.join(cache, "fonts.conf")
    text = FONTS_CONF.format(cache=os.path.join(cache, "fontconfig"))
    try:
        os.makedirs(cache, exist_ok=True)
        old = open(path).read() if os.path.exists(path) else None
        if old != text:
            with open(path, "w") as f:
                f.write(text)
    except OSError:
        return
    os.environ["FONTCONFIG_FILE"] = os.environ["GRASP_GUI_FONTCONFIG"] = path


fix_wsl_display()
fix_fontconfig()

from PySide6.QtCore import QByteArray, QEvent, QObject, Qt, QTimer  # noqa: E402
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont,    # noqa: E402
                           QFontDatabase, QKeySequence, QPalette, QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox,  # noqa: E402
                               QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QSplitter, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grasp_core as core                                           # noqa: E402
from grasp_core import T                                            # noqa: E402

CJK_FONTS = ["Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei", "WenQuanYi Micro Hei",
             "Droid Sans Fallback", "AR PL UMing CN"]
LATIN_FONTS = ["Noto Sans", "DejaVu Sans", "Liberation Sans"]
MONO_FONTS = ["DejaVu Sans Mono", "Noto Sans Mono", "Liberation Mono", "Noto Sans Mono CJK SC"]
DEFAULT_PT = 10.0          # 系统默认字号 (main 中按 QApplication 的默认字体设置)；"视图"菜单可调整并保存


def load_fonts():
    """注册随程序打包的字体 (build.sh 放在 fonts/ 中)，使没有安装字体的机器也能正常显示。
    系统已有的字体照常可用；查找位置为可执行文件内部和程序所在目录的 fonts/。"""
    dirs = [os.path.join(getattr(sys, "_MEIPASS", ""), "fonts"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")]
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.lower().endswith((".ttf", ".otf", ".ttc")):
                QFontDatabase.addApplicationFont(os.path.join(d, name))


def first_family(candidates):
    fams = set(QFontDatabase.families())
    return next((f for f in candidates if f in fams), None)


def fixed_font():
    """等宽字体：优先用常见的等宽字体 (包括打包的 DejaVu Sans Mono)，都没有时用系统默认。"""
    family = first_family(MONO_FONTS)
    if family:
        font = QFont(family)
        font.setStyleHint(QFont.Monospace)
    else:
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSizeF(QApplication.font().pointSizeF())       # 与界面字号一致
    return font


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
#  示例对话框
# ---------------------------------------------------------------------------

DEMO_ROOT = os.path.join(os.path.expanduser("~"), "grasp_demos")


def free_dir(path):
    """path 不存在或为空时原样返回，否则依次尝试 path_2, path_3 …"""
    cand, k = path, 2
    while os.path.isdir(cand) and os.listdir(cand):
        cand, k = f"{path}_{k}", k + 1
    return cand


class DemoDialog(QDialog):
    """选择 GRASP2018 手册中的算例，导入到一个空目录。"""

    def __init__(self, parent, demos, bindir):
        super().__init__(parent)
        self.setWindowTitle(T("导入示例"))
        self.resize(900, 560)
        self.demos, self.bindir = demos, bindir
        lay = QVBoxLayout(self)
        note = QLabel(T("示例来自 GRASP2018 手册的算例，只包含各程序的参数和计算流程。导入到一个空目录后，"
                        "点“▶ 运行全部”即可从头计算；各程序页显示该程序在流程中最后一次使用的参数。"))
        note.setWordWrap(True)
        lay.addWidget(note)
        split = QSplitter()
        self.list = QListWidget()
        self.list.setWordWrap(True)             # 标题较长：换行显示，不出现横向滚动条
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setSpacing(2)
        self.list.addItems([core.demo_text(d, "title") for d in demos])
        split.addWidget(self.list)
        self.info = QTextBrowser()
        split.addWidget(self.info)
        split.setStretchFactor(1, 2)
        split.setSizes([300, 600])
        lay.addWidget(split, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel(T("导入到目录")))
        self.dir = QLineEdit()
        self.dir.textEdited.connect(lambda: setattr(self, "dir_edited", True))
        row.addWidget(self.dir, 1)
        row.addWidget(button("浏览…", self.pick))
        lay.addLayout(row)
        bar = QHBoxLayout()
        bar.addStretch()
        ok = button("导入", self.accept)
        ok.setDefault(True)
        bar.addWidget(ok)
        bar.addWidget(button("取消", self.reject))
        lay.addLayout(bar)
        self.dir_edited = False
        self.list.currentRowChanged.connect(self.show_demo)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        self.list.setCurrentRow(0)

    def demo(self):
        return self.demos[max(self.list.currentRow(), 0)]

    def show_demo(self, row):
        d = self.demos[row]
        esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")     # noqa: E731
        html = [f"<h3>{esc(core.demo_text(d, 'title'))}</h3>", f"<p>{esc(core.demo_text(d, 'summary'))}</p>",
                f"<p><b>{T('预计时间')}:</b> {esc(core.demo_text(d, 'runtime'))}<br>"
                f"<b>{T('流程')}:</b> {T('{n} 步', n=len(d['jobs']))}<br>"
                f"<b>{T('用到的程序')}:</b> {esc(', '.join(core.demo_programs(d)))}</p>"]
        missing = core.missing_programs(d, self.bindir)
        if missing:
            html.append(f"<p style='color:#c00000'><b>{T('在 bin 目录和 PATH 中找不到')}:</b> "
                        f"{esc(', '.join(missing))}<br>{T('流程运行到这些程序时会出错。')}</p>")
        refs = d.get("reference", [])
        if refs:
            html.append(f"<p><b>{T('参考结果')}</b> ({T('手册脚本算出的能量，可与自己的结果对照')}):</p><ul>")
            for r in refs:
                e = r["energies"]
                html.append(f"<li>{esc(r['file'])}: {T('{n} 个能级', n=len(e))}, "
                            f"{T('最低')} {min(e):.8f} Eh</li>")
            html.append("</ul>")
        self.info.setHtml("".join(html))
        if not self.dir_edited:
            self.dir.setText(free_dir(os.path.join(DEMO_ROOT, d["id"])))

    def pick(self):
        d = QFileDialog.getExistingDirectory(self, "", os.path.dirname(self.dir.text()) or os.path.expanduser("~"))
        if d:
            self.dir.setText(d)
            self.dir_edited = True

    def target(self):
        return os.path.abspath(os.path.expanduser(self.dir.text().strip()))


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
        self.restore_layout()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(100)
        core.save_config(workdir=self.cur_workdir)
        self.open_workdir(self.cur_workdir)

    # ---- 布局 ----
    def build(self):
        """创建全部控件；切换语言时重新调用。"""
        # 中文界面优先用中文字体，英文界面优先用西文字体；另一种文字由 Qt 自动换用其他字体显示
        app = QApplication.instance()
        family = first_family(CJK_FONTS + LATIN_FONTS if core.LANG == "zh" else LATIN_FONTS + CJK_FONTS)
        font = app.font()
        if family:
            font.setFamily(family)
        font.setPointSizeF(core.load_config().get("font_size") or DEFAULT_PT)
        app.setFont(font)
        self.setWindowTitle(T("GRASP 图形界面"))
        self.build_menu()

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(self.build_top())
        self.split = QSplitter(Qt.Vertical)
        self.split.addWidget(self.build_steps())
        self.split.addWidget(self.build_bottom())
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([620, 240])         # 默认给参数区更多空间
        lay.addWidget(self.split, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage(T("就绪"))

    def build_menu(self):
        mb = self.menuBar()
        mb.clear()
        fm = mb.addMenu(T("文件"))
        for item in [("导入示例…", self.import_demo), None,
                     ("保存参数…", self.save_params), ("载入参数…", self.load_params), None,
                     ("导出流程为 shell 脚本…", self.export_script),
                     ("导出 Slurm 作业脚本…", self.export_slurm), None, ("退出", self.close)]:
            if item is None:
                fm.addSeparator()
            else:
                fm.addAction(T(item[0])).triggered.connect(item[1])
        tm = mb.addMenu(T("工具"))
        tm.addAction(T("波函数查看器…")).triggered.connect(self.open_viewer)
        tm.addAction(T("能级与组成查看器…")).triggered.connect(self.open_levels)
        vm = mb.addMenu(T("视图"))
        for text, keys, step in [("放大字体", [QKeySequence.ZoomIn, "Ctrl+="], 1),
                                 ("缩小字体", [QKeySequence.ZoomOut], -1), ("默认字体大小", ["Ctrl+0"], 0)]:
            act = vm.addAction(T(text))
            act.setShortcuts([QKeySequence(k) for k in keys])
            act.triggered.connect(lambda _=False, d=step: self.change_font_size(d))
        lm = mb.addMenu(T("语言") + " / Language" if core.LANG == "zh" else "Language / 语言")
        group = QActionGroup(self)
        for code, label in [("zh", "中文"), ("en", "English")]:
            act = QAction(label, self, checkable=True, checked=core.LANG == code)
            act.triggered.connect(lambda _=False, c=code: self.set_language(c))
            group.addAction(act)
            lm.addAction(act)

    def build_top(self):
        """工作目录一行始终显示；GRASP bin 目录和 MPI 设置放在可收起的设置区。"""
        s = self.settings
        top = QVBoxLayout()
        row = QHBoxLayout()
        self.workdir = QLineEdit(s["workdir"])
        self.workdir.editingFinished.connect(self.workdir_changed)
        row.addWidget(QLabel(T("工作目录")))
        row.addWidget(self.workdir, 1)
        row.addWidget(button("浏览…", lambda: self.pick_dir(self.workdir)))
        row.addWidget(button("查看文件", self.list_files))
        row.addWidget(button("波函数…", self.open_viewer))
        row.addWidget(button("能级…", self.open_levels))
        self.settings_btn = QPushButton()
        self.settings_btn.setToolTip(T("展开或收起 GRASP bin 目录和 MPI 设置"))
        self.settings_btn.clicked.connect(lambda: self.show_settings(not self.settings_box.isVisible()))
        row.addWidget(self.settings_btn)
        top.addLayout(row)
        self.settings_summary = hint_label("")
        top.addWidget(self.settings_summary)

        self.settings_box = QWidget()
        g = QGridLayout(self.settings_box)
        g.setContentsMargins(0, 0, 0, 0)
        self.bindir = QLineEdit(s["bindir"])
        self.bindir.editingFinished.connect(self.save_settings)     # 改完立即保存，下次启动沿用
        g.addWidget(QLabel(T("GRASP bin 目录")), 0, 0)
        g.addWidget(self.bindir, 0, 1)
        g.addWidget(button("浏览…", lambda: self.pick_dir(self.bindir)), 0, 2)
        mp = QHBoxLayout()
        self.np = QSpinBox()
        self.np.setRange(1, max(os.cpu_count() or 1, 1))
        self.np.setValue(s["np"])
        self.mpirun = QLineEdit(s["mpirun"])
        self.mpitmp = QLineEdit(s["mpitmp"])
        self.nice = QCheckBox(T("降低计算进程优先级 (nice)"))
        self.nice.setChecked(s["nice"])
        mpi_hint = T("进程数 > 1 时 rangular / rmcdhf / rci / rbiotransform / rtransition 改用 *_mpi 版本；"
                     "rangular 与 rmcdhf 须使用相同的进程数和 MPI_TMP。")
        for w in [QLabel(T("MPI 进程数")), self.np, QLabel(T("mpirun 命令")), self.mpirun,
                  QLabel("MPI_TMP"), self.mpitmp, self.nice]:
            w.setToolTip(mpi_hint)
            mp.addWidget(w)
        mp.addStretch()
        g.addLayout(mp, 1, 0, 1, 3)
        g.setColumnStretch(1, 1)
        top.addWidget(self.settings_box)

        self.bindir.textChanged.connect(self.update_settings_summary)
        self.np.valueChanged.connect(self.update_settings_summary)
        # 按上次的收起状态显示；GRASP bin 目录中找不到 GRASP 时总是展开，提醒检查路径
        collapsed = core.load_config().get("settings_collapsed", True)
        if not os.path.isfile(os.path.join(s["bindir"], "rmcdhf")):
            collapsed = False
        self.show_settings(not collapsed, save=False)
        return top

    def show_settings(self, visible, save=True):
        self.settings_box.setVisible(visible)
        self.settings_summary.setVisible(not visible)
        self.settings_btn.setText(("▾ " if visible else "▸ ") + T("设置"))
        self.update_settings_summary()
        if save:
            core.save_config(settings_collapsed=not visible)

    def update_settings_summary(self):
        n = self.np.value()
        mpi = T("MPI {n} 进程", n=n) if n > 1 else T("串行")
        self.settings_summary.setText(T("GRASP bin：{b}　·　{m}", b=self.bindir.text(), m=mpi))

    def build_steps(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        # 态组切换放在分组标签栏右侧的空白处，不单独占一行
        corner = QWidget()
        gb = QHBoxLayout(corner)
        gb.setContentsMargins(0, 0, 4, 2)
        group_hint = T("标签上带组名的程序页按态组分别保存参数，其余程序页两组共用。")
        label = QLabel(T("态组"))
        label.setToolTip(group_hint)
        gb.addWidget(label)
        self.group_buttons = QButtonGroup(w)
        for g in core.GROUPS:
            b = QPushButton(g)
            b.setCheckable(True)
            b.setChecked(g == self.group)
            b.setToolTip(group_hint)
            b.setStyleSheet("QPushButton { padding: 2px 16px; } "
                            "QPushButton:checked { background: #2d6cdf; color: white; font-weight: bold; }")
            b.clicked.connect(lambda _=False, g=g: self.switch_group(g))
            self.group_buttons.addButton(b)
            gb.addWidget(b)
        self.copy_btn = QPushButton()
        self.copy_btn.clicked.connect(self.copy_group)
        gb.addWidget(self.copy_btn)

        self.forms = [StepForm(step, self.bindir.text()) for step in core.STEPS]
        self.nav = StepNav(self.forms)
        self.nav.groups.setCornerWidget(corner, Qt.TopRightCorner)
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
        # 按钮排成两列，面板不会因为按钮多而被撑高
        btns = QGridLayout()
        export = QPushButton(T("导出"))         # 带菜单的按钮会自动显示下拉箭头
        menu = QMenu(export)
        menu.addAction(T("导出脚本…")).triggered.connect(self.export_script)
        menu.addAction(T("导出 Slurm 作业脚本…")).triggered.connect(self.export_slurm)
        export.setMenu(menu)
        for i, b in enumerate([button("▶ 运行全部", self.run_pipeline), button("▶ 从选中开始", self.run_from_selected),
                               button("上移", lambda: self.move(-1)), button("下移", lambda: self.move(1)),
                               button("查看", self.show_job), button("删除", self.remove_job),
                               button("清空", self.clear_pipeline), export]):
            btns.addWidget(b, i // 2, i % 2)
        btns.setRowStretch(4, 1)
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
        self.save_settings()
        core.save_config(geometry=bytes(self.saveGeometry().toBase64()).decode(), split=self.split.sizes())
        event.accept()

    def save_settings(self):
        """GRASP bin 目录和 MPI 设置保存到 ~/.config/grasp_gui.json，作为下次启动的默认值。"""
        core.save_config(bindir=self.bindir.text().strip(), np=self.np.value(), mpirun=self.mpirun.text(),
                         mpitmp=self.mpitmp.text().strip() or "tmp_mpi", nice=self.nice.isChecked())

    def restore_layout(self):
        """恢复上次的窗口大小和参数区 / 输出区的分隔位置。"""
        cfg = core.load_config()
        if cfg.get("geometry"):
            self.restoreGeometry(QByteArray.fromBase64(cfg["geometry"].encode()))
        if cfg.get("split"):
            self.split.setSizes(cfg["split"])

    def pick_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "", edit.text() or os.getcwd())
        if d:
            edit.setText(d)
            if edit is self.workdir:
                self.workdir_changed()
            else:
                self.save_settings()

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
        core.set_lang(lang)
        core.save_config(lang=lang)
        self.rebuild()

    def change_font_size(self, step):
        """step = +1 / -1 磅，0 恢复系统默认；保存在配置中，下次启动沿用。"""
        cur = QApplication.font().pointSizeF()
        size = DEFAULT_PT if step == 0 else min(max(cur + step, 6.0), 30.0)
        if size == cur:
            return
        core.save_config(font_size=None if step == 0 else size)
        self.rebuild()
        self.statusBar().showMessage(T("字体大小 {pt} 磅", pt=f"{size:g}"))

    def rebuild(self):
        """重新创建全部控件 (切换语言或字号后)，保留参数、流程和输出。"""
        data = self.collect()
        output = self.out.toPlainText()
        sizes = self.split.sizes()
        self.build()
        self.split.setSizes(sizes)
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

    def open_window(self, attr, cls):
        """打开 (或切换到) 一个查看器窗口，显示当前工作目录。"""
        win = getattr(self, attr, None)
        if win is None or not win.isVisible():
            win = cls(self.cur_workdir)
            setattr(self, attr, win)
        else:
            win.set_dir(self.cur_workdir)
        win.show()
        win.raise_()
        win.activateWindow()

    def open_viewer(self):
        from wfn_viewer import WfnViewer
        self.open_window("viewer", WfnViewer)

    def open_levels(self):
        from level_viewer import LevelViewer
        self.open_window("levels", LevelViewer)

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

    def import_demo(self):
        if self.busy:
            QMessageBox.information(self, T("运行中"), T("已有任务在运行，请等待或先停止。"))
            return
        demos = core.list_demos()
        if not demos:
            QMessageBox.warning(self, T("导入示例"), T("找不到示例文件 ({p})", p=core.DEMO_DIR))
            return
        dlg = DemoDialog(self, demos, self.bindir.text())
        if dlg.exec() != QDialog.Accepted:
            return
        demo, path = dlg.demo(), dlg.target()
        try:
            core.install_demo(demo, path)
        except OSError as e:
            QMessageBox.warning(self, T("导入示例"), str(e))
            return
        if path == self.cur_workdir:
            self.open_workdir(path)
        else:
            self.workdir.setText(path)
            self.workdir_changed()
        self.statusBar().showMessage(T("已导入示例“{t}”到 {p}；点“▶ 运行全部”开始计算",
                                       t=core.demo_text(demo, "title"), p=path))

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


class WindowFrames(QObject):
    """在 Wayland 下 (如 WSLg) 窗口的标题栏和边框由 Qt 自己绘制 (bradient 装饰)，颜色取自程序调色板的
    窗口背景色，与窗口内容相同，又没有窗口阴影，对话框叠在主窗口上时分不清边界。因此把程序调色板的
    窗口背景色换成 FRAME_COLOR (只有标题栏和边框直接使用程序调色板)，各窗口在显示前恢复原来的调色板。"""
    FRAME_COLOR = QColor("#c3cede")

    def __init__(self, app):
        super().__init__(app)
        framed = app.palette()
        # 每种颜色都显式设置：复制来的调色板不带“已设置”标记，设给窗口后仍会沿用程序调色板
        self.normal = QPalette()
        for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
            for role in range(QPalette.NColorRoles.value):
                role = QPalette.ColorRole(role)
                self.normal.setBrush(group, role, framed.brush(group, role))
        for group in (QPalette.Active, QPalette.Inactive):
            framed.setColor(group, QPalette.Window, self.FRAME_COLOR)
        app.setPalette(framed)
        app.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Polish and obj.isWidgetType() and obj.isWindow():
            obj.setPalette(self.normal)
        return False


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
    global DEFAULT_PT
    DEFAULT_PT = app.font().pointSizeF() if app.font().pointSizeF() > 0 else DEFAULT_PT
    load_fonts()
    if app.platformName().startswith("wayland"):
        app.frames = WindowFrames(app)
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
