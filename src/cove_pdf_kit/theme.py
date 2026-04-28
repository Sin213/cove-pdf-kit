"""Cove design system for the PDF Kit.

Mirrors the design reference (Cove PDF Kit.html / pdf-kit.jsx): teal accent on a
deep, slightly purple-tinted dark background, Geist for text, Geist Mono for
technical metadata. Exposes:

* Color, radius, font constants — for paint code in the rest of the package.
* `apply(app)` — installs the QPalette + global QSS on a `QApplication`.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


# ----- Palette ------------------------------------------------------------
# Tokens lifted from the Cove design reference.

BG          = "#0b0b10"
BG_2        = "#0d0d14"
BG_GRAD_TOP = "#0d0d14"
BG_GRAD_BOT = "#0a0a0f"
SURFACE     = "#13131b"
SURFACE_2   = "#181822"
SURFACE_3   = "#1f1f2b"
SURFACE_4   = "#262635"
BORDER         = "rgba(255,255,255,0.06)"
BORDER_HARD    = "rgba(255,255,255,0.10)"
BORDER_STRONG  = "rgba(255,255,255,0.16)"

TEXT         = "#ececf1"
TEXT_DIM     = "#9a9aae"
TEXT_FAINT   = "#6b6b80"
TEXT_FAINTER = "#4a4a5c"

# Accent is teal with a slightly brighter companion used for gradients.
ACCENT       = "#50e6cf"
ACCENT_2     = "#7af5e0"
ACCENT_SOFT  = "rgba(80,230,207,0.14)"
ACCENT_RING  = "rgba(80,230,207,0.35)"
ACCENT_GLOW  = "rgba(80,230,207,0.55)"
ACCENT_ON    = "#07221d"

GOOD   = "#3ddc97"
WARN   = "#ffb454"
DANGER = "#ff6b6b"

# Solid-color helpers (for paint code that wants QColor instances).
QC_BG          = QColor(BG)
QC_BG_2        = QColor(BG_2)
QC_SURFACE     = QColor(SURFACE)
QC_SURFACE_2   = QColor(SURFACE_2)
QC_SURFACE_3   = QColor(SURFACE_3)
QC_SURFACE_4   = QColor(SURFACE_4)
QC_TEXT        = QColor(TEXT)
QC_TEXT_DIM    = QColor(TEXT_DIM)
QC_TEXT_FAINT  = QColor(TEXT_FAINT)
QC_TEXT_FAINTER = QColor(TEXT_FAINTER)
QC_ACCENT      = QColor(ACCENT)
QC_ACCENT_2    = QColor(ACCENT_2)
QC_BORDER      = QColor(255, 255, 255, 15)

# ----- Geometry & typography ---------------------------------------------

RADIUS    = 12
RADIUS_SM = 8
RADIUS_XS = 6

FONT_SANS = "Geist"
FONT_MONO = "Geist Mono"
FONT_FALLBACK_SANS = "Inter, ui-sans-serif, system-ui, Segoe UI, Roboto, sans-serif"
FONT_FALLBACK_MONO = "JetBrains Mono, ui-monospace, Cascadia Mono, Menlo, monospace"


# ----- App-wide QSS -------------------------------------------------------

def _stylesheet() -> str:
    return f"""
    /* ---- Window root ---------------------------------------------- */
    QMainWindow, QWidget#cove-root {{
        background: {BG};
        color: {TEXT};
    }}
    QWidget#cove-chrome {{
        background: {BG};
        border: none;
        border-radius: 0;
    }}
    QWidget#cove-sidebar {{
        background: {BG_2};
        border-right: 1px solid {BORDER};
    }}
    QWidget#cove-main {{ background: transparent; }}
    QWidget#cove-head {{
        background: rgba(255,255,255,0.012);
        border-bottom: 1px solid {BORDER};
    }}
    QWidget#cove-footer {{
        background: rgba(255,255,255,0.014);
        border-top: 1px solid {BORDER};
    }}
    QFrame#cove-divider {{
        background: {BORDER};
        max-height: 1px; min-height: 1px;
    }}

    /* ---- Tooltips ------------------------------------------------- */
    QToolTip {{
        background: {SURFACE_2};
        color: {TEXT};
        border: 1px solid {BORDER_HARD};
        padding: 6px 9px;
        border-radius: {RADIUS_SM}px;
        font-size: 11.5px;
    }}

    /* ---- Labels --------------------------------------------------- */
    QLabel {{ color: {TEXT}; }}
    QLabel[role="dim"]   {{ color: {TEXT_DIM}; }}
    QLabel[role="faint"] {{ color: {TEXT_FAINT}; font-size: 11px; }}
    QLabel[role="title"] {{
        color: {TEXT};
        font-size: 18px;
        font-weight: 600;
        letter-spacing: -0.01em;
    }}
    QLabel[role="subtitle"] {{
        color: {TEXT_DIM};
        font-family: "{FONT_MONO}", {FONT_FALLBACK_MONO};
        font-size: 12px;
    }}
    QLabel[role="section"] {{
        color: {TEXT_FAINT};
        font-family: "{FONT_MONO}", {FONT_FALLBACK_MONO};
        font-size: 10.5px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }}
    QLabel[role="mono"] {{
        color: {TEXT_DIM};
        font-family: "{FONT_MONO}", {FONT_FALLBACK_MONO};
        font-size: 11.5px;
    }}
    QLabel[role="status-pill"] {{
        color: {TEXT_DIM};
        background: rgba(255,255,255,0.03);
        border: 1px solid {BORDER};
        border-radius: 999px;
        padding: 2px 10px;
        font-family: "{FONT_MONO}", {FONT_FALLBACK_MONO};
        font-size: 10.5px;
        letter-spacing: 0.04em;
    }}
    QLabel[role="status-pill-accent"] {{
        color: {ACCENT};
        background: {ACCENT_SOFT};
        border: 1px solid {ACCENT_RING};
        border-radius: 999px;
        padding: 2px 10px;
        font-family: "{FONT_MONO}", {FONT_FALLBACK_MONO};
        font-size: 10.5px;
        letter-spacing: 0.04em;
    }}
    QLabel[role="hint"] {{
        color: {TEXT_FAINT};
        font-family: "{FONT_MONO}", {FONT_FALLBACK_MONO};
        font-size: 10.5px;
    }}
    QLabel[role="brand-name"] {{
        color: {TEXT};
        font-size: 13.5px;
        font-weight: 600;
        letter-spacing: -0.01em;
    }}
    QLabel[role="brand-version"] {{
        color: {TEXT_FAINT};
        font-family: "{FONT_MONO}", {FONT_FALLBACK_MONO};
        font-size: 10.5px;
        letter-spacing: 0.04em;
    }}
    QLabel[role="nav-label"] {{
        color: {TEXT_FAINT};
        font-family: "{FONT_MONO}", {FONT_FALLBACK_MONO};
        font-size: 10.5px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        padding: 0 10px;
    }}
    QLabel[role="kv-label"] {{
        color: {TEXT_DIM};
        font-family: "{FONT_MONO}", {FONT_FALLBACK_MONO};
        font-size: 11px;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }}

    /* ---- Buttons -------------------------------------------------- */
    QPushButton, QToolButton {{
        background: {SURFACE};
        color: {TEXT_DIM};
        border: 1px solid {BORDER};
        padding: 7px 12px;
        border-radius: {RADIUS_SM}px;
        font-size: 12.5px;
    }}
    QPushButton:hover, QToolButton:hover {{
        color: {TEXT};
        background: {SURFACE_2};
        border-color: {BORDER_HARD};
    }}
    QPushButton:pressed, QToolButton:pressed {{ background: {SURFACE_3}; }}
    QPushButton:disabled, QToolButton:disabled {{
        color: {TEXT_FAINTER};
        background: transparent;
        border-color: {BORDER};
    }}

    QPushButton#btn-primary {{
        color: {ACCENT_ON};
        background: {ACCENT};
        border: 1px solid rgba(255,255,255,0.10);
        font-weight: 600;
        padding: 8px 16px;
    }}
    QPushButton#btn-primary:hover    {{ background: {ACCENT_2}; }}
    QPushButton#btn-primary:pressed  {{ background: #44d4be; }}
    QPushButton#btn-primary:disabled {{
        color: {TEXT_FAINT};
        background: {SURFACE_2};
        border-color: {BORDER};
    }}

    QPushButton#btn-outline {{
        color: {ACCENT};
        background: {ACCENT_SOFT};
        border: 1px solid {ACCENT_RING};
    }}
    QPushButton#btn-outline:hover {{
        color: #ffffff;
        background: rgba(80,230,207,0.22);
        border-color: {ACCENT};
    }}
    QPushButton#btn-outline:disabled {{
        color: {TEXT_FAINT};
        background: transparent;
        border-color: {BORDER};
    }}

    QPushButton#btn-danger-ghost {{
        color: {DANGER};
        background: rgba(255,107,107,0.05);
        border: 1px solid rgba(255,107,107,0.18);
    }}
    QPushButton#btn-danger-ghost:hover {{
        background: rgba(255,107,107,0.14);
        border-color: rgba(255,107,107,0.40);
    }}
    QPushButton#btn-danger-ghost:disabled {{
        color: {TEXT_FAINT};
        background: transparent;
        border-color: {BORDER};
    }}

    /* Sidebar nav buttons (object name nav-btn). */
    QPushButton#nav-btn {{
        text-align: left;
        background: transparent;
        color: {TEXT_DIM};
        border: none;
        padding: 8px 10px;
        border-radius: {RADIUS_SM}px;
        font-size: 13px;
    }}
    QPushButton#nav-btn:hover {{
        background: {SURFACE};
        color: {TEXT};
    }}
    QPushButton#nav-btn:checked {{
        background: {ACCENT_SOFT};
        color: {TEXT};
    }}

    /* Radio-pill (Protect Add/Remove). */
    QPushButton#radio-pill {{
        background: {SURFACE};
        color: {TEXT_DIM};
        border: 1px solid {BORDER};
        padding: 6px 12px;
        border-radius: {RADIUS_SM}px;
        font-size: 12.5px;
    }}
    QPushButton#radio-pill:hover {{
        color: {TEXT};
        border-color: {BORDER_HARD};
    }}
    QPushButton#radio-pill:checked {{
        color: {TEXT};
        background: {ACCENT_SOFT};
        border-color: {ACCENT_RING};
    }}

    /* ---- Inputs / combos ------------------------------------------ */
    QLineEdit {{
        background: {SURFACE};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        padding: 7px 12px;
        selection-background-color: {ACCENT};
        selection-color: {ACCENT_ON};
    }}
    QLineEdit:hover  {{ border-color: {BORDER_HARD}; }}
    QLineEdit:focus  {{
        border-color: {ACCENT_RING};
        background: {SURFACE_2};
    }}
    QLineEdit:disabled {{ color: {TEXT_FAINT}; background: transparent; }}

    QComboBox {{
        background: {SURFACE};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        padding: 6px 12px;
        min-height: 22px;
        selection-background-color: {ACCENT};
        selection-color: {ACCENT_ON};
    }}
    QComboBox:hover  {{ border-color: {BORDER_HARD}; }}
    QComboBox:focus  {{ border-color: {ACCENT_RING}; }}
    QComboBox::drop-down {{
        subcontrol-origin: padding; subcontrol-position: top right;
        width: 22px; border: none;
        background: transparent;
    }}
    QComboBox QAbstractItemView {{
        background: {SURFACE_2};
        color: {TEXT};
        border: 1px solid {BORDER_HARD};
        border-radius: {RADIUS_SM}px;
        padding: 4px;
        outline: 0;
        selection-background-color: {ACCENT_SOFT};
        selection-color: {TEXT};
    }}

    /* ---- Progress bar -------------------------------------------- */
    QProgressBar {{
        background: {SURFACE_3};
        color: #ffffff;
        border: 1px solid {BORDER};
        border-radius: 999px;
        text-align: center;
        font-family: "{FONT_MONO}", {FONT_FALLBACK_MONO};
        font-size: 10px;
        font-weight: 600;
        padding: 0;
        min-height: 6px;
        max-height: 6px;
    }}
    QProgressBar::chunk {{
        background: {ACCENT};
        border-radius: 999px;
    }}

    /* ---- Status bar ---------------------------------------------- */
    QStatusBar {{
        background: rgba(255,255,255,0.012);
        color: {TEXT_FAINT};
        border-top: 1px solid {BORDER};
        font-family: "{FONT_MONO}", {FONT_FALLBACK_MONO};
        font-size: 10.5px;
        letter-spacing: 0.04em;
    }}
    QStatusBar::item {{ border: none; }}

    /* ---- List views ---------------------------------------------- */
    QListView {{
        background: transparent;
        border: none;
        color: {TEXT};
        outline: 0;
    }}
    QListView::item {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: {RADIUS_SM}px;
        padding: 4px;
        color: {TEXT};
    }}
    QListView::item:hover {{
        border: 1px solid {BORDER_HARD};
    }}
    QListView::item:selected {{
        border: 1px solid {ACCENT};
        background: {ACCENT_SOFT};
    }}

    QListWidget {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: {RADIUS}px;
        color: {TEXT};
        padding: 4px;
        outline: 0;
    }}
    QListWidget::item {{
        padding: 8px 10px;
        border-radius: {RADIUS_SM}px;
    }}
    QListWidget::item:hover {{ background: rgba(255,255,255,0.02); }}
    QListWidget::item:selected {{
        background: {ACCENT_SOFT};
        color: {TEXT};
    }}

    /* ---- Scrollbars ---------------------------------------------- */
    QScrollBar:vertical, QScrollBar:horizontal {{
        background: transparent; border: none; margin: 0;
        width: 10px; height: 10px;
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: rgba(255,255,255,0.06);
        border-radius: 5px; min-height: 24px; min-width: 24px;
    }}
    QScrollBar::handle:hover {{ background: rgba(255,255,255,0.12); }}
    QScrollBar::add-line, QScrollBar::sub-line,
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; }}

    /* ---- Menu / message box -------------------------------------- */
    QMenu {{
        background: {SURFACE_2};
        color: {TEXT};
        border: 1px solid {BORDER_HARD};
        border-radius: {RADIUS_SM}px;
        padding: 4px;
    }}
    QMenu::item {{ padding: 6px 14px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}

    QMessageBox {{ background: {SURFACE}; }}
    QMessageBox QLabel {{ color: {TEXT}; }}
    """


def apply(app: QApplication) -> None:
    """Apply the cove design system to a Qt app."""
    app.setStyle("Fusion")

    base_font = QFont(FONT_SANS, 10)
    base_font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(base_font)

    p = QPalette()
    p.setColor(QPalette.Window,          QColor(BG))
    p.setColor(QPalette.WindowText,      QColor(TEXT))
    p.setColor(QPalette.Base,            QColor(SURFACE_2))
    p.setColor(QPalette.AlternateBase,   QColor(SURFACE_3))
    p.setColor(QPalette.ToolTipBase,     QColor(SURFACE_2))
    p.setColor(QPalette.ToolTipText,     QColor(TEXT))
    p.setColor(QPalette.Text,            QColor(TEXT))
    p.setColor(QPalette.Button,          QColor(SURFACE))
    p.setColor(QPalette.ButtonText,      QColor(TEXT))
    p.setColor(QPalette.BrightText,      QColor(DANGER))
    p.setColor(QPalette.Link,            QColor(ACCENT))
    p.setColor(QPalette.Highlight,       QColor(ACCENT))
    p.setColor(QPalette.HighlightedText, QColor(ACCENT_ON))
    p.setColor(QPalette.PlaceholderText, QColor(TEXT_FAINT))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        p.setColor(QPalette.Disabled, role, QColor(TEXT_FAINT))
    app.setPalette(p)

    app.setStyleSheet(_stylesheet())
