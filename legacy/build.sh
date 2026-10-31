#!/bin/bash
# Build the legacy executable for old Linux systems (glibc >= 2.17, e.g. CentOS 7) in a container:
#
#   legacy/build.sh       -> dist/grasp_gui-legacy
#
# Needs Docker (DOCKER=... selects the client, e.g. docker.exe of Docker Desktop from WSL). The program is the same
# as the normal build (build.sh), but runs on Qt 5.15 (PySide2) through the stand-in package legacy/PySide6.
set -e
cd "$(dirname "$0")/.."
DOCKER=${DOCKER:-docker}

# Fonts bundled into the executable, taken from this machine as in build.sh
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

# Build context: the source files (tracked or new, not ignored, as they are in the working tree) and the fonts;
# the result comes back as a tar stream.
mkdir -p dist
{ git ls-files -z --cached --others --exclude-standard; find "$FONTS" -type f -print0; } \
    | tar --null -T - -c \
    | "$DOCKER" build -f legacy/Dockerfile -o - - \
    | tar -x -O grasp_gui > dist/grasp_gui-legacy
chmod +x dist/grasp_gui-legacy

echo
echo "Built: dist/grasp_gui-legacy"
