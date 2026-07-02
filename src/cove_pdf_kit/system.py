"""Cross-platform OS integration helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def child_env() -> dict | None:
    """Scrubbed env for spawning external programs from inside an AppImage.

    The AppImage runtime exports LD_LIBRARY_PATH pointing at the bundle's
    libraries; children like xdg-open and whatever it launches (dolphin,
    a browser) inherit it, load the bundle's outdated libs, and crash on
    startup. Returns None outside an AppImage ("inherit unchanged").
    """
    if not (os.environ.get("APPDIR") or os.environ.get("APPIMAGE")):
        return None
    env = os.environ.copy()
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH",
                "QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        env.pop(key, None)
    return env


def reveal_in_file_manager(path: Path) -> bool:
    """Open the OS file manager and (where supported) highlight ``path``.

    Returns True if a reveal command was launched.
    """
    p = Path(path)
    if not p.exists():
        # Fall back to the parent directory if the exact file is gone.
        p = p.parent if p.parent.exists() else p

    target = p
    try:
        if sys.platform.startswith("win"):
            # explorer /select highlights the file in its parent folder.
            if p.is_file():
                subprocess.Popen(["explorer", "/select,", str(p)])
            else:
                subprocess.Popen(["explorer", str(p)])
            return True
        if sys.platform == "darwin":
            if p.is_file():
                subprocess.Popen(["open", "-R", str(p)])
            else:
                subprocess.Popen(["open", str(p)])
            return True
        # Linux / BSD: try DBus FileManager1 first (highlights the file in
        # nautilus / nemo / dolphin), fall back to xdg-open on the parent.
        if p.is_file() and _try_dbus_show_items(p):
            return True
        target = p if p.is_dir() else p.parent
        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", str(target)], env=child_env())
            return True
        # Last-resort: let Qt try.
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
    except Exception:  # noqa: BLE001
        try:
            return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        except Exception:  # noqa: BLE001
            return False


def _try_dbus_show_items(path: Path) -> bool:
    """Use the FileManager1 DBus interface to highlight a file.

    Most Linux file managers (Nautilus, Nemo, Dolphin) implement it.
    """
    if not shutil.which("dbus-send"):
        return False
    uri = QUrl.fromLocalFile(str(path)).toString()
    cmd = [
        "dbus-send", "--session", "--print-reply",
        "--dest=org.freedesktop.FileManager1",
        "/org/freedesktop/FileManager1",
        "org.freedesktop.FileManager1.ShowItems",
        f"array:string:{uri}",
        "string:",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=2)
        return result.returncode == 0
    except Exception:  # noqa: BLE001
        return False
