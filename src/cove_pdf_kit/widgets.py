"""Shared cove-style widgets used by the three tool views."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .icons import make_pixmap


class DropZone(QWidget):
    """Dashed-border drop area used as the empty-state for every tool.

    Emits :py:meth:`filesDropped` with absolute paths when the user drops
    files; emits :py:meth:`clicked` when they click on the zone (e.g. to
    open a file picker).
    """

    filesDropped = Signal(list)
    clicked = Signal()

    def __init__(self, *, glyph: str, headline: str, body: str,
                 cta_label: str = "Choose files",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._glyph = glyph
        self._drag_active = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(14)
        layout.addStretch(1)

        # Centered glyph label.
        self._glyph_lbl = QLabel()
        self._glyph_lbl.setAlignment(Qt.AlignCenter)
        self._glyph_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self._glyph_lbl, alignment=Qt.AlignHCenter)

        self._head_lbl = QLabel(headline)
        self._head_lbl.setAlignment(Qt.AlignCenter)
        self._head_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._head_lbl.setStyleSheet(
            f"color: {theme.TEXT}; font-size: 14.5px; font-weight: 500;"
            f" background: transparent;"
        )
        layout.addWidget(self._head_lbl)

        sub = QLabel(body)
        sub.setAlignment(Qt.AlignCenter)
        sub.setAttribute(Qt.WA_TransparentForMouseEvents)
        sub.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 12.5px;"
            f" background: transparent;"
        )
        layout.addWidget(sub)

        sep = QLabel("— or —")
        sep.setAlignment(Qt.AlignCenter)
        sep.setAttribute(Qt.WA_TransparentForMouseEvents)
        sep.setStyleSheet(
            f"color: {theme.TEXT_FAINT};"
            f" font-family: '{theme.FONT_MONO}', monospace;"
            f" font-size: 10.5px; letter-spacing: 0.1em;"
            f" background: transparent;"
        )
        layout.addWidget(sep)

        cta = QPushButton(f"  {cta_label}")
        cta.setIcon(_icon("upload"))
        cta.setCursor(Qt.PointingHandCursor)
        cta.setFixedHeight(28)
        cta.setStyleSheet(
            f"QPushButton {{"
            f" background: {theme.SURFACE}; color: {theme.TEXT_DIM};"
            f" border: 1px solid {theme.BORDER}; border-radius: 7px;"
            f" padding: 0 12px; font-size: 11.5px;"
            f"}}"
            f"QPushButton:hover {{"
            f" color: {theme.TEXT}; background: {theme.SURFACE_2};"
            f" border-color: {theme.BORDER_HARD};"
            f"}}"
        )
        cta.clicked.connect(self.clicked.emit)
        cta_wrap = QWidget()
        cta_wrap_layout = QHBoxLayout(cta_wrap)
        cta_wrap_layout.setContentsMargins(0, 0, 0, 0)
        cta_wrap_layout.setSpacing(0)
        cta_wrap_layout.addStretch(1)
        cta_wrap_layout.addWidget(cta)
        cta_wrap_layout.addStretch(1)
        layout.addWidget(cta_wrap)
        layout.addStretch(1)

        self._render_glyph()

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        self._render_glyph()

    def set_headline(self, text: str) -> None:
        self._head_lbl.setText(text)

    def _render_glyph(self) -> None:
        dpr = self.devicePixelRatioF() or 1.0
        color = theme.ACCENT if self._drag_active else theme.TEXT_DIM
        pix = make_pixmap(self._glyph, 44, color, 1.4, dpr)
        self._glyph_lbl.setPixmap(pix)

    # ----- Painting (dashed grid background) -----------------------------

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # Background fill: solid #08080d.
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#08080d"))
        p.drawRoundedRect(rect, 12, 12)

        # Grid pattern.
        grid = QColor(255, 255, 255, 5)
        p.setPen(QPen(grid, 1))
        cell = 24
        # Use a clip path so grid lines don't escape the rounded corners.
        clip = QPainterPath()
        clip.addRoundedRect(rect, 12, 12)
        p.setClipPath(clip)
        for y in range(0, int(rect.height()), cell):
            p.drawLine(QPointF(rect.left(), rect.top() + y),
                       QPointF(rect.right(), rect.top() + y))
        for x in range(0, int(rect.width()), cell):
            p.drawLine(QPointF(rect.left() + x, rect.top()),
                       QPointF(rect.left() + x, rect.bottom()))
        p.setClipping(False)

        # Dashed border.
        if self._drag_active:
            border_color = QColor(theme.ACCENT)
        else:
            border_color = QColor(255, 255, 255, 41)  # 0.16 alpha
        pen = QPen(border_color)
        pen.setWidthF(1.5)
        pen.setStyle(Qt.DashLine)
        pen.setDashPattern([5, 4])
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, 12, 12)
        p.end()

    # ----- Mouse / drag --------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drag_active = True
            self._render_glyph()
            self.update()

    def dragLeaveEvent(self, _event: QDragLeaveEvent) -> None:
        self._drag_active = False
        self._render_glyph()
        self.update()

    def dropEvent(self, event: QDropEvent) -> None:
        self._drag_active = False
        self._render_glyph()
        self.update()
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.filesDropped.emit(paths)


def make_button(label: str, *, icon: str | None = None,
                kind: str = "ghost",
                tooltip: str | None = None) -> QPushButton:
    """Create a styled toolbar button.

    `kind`: "ghost" (default), "primary", "outline", "danger-ghost".
    """
    obj_name = {
        "ghost": "",
        "primary": "btn-primary",
        "outline": "btn-outline",
        "danger-ghost": "btn-danger-ghost",
    }.get(kind, "")
    btn = QPushButton(f"  {label}" if icon else label)
    if obj_name:
        btn.setObjectName(obj_name)
    if icon:
        # Color depends on kind.
        color = {
            "primary":      theme.ACCENT_ON,
            "outline":      theme.ACCENT,
            "danger-ghost": theme.DANGER,
        }.get(kind, theme.TEXT_DIM)
        btn.setIcon(_icon(icon, color=color))
    btn.setCursor(Qt.PointingHandCursor)
    btn.setMinimumHeight(32)
    if tooltip:
        btn.setToolTip(tooltip)
    return btn


def make_icon_label(name: str, size: int = 16, color: str = theme.TEXT_DIM,
                    stroke: float = 1.8) -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
    lbl.setPixmap(make_pixmap(name, size, color, stroke))
    return lbl


def _icon(name: str, *, color: str = theme.TEXT_DIM, size: int = 14):
    from PySide6.QtGui import QIcon
    return QIcon(make_pixmap(name, size, color, 1.8))


class Divider(QWidget):
    """Thin vertical divider for toolbars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(1, 20)
        self.setStyleSheet(f"background: {theme.BORDER};")


class StatusPill(QLabel):
    """Tag-style pill used to surface counts (file count, selection count)."""

    def __init__(self, text: str = "", *, accent: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty(
            "role",
            "status-pill-accent" if accent else "status-pill",
        )

    def set_accent(self, accent: bool) -> None:
        self.setProperty(
            "role",
            "status-pill-accent" if accent else "status-pill",
        )
        # Re-polish so the property change picks up new QSS.
        self.style().unpolish(self)
        self.style().polish(self)


# =====================================================================
# File list — used by Compress and Protect
# =====================================================================


@dataclass
class FileItem:
    name: str
    size_str: str
    pages: int
    status: str = "idle"   # idle | queued | run | done


_STATUS_LABEL = {
    "idle": "Idle", "queued": "Queued", "run": "Running", "done": "Done",
}
_STATUS_COLOR = {
    "idle":   theme.TEXT_FAINT,
    "queued": theme.WARN,
    "run":    theme.ACCENT,
    "done":   theme.GOOD,
}


class _StatusDot(QWidget):
    def __init__(self, status: str = "idle", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._status = status

    def set_status(self, status: str) -> None:
        self._status = status
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        color = QColor(_STATUS_COLOR.get(self._status, theme.TEXT_FAINT))
        if self._status in ("run", "done", "queued"):
            glow = QColor(color)
            glow.setAlpha(80)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QRectF(2, 2, 8, 8))
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(QRectF(3, 3, 6, 6))
        p.end()


class _FileRow(QWidget):
    """One row in the file list."""

    removeRequested = Signal(int)

    def __init__(self, idx: int, item: FileItem, *, removable: bool = True,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._idx = idx
        self._item = item
        self.setMinimumHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        # File icon (PDF document glyph in a faux page badge).
        ico = _PdfFileBadge()
        ico.setFixedSize(32, 38)
        layout.addWidget(ico)

        # Name + sub.
        text = QWidget()
        text_layout = QVBoxLayout(text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        self._name_lbl = QLabel(item.name)
        self._name_lbl.setStyleSheet(
            f"color: {theme.TEXT}; font-size: 13px; background: transparent;"
        )
        self._name_lbl.setMinimumWidth(0)
        sub = QLabel("PDF document")
        sub.setStyleSheet(
            f"color: {theme.TEXT_FAINT};"
            f"font-family: '{theme.FONT_MONO}', monospace;"
            f"font-size: 10.5px; background: transparent;"
        )
        text_layout.addWidget(self._name_lbl)
        text_layout.addWidget(sub)
        text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(text, stretch=1)

        # Size column.
        self._size_lbl = QLabel(item.size_str)
        self._size_lbl.setFixedWidth(90)
        self._size_lbl.setStyleSheet(
            f"color: {theme.TEXT_DIM};"
            f"font-family: '{theme.FONT_MONO}', monospace;"
            f"font-size: 11.5px; background: transparent;"
        )
        layout.addWidget(self._size_lbl)

        # Pages column.
        self._pages_lbl = QLabel(str(item.pages) if item.pages else "—")
        self._pages_lbl.setFixedWidth(70)
        self._pages_lbl.setStyleSheet(self._size_lbl.styleSheet())
        layout.addWidget(self._pages_lbl)

        # Status column.
        status = QWidget()
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(6)
        self._dot = _StatusDot(item.status)
        status_layout.addWidget(self._dot)
        self._status_lbl = QLabel(_STATUS_LABEL.get(item.status, "Idle"))
        self._status_lbl.setStyleSheet(
            f"color: {_STATUS_COLOR.get(item.status, theme.TEXT_FAINT)};"
            f"font-family: '{theme.FONT_MONO}', monospace;"
            f"font-size: 11.5px; background: transparent;"
        )
        status_layout.addWidget(self._status_lbl)
        status_layout.addStretch(1)
        status.setFixedWidth(110)
        layout.addWidget(status)

        # Remove button.
        if removable:
            self._remove = QPushButton()
            self._remove.setObjectName("file-remove")
            self._remove.setFixedSize(26, 26)
            self._remove.setIcon(_icon("x", color=theme.TEXT_FAINT, size=12))
            self._remove.setCursor(Qt.PointingHandCursor)
            self._remove.setStyleSheet(
                f"QPushButton#file-remove {{"
                f" background: transparent; border: none;"
                f" border-radius: 6px;"
                f"}}"
                f"QPushButton#file-remove:hover {{"
                f" background: rgba(255,107,107,0.10);"
                f"}}"
            )
            self._remove.clicked.connect(lambda: self.removeRequested.emit(self._idx))
            layout.addWidget(self._remove)
        else:
            spacer = QWidget()
            spacer.setFixedSize(26, 26)
            layout.addWidget(spacer)

    def set_status(self, status: str) -> None:
        self._item.status = status
        self._dot.set_status(status)
        self._status_lbl.setText(_STATUS_LABEL.get(status, status.title()))
        self._status_lbl.setStyleSheet(
            f"color: {_STATUS_COLOR.get(status, theme.TEXT_FAINT)};"
            f"font-family: '{theme.FONT_MONO}', monospace;"
            f"font-size: 11.5px; background: transparent;"
        )

    def set_size(self, size_str: str) -> None:
        self._item.size_str = size_str
        self._size_lbl.setText(size_str)


class _PdfFileBadge(QWidget):
    """Small page-with-folded-corner badge used as the file icon."""

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # Background gradient.
        path = QPainterPath()
        path.addRoundedRect(rect, 4, 4)
        p.setPen(Qt.NoPen)
        from PySide6.QtGui import QLinearGradient
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, QColor("#1d1d28"))
        grad.setColorAt(1.0, QColor("#14141d"))
        p.setBrush(grad)
        p.drawPath(path)
        # Border.
        p.setPen(QColor(255, 255, 255, 26))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, 4, 4)
        # Folded corner.
        fold = 9
        p.setPen(QColor(255, 255, 255, 26))
        p.setBrush(QColor(theme.SURFACE))
        p.drawPolygon([
            QPointF(rect.right() - fold, rect.top()),
            QPointF(rect.right(), rect.top() + fold),
            QPointF(rect.right() - fold, rect.top() + fold),
        ])
        # PDF glyph.
        from .icons import make_pixmap
        dpr = self.devicePixelRatioF() or 1.0
        pix = make_pixmap("pdf_doc", 14, theme.TEXT_DIM, 1.6, dpr)
        p.drawPixmap(int(rect.center().x() - 7), int(rect.center().y() - 7), pix)
        p.end()


class FileListWidget(QWidget):
    """Card-style file list with header row and stack of rows."""

    removeRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[_FileRow] = []
        self._removable = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("file-list-card")
        card.setStyleSheet(
            f"QFrame#file-list-card {{"
            f" background: {theme.SURFACE};"
            f" border: 1px solid {theme.BORDER};"
            f" border-radius: 12px;"
            f"}}"
        )
        outer.addWidget(card, stretch=1)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        header = self._build_header()
        card_layout.addWidget(header)

        # Scrollable area with rows stacked vertically.
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        self._rows_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(self._rows_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                              "QScrollArea > QWidget > QWidget { background: transparent; }")
        card_layout.addWidget(scroll, stretch=1)

    def _build_header(self) -> QWidget:
        head = QWidget()
        head.setStyleSheet(
            f"background: rgba(255,255,255,0.012);"
            f"border-bottom: 1px solid {theme.BORDER};"
        )
        layout = QHBoxLayout(head)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)
        # Leading spacer to align with the 32-px badge column on data rows.
        spacer = QWidget()
        spacer.setFixedSize(32, 1)
        layout.addWidget(spacer)
        for text, width, stretch in (
            ("Name", None, 1),
            ("Size", 90, 0),
            ("Pages", 70, 0),
            ("Status", 110, 0),
            ("", 26, 0),
        ):
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color: {theme.TEXT_FAINT};"
                f"font-family: '{theme.FONT_MONO}', monospace;"
                f"font-size: 10.5px;"
                f"letter-spacing: 0.1em;"
                f"background: transparent;"
            )
            if width is not None:
                lbl.setFixedWidth(width)
            if stretch:
                layout.addWidget(lbl, stretch=stretch)
            else:
                layout.addWidget(lbl)
        return head

    # ----- public API ----------------------------------------------------

    def set_removable(self, removable: bool) -> None:
        self._removable = removable
        for row in self._rows:
            if hasattr(row, "_remove"):
                row._remove.setEnabled(removable)
                row._remove.setVisible(removable)

    def set_items(self, items: list[FileItem]) -> None:
        # Drop existing rows AND their separator siblings — separators are
        # added by `_add_row` and must be removed in lockstep, otherwise
        # repeated set_items() calls leak QFrames into the layout.
        for row in self._rows:
            sep = getattr(row, "_sep", None)
            if sep is not None:
                self._rows_layout.removeWidget(sep)
                sep.deleteLater()
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        for i, item in enumerate(items):
            self._add_row(i, item)

    def _add_row(self, idx: int, item: FileItem) -> None:
        row = _FileRow(idx, item, removable=self._removable)
        row.removeRequested.connect(self.removeRequested.emit)
        # Insert before the trailing stretch.
        insert_at = self._rows_layout.count() - 1
        self._rows_layout.insertWidget(insert_at, row)
        # Add a thin separator between rows.
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {theme.BORDER};")
        self._rows_layout.insertWidget(insert_at + 1, sep)
        # Keep references so set_items() can clean both up together.
        row._sep = sep  # type: ignore[attr-defined]
        self._rows.append(row)

    def update_status(self, idx: int, status: str) -> None:
        if 0 <= idx < len(self._rows):
            self._rows[idx].set_status(status)

    def update_size(self, idx: int, size_str: str) -> None:
        if 0 <= idx < len(self._rows):
            self._rows[idx].set_size(size_str)

    def set_all_status(self, status: str) -> None:
        for row in self._rows:
            row.set_status(status)
