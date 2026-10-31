# Legacy build for old servers / 旧系统版

`grasp_gui-legacy` is the same program as `grasp_gui`, built for old Linux systems and for use over `ssh -X`:

* runs on **glibc ≥ 2.17**: CentOS / RHEL 7, Rocky / RHEL 8, Ubuntu 18.04, Debian 9 and newer
  (the normal build needs glibc ≥ 2.35, i.e. Ubuntu 22.04, Debian 12, RHEL 10);
* **X11 forwarding**: start it on the server where the (large) result files are, the window appears on your computer.
  Besides glibc it needs nothing on the server: Qt, the X11 libraries, fonts and Python are inside the executable
  (X11 forwarding itself needs `xauth` on the server).

It uses Qt 5.15 (PySide2) instead of Qt 6: PySide6 is built for glibc ≥ 2.28 in all versions. Use the normal build on
your own desktop computer; the legacy build is for servers.

`grasp_gui-legacy` 与 `grasp_gui` 是同一个程序，为旧的 Linux 系统和 `ssh -X` 远程显示构建：

* 支持 **glibc ≥ 2.17**：CentOS / RHEL 7、Rocky / RHEL 8、Ubuntu 18.04、Debian 9 及更新的系统 (普通版需要 glibc ≥ 2.35)；
* **X11 转发**：在存放 (很大的) 计算结果的服务器上运行，窗口显示在自己的电脑上。除 glibc 外服务器上不需要任何库：
  Qt、X11 库、字体和 Python 都在可执行文件中 (X11 转发本身需要服务器上有 `xauth`)。

它用 Qt 5.15 (PySide2) 而不是 Qt 6 (PySide6 的所有版本都要求 glibc ≥ 2.28)。自己的桌面电脑请用普通版，旧系统版用于服务器。

## Use / 使用

```bash
ssh -X user@server            # -Y if the server refuses -X; add -C on slow connections
./grasp_gui-legacy            # or: ./grasp_gui-legacy levels ~/calc/run1
```

* Windows: use an SSH client with an X server, e.g. MobaXterm, or WSL (Windows 11). macOS: install XQuartz.
* `Cannot open a window: no display`: X11 forwarding is off. `echo $DISPLAY` on the server should print something
  like `localhost:10.0`; otherwise the server needs `X11Forwarding yes` in `/etc/ssh/sshd_config` and `xauth`.
* Over a slow connection the window reacts with a delay; the level diagram and wave function plots are drawn on the
  server, only the picture is transferred, so file size does not matter.

* Windows 上使用带 X 服务器的 SSH 客户端 (如 MobaXterm) 或 WSL (Windows 11)；macOS 需安装 XQuartz。
* 提示“无法打开窗口：没有显示设备”：X11 转发没有打开。在服务器上 `echo $DISPLAY` 应显示 `localhost:10.0` 之类；
  否则服务器需在 `/etc/ssh/sshd_config` 中设置 `X11Forwarding yes` 并安装 `xauth`。
* 网络慢时界面反应有延迟；能级图和波函数图在服务器上绘制，只传输画面，与结果文件的大小无关。

## Branch and build / 分支与构建

The branch `legacy` is `main` plus the directory `legacy/` (nothing else is changed), so `git merge main` never
conflicts. The program code stays written for PySide6; `legacy/PySide6/` is a stand-in package that maps the Qt 6
names used by the GUI to PySide2 and is bundled only into this build. Releases ship both executables.

分支 `legacy` = `main` + `legacy/` 目录 (其他文件不改)，合并 main 不会冲突。程序代码仍按 PySide6 编写；
`legacy/PySide6/` 是一个替身包，把界面用到的 Qt 6 写法对应到 PySide2，只打包进旧系统版。发布时两个可执行文件一起发布。

```bash
git checkout legacy && git merge main
python3 legacy/check_imports.py     # with PySide2 installed (Python <= 3.10): every imported Qt name exists
legacy/build.sh                     # -> dist/grasp_gui-legacy (Docker; DOCKER=docker.exe from WSL)
```

The build runs in a CentOS 7 container (`legacy/Dockerfile`: manylinux2014, python-build-standalone 3.10, PySide2
5.15.2.1, PyInstaller), so the executable only needs glibc 2.17. When `check_imports.py` reports a missing name, or a
GUI test fails on PySide2 (`PYTHONPATH=legacy python3 <test>`), add the Qt 6 spelling to the module in `legacy/PySide6/`.

What the stand-in adds (Qt 6 behaviour on Qt 5): `exec()`, `QAction` / `QActionGroup` / `QShortcut` in QtGui,
`event.position()` / `globalPosition()`, static `QFontDatabase.families()`, `QPdfWriter.setPageSize(QPageSize)`,
`enum.value` for `QPalette.ColorRole`, high-DPI scaling, bold tab labels sized correctly, a clear message instead of
Qt 5's abort when there is no display. Environment: no MIT-SHM over ssh, no OpenGL, no session D-Bus (old libdbus
aborts without `/etc/machine-id`), xcb instead of Wayland. Bundled besides what PyInstaller collects: `libxcb` and the
glvnd `libGL` (loadable only; OpenGL is not used).

Test without old hardware: run the executable in `centos:7`, `debian:9`, `ubuntu:18.04`, `rockylinux:8` containers
with `DISPLAY` pointing to an Xvfb container on the same Docker network, and log in with `ssh -X` from the Xvfb
container into a `centos:7` container running sshd.
