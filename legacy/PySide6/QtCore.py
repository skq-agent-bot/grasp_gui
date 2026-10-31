from PySide2.QtCore import *  # noqa: F401,F403
from PySide2.QtCore import QCoreApplication, Qt

# Qt 6 中 exec 不再带下划线
QCoreApplication.exec = QCoreApplication.exec_

# Qt 6 总是按屏幕缩放比例显示 (高分屏)，Qt 5 需要在创建 QApplication 之前打开
QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
