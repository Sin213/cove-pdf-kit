"""Lucide-style stroke icons rendered via QSvgRenderer.

The design reference uses Lucide icons. We embed the relevant SVG paths
inline so we don't ship a font or extra assets.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


# 24×24 viewBox; stroke="currentColor" is replaced at render time.
_SVG_PATHS = {
    "organize": (
        '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 3v5h5"/>'
    ),
    "compress": (
        '<path d="M4 14h6v6"/>'
        '<path d="M20 10h-6V4"/>'
        '<path d="M14 10 21 3"/>'
        '<path d="M3 21l7-7"/>'
    ),
    "protect": (
        '<rect x="4" y="11" width="16" height="10" rx="2"/>'
        '<path d="M8 11V7a4 4 0 0 1 8 0v4"/>'
    ),
    "plus": (
        '<path d="M12 5v14M5 12h14"/>'
    ),
    "rotate_cw": (
        '<path d="M21 12a9 9 0 1 1-3-6.7"/>'
        '<path d="M21 4v5h-5"/>'
    ),
    "rotate_ccw": (
        '<path d="M3 12a9 9 0 1 0 3-6.7"/>'
        '<path d="M3 4v5h5"/>'
    ),
    "trash": (
        '<path d="M3 6h18"/>'
        '<path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
        '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>'
    ),
    "download": (
        '<path d="M12 3v13"/>'
        '<path d="m7 11 5 5 5-5"/>'
        '<path d="M5 21h14"/>'
    ),
    "eye": (
        '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "eye_off": (
        '<path d="m3 3 18 18"/>'
        '<path d="M10.6 10.6a3 3 0 0 0 4.2 4.2"/>'
        '<path d="M9.9 4.2A11 11 0 0 1 12 4c7 0 10 7 10 7a13.7 13.7 0 0 1-2.4 3.4"/>'
        '<path d="M6.6 6.6A13.7 13.7 0 0 0 2 11s3 7 10 7c2 0 3.7-.6 5.1-1.4"/>'
    ),
    "upload": (
        '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
    ),
    "drop_doc": (
        '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 3v5h5"/>'
        '<path d="M12 18v-6"/>'
        '<path d="m9 15 3-3 3 3"/>'
    ),
    "x": (
        '<path d="M18 6 6 18M6 6l12 12"/>'
    ),
    "check": (
        '<path d="M20 6 9 17l-5-5"/>'
    ),
    "pdf_doc": (
        '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 3v5h5"/>'
        '<path d="M9 14h6M9 17h4"/>'
    ),
}


def _svg(paths: str, color: str, stroke: float) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        f' fill="none" stroke="{color}" stroke-width="{stroke}"'
        f' stroke-linecap="round" stroke-linejoin="round">{paths}</svg>'
    )


def make_pixmap(name: str, size: int = 16, color: str = "#9a9aae",
                stroke: float = 1.8, dpr: float = 1.0) -> QPixmap:
    paths = _SVG_PATHS.get(name)
    if paths is None:
        return QPixmap()
    svg = _svg(paths, color, stroke)
    renderer = QSvgRenderer(svg.encode("utf-8"))
    actual = max(1, int(round(size * dpr)))
    pix = QPixmap(actual, actual)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(p)
    p.end()
    pix.setDevicePixelRatio(dpr)
    return pix


def make_icon(name: str, size: int = 16, color: str = "#9a9aae",
              stroke: float = 1.8) -> QIcon:
    return QIcon(make_pixmap(name, size, color, stroke))
