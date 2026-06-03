"""The Organize tool.

A grid of page thumbnails that acts as a unified merge / reorder /
rotate / delete / split view. Drop one or more PDFs, drag to reorder,
right-click for actions, hit Export to write a new PDF.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QImage,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .icons import make_pixmap
from .pdf_ops import PageRef, pages_to_jpeg, read_page_count, write_merged
from .rendering import ThumbnailService
from .system import reveal_in_file_manager
from .widgets import Divider, DropZone, StatusPill, make_button


THUMB_WIDTH = 184
THUMB_HEIGHT = 244


class PageModel(QAbstractListModel):
    """Flat ordered list of :class:`PageRef` values."""

    PageRole = Qt.UserRole + 1

    def __init__(self, thumbs: ThumbnailService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pages: list[PageRef] = []
        self._thumbs = thumbs
        self._tokens: dict[int, PageRef] = {}
        self._icons: dict[PageRef, QIcon] = {}
        self._requested: set[PageRef] = set()
        self._placeholder = _placeholder_icon()
        self._thumbs.rendered.connect(self._on_thumb, Qt.QueuedConnection)

    # --- QAbstractListModel API -------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._pages)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: ANN001
        if not index.isValid() or index.row() >= len(self._pages):
            return None
        ref = self._pages[index.row()]
        if role == Qt.DisplayRole:
            return f"{ref.source.name} · p{ref.index + 1}"
        if role == Qt.DecorationRole:
            return self._pixmap_for(index.row(), ref)
        if role == Qt.SizeHintRole:
            return QSize(THUMB_WIDTH + 12, THUMB_HEIGHT + 36)
        if role == self.PageRole:
            return ref
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        base = super().flags(index)
        if index.isValid():
            return base | Qt.ItemIsDragEnabled
        return base | Qt.ItemIsDropEnabled

    def supportedDropActions(self) -> Qt.DropActions:
        return Qt.MoveAction

    # --- Drag-drop (InternalMove) ----------------------------------

    MIME = "application/x-cove-pdf-kit-rows"

    def mimeTypes(self) -> list[str]:
        return [self.MIME]

    def mimeData(self, indexes: list[QModelIndex]):  # noqa: ANN201
        from PySide6.QtCore import QMimeData
        rows = sorted({i.row() for i in indexes if i.isValid()})
        data = QMimeData()
        data.setData(self.MIME, ",".join(map(str, rows)).encode())
        return data

    def dropMimeData(self, data, action, row, column, parent) -> bool:  # noqa: ANN001
        if action != Qt.MoveAction or not data.hasFormat(self.MIME):
            return False
        src_rows = [int(x) for x in bytes(data.data(self.MIME)).decode().split(",") if x]
        if not src_rows:
            return False
        dest = row if row >= 0 else len(self._pages)
        moving = [self._pages[r] for r in src_rows]
        for r in sorted(src_rows, reverse=True):
            self.beginRemoveRows(QModelIndex(), r, r)
            del self._pages[r]
            self.endRemoveRows()
            if r < dest:
                dest -= 1
        dest = max(0, min(len(self._pages), dest))
        self.beginInsertRows(QModelIndex(), dest, dest + len(moving) - 1)
        for offset, page in enumerate(moving):
            self._pages.insert(dest + offset, page)
        self.endInsertRows()
        return True

    def removeRows(self, row: int, count: int, parent: QModelIndex = QModelIndex()) -> bool:
        if parent.isValid():
            return False
        if row < 0 or row + count > len(self._pages):
            return False
        self.beginRemoveRows(QModelIndex(), row, row + count - 1)
        del self._pages[row:row + count]
        self.endRemoveRows()
        return True

    # --- Public mutation API ---------------------------------------

    def add_pdf(self, path: Path) -> int:
        try:
            n = read_page_count(path)
        except PermissionError:
            raise
        first_row = len(self._pages)
        self.beginInsertRows(QModelIndex(), first_row, first_row + n - 1)
        for i in range(n):
            self._pages.append(PageRef(source=path, index=i))
        self.endInsertRows()
        return n

    def rotate_rows(self, rows: list[int], delta: int) -> None:
        for row in rows:
            if 0 <= row < len(self._pages):
                self._pages[row] = self._pages[row].rotated(delta)
                idx = self.index(row)
                self.dataChanged.emit(idx, idx, [Qt.DecorationRole, self.PageRole])

    def remove_rows(self, rows: list[int]) -> None:
        for row in sorted(rows, reverse=True):
            if 0 <= row < len(self._pages):
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._pages[row]
                self.endRemoveRows()

    def all_pages(self) -> list[PageRef]:
        return list(self._pages)

    def pages_at(self, rows: list[int]) -> list[PageRef]:
        return [self._pages[r] for r in rows if 0 <= r < len(self._pages)]

    def unique_sources(self) -> int:
        return len({p.source for p in self._pages})

    def clear(self) -> None:
        if not self._pages:
            return
        self.beginResetModel()
        self._pages.clear()
        self.endResetModel()

    # --- Thumbnail loading -----------------------------------------

    def _pixmap_for(self, row: int, ref: PageRef) -> QIcon:
        icon = self._icons.get(ref)
        if icon is not None:
            return icon
        if ref not in self._requested:
            self._requested.add(ref)
            token = self._thumbs.request(ref.source, ref.index, ref.rotation, THUMB_WIDTH)
            self._tokens[token] = ref
        return self._placeholder

    def _on_thumb(self, token: int, image: QImage) -> None:
        ref = self._tokens.pop(token, None)
        if ref is None:
            return
        scaled = image.scaled(
            THUMB_WIDTH, THUMB_HEIGHT, Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._icons[ref] = QIcon(QPixmap.fromImage(scaled))
        for r, p in enumerate(self._pages):
            if p == ref:
                idx = self.index(r)
                self.dataChanged.emit(idx, idx, [Qt.DecorationRole])


def _placeholder_icon() -> QIcon:
    pix = QPixmap(THUMB_WIDTH, THUMB_HEIGHT)
    pix.fill(QPixmap(0, 0).toImage().pixelColor(0, 0)
             if False else  # keep the type checker quiet
             Qt.transparent)
    pix.fill(Qt.transparent)
    from PySide6.QtGui import QPainter, QColor, QLinearGradient
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    grad = QLinearGradient(0, 0, 0, THUMB_HEIGHT)
    grad.setColorAt(0.0, QColor("#1d1d28"))
    grad.setColorAt(1.0, QColor("#14141d"))
    p.setBrush(grad)
    p.setPen(QColor(255, 255, 255, 12))
    p.drawRoundedRect(0, 0, THUMB_WIDTH - 1, THUMB_HEIGHT - 1, 6, 6)
    p.end()
    return QIcon(pix)


class OrganizeView(QWidget):
    statusMessage = Signal(str, int)
    itemsChanged = Signal(int)   # unique source count

    def __init__(self, thumbs: ThumbnailService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._thumbs = thumbs
        self._last_export_path: Path | None = None
        self._model = PageModel(thumbs, self)
        self._build_ui()
        self.setAcceptDrops(True)
        self._update_state()
        self._model.rowsInserted.connect(self._update_state)
        self._model.rowsRemoved.connect(self._update_state)
        self._model.modelReset.connect(self._update_state)

        # Delete key removes the current selection. Scoped to this widget
        # so the rest of the app isn't affected.
        del_sc = QShortcut(QKeySequence(Qt.Key_Delete), self)
        del_sc.setContext(Qt.WidgetWithChildrenShortcut)
        del_sc.activated.connect(self._delete_selection)
        backspace_sc = QShortcut(QKeySequence(Qt.Key_Backspace), self)
        backspace_sc.setContext(Qt.WidgetWithChildrenShortcut)
        backspace_sc.activated.connect(self._delete_selection)

    # --- UI build --------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_head())
        root.addWidget(self._build_content(), stretch=1)
        root.addWidget(self._build_statusbar())

    def _build_head(self) -> QWidget:
        head = QWidget()
        head.setObjectName("cove-head")
        layout = QVBoxLayout(head)
        layout.setContentsMargins(24, 18, 24, 14)
        layout.setSpacing(12)

        # Row 1 — toolbar.
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self.add_btn       = make_button("Add PDFs…", icon="plus")
        self.add_btn.clicked.connect(self._on_add_clicked)
        self.rot_left_btn  = make_button("Rotate ↶", icon="rotate_ccw")
        self.rot_left_btn.clicked.connect(lambda: self._rotate_selection(-90))
        self.rot_right_btn = make_button("Rotate ↷", icon="rotate_cw")
        self.rot_right_btn.clicked.connect(lambda: self._rotate_selection(90))
        self.delete_btn    = make_button("Delete", icon="trash", kind="danger-ghost")
        self.delete_btn.clicked.connect(self._delete_selection)
        self.clear_btn     = make_button("Clear all")
        self.clear_btn.clicked.connect(self._on_clear)

        row1.addWidget(self.add_btn)
        row1.addSpacing(2)
        row1.addWidget(Divider())
        row1.addSpacing(2)
        row1.addWidget(self.rot_left_btn)
        row1.addWidget(self.rot_right_btn)
        row1.addWidget(self.delete_btn)
        row1.addWidget(self.clear_btn)
        row1.addStretch(1)

        self.export_sel_btn = make_button("Selection…", icon="download")
        self.export_sel_btn.clicked.connect(self._on_export_selection)
        self.export_jpeg_btn = make_button("JPEG…", icon="download")
        self.export_jpeg_btn.clicked.connect(self._on_export_jpeg)
        self.export_btn = make_button("Export PDF…", icon="download")
        self.export_btn.clicked.connect(self._on_export)
        row1.addWidget(self.export_sel_btn)
        row1.addWidget(self.export_jpeg_btn)
        row1.addWidget(self.export_btn)
        layout.addLayout(row1)

        # Row 2 — pills + drag hint.
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        self.count_pill = StatusPill("0 files")
        self.sel_pill   = StatusPill("0 selected", accent=True)
        self.sel_pill.hide()
        row2.addWidget(self.count_pill)
        row2.addWidget(self.sel_pill)
        row2.addStretch(1)
        self.show_folder_btn = make_button("Show folder", icon="upload", kind="outline")
        self.show_folder_btn.setMinimumHeight(28)
        self.show_folder_btn.clicked.connect(self._on_show_folder)
        self.show_folder_btn.hide()
        row2.addWidget(self.show_folder_btn)
        hint = QLabel(
            "Drag thumbnails to reorder · right-click for rotate / delete / split"
        )
        hint.setProperty("role", "hint")
        row2.addWidget(hint)
        layout.addLayout(row2)
        return head

    def _build_content(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(0)

        self._stack = QStackedWidget()

        # Empty state — drop zone.
        self._dropzone = DropZone(
            glyph="drop_doc",
            headline='Drop PDFs here, or click "Add PDFs…"',
            body="Then drag the thumbnails to reorder, right-click for rotate / delete / split.",
        )
        self._dropzone.clicked.connect(self._on_add_clicked)
        self._dropzone.filesDropped.connect(self._on_files_dropped)
        self._stack.addWidget(self._dropzone)

        # Loaded state — page grid.
        self.view = QListView()
        self.view.setModel(self._model)
        self.view.setViewMode(QListView.IconMode)
        self.view.setFlow(QListView.LeftToRight)
        self.view.setWrapping(True)
        self.view.setResizeMode(QListView.Adjust)
        self.view.setMovement(QListView.Snap)
        self.view.setUniformItemSizes(True)
        self.view.setIconSize(QSize(THUMB_WIDTH, THUMB_HEIGHT))
        self.view.setSpacing(14)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setDragDropMode(QAbstractItemView.InternalMove)
        self.view.setDefaultDropAction(Qt.MoveAction)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        self.view.selectionModel().selectionChanged.connect(self._update_state)
        self.view.setStyleSheet(
            f"QListView {{ background: transparent; border: none;"
            f" color: {theme.TEXT}; outline: 0;"
            f" padding: 4px;"
            f"}}"
            f"QListView::item {{"
            f" border: 1px solid {theme.BORDER};"
            f" border-radius: 10px;"
            f" background: {theme.SURFACE};"
            f" color: {theme.TEXT};"
            f" padding: 6px;"
            f"}}"
            f"QListView::item:hover {{"
            f" border-color: {theme.BORDER_STRONG};"
            f"}}"
            f"QListView::item:selected {{"
            f" border: 1px solid {theme.ACCENT};"
            f" background: {theme.ACCENT_SOFT};"
            f"}}"
        )
        self._stack.addWidget(self.view)

        layout.addWidget(self._stack, stretch=1)
        return wrapper

    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(26)
        bar.setStyleSheet(
            f"background: rgba(255,255,255,0.012);"
            f"border-top: 1px solid {theme.BORDER};"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)
        from .app import _PulseDot  # late import to avoid cycle
        layout.addWidget(_PulseDot(theme.GOOD, 6))
        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet(
            f"color: {theme.TEXT_FAINT};"
            f"font-family: '{theme.FONT_MONO}', monospace;"
            f"font-size: 10.5px;"
            f"letter-spacing: 0.04em;"
            f"background: transparent;"
        )
        layout.addWidget(self._status_lbl)
        layout.addStretch(1)
        self._totals_lbl = QLabel("0 files · 0 pages total")
        self._totals_lbl.setStyleSheet(self._status_lbl.styleSheet())
        layout.addWidget(self._totals_lbl)
        return bar

    # --- actions ----------------------------------------------------

    def _on_add_clicked(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add PDFs", "", "PDF files (*.pdf);;All files (*)",
        )
        for p in paths:
            self._add_path(Path(p))

    def _on_files_dropped(self, paths: list[str]) -> None:
        for p in paths:
            self._add_path(Path(p))

    def _add_path(self, path: Path) -> None:
        if path.suffix.lower() != ".pdf":
            self.statusMessage.emit(f"Skipped (not a PDF): {path.name}", 4000)
            return
        try:
            n = self._model.add_pdf(path)
        except PermissionError:
            QMessageBox.warning(
                self, "Encrypted PDF",
                f"{path.name} is password-protected. Use the Protect tool to unlock it first.",
            )
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Could not open PDF", f"{path.name}: {exc}")
            return
        self.statusMessage.emit(f"Added {path.name} ({n} pages)", 4000)

    def _selected_rows(self) -> list[int]:
        return sorted({idx.row() for idx in self.view.selectedIndexes()})

    def _rotate_selection(self, delta: int) -> None:
        rows = self._selected_rows() or list(range(self._model.rowCount()))
        if not rows:
            return
        self._model.rotate_rows(rows, delta)

    def _delete_selection(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        self._model.remove_rows(rows)

    def _on_clear(self) -> None:
        if self._model.rowCount() == 0:
            return
        self._model.clear()

    def _on_export(self) -> None:
        pages = self._model.all_pages()
        if not pages:
            return
        self._write_pages(pages, suggested_name="merged.pdf")

    def _on_export_selection(self) -> None:
        pages = self._model.pages_at(self._selected_rows())
        if not pages:
            QMessageBox.information(self, "Nothing selected", "Select pages first.")
            return
        self._write_pages(pages, suggested_name="selection.pdf")

    def _write_pages(self, pages: list, suggested_name: str) -> None:
        default = str(pages[0].source.with_name(suggested_name))
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF", default, "PDF (*.pdf);;All files (*)",
        )
        if not out_path:
            return
        try:
            write_merged(pages, Path(out_path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self._last_export_path = Path(out_path)
        self.show_folder_btn.show()
        self._status_lbl.setText(f"Saved {Path(out_path).name}")
        self.statusMessage.emit(f"Saved {Path(out_path).name} ({len(pages)} pages)", 6000)

    def _on_export_jpeg(self) -> None:
        pages = self._model.all_pages()
        if not pages:
            return
        first_source = pages[0].source
        default_dir = str(first_source.with_suffix(""))
        out_dir = QFileDialog.getExistingDirectory(
            self, "Choose folder for JPEG export", str(first_source.parent),
        )
        if not out_dir:
            return
        folder = Path(out_dir) / first_source.stem
        try:
            written = pages_to_jpeg(pages, folder)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self._last_export_path = folder
        self.show_folder_btn.show()
        self._status_lbl.setText(f"Exported {len(written)} JPEG files")
        self.statusMessage.emit(
            f"Exported {len(written)} pages to {folder.name}/", 6000,
        )

    def _on_show_folder(self) -> None:
        if self._last_export_path is not None:
            reveal_in_file_manager(self._last_export_path)

    def _on_context_menu(self, pos) -> None:  # noqa: ANN001
        idx = self.view.indexAt(pos)
        if not idx.isValid():
            return
        if idx not in self.view.selectedIndexes():
            self.view.clearSelection()
            self.view.setCurrentIndex(idx)
        menu = QMenu(self)
        act_rot_l = QAction("Rotate ↺ 90°", self)
        act_rot_r = QAction("Rotate ↻ 90°", self)
        act_del = QAction("Delete", self)
        act_exp = QAction("Export selection as new PDF…", self)
        act_rot_l.triggered.connect(lambda: self._rotate_selection(-90))
        act_rot_r.triggered.connect(lambda: self._rotate_selection(90))
        act_del.triggered.connect(self._delete_selection)
        act_exp.triggered.connect(self._on_export_selection)
        for a in (act_rot_l, act_rot_r, act_del, act_exp):
            menu.addAction(a)
        menu.exec(self.view.viewport().mapToGlobal(pos))

    # --- drag-drop --------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p:
                self._add_path(Path(p))
        event.acceptProposedAction()

    # --- UI state ---------------------------------------------------

    def _update_state(self, *_a, **_kw) -> None:  # noqa: ANN001
        n_pages = self._model.rowCount()
        n_sources = self._model.unique_sources()
        n_selected = len(self._selected_rows()) if hasattr(self, "view") else 0

        # Stack state.
        self._stack.setCurrentIndex(1 if n_pages > 0 else 0)

        has_pages = n_pages > 0
        has_sel = n_selected > 0

        for btn in (self.rot_left_btn, self.rot_right_btn, self.delete_btn):
            btn.setEnabled(has_sel)
        self.clear_btn.setEnabled(has_pages)
        self.export_btn.setEnabled(has_pages)
        self.export_sel_btn.setEnabled(has_sel)

        # Pills.
        self.count_pill.setText(
            f"{n_sources} file{'s' if n_sources != 1 else ''}"
        )
        if has_sel:
            self.sel_pill.setText(f"{n_selected} selected")
            self.sel_pill.show()
        else:
            self.sel_pill.hide()

        # Status totals.
        self._totals_lbl.setText(
            f"{n_sources} file{'s' if n_sources != 1 else ''} · "
            f"{n_pages} page{'s' if n_pages != 1 else ''} total"
        )

        # Sidebar count.
        self.itemsChanged.emit(n_sources)
