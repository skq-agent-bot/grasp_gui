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

# Fonts bundled into the executable, so that machines without (Chinese) fonts can display the GUI:
# Noto Sans CJK (SIL Open Font License) and DejaVu Sans / Sans Mono (free licence), taken from this
# machine via fontconfig (Debian/Ubuntu: apt install fonts-noto-cjk fonts-dejavu-core), with their
# licence files.
FONTS=build/fonts
rm -rf "$FONTS"
mkdir -p "$FONTS"
for pattern in "Noto Sans CJK SC:style=Regular" "DejaVu Sans:style=Book" "DejaVu Sans:style=Bold" \
               "DejaVu Sans Mono:style=Book" "DejaVu Sans Mono:style=Bold"; do
    file=$(fc-match -f '%{file}' "$pattern" 2>/dev/null || true)
    family=${pattern%%:*}
    if [ -f "$file" ] && fc-scan -f '%{family}\n' "$file" 2>/dev/null | tr ',' '\n' | grep -qx "$family"; then
        cp "$file" "$FONTS/"
    else
        echo "warning: font '$pattern' not found; it will not be bundled" >&2
    fi
done
for doc in fonts-noto-cjk fonts-dejavu-core; do
    [ -f "/usr/share/doc/$doc/copyright" ] && cp "/usr/share/doc/$doc/copyright" "$FONTS/LICENSE-$doc"
done

# __future__ is imported by shiboken's signature bootstrap, which PyInstaller does not detect
"$ENV/bin/pyinstaller" --noconfirm --clean --log-level WARN "$MODE" --name grasp_gui \
    --distpath dist --workpath build/pyinstaller --specpath build \
    --hidden-import __future__ \
    --add-data "$PWD/$FONTS:fonts" \
    --add-data "$PWD/demos/*.json:demos" \
    grasp_gui.py

echo
echo "Built: $(ls -d dist/grasp_gui)"
