"""Cove PDF Kit — main window.

Frameless cove-design shell: custom titlebar (no traffic lights),
sidebar with brand mark + tool nav, stacked content area for the three
tools, and a per-view footer/statusbar driven by the active tool.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizeGrip,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from . import __version__, theme, updater
from .chrome import CoveTitleBar, FramelessResizer
from .compress import CompressView
from .icons import make_icon, make_pixmap
from .organize import OrganizeView
from .protect import ProtectView
from .rendering import ThumbnailService


ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICON_PATH = ASSETS_DIR / "cove_icon.png"


class CoveRoot(QWidget):
    """Central widget that paints the cove radial-glow background."""

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        base = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        base.setColorAt(0.0, QColor(theme.BG_GRAD_TOP))
        base.setColorAt(1.0, QColor(theme.BG_GRAD_BOT))
        p.fillRect(rect, base)
        a = QColor(theme.ACCENT)
        g1 = QRadialGradient(rect.right() - 200, -120, max(rect.width(), rect.height()))
        g1.setColorAt(0.00, QColor(a.red(), a.green(), a.blue(), 15))
        g1.setColorAt(0.55, QColor(a.red(), a.green(), a.blue(), 0))
        p.fillRect(rect, g1)
        g2 = QRadialGradient(80, rect.bottom() + 80, max(rect.width(), rect.height()))
        g2.setColorAt(0.00, QColor(124, 92, 255, 10))
        g2.setColorAt(0.60, QColor(124, 92, 255, 0))
        p.fillRect(rect, g2)
        p.end()


class _BrandMark(QWidget):
    """The 32×32 brand square with the icon centered inside."""

    def __init__(self, icon_path: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self._pix: QPixmap | None = None
        if icon_path and icon_path.exists():
            self._icon_path = str(icon_path)
        else:
            self._icon_path = None

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        if self._icon_path is None:
            return
        dpr = self.devicePixelRatioF() or 1.0
        target = int(round(24 * dpr))
        pix = QPixmap(self._icon_path).scaled(
            target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        pix.setDevicePixelRatio(dpr)
        self._pix = pix
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        rectf = QRectF(rect)
        # Background gradient.
        grad = QLinearGradient(rectf.topLeft(), rectf.bottomRight())
        grad.setColorAt(0.0, QColor("#16161f"))
        grad.setColorAt(1.0, QColor("#0d0d14"))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(rectf, 8, 8)
        # Border.
        p.setBrush(Qt.NoBrush)
        p.setPen(QColor(255, 255, 255, 28))
        p.drawRoundedRect(rectf, 8, 8)
        # Icon.
        if self._pix is not None:
            ix = (self.width() - 24) / 2
            iy = (self.height() - 24) / 2
            p.drawPixmap(int(ix), int(iy), self._pix)
        p.end()


class _PulseDot(QWidget):
    """Small accent-colored pulse dot used in sidebar foot / statusbar."""

    def __init__(self, color: str = theme.GOOD, size: int = 6,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size + 4, size + 4)
        self._size = size
        self._color = QColor(color)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        cx = self.width() / 2
        cy = self.height() / 2
        # Soft glow.
        glow = QColor(self._color)
        glow.setAlpha(96)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QRectF(cx - self._size, cy - self._size,
                             self._size * 2, self._size * 2))
        # Solid core.
        p.setBrush(self._color)
        r = self._size / 2
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        p.end()


class _NavButton(QPushButton):
    """Sidebar navigation button with icon, label, and trailing count."""

    def __init__(self, label: str, icon_name: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("nav-btn")
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMinimumHeight(34)
        self._icon_name = icon_name
        self._count = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)

        self._ico = QLabel()
        self._ico.setFixedSize(16, 16)
        self._ico.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self._ico)

        self._label = QLabel(label)
        self._label.setStyleSheet("color: inherit; background: transparent;")
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self._label)

        layout.addStretch(1)

        self._count_lbl = QLabel("")
        self._count_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._count_lbl.setStyleSheet(
            f"font-family: '{theme.FONT_MONO}', monospace;"
            f"font-size: 10.5px;"
            f"color: {theme.TEXT_FAINT};"
            f"background: rgba(255,255,255,0.04);"
            f"padding: 1px 6px;"
            f"border-radius: 4px;"
        )
        self._count_lbl.hide()
        layout.addWidget(self._count_lbl)

        self.toggled.connect(self._refresh_icon)
        self._refresh_icon(False)

    def set_count(self, n: int) -> None:
        self._count = n
        if n > 0:
            self._count_lbl.setText(str(n))
            if self.isChecked():
                self._count_lbl.setStyleSheet(
                    f"font-family: '{theme.FONT_MONO}', monospace;"
                    f"font-size: 10.5px;"
                    f"color: {theme.ACCENT};"
                    f"background: {theme.ACCENT_SOFT};"
                    f"padding: 1px 6px;"
                    f"border-radius: 4px;"
                )
            else:
                self._count_lbl.setStyleSheet(
                    f"font-family: '{theme.FONT_MONO}', monospace;"
                    f"font-size: 10.5px;"
                    f"color: {theme.TEXT_FAINT};"
                    f"background: rgba(255,255,255,0.04);"
                    f"padding: 1px 6px;"
                    f"border-radius: 4px;"
                )
            self._count_lbl.show()
        else:
            self._count_lbl.hide()

    def _refresh_icon(self, checked: bool) -> None:
        color = theme.ACCENT if checked else theme.TEXT_DIM
        dpr = self.devicePixelRatioF() or 1.0
        self._ico.setPixmap(make_pixmap(self._icon_name, 16, color, 1.8, dpr))
        # Re-style the label: active tab uses TEXT, inactive uses TEXT_DIM.
        label_color = theme.TEXT if checked else theme.TEXT_DIM
        self._label.setStyleSheet(
            f"color: {label_color}; background: transparent; font-size: 13px;"
        )
        if self._count > 0:
            self.set_count(self._count)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Cove PDF Kit v{__version__}")
        self.resize(1200, 780)
        self.setMinimumSize(900, 600)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        # Frameless window with custom titlebar.
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self._frameless_resizer = FramelessResizer(self)
        # Visible SE-corner resize grip so the user has a discoverable
        # affordance to grab. FramelessResizer handles invisible edge drag.
        self._size_grip = QSizeGrip(self)
        self._size_grip.setFixedSize(16, 16)
        self._size_grip.raise_()
        self.setMouseTracking(True)

        self._thumbs = ThumbnailService(self)
        self._build_ui()

        self._updater = updater.UpdateController(
            parent=self,
            current_version=__version__,
            repo="Sin213/cove-pdf-kit",
            app_display_name="Cove PDF Kit",
            cache_subdir="cove-pdf-kit",
        )
        QTimer.singleShot(4000, self._updater.check)

    # -----------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Reposition the SE-corner QSizeGrip on every resize so it stays
        # pinned to the bottom-right of the window.
        s = self._size_grip.sizeHint()
        self._size_grip.move(self.width() - s.width(), self.height() - s.height())

    def _build_ui(self) -> None:
        central = CoveRoot()
        central.setObjectName("cove-root")
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        chrome = QWidget()
        chrome.setObjectName("cove-chrome")
        outer.addWidget(chrome)

        chrome_layout = QVBoxLayout(chrome)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.setSpacing(0)

        self._titlebar = CoveTitleBar(
            self,
            icon_path=str(ICON_PATH) if ICON_PATH.exists() else None,
            title="Cove PDF Kit",
            version=f"v{__version__}",
        )
        chrome_layout.addWidget(self._titlebar)

        body = QWidget()
        chrome_layout.addWidget(body, stretch=1)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._build_sidebar())
        body_layout.addWidget(self._build_stack(), stretch=1)

        # Hidden status bar — views surface their own status in their footer.
        self.status = QStatusBar()
        self.status.setVisible(False)
        self.setStatusBar(self.status)

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("cove-sidebar")
        side.setFixedWidth(220)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(12, 18, 12, 14)
        layout.setSpacing(0)

        # Brand block (text only — icon removed per UI request).
        brand = QWidget()
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(10, 0, 8, 14)
        brand_layout.setSpacing(2)
        name_lbl = QLabel("Cove PDF Kit")
        name_lbl.setProperty("role", "brand-name")
        ver_lbl = QLabel(f"v{__version__}")
        ver_lbl.setProperty("role", "brand-version")
        brand_layout.addWidget(name_lbl)
        brand_layout.addWidget(ver_lbl)
        layout.addWidget(brand)

        # Section label.
        section = QLabel("Tools")
        section.setProperty("role", "nav-label")
        section_wrap = QWidget()
        section_layout = QVBoxLayout(section_wrap)
        section_layout.setContentsMargins(0, 6, 0, 6)
        section_layout.setSpacing(0)
        section_layout.addWidget(section)
        layout.addWidget(section_wrap)

        # Nav buttons.
        self.btn_organize = _NavButton("Organize", "organize")
        self.btn_compress = _NavButton("Compress", "compress")
        self.btn_protect  = _NavButton("Protect",  "protect")
        self.btn_organize.setChecked(True)
        self.btn_organize.clicked.connect(lambda: self._select(0))
        self.btn_compress.clicked.connect(lambda: self._select(1))
        self.btn_protect.clicked.connect(lambda: self._select(2))
        layout.addWidget(self.btn_organize)
        layout.addWidget(self.btn_compress)
        layout.addWidget(self.btn_protect)

        layout.addStretch(1)

        return side

    def _build_stack(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("cove-main")
        wlayout = QVBoxLayout(wrapper)
        wlayout.setContentsMargins(0, 0, 0, 0)
        wlayout.setSpacing(0)

        self._stack = QStackedWidget()
        self._organize = OrganizeView(self._thumbs)
        self._compress = CompressView()
        self._protect  = ProtectView()
        for view in (self._organize, self._compress, self._protect):
            view.statusMessage.connect(self._on_status)
            self._stack.addWidget(view)

        # Hook up count signals so the sidebar pills stay live.
        self._organize.itemsChanged.connect(self.btn_organize.set_count)
        self._compress.itemsChanged.connect(self.btn_compress.set_count)
        self._protect.itemsChanged.connect(self.btn_protect.set_count)

        wlayout.addWidget(self._stack, stretch=1)
        return wrapper

    # -----------------------------------------------------------------
    # Behaviors
    # -----------------------------------------------------------------

    def _select(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate((self.btn_organize, self.btn_compress, self.btn_protect)):
            btn.setChecked(i == idx)

    def _on_status(self, text: str, timeout: int) -> None:
        self.status.showMessage(text, timeout)

    # -----------------------------------------------------------------
    # Frameless resize / lifecycle
    # -----------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._frameless_resizer is not None and self._frameless_resizer.try_press(event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._frameless_resizer is not None and self._frameless_resizer.try_move(event):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._frameless_resizer is not None and self._frameless_resizer.try_release(event):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        if self._frameless_resizer is not None:
            self._frameless_resizer.clear_hover()
        super().leaveEvent(event)

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self._thumbs.shutdown()
        super().closeEvent(event)
