import os
import sys

from PySide2.QtWidgets import *  # noqa: F401,F403
from PySide2.QtWidgets import QApplication as _QApplication
from PySide2.QtWidgets import QDialog, QMenu, QTabBar

from . import QtCore, QtGui  # noqa: F401  先补上 QtCore / QtGui

NO_DISPLAY = """Cannot open a window: no display (DISPLAY is not set).
Over ssh, log in with X11 forwarding: ssh -X user@server (or ssh -Y). If DISPLAY is still empty, the server
needs "X11Forwarding yes" in /etc/ssh/sshd_config and the xauth program.

无法打开窗口：没有显示设备 (未设置 DISPLAY)。
通过 ssh 使用时请打开 X11 转发登录：ssh -X 用户名@服务器 (或 ssh -Y)。若 DISPLAY 仍为空，服务器需要在
/etc/ssh/sshd_config 中设置 "X11Forwarding yes" 并安装 xauth。"""


class QApplication(_QApplication):
    """没有显示设备时 Qt 5 只打印 "no Qt platform plugin could be initialized" 并异常终止；先给出明确的提示。"""

    def __init__(self, *args):
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or os.environ.get("QT_QPA_PLATFORM")):
            print(NO_DISPLAY, file=sys.stderr)
            sys.exit(1)
        super().__init__(*args)


for _cls in (_QApplication, QDialog, QMenu):
    _cls.exec = _cls.exec_

# Qt 5 按控件字体而不是样式表中的字体计算标签宽度，样式表把标签设为粗体时文字被截掉；同时设置粗体字体
_tab_style = QTabBar.setStyleSheet


def _tab_bar_style(self, sheet):
    _tab_style(self, sheet)
    if "font-weight: bold" in sheet:
        font = self.font()
        font.setBold(True)
        self.setFont(font)


QTabBar.setStyleSheet = _tab_bar_style
