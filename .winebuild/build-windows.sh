#!/bin/bash
# Cross-compile Windows binaries from Linux using Docker.
#
# Mirrors the cove-gif-maker .winebuild/build-windows.sh pattern. Two
# containers, two stages:
#   1. tobix/pywine:3.12 — PyInstaller builds (onedir + onefile) under wine
#   2. amake/innosetup   — Inno Setup compiler (ISCC) for Setup.exe
#
# Run from the HOST (not inside a container):
#   bash .winebuild/build-windows.sh
#   VERSION=2.0.0 bash .winebuild/build-windows.sh   # explicit override
#
# Or run an inner stage directly inside its respective container (see the
# stage_pyinstaller / stage_innosetup branches below).
set -euo pipefail

APP="cove-pdf-kit"
DISPLAY="Cove-PDF-Kit"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Single source of truth: pyproject.toml (matches build.ps1 / build-release.sh).
if [ -z "${VERSION:-}" ]; then
    if [ -f "$ROOT/pyproject.toml" ]; then
        VERSION="$(awk -F'"' '/^version[[:space:]]*=/ { print $2; exit }' "$ROOT/pyproject.toml")"
    fi
fi
if [ -z "${VERSION:-}" ]; then
    echo "build-windows.sh: cannot determine VERSION (set VERSION=… or repair pyproject.toml)" >&2
    exit 2
fi

# ------------------------------------------------------------------
# Stage 1: PyInstaller (inside tobix/pywine:3.12)
# ------------------------------------------------------------------
if [ "${_STAGE:-}" = "pyinstaller" ]; then
    SRC="/src"
    WORK="/work"
    mkdir -p "$WORK"
    cd "$SRC"

    echo "==> Installing build deps into wine-Python"
    wine pip install --quiet --no-warn-script-location \
      PySide6 Pillow pypdf pikepdf pypdfium2 pyinstaller

    echo "==> Locating extracted Ghostscript tree"
    # The host orchestrator (below) downloads the Ghostscript Inno
    # installer once and 7z-extracts it into .winebuild/gs-cache. Wine's
    # silent-install path is unreliable inside the tobix/pywine container
    # (the installer exits cleanly but lays nothing down), so we keep the
    # extraction outside Docker and just point PyInstaller at the result.
    GS_EXTRACTED="/src/.winebuild/gs-cache/extracted"
    GS_BIN_EXE="$GS_EXTRACTED/bin/gswin64c.exe"
    if [ ! -f "$GS_BIN_EXE" ]; then
        echo "Ghostscript not extracted at $GS_BIN_EXE — host orchestrator should have done this." >&2
        exit 1
    fi
    echo "    -> $(ls -lh "$GS_BIN_EXE" | awk '{print $5, $9}')"

    GS_BIN_W="$(wine winepath -w "$GS_EXTRACTED/bin" 2>/dev/null | tr -d '\r')"
    GS_LIB_W="$(wine winepath -w "$GS_EXTRACTED/lib" 2>/dev/null | tr -d '\r')"
    GS_RES_W="$(wine winepath -w "$GS_EXTRACTED/Resource" 2>/dev/null | tr -d '\r')"
    GS_ICC_W="$(wine winepath -w "$GS_EXTRACTED/iccprofiles" 2>/dev/null | tr -d '\r')"
    GS_PREFIX_L="$GS_EXTRACTED"

    echo "==> Generating cove_icon.ico from PNG"
    wine python - <<'PY'
from PIL import Image
Image.open(r"Z:\src\cove_icon.png").save(
    r"Z:\src\cove_icon.ico",
    sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)],
)
PY
    test -f "$SRC/cove_icon.ico" || { echo "icon generation failed"; exit 1; }

    echo "==> Cleaning previous build artifacts"
    rm -rf "$SRC/build" "$SRC/dist"
    find "$SRC" -maxdepth 1 -name '*.spec' -delete

    PORTABLE_NAME="${APP}-portable"
    SEP=";"

    PYSIDE_DIR_W=$(wine python -c \
      "import PySide6, os; print(os.path.dirname(PySide6.__file__))" \
      2>/dev/null | tr -d '\r')
    PYSIDE_DIR=$(wine winepath -u "$PYSIDE_DIR_W" 2>/dev/null | tr -d '\r')
    [ -d "$PYSIDE_DIR" ] || { echo "PySide6 install not found at $PYSIDE_DIR"; exit 1; }
    echo "==> PySide6 dir (Linux view): $PYSIDE_DIR"

    PLUGIN_BASE=""
    for cand in "$PYSIDE_DIR/plugins" "$PYSIDE_DIR/Qt6/plugins" "$PYSIDE_DIR/Qt/plugins"; do
        if [ -d "$cand/platforms" ]; then PLUGIN_BASE="$cand"; break; fi
    done
    [ -n "$PLUGIN_BASE" ] || { echo "Qt platforms dir not located"; exit 1; }
    echo "==> Qt plugins dir: $PLUGIN_BASE"

    # Cove PDF Kit needs platforms / imageformats / styles / iconengines.
    # SVG is also needed because icons.py renders Lucide-style glyphs via
    # QSvgRenderer at runtime.
    PLUGIN_DIRS=(platforms imageformats styles iconengines tls)
    PLUGIN_ARGS=()
    for d in "${PLUGIN_DIRS[@]}"; do
        src="$PLUGIN_BASE/$d"
        if [ -d "$src" ]; then
            wpath=$(wine winepath -w "$src" 2>/dev/null | tr -d '\r')
            PLUGIN_ARGS+=(--add-data "${wpath}${SEP}PySide6\\plugins\\$d")
            echo "    + plugins/$d"
        fi
    done

    # Ghostscript layout inside the bundle:
    #   gs/bin/gswin64c.exe      ← PDF compression backend
    #   gs/bin/gsdll64.dll       ← required by gswin64c.exe
    #   gs/lib/                   ← PostScript libraries
    #   gs/Resource/              ← PostScript resources
    #   gs/iccprofiles/           ← ICC color profiles
    #   gs/LICENSE                ← AGPL — required for redistribution
    GS_LICENSE_W=""
    if [ -f "$GS_PREFIX_L/LICENSE" ]; then
        GS_LICENSE_W="$(wine winepath -w "$GS_PREFIX_L/LICENSE" 2>/dev/null | tr -d '\r')"
    fi

    COMMON_PYINSTALLER_ARGS=(
      --noconfirm --clean --log-level WARN
      --windowed
      --icon "Z:\\src\\cove_icon.ico"
      --paths "Z:\\src\\src"
      --add-data "Z:\\src\\src\\cove_pdf_kit\\assets\\cove_icon.png${SEP}cove_pdf_kit\\assets"
      --hidden-import PySide6.QtSvg
      --hidden-import pikepdf._core
      # pypdfium2 ships its native pdfium.dll inside pypdfium2_raw/ along
      # with a version.json that the Python loader reads. --hidden-import
      # only carries the Python modules, so without --collect-all the
      # frozen app crashes at startup with
      # "ImportError: Could not find library 'pdfium'". Collect both
      # packages: pypdfium2 (high-level API) and pypdfium2_raw (binary +
      # ctypes bindings).
      --collect-all pypdfium2
      --collect-all pypdfium2_raw
      --exclude-module PySide6.QtWebEngineCore
      --exclude-module PySide6.QtWebEngineWidgets
      --exclude-module PySide6.QtQml
      --exclude-module PySide6.QtQuick
      --exclude-module PySide6.QtPdf
      --exclude-module PySide6.Qt3DCore
      --exclude-module PySide6.QtCharts
      --exclude-module PySide6.QtDataVisualization
      --exclude-module PySide6.QtMultimedia
      --exclude-module PySide6.QtMultimediaWidgets
      --exclude-module tkinter
      "${PLUGIN_ARGS[@]}"
      --add-binary "${GS_BIN_W}\\gswin64c.exe${SEP}gs\\bin"
      --add-binary "${GS_BIN_W}\\gsdll64.dll${SEP}gs\\bin"
      --add-data "${GS_LIB_W}${SEP}gs\\lib"
      --add-data "${GS_RES_W}${SEP}gs\\Resource"
      --add-data "${GS_ICC_W}${SEP}gs\\iccprofiles"
    )
    if [ -n "$GS_LICENSE_W" ]; then
        COMMON_PYINSTALLER_ARGS+=(--add-data "${GS_LICENSE_W}${SEP}gs")
    fi

    echo "==> Running PyInstaller (onedir, windowed)"
    wine pyinstaller \
      "${COMMON_PYINSTALLER_ARGS[@]}" \
      --name "$APP" \
      "Z:\\src\\packaging\\launcher.py"

    ONEDIR_BUNDLE="$SRC/dist/$APP"
    test -d "$ONEDIR_BUNDLE" || { echo "PyInstaller onedir bundle not found at $ONEDIR_BUNDLE"; exit 1; }

    cp -f "$SRC/LICENSE"  "$ONEDIR_BUNDLE/" 2>/dev/null || true
    cp -f "$SRC/README.md" "$ONEDIR_BUNDLE/" 2>/dev/null || true

    echo "==> Running PyInstaller (onefile, windowed)"
    wine pyinstaller \
      "${COMMON_PYINSTALLER_ARGS[@]}" \
      --onefile \
      --name "$PORTABLE_NAME" \
      "Z:\\src\\packaging\\launcher.py"

    mkdir -p "$SRC/release"
    SRC_EXE="$SRC/dist/${PORTABLE_NAME}.exe"
    test -f "$SRC_EXE" || { echo "PyInstaller did not produce $SRC_EXE"; exit 1; }
    PORTABLE_DEST="$SRC/release/${DISPLAY}-${VERSION}-Portable.exe"
    cp -f "$SRC_EXE" "$PORTABLE_DEST"
    ( cd "$SRC/release" && sha256sum "$(basename "$PORTABLE_DEST")" > "$(basename "$PORTABLE_DEST").sha256" )

    echo "==> PyInstaller stage done"
    ls -lh "$PORTABLE_DEST" "$PORTABLE_DEST.sha256"
    ls -lh "$ONEDIR_BUNDLE/" | head -20
    exit 0
fi

# ------------------------------------------------------------------
# Stage 2: Inno Setup (inside amake/innosetup)
# ------------------------------------------------------------------
if [ "${_STAGE:-}" = "innosetup" ]; then
    echo "==> Building Setup.exe via Inno Setup"
    ISCC_PATH="$(winepath -u "$(wine cmd /c 'echo %PROGRAMFILES%' 2>/dev/null | tr -d '\r')" 2>/dev/null)/Inno Setup 6/ISCC.exe"
    wine "$ISCC_PATH" \
      "/DAppVersion=$VERSION" \
      "/DSourceDir=Z:\src\dist\\$APP" \
      "/DOutputDir=Z:\src\release" \
      "/DIconFile=Z:\src\cove_icon.ico" \
      "Z:\src\packaging\installer.iss"

    # installer.iss writes "<app>-<version>-Setup.exe"; rename to the
    # canonical "Cove-PDF-Kit-<version>-Setup.exe" to match the AppImage
    # naming style used elsewhere in this repo.
    SETUP_DEST="/src/release/${DISPLAY}-${VERSION}-Setup.exe"
    SETUP_ISS_OUT="/src/release/${APP}-${VERSION}-Setup.exe"
    if [ -f "$SETUP_ISS_OUT" ] && [ "$SETUP_ISS_OUT" != "$SETUP_DEST" ]; then
        mv -f "$SETUP_ISS_OUT" "$SETUP_DEST"
    fi
    test -f "$SETUP_DEST" || { echo "Inno Setup did not produce Setup.exe"; ls -la /src/release/; exit 1; }

    ( cd /src/release && sha256sum "$(basename "$SETUP_DEST")" > "$(basename "$SETUP_DEST").sha256" )
    echo "==> Inno Setup stage done"
    ls -lh "$SETUP_DEST" "$SETUP_DEST.sha256"
    exit 0
fi

# ------------------------------------------------------------------
# Host orchestrator: run both stages via Docker
# ------------------------------------------------------------------
cd "$ROOT"

echo "============================================="
echo "  Cove PDF Kit — Windows cross-compile"
echo "  Version: $VERSION"
echo "============================================="

# Make sure the project-root cove_icon.png exists (the wine stage reads
# it directly to mint the .ico).
if [ ! -f "$ROOT/cove_icon.png" ]; then
    cp "$ROOT/src/cove_pdf_kit/assets/cove_icon.png" "$ROOT/cove_icon.png"
fi

# ------------------------------------------------------------------
# Pre-stage: download + 7z-extract Ghostscript on the host.
#
# The Inno-installer silent path inside tobix/pywine swallows /DIR=
# silently (installer reports rc=0 but never actually drops files), so
# we extract the archive outside Docker — 7z understands Inno installer
# layouts natively — and bind-mount the result into the container.
# ------------------------------------------------------------------
GS_RELEASE_TAG="gs10070"
GS_INSTALLER_NAME="${GS_RELEASE_TAG}w64.exe"
GS_INSTALLER_URL="https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/${GS_RELEASE_TAG}/${GS_INSTALLER_NAME}"
GS_CACHE="$ROOT/.winebuild/gs-cache"
GS_INSTALLER="$GS_CACHE/${GS_INSTALLER_NAME}"
GS_EXTRACTED="$GS_CACHE/extracted"

if [ ! -f "$GS_EXTRACTED/bin/gswin64c.exe" ]; then
    echo ""
    echo "=== Pre-stage: fetch + extract Ghostscript ($GS_RELEASE_TAG) ==="
    mkdir -p "$GS_CACHE"
    if [ ! -f "$GS_INSTALLER" ]; then
        echo "    downloading $GS_INSTALLER_NAME"
        curl -fLo "$GS_INSTALLER" "$GS_INSTALLER_URL"
    fi
    if ! command -v 7z >/dev/null 2>&1; then
        echo "build-windows.sh: 7z is required to extract the Ghostscript installer." >&2
        echo "                  install p7zip / 7zip and re-run." >&2
        exit 2
    fi
    rm -rf "$GS_EXTRACTED"
    mkdir -p "$GS_EXTRACTED"
    7z x -bso0 -bsp0 -y "$GS_INSTALLER" -o"$GS_EXTRACTED" >/dev/null
    test -f "$GS_EXTRACTED/bin/gswin64c.exe" || {
        echo "build-windows.sh: extracted tree is missing bin/gswin64c.exe" >&2
        exit 2
    }
    # The Inno installer drops a $PLUGINSDIR full of installer-only
    # helpers — useless to us and ~1MB. Drop it from the bundled tree.
    rm -rf "$GS_EXTRACTED/\$PLUGINSDIR" "$GS_EXTRACTED/\$_PLUGINSDIR" 2>/dev/null || true
    echo "    extracted -> $GS_EXTRACTED"
fi

# Clean any root-owned leftovers from previous Docker runs.
if [ -d build ] || [ -d dist ]; then
    echo "==> Cleaning previous build artifacts"
    docker run --rm -v "$ROOT:/src" tobix/pywine:3.12 \
      rm -rf /src/build /src/dist
fi

echo ""
echo "=== Stage 1/2: PyInstaller (tobix/pywine:3.12) ==="
docker run --rm \
  -v "$ROOT:/src" \
  -e VERSION="$VERSION" \
  -e _STAGE=pyinstaller \
  tobix/pywine:3.12 \
  bash /src/.winebuild/build-windows.sh

echo ""
echo "=== Stage 2/2: Inno Setup (amake/innosetup) ==="
docker run --rm \
  -v "$ROOT:/src" \
  -e VERSION="$VERSION" \
  -e APP="$APP" \
  -e _STAGE=innosetup \
  --entrypoint bash \
  amake/innosetup \
  /src/.winebuild/build-windows.sh

echo ""
echo "==> Resetting host ownership on Docker-written paths"
# tobix/pywine and amake/innosetup both write as root inside the container.
# Map the files back to the host user so subsequent rm/git operations don't
# need sudo.
docker run --rm -v "$ROOT:/src" tobix/pywine:3.12 \
  chown -R "$(id -u):$(id -g)" /src/release /src/build /src/dist 2>/dev/null || true

echo ""
echo "==> All Windows artifacts:"
ls -lh "$ROOT/release/"*"$VERSION"*exe* 2>/dev/null || echo "(none found)"
