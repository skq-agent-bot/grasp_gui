"""
旧系统版 (legacy) 用的 PySide6 替身：界面代码照常 `from PySide6.X import ...`，实际使用 PySide2 (Qt 5.15)。
PySide6 的所有版本都要求 glibc >= 2.28，PySide2 5.15 只要求 glibc 2.17 (CentOS 7)；Qt 5 的 xcb 插件也不需要
libxcb-cursor0，ssh -X 转发到的服务器上通常都能直接运行。只打包进旧系统版，见 legacy/README.md。

这里只补上界面代码用到的 Qt 6 写法，新代码用到其他 Qt 6 才有的接口时在相应模块中补充
(检查: legacy/check_imports.py，以及在 PySide2 下运行界面测试)。
"""

import os

from PySide2 import __version__, __version_info__  # noqa: F401

LEGACY = True

# ssh -X / -Y 转发：X 服务器在本地，MIT-SHM 共享内存和 GLX 不能跨机器使用；Qt 5 有时检测不出来，
# 结果是窗口全黑或打印 GLX 错误。界面只用软件绘制，关掉它们没有损失。
if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
    os.environ.setdefault("QT_X11_NO_MITSHM", "1")
os.environ.setdefault("QT_XCB_GL_INTEGRATION", "none")
# 没有会话 D-Bus 时 (ssh 登录通常如此) Qt 会让 libdbus 自动启动一个，缺少 /etc/machine-id 时旧版 libdbus 直接
# 终止程序。界面不需要 D-Bus，给一个无效地址，连接失败后 Qt 照常运行。
os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", "disabled:")
# grasp_gui.fix_wsl_display 在 Wayland 下 (WSLg) 选 "wayland;xcb"；Qt 5 的 Wayland 支持依赖系统的 EGL，容易出错，
# 有 X11 (XWayland) 时改用 xcb。用户自己设置的 QT_QPA_PLATFORM 不变 (fix_wsl_display 不会改动它)。
if os.environ.get("QT_QPA_PLATFORM") == "wayland;xcb" and os.environ.get("DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "xcb"
