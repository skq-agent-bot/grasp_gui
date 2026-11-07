from PySide2.QtGui import *  # noqa: F401,F403
from PySide2.QtGui import (QFontDatabase, QGuiApplication, QHoverEvent, QMouseEvent, QNativeGestureEvent, QPageSize,
                           QPalette, QPdfWriter)
from PySide2.QtWidgets import QAction, QActionGroup, QShortcut  # noqa: F401  Qt 6 移到了 QtGui

from . import QtCore  # noqa: F401

QGuiApplication.exec = QGuiApplication.exec_

# Qt 6: 鼠标事件的坐标为 position() / globalPosition() (QPointF)
QMouseEvent.position = QMouseEvent.localPos
QMouseEvent.globalPosition = QMouseEvent.screenPos
QHoverEvent.position = QHoverEvent.posF
QNativeGestureEvent.position = QNativeGestureEvent.localPos

# Qt 6 中 families() 是静态函数
_families = QFontDatabase.families
QFontDatabase.families = staticmethod(lambda *args: _families(QFontDatabase(), *args))

# Qt 6 的枚举是 Python 的 enum，有 .value
QPalette.ColorRole.value = property(int)

# PySide2 只提供按纸张代号设置页面大小的 setPageSize
_set_page_size = QPdfWriter.setPageSize


def _page_size(self, size):
    if not isinstance(size, QPageSize):
        return _set_page_size(self, size)
    layout = self.pageLayout()
    layout.setPageSize(size)
    return self.setPageLayout(layout)


QPdfWriter.setPageSize = _page_size
