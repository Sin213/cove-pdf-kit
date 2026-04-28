"""Compress tool: drop PDFs, pick quality, save compressed copies.

Runs one pikepdf pass per file on a background thread so the UI stays
responsive for multi-file batches.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .pdf_ops import compress, read_page_count
from .system import reveal_in_file_manager
from .widgets import DropZone, FileItem, FileListWidget, make_button


@dataclass
class CompressJob:
    sources: list[Path]
    out_dir: Path
    suffix: str
    quality: str


class _Worker(QObject):
    progress = Signal(int, int)               # done, total
    item_started = Signal(int)                # row index that just started
    item_done = Signal(int, str, int, int)    # row index, name, before, after
    finished = Signal()
    failed = Signal(str)

    def __init__(self, job: CompressJob) -> None:
        super().__init__()
        self._job = job
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        total = len(self._job.sources)
        try:
            for i, src in enumerate(self._job.sources):
                if self._cancel:
                    break
                self.item_started.emit(i)
                before = src.stat().st_size
                dst = self._job.out_dir / f"{src.stem}{self._job.suffix}.pdf"
                compress(src, dst, quality=self._job.quality)
                after = dst.stat().st_size
                self.item_done.emit(i, src.name, before, after)
                self.progress.emit(i + 1, total)
            self.finished.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class CompressView(QWidget):
    statusMessage = Signal(str, int)
    itemsChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sources: list[Path] = []
        self._items: list[FileItem] = []
        self._thread: QThread | None = None
        self._worker: _Worker | None = None
        self._total_before = 0
        self._total_after = 0
        self._last_out_dir: Path | None = None
        self._build_ui()
        self.setAcceptDrops(True)
        self._update_state()

    # ----- UI build ----------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_head())
        root.addWidget(self._build_content(), stretch=1)
        root.addWidget(self._build_footer())
        root.addWidget(self._build_statusbar())

    def _build_head(self) -> QWidget:
        head = QWidget()
        head.setObjectName("cove-head")
        layout = QHBoxLayout(head)
        layout.setContentsMargins(24, 18, 24, 14)
        layout.setSpacing(12)

        title_block = QWidget()
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        title = QLabel("Compress PDFs")
        title.setProperty("role", "title")
        sub = QLabel("Reduce file size · saved as <name>-compressed.pdf beside each source")
        sub.setProperty("role", "subtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(sub)
        layout.addWidget(title_block, stretch=1)

        self.add_btn = make_button("Add PDFs…", icon="plus")
        self.add_btn.clicked.connect(self._on_add)
        self.clear_btn = make_button("Clear")
        self.clear_btn.clicked.connect(self._on_clear)
        layout.addWidget(self.add_btn)
        layout.addWidget(self.clear_btn)
        return head

    def _build_content(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(0)

        self._stack = QStackedWidget()

        self._dropzone = DropZone(
            glyph="compress",
            headline="Drop PDFs to compress",
            body="Originals are left untouched · output written next to each source file",
        )
        self._dropzone.clicked.connect(self._on_add)
        self._dropzone.filesDropped.connect(self._on_files_dropped)
        self._stack.addWidget(self._dropzone)

        self._file_list = FileListWidget()
        self._file_list.removeRequested.connect(self._remove_at)
        self._stack.addWidget(self._file_list)

        layout.addWidget(self._stack, stretch=1)
        return wrapper

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("cove-footer")
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(24, 14, 24, 16)
        layout.setSpacing(12)

        # Quality field row.
        field_row = QHBoxLayout()
        field_row.setSpacing(14)
        qlabel = QLabel("QUALITY")
        qlabel.setProperty("role", "kv-label")
        qlabel.setFixedWidth(80)
        field_row.addWidget(qlabel)
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("High quality (smallest savings)", "high")
        self.quality_combo.addItem("Balanced", "medium")
        self.quality_combo.addItem("Aggressive (smaller file)", "low")
        self.quality_combo.setCurrentIndex(1)
        self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
        field_row.addWidget(self.quality_combo, stretch=1)
        layout.addLayout(field_row)

        # Progress row.
        prog_row = QHBoxLayout()
        prog_row.setSpacing(12)
        self._prog_label = QLabel("Idle")
        self._prog_label.setStyleSheet(
            f"color: {theme.TEXT_FAINT};"
            f"font-family: '{theme.FONT_MONO}', monospace;"
            f"font-size: 10.5px;"
            f"letter-spacing: 0.06em;"
            f"text-transform: uppercase;"
            f"background: transparent;"
        )
        self._prog_label.setFixedWidth(80)
        prog_row.addWidget(self._prog_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        prog_row.addWidget(self.progress, stretch=1)
        self._pct_lbl = QLabel("—")
        self._pct_lbl.setFixedWidth(50)
        self._pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._pct_lbl.setStyleSheet(
            f"color: {theme.TEXT_DIM};"
            f"font-family: '{theme.FONT_MONO}', monospace;"
            f"font-size: 11px; background: transparent;"
        )
        prog_row.addWidget(self._pct_lbl)
        layout.addLayout(prog_row)

        # Action row.
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self._savings_lbl = QLabel("")
        self._savings_lbl.setStyleSheet(
            f"color: {theme.TEXT_FAINT};"
            f"font-family: '{theme.FONT_MONO}', monospace;"
            f"font-size: 11px; background: transparent;"
        )
        actions.addWidget(self._savings_lbl)
        actions.addStretch(1)
        self.show_folder_btn = make_button("Show folder", icon="upload", kind="outline")
        self.show_folder_btn.setMinimumHeight(36)
        self.show_folder_btn.clicked.connect(self._on_show_folder)
        self.show_folder_btn.hide()
        actions.addWidget(self.show_folder_btn)
        self.cancel_btn = make_button("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.setMinimumHeight(36)
        self.run_btn = make_button("Compress", icon="compress", kind="primary")
        self.run_btn.clicked.connect(self._on_run)
        self.run_btn.setMinimumHeight(36)
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.run_btn)
        layout.addLayout(actions)
        return footer

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
        from .app import _PulseDot
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
        self._mode_lbl = QLabel("quality: medium")
        self._mode_lbl.setStyleSheet(self._status_lbl.styleSheet())
        layout.addWidget(self._mode_lbl)
        return bar

    # ----- File mgmt ---------------------------------------------------

    def _on_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add PDFs", "", "PDF files (*.pdf);;All files (*)",
        )
        for p in paths:
            self._add(Path(p))

    def _on_files_dropped(self, paths: list[str]) -> None:
        for p in paths:
            self._add(Path(p))

    def _add(self, path: Path) -> None:
        if path.suffix.lower() != ".pdf":
            self.statusMessage.emit(f"Skipped {path.name} (not a PDF)", 3000)
            return
        if path in self._sources:
            return
        try:
            pages = read_page_count(path)
        except PermissionError:
            pages = 0
        except Exception:  # noqa: BLE001
            pages = 0
        self._sources.append(path)
        self._items.append(FileItem(
            name=path.name,
            size_str=_fmt_bytes(path.stat().st_size),
            pages=pages,
            status="idle",
        ))
        self._refresh_list()
        self._update_state()

    def _on_clear(self) -> None:
        self._sources.clear()
        self._items.clear()
        self._refresh_list()
        self._reset_progress()
        self._update_state()

    def _remove_at(self, idx: int) -> None:
        if 0 <= idx < len(self._sources):
            del self._sources[idx]
            del self._items[idx]
            self._refresh_list()
            self._update_state()

    def _refresh_list(self) -> None:
        self._file_list.set_items(self._items)

    # ----- Run ---------------------------------------------------------

    def _on_run(self) -> None:
        if not self._sources:
            return
        out_dir = self._sources[0].parent
        self._last_out_dir = out_dir
        self.show_folder_btn.hide()
        job = CompressJob(
            sources=list(self._sources),
            out_dir=out_dir,
            suffix="-compressed",
            quality=self.quality_combo.currentData(),
        )
        self._total_before = 0
        self._total_after = 0
        self.progress.setRange(0, len(job.sources))
        self.progress.setValue(0)
        self._prog_label.setText("Compressing")
        self._pct_lbl.setText("0%")
        self._savings_lbl.setText("")
        self.run_btn.setEnabled(False)
        self.add_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._file_list.set_removable(False)
        # Mark first as run, rest as queued.
        for i in range(len(self._items)):
            self._file_list.update_status(i, "run" if i == 0 else "queued")

        thread = QThread(self)
        worker = _Worker(job)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress, Qt.QueuedConnection)
        worker.item_started.connect(self._on_item_started, Qt.QueuedConnection)
        worker.item_done.connect(self._on_item_done, Qt.QueuedConnection)
        worker.finished.connect(thread.quit)
        worker.failed.connect(self._on_failed, Qt.QueuedConnection)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._reset_after_run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setValue(done)
        pct = int(round(done / total * 100)) if total else 0
        self._pct_lbl.setText(f"{pct}%")

    def _on_item_started(self, idx: int) -> None:
        self._file_list.update_status(idx, "run")
        if 0 <= idx < len(self._items):
            self._status_lbl.setText(f"Compressing {self._items[idx].name}…")

    def _on_item_done(self, idx: int, name: str, before: int, after: int) -> None:
        saved = max(0, before - after)
        pct = saved / before * 100 if before else 0
        self.statusMessage.emit(
            f"{name}: {_fmt_bytes(before)} → {_fmt_bytes(after)}  (−{pct:.0f}%)", 6000,
        )
        self._total_before += before
        self._total_after += after
        self._file_list.update_status(idx, "done")
        if 0 <= idx < len(self._items):
            self._items[idx].size_str = _fmt_bytes(after)
            self._file_list.update_size(idx, _fmt_bytes(after))

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()

    def _on_failed(self, msg: str) -> None:
        QMessageBox.warning(self, "Compress failed", msg)

    def _reset_after_run(self) -> None:
        self._thread = None
        self._worker = None
        self.run_btn.setEnabled(bool(self._sources))
        self.add_btn.setEnabled(True)
        self.clear_btn.setEnabled(bool(self._sources))
        self.cancel_btn.setEnabled(False)
        self._file_list.set_removable(True)
        self._prog_label.setText("Done")
        self.progress.setValue(self.progress.maximum())
        self._pct_lbl.setText("100%")
        if self._total_before:
            saved = max(0, self._total_before - self._total_after)
            pct = int(round(saved / self._total_before * 100)) if self._total_before else 0
            if saved == 0:
                self._savings_lbl.setText(
                    f"<span style='color:{theme.WARN}'>"
                    f"already optimized · {_fmt_bytes(self._total_before)} kept</span>"
                )
                self._status_lbl.setText(
                    f"{len(self._items)} file{'s' if len(self._items) != 1 else ''} "
                    f"already optimized — copied originals"
                )
            else:
                self._savings_lbl.setText(
                    f"{_fmt_bytes(self._total_before)} → "
                    f"<b style='color:{theme.GOOD}'>{_fmt_bytes(self._total_after)}</b>"
                    f" · saved {pct}%"
                )
                self._status_lbl.setText(
                    f"Saved {pct}% across {len(self._items)} "
                    f"file{'s' if len(self._items) != 1 else ''}"
                )
            if self._last_out_dir is not None:
                self.show_folder_btn.show()

    def _on_show_folder(self) -> None:
        if self._last_out_dir is not None:
            reveal_in_file_manager(self._last_out_dir)

    def _reset_progress(self) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._prog_label.setText("Idle")
        self._pct_lbl.setText("—")
        self._savings_lbl.setText("")

    # ----- State -------------------------------------------------------

    def _update_state(self, *_a, **_kw) -> None:  # noqa: ANN001
        running = self._worker is not None
        n = len(self._items)
        self._stack.setCurrentIndex(1 if n > 0 else 0)
        self.run_btn.setEnabled(n > 0 and not running)
        self.clear_btn.setEnabled(n > 0 and not running)
        self.add_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        if not running:
            self._status_lbl.setText("Ready" if n == 0 else f"{n} file{'s' if n != 1 else ''} ready")
        self.itemsChanged.emit(n)

    def _on_quality_changed(self, _idx: int) -> None:
        q = self.quality_combo.currentData()
        labels = {"high": "high", "medium": "medium", "low": "aggressive"}
        self._mode_lbl.setText(f"quality: {labels.get(q, q)}")

    # ----- Drag-drop ---------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p:
                self._add(Path(p))


def _fmt_bytes(n: int) -> str:
    kb = n / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    return f"{kb/1024:.2f} MB"
