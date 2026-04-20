#!/usr/bin/env bash
# Build .AppImage and .deb for Cove PDF Kit.
#
# Requires:
#   - python (with PyInstaller installed via pip)
#   - ar, tar, xz (binutils + tar)
#   - curl (only if appimagetool isn't already on PATH)
#
# Output lands in release/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_NAME="cove-pdf-kit"
DISPLAY_NAME="Cove PDF Kit"
VERSION="${VERSION:-1.0.0}"
ARCH="x86_64"
DEB_ARCH="amd64"
RELEASE_DIR="$ROOT/release"
DIST_DIR="$ROOT/dist"
APPDIR="$ROOT/build/AppDir"
DEB_BUILD="$ROOT/build/deb"
ICON_SRC="$ROOT/src/cove_pdf_kit/assets/cove_icon.png"

LOCAL_BIN="${HOME}/.local/bin"
APPIMAGETOOL="${LOCAL_BIN}/appimagetool"

mkdir -p "$RELEASE_DIR" "$LOCAL_BIN"
rm -rf "$DIST_DIR" "$ROOT/build"
mkdir -p "$ROOT/build"

echo "==> Running PyInstaller"
python -m PyInstaller --noconfirm --clean packaging/cove-pdf-kit.spec

BUNDLE="$DIST_DIR/$APP_NAME"
[ -d "$BUNDLE" ] || { echo "PyInstaller bundle not found at $BUNDLE"; exit 1; }

echo "==> Assembling AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib/$APP_NAME" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -r "$BUNDLE"/. "$APPDIR/usr/lib/$APP_NAME/"
cp "$ICON_SRC" "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png"
cp "$ICON_SRC" "$APPDIR/$APP_NAME.png"
cp "$ICON_SRC" "$APPDIR/.DirIcon" 2>/dev/null || true

cat > "$APPDIR/$APP_NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$DISPLAY_NAME
GenericName=Offline PDF Toolkit
Comment=Merge, split, reorder, compress, and protect PDFs — fully offline
Exec=$APP_NAME
Icon=$APP_NAME
Terminal=false
Categories=Office;Utility;
Keywords=pdf;merge;split;compress;rotate;encrypt;password;
StartupNotify=true
EOF
cp "$APPDIR/$APP_NAME.desktop" "$APPDIR/usr/share/applications/$APP_NAME.desktop"

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="$HERE/usr/bin:$PATH"
export LD_LIBRARY_PATH="$HERE/usr/lib/cove-pdf-kit:${LD_LIBRARY_PATH:-}"
exec "$HERE/usr/lib/cove-pdf-kit/cove-pdf-kit" "$@"
EOF
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/usr/bin/$APP_NAME" <<'EOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${0}")")/../lib/cove-pdf-kit"
exec "$HERE/cove-pdf-kit" "$@"
EOF
chmod +x "$APPDIR/usr/bin/$APP_NAME"

if [ ! -x "$APPIMAGETOOL" ]; then
    if command -v appimagetool >/dev/null 2>&1; then
        APPIMAGETOOL="$(command -v appimagetool)"
    else
        echo "==> Downloading appimagetool to $APPIMAGETOOL"
        curl -fL --retry 3 -o "$APPIMAGETOOL" \
            "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
        chmod +x "$APPIMAGETOOL"
    fi
fi

echo "==> Building AppImage"
APPIMAGE_OUT="$RELEASE_DIR/${DISPLAY_NAME// /-}-${VERSION}-${ARCH}.AppImage"
ARCH=$ARCH "$APPIMAGETOOL" --no-appstream "$APPDIR" "$APPIMAGE_OUT"
chmod +x "$APPIMAGE_OUT"
echo "    -> $APPIMAGE_OUT"

echo "==> Assembling .deb tree"
PKG_ROOT="$DEB_BUILD/${APP_NAME}_${VERSION}_${DEB_ARCH}"
rm -rf "$DEB_BUILD"
mkdir -p "$PKG_ROOT/DEBIAN" \
         "$PKG_ROOT/usr/bin" \
         "$PKG_ROOT/usr/lib/$APP_NAME" \
         "$PKG_ROOT/usr/share/applications" \
         "$PKG_ROOT/usr/share/icons/hicolor/256x256/apps" \
         "$PKG_ROOT/usr/share/doc/$APP_NAME"

cp -r "$BUNDLE"/. "$PKG_ROOT/usr/lib/$APP_NAME/"
cp "$ICON_SRC" "$PKG_ROOT/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png"

cat > "$PKG_ROOT/usr/bin/$APP_NAME" <<'EOF'
#!/usr/bin/env bash
exec /usr/lib/cove-pdf-kit/cove-pdf-kit "$@"
EOF
chmod +x "$PKG_ROOT/usr/bin/$APP_NAME"

cat > "$PKG_ROOT/usr/share/applications/$APP_NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$DISPLAY_NAME
GenericName=Offline PDF Toolkit
Comment=Merge, split, reorder, compress, and protect PDFs — fully offline
Exec=$APP_NAME
Icon=$APP_NAME
Terminal=false
Categories=Office;Utility;
Keywords=pdf;merge;split;compress;rotate;encrypt;password;
StartupNotify=true
EOF

cp "$ROOT/LICENSE" "$PKG_ROOT/usr/share/doc/$APP_NAME/copyright"

INSTALLED_SIZE=$(du -sk "$PKG_ROOT/usr" | awk '{print $1}')

cat > "$PKG_ROOT/DEBIAN/control" <<EOF
Package: $APP_NAME
Version: $VERSION
Architecture: $DEB_ARCH
Maintainer: Cove <noreply@cove.local>
Installed-Size: $INSTALLED_SIZE
Section: utils
Priority: optional
Description: Offline PDF toolkit — organize, compress, and protect PDFs
 Cove PDF Kit is a focused desktop app for the most common PDF tasks:
 merge, split, reorder, rotate, and delete pages in a visual grid;
 compress files to shrink their size; add or remove passwords. No cloud,
 no templates, no account — everything runs locally on your machine.
EOF

echo "==> Building .deb archive"
DEB_OUT="$RELEASE_DIR/${APP_NAME}_${VERSION}_${DEB_ARCH}.deb"
WORK="$DEB_BUILD/work"
rm -rf "$WORK"
mkdir -p "$WORK"

(cd "$PKG_ROOT" && tar --xz --owner=0 --group=0 -cf "$WORK/control.tar.xz" -C DEBIAN .)
(cd "$PKG_ROOT" && tar --xz --owner=0 --group=0 -cf "$WORK/data.tar.xz" \
    --transform 's,^\./,,' \
    --exclude=./DEBIAN \
    .)
echo -n "2.0" > "$WORK/debian-binary"
echo "" >> "$WORK/debian-binary"

(cd "$WORK" && ar -rc "$DEB_OUT" debian-binary control.tar.xz data.tar.xz)

echo "    -> $DEB_OUT"

echo ""
echo "Release artifacts in $RELEASE_DIR:"
ls -lh "$RELEASE_DIR"
