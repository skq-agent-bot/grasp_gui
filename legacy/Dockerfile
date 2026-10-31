# Build of the legacy executable (see legacy/README.md): CentOS 7 base (glibc 2.17), Qt 5.15 (PySide2) and Python 3.10.
# Used by legacy/build.sh, which supplies the source tree and the fonts as the build context.
FROM quay.io/pypa/manylinux2014_x86_64 AS build

# Libraries of Qt 5's xcb platform plugin that a bare X11 server (ssh -X) may lack; PyInstaller bundles them.
# libglvnd-glx: Qt 5's QtGui links libGL.so.1, which servers often lack; see below.
RUN yum install -y -q libxkbcommon-x11 xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil \
        libXrender fontconfig freetype libglvnd-glx && yum clean all

# PyInstaller needs a Python with a shared libpython; the manylinux Pythons are static. python-build-standalone
# targets glibc 2.17. PySide2 5.15 supports Python <= 3.10.
ARG PY_URL=https://github.com/astral-sh/python-build-standalone/releases/download/20261009/cpython-3.10.22%2B20261009-x86_64-unknown-linux-gnu-install_only.tar.gz
ARG PY_SHA256=1780de9ddda04e956d2a4a0ad09b7f5667d92f4f12cd0881ec939de5d542903f
RUN curl -sSfL "$PY_URL" -o /tmp/python.tar.gz \
    && echo "$PY_SHA256  /tmp/python.tar.gz" | sha256sum -c - \
    && mkdir /opt/pbs && tar xzf /tmp/python.tar.gz -C /opt/pbs && rm /tmp/python.tar.gz
ENV PATH=/opt/pbs/python/bin:$PATH
RUN python3 -m pip install -q --no-cache-dir "PySide2==5.15.2.1" "pyinstaller==6.22.3"

COPY . /src
WORKDIR /src
# The PySide6 stand-in (legacy/PySide6) is bundled as source files next to the program, found on sys.path at run time;
# PyInstaller analyses PySide2 directly (hidden imports), so that its PySide2 hooks collect the Qt 5 libraries and plugins.
# PyInstaller never bundles libGL (it belongs to the graphics driver); the GUI does not use OpenGL (QT_XCB_GL_INTEGRATION
# is none), so libGL only has to be loadable: the driver-independent glvnd dispatch library is bundled.
# libxcb is not bundled by PyInstaller either; with it (libX11 and the other X libraries are bundled) the program
# needs nothing but glibc.
RUN pyinstaller --noconfirm --clean --log-level WARN --onefile --name grasp_gui \
        --distpath dist --workpath build/pyinstaller --specpath build \
        --hidden-import __future__ \
        --hidden-import PySide2.QtCore --hidden-import PySide2.QtGui \
        --hidden-import PySide2.QtWidgets --hidden-import PySide2.QtSvg \
        --exclude-module PySide6 \
        --add-binary "/usr/lib64/libGL.so.1:." --add-binary "/usr/lib64/libGLX.so.0:." \
        --add-binary "/usr/lib64/libGLdispatch.so.0:." --add-binary "/usr/lib64/libxcb.so.1:." \
        --add-data "/src/legacy/PySide6:PySide6" \
        --add-data "/src/build/fonts:fonts" \
        --add-data "/src/demos/*.json:demos" \
        grasp_gui.py

FROM scratch
COPY --from=build /src/dist/grasp_gui /grasp_gui
