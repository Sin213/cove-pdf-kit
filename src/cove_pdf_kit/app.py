from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from . import __version__, updater
from .compress import CompressView
from .organize import OrganizeView
from .protect import ProtectView
from .rendering import ThumbnailService


ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICON_PATH = ASSETS_DIR / "cove_icon.png"


_TOOL_BTN_STYLE = """
QPushButton {
    text-align: left;
    padding: 10px 14px;
    border: none;
    border-radius: 6px;
    color: #cfd0d4;
    background: transparent;
    font-size: 13px;
}
QPushButton:hover { background: #1b2330; }
QPushButton:checked { background: #1f3a5c; color: #ffffff; font-weight: 600; }
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Cove PDF Kit v{__version__}")
        self.resize(1100, 760)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

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

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        side = QFrame()
        side.setFixedWidth(180)
        side.setStyleSheet("QFrame { background:#14181f; border-right:1px solid #2a2f3a; }")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(10, 16, 10, 16)
        side_layout.setSpacing(4)

        title = QLabel("Cove PDF Kit")
        title.setStyleSheet("color:#ffffff; font-size:15px; font-weight:700; padding:4px 10px 14px 10px;")
        side_layout.addWidget(title)

        self.btn_organize = _tool_button("Organize", "📄")
        self.btn_compress = _tool_button("Compress", "🗜")
        self.btn_protect = _tool_button("Protect", "🔒")

        self.btn_organize.setChecked(True)
        self.btn_organize.clicked.connect(lambda: self._select(0))
        self.btn_compress.clicked.connect(lambda: self._select(1))
        self.btn_protect.clicked.connect(lambda: self._select(2))

        side_layout.addWidget(self.btn_organize)
        side_layout.addWidget(self.btn_compress)
        side_layout.addWidget(self.btn_protect)
        side_layout.addStretch(1)

        footer = QLabel("v1.0.0 · offline")
        footer.setStyleSheet("color:#5a616f; font-size:11px; padding:4px 10px;")
        side_layout.addWidget(footer)

        root.addWidget(side)

        # Views
        self._stack = QStackedWidget()
        self._organize = OrganizeView(self._thumbs)
        self._compress = CompressView()
        self._protect = ProtectView()
        for view in (self._organize, self._compress, self._protect):
            view.statusMessage.connect(self._on_status)
            self._stack.addWidget(view)
        root.addWidget(self._stack, stretch=1)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)

    def _select(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate((self.btn_organize, self.btn_compress, self.btn_protect)):
            btn.setChecked(i == idx)

    def _on_status(self, text: str, timeout: int) -> None:
        self._status.showMessage(text, timeout)

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self._thumbs.shutdown()
        super().closeEvent(event)


def _tool_button(label: str, emoji: str) -> QPushButton:
    btn = QPushButton(f"  {emoji}   {label}")
    btn.setCheckable(True)
    btn.setAutoExclusive(True)
    btn.setStyleSheet(_TOOL_BTN_STYLE)
    btn.setIconSize(QSize(16, 16))
    btn.setCursor(Qt.PointingHandCursor)
    return btn
