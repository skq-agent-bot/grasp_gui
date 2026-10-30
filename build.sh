#!/bin/bash
# Build a standalone executable of the GRASP GUI with PyInstaller; it runs
# without Python or PySide6 installed.
#
#   ./build.sh            -> dist/grasp_gui    single file
#   ./build.sh --onedir   -> dist/grasp_gui/   folder (starts faster: no unpacking on each start)
#
# The build environment is created in build/venv (or $GRASP_BUILD_ENV) on first use.
set -e
cd "$(dirname "$0")"

ENV=${GRASP_BUILD_ENV:-build/venv}
if [ ! -x "$ENV/bin/pyinstaller" ]; then
    python3 -m venv "$ENV"
    # only the essential Qt modules: keeps the executable much smaller than the full PySide6
    "$ENV/bin/pip" install -q "pyside6-essentials>=6.5" "pyinstaller>=6"
fi

MODE=--onefile
[ "$1" = "--onedir" ] && MODE=--onedir

# __future__ is imported by shiboken's signature bootstrap, which PyInstaller does not detect
"$ENV/bin/pyinstaller" --noconfirm --clean --log-level WARN "$MODE" --name grasp_gui \
    --distpath dist --workpath build/pyinstaller --specpath build \
    --hidden-import __future__ \
    grasp_gui.py

echo
echo "Built: $(ls -d dist/grasp_gui)"
