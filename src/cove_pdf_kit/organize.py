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
    QPixmap,
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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .pdf_ops import PageRef, read_page_count, write_merged
from .rendering import ThumbnailService


THUMB_WIDTH = 160  # device pixels
THUMB_HEIGHT = 220


class PageModel(QAbstractListModel):
    """Flat ordered list of :class:`PageRef` values."""

    PageRole = Qt.UserRole + 1

    def __init__(self, thumbs: ThumbnailService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pages: list[PageRef] = []
        self._thumbs = thumbs
        # Cache and request-tracking keyed by PageRef so row moves / deletes
        # don't invalidate already-rendered thumbnails.
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
    #
    # QListView's InternalMove does DnD via mime data; the model has to
    # serialize the dragged rows, then apply a row-wise move on drop.

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
        # Target row: row < 0 means dropped after last
        dest = row if row >= 0 else len(self._pages)
        # Pull source pages out in original order.
        moving = [self._pages[r] for r in src_rows]
        # Remove from the end of the list first so earlier indices stay valid.
        for r in sorted(src_rows, reverse=True):
            self.beginRemoveRows(QModelIndex(), r, r)
            del self._pages[r]
            self.endRemoveRows()
            # Adjust dest if rows before it were removed.
            if r < dest:
                dest -= 1
        dest = max(0, min(len(self._pages), dest))
        self.beginInsertRows(QModelIndex(), dest, dest + len(moving) - 1)
        for offset, page in enumerate(moving):
            self._pages.insert(dest + offset, page)
        self.endInsertRows()
        return True

    # We do the removal inside dropMimeData, so tell the view not to call
    # removeRows afterwards.
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
        """Append every page of ``path`` to the model. Returns the number
        of pages added."""
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
        # Poke every row that currently maps to this ref so the view picks
        # up the new icon.
        for r, p in enumerate(self._pages):
            if p == ref:
                idx = self.index(r)
                self.dataChanged.emit(idx, idx, [Qt.DecorationRole])


def _placeholder_icon() -> QIcon:
    pix = QPixmap(THUMB_WIDTH, THUMB_HEIGHT)
    pix.fill(Qt.gray)
    return QIcon(pix)


class OrganizeView(QWidget):
    statusMessage = Signal(str, int)   # text, timeout ms

    def __init__(self, thumbs: ThumbnailService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._thumbs = thumbs
        self._model = PageModel(thumbs, self)
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        toolbar = QHBoxLayout()
        self.add_btn = QPushButton("Add PDFs…")
        self.add_btn.clicked.connect(self._on_add_clicked)
        self.rot_left_btn = QPushButton("Rotate ↺")
        self.rot_left_btn.clicked.connect(lambda: self._rotate_selection(-90))
        self.rot_right_btn = QPushButton("Rotate ↻")
        self.rot_right_btn.clicked.connect(lambda: self._rotate_selection(90))
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete_selection)
        self.clear_btn = QPushButton("Clear all")
        self.clear_btn.clicked.connect(self._on_clear)
        self.export_btn = QPushButton("Export PDF…")
        self.export_btn.setStyleSheet(
            "QPushButton { background:#2563eb; color:white; font-weight:600; "
            "border:none; border-radius:6px; padding:6px 14px; }"
            "QPushButton:hover { background:#1d4ed8; }"
            "QPushButton:disabled { background:#3a4150; color:#9aa0ad; }"
        )
        self.export_btn.clicked.connect(self._on_export)
        self.export_selected_btn = QPushButton("Export selection…")
        self.export_selected_btn.clicked.connect(self._on_export_selection)
        toolbar.addWidget(self.add_btn)
        toolbar.addSpacing(8)
        toolbar.addWidget(self.rot_left_btn)
        toolbar.addWidget(self.rot_right_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addSpacing(8)
        toolbar.addWidget(self.clear_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self.export_selected_btn)
        toolbar.addWidget(self.export_btn)
        root.addLayout(toolbar)

        self.view = QListView()
        self.view.setModel(self._model)
        self.view.setViewMode(QListView.IconMode)
        self.view.setFlow(QListView.LeftToRight)
        self.view.setWrapping(True)
        self.view.setResizeMode(QListView.Adjust)
        self.view.setMovement(QListView.Snap)
        self.view.setUniformItemSizes(True)
        self.view.setIconSize(QSize(THUMB_WIDTH, THUMB_HEIGHT))
        self.view.setSpacing(10)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setDragDropMode(QAbstractItemView.InternalMove)
        self.view.setDefaultDropAction(Qt.MoveAction)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        self.view.setStyleSheet(
            "QListView { background:#0e1116; border:1px solid #2a2f3a; border-radius:6px; }"
            "QListView::item { color:#cfd0d4; padding:4px; }"
            "QListView::item:selected { background:#1f3a5c; border-radius:4px; }"
        )

        self.placeholder = QLabel(
            "Drop PDFs here, or click \"Add PDFs…\"\n"
            "Then drag the thumbnails to reorder, right-click for rotate / delete / split."
        )
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet(
            "color:#7a8294; font-size:14px; padding:48px;"
            "border:2px dashed #4a5160; border-radius:8px; background:#14181f;"
        )
        root.addWidget(self.placeholder, stretch=1)
        root.addWidget(self.view, stretch=1)
        self.view.hide()
        self._update_controls()
        self._model.rowsInserted.connect(self._update_controls)
        self._model.rowsRemoved.connect(self._update_controls)
        self._model.modelReset.connect(self._update_controls)

    # --- actions ----------------------------------------------------

    def _on_add_clicked(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add PDFs", "", "PDF files (*.pdf);;All files (*)",
        )
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
        self.statusMessage.emit(f"Saved {Path(out_path).name} ({len(pages)} pages)", 6000)

    def _on_context_menu(self, pos) -> None:  # noqa: ANN001
        idx = self.view.indexAt(pos)
        if not idx.isValid():
            return
        # Ensure the clicked row is included in the selection.
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

    def _update_controls(self, *_a, **_kw) -> None:  # noqa: ANN001
        has_pages = self._model.rowCount() > 0
        self.view.setVisible(has_pages)
        self.placeholder.setVisible(not has_pages)
        for btn in (
            self.rot_left_btn, self.rot_right_btn, self.delete_btn,
            self.clear_btn, self.export_btn, self.export_selected_btn,
        ):
            btn.setEnabled(has_pages)
