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
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .pdf_ops import compress


@dataclass
class CompressJob:
    sources: list[Path]
    out_dir: Path
    suffix: str
    quality: str


class _Worker(QObject):
    progress = Signal(int, int)         # done, total
    item_done = Signal(str, int, int)   # source name, before_bytes, after_bytes
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
                before = src.stat().st_size
                dst = self._job.out_dir / f"{src.stem}{self._job.suffix}.pdf"
                compress(src, dst, quality=self._job.quality)
                after = dst.stat().st_size
                self.item_done.emit(src.name, before, after)
                self.progress.emit(i + 1, total)
            self.finished.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class CompressView(QWidget):
    statusMessage = Signal(str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sources: list[Path] = []
        self._thread: QThread | None = None
        self._worker: _Worker | None = None
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header = QLabel("Compress PDFs")
        header.setStyleSheet("font-size:18px; font-weight:600; color:#cfd0d4;")
        root.addWidget(header)

        toolbar = QHBoxLayout()
        self.add_btn = QPushButton("Add PDFs…")
        self.add_btn.clicked.connect(self._on_add)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._on_clear)
        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.clear_btn)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self.list = QListWidget()
        self.list.setStyleSheet(
            "QListWidget { background:#0e1116; border:1px solid #2a2f3a; "
            "border-radius:6px; color:#cfd0d4; padding:4px; }"
        )
        self.list.setMinimumHeight(220)
        root.addWidget(self.list, stretch=1)

        form = QFormLayout()
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("High quality (smallest savings)", "high")
        self.quality_combo.addItem("Balanced", "medium")
        self.quality_combo.addItem("Aggressive (smaller file)", "low")
        self.quality_combo.setCurrentIndex(1)

        self.suffix_label = QLabel('Saved as "<name>-compressed.pdf" beside each source.')
        self.suffix_label.setStyleSheet("color:#7a8294;")

        form.addRow("Quality", self.quality_combo)
        root.addLayout(form)
        root.addWidget(self.suffix_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("idle")
        root.addWidget(self.progress)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.run_btn = QPushButton("Compress")
        self.run_btn.setStyleSheet(
            "QPushButton { background:#2563eb; color:white; font-weight:600; "
            "border:none; border-radius:6px; padding:8px 16px; }"
            "QPushButton:hover { background:#1d4ed8; }"
            "QPushButton:disabled { background:#3a4150; color:#9aa0ad; }"
        )
        self.run_btn.clicked.connect(self._on_run)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.run_btn)
        root.addLayout(buttons)

        self._update_controls()

    def _on_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add PDFs", "", "PDF files (*.pdf);;All files (*)",
        )
        for p in paths:
            self._add(Path(p))

    def _add(self, path: Path) -> None:
        if path.suffix.lower() != ".pdf":
            self.statusMessage.emit(f"Skipped {path.name} (not a PDF)", 3000)
            return
        if path in self._sources:
            return
        self._sources.append(path)
        size_kb = path.stat().st_size / 1024
        if size_kb < 1024:
            size = f"{size_kb:.1f} KB"
        else:
            size = f"{size_kb/1024:.1f} MB"
        QListWidgetItem(f"{path.name}  •  {size}", self.list)
        self._update_controls()

    def _on_clear(self) -> None:
        self._sources.clear()
        self.list.clear()
        self._update_controls()

    def _on_run(self) -> None:
        if not self._sources:
            return
        # Default output dir: same as first source's parent.
        out_dir = self._sources[0].parent
        job = CompressJob(
            sources=list(self._sources),
            out_dir=out_dir,
            suffix="-compressed",
            quality=self.quality_combo.currentData(),
        )
        self.progress.setRange(0, len(job.sources))
        self.progress.setValue(0)
        self.progress.setFormat("starting…")
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        thread = QThread(self)
        worker = _Worker(job)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress, Qt.QueuedConnection)
        worker.item_done.connect(self._on_item_done, Qt.QueuedConnection)
        worker.finished.connect(thread.quit)
        worker.failed.connect(self._on_failed, Qt.QueuedConnection)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._reset)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setValue(done)
        self.progress.setFormat(f"{done}/{total}")

    def _on_item_done(self, name: str, before: int, after: int) -> None:
        saved = max(0, before - after)
        pct = saved / before * 100 if before else 0
        self.statusMessage.emit(
            f"{name}: {_fmt_bytes(before)} → {_fmt_bytes(after)}  (−{pct:.0f}%)", 6000,
        )

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()

    def _on_failed(self, msg: str) -> None:
        QMessageBox.warning(self, "Compress failed", msg)

    def _reset(self) -> None:
        self._thread = None
        self._worker = None
        self.run_btn.setEnabled(bool(self._sources))
        self.cancel_btn.setEnabled(False)
        self.progress.setFormat("done")

    def _update_controls(self) -> None:
        has = bool(self._sources)
        self.run_btn.setEnabled(has)
        self.clear_btn.setEnabled(has)

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
