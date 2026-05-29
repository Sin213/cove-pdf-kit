"""Protect tool: add or remove a password from one or more PDFs.

Encrypt/decrypt operations run on a background QThread so the UI event
loop is never blocked, even for large or batch PDF operations.  Progress
is surfaced per-file via Qt signals so the progress bar and status labels
stay responsive.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .icons import make_pixmap
from .pdf_ops import decrypt, encrypt, is_encrypted, read_page_count
from .system import reveal_in_file_manager
from .widgets import DropZone, FileItem, FileListWidget, make_button


class _CryptWorker(QObject):
    """Runs one encrypt or decrypt call on a background thread.

    Signals are emitted back to the UI thread via Qt's queued-connection
    mechanism, so all widget updates stay on the main thread.
    """

    # Emitted when the file finished successfully; carries the output filename.
    succeeded = Signal(str)
    # Emitted on failure; carries the error description.
    failed = Signal(str)

    def __init__(
        self,
        mode: str,
        src: Path,
        dst: Path,
        password: str,
    ) -> None:
        super().__init__()
        self._mode = mode
        self._src = src
        self._dst = dst
        self._password = password

    @Slot()
    def run(self) -> None:
        try:
            if self._mode == "add":
                encrypt(self._src, self._dst, user_password=self._password)
            else:
                decrypt(self._src, self._dst, password=self._password)
            self.succeeded.emit(self._dst.name)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"{self._src.name}: {exc}")


class ProtectView(QWidget):
    statusMessage = Signal(str, int)
    itemsChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sources: list[Path] = []
        self._items: list[FileItem] = []
        self._mode = "add"  # "add" | "remove"
        self._show_pw = False
        self._running = False
        self._last_out_dir: Path | None = None
        # Background-thread state (populated during a run).
        self._crypt_thread: QThread | None = None
        self._crypt_worker: _CryptWorker | None = None
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
        layout = QVBoxLayout(head)
        layout.setContentsMargins(24, 18, 24, 14)
        layout.setSpacing(12)

        row1 = QHBoxLayout()
        row1.setSpacing(12)
        title_block = QWidget()
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        self._title_lbl = QLabel("Protect / Unprotect PDFs")
        self._title_lbl.setProperty("role", "title")
        self._sub_lbl = QLabel("Set a password on each PDF")
        self._sub_lbl.setProperty("role", "subtitle")
        title_layout.addWidget(self._title_lbl)
        title_layout.addWidget(self._sub_lbl)
        row1.addWidget(title_block, stretch=1)

        # Mode radio pills.
        pill_row = QHBoxLayout()
        pill_row.setSpacing(6)
        self.add_pill = QPushButton("●  Add password")
        self.add_pill.setObjectName("radio-pill")
        self.add_pill.setCheckable(True)
        self.add_pill.setAutoExclusive(True)
        self.add_pill.setChecked(True)
        self.add_pill.setCursor(Qt.PointingHandCursor)
        self.add_pill.clicked.connect(lambda: self._set_mode("add"))
        self.remove_pill = QPushButton("○  Remove password")
        self.remove_pill.setObjectName("radio-pill")
        self.remove_pill.setCheckable(True)
        self.remove_pill.setAutoExclusive(True)
        self.remove_pill.setCursor(Qt.PointingHandCursor)
        self.remove_pill.clicked.connect(lambda: self._set_mode("remove"))
        pill_row.addWidget(self.add_pill)
        pill_row.addWidget(self.remove_pill)
        row1.addLayout(pill_row)
        layout.addLayout(row1)

        # Row 2 — toolbar buttons.
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.add_btn = make_button("Add PDFs…", icon="plus")
        self.add_btn.clicked.connect(self._on_add)
        self.clear_btn = make_button("Clear")
        self.clear_btn.clicked.connect(self._on_clear)
        row2.addWidget(self.add_btn)
        row2.addWidget(self.clear_btn)
        row2.addStretch(1)
        layout.addLayout(row2)
        return head

    def _build_content(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._dropzone = DropZone(
            glyph="protect",
            headline="Drop PDFs to protect",
            body="Files are processed locally · originals are kept",
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

        # Password field row.
        pw_row = QHBoxLayout()
        pw_row.setSpacing(14)
        plabel = QLabel("PASSWORD")
        plabel.setProperty("role", "kv-label")
        plabel.setFixedWidth(80)
        pw_row.addWidget(plabel)

        pw_input_row = QHBoxLayout()
        pw_input_row.setSpacing(8)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("password")
        self.password_edit.setFont(_mono_font())
        self.password_edit.textChanged.connect(self._update_state)
        pw_input_row.addWidget(self.password_edit, stretch=1)
        self.show_btn = QPushButton(" Show")
        self.show_btn.setIcon(_icon("eye"))
        self.show_btn.setCheckable(True)
        self.show_btn.setCursor(Qt.PointingHandCursor)
        self.show_btn.toggled.connect(self._on_show_toggled)
        self.show_btn.setMinimumHeight(32)
        pw_input_row.addWidget(self.show_btn)
        pw_row.addLayout(pw_input_row, stretch=1)
        layout.addLayout(pw_row)

        # Confirm field row (only visible in add mode).
        self._confirm_row_widget = QWidget()
        confirm_row = QHBoxLayout(self._confirm_row_widget)
        confirm_row.setContentsMargins(0, 0, 0, 0)
        confirm_row.setSpacing(14)
        clabel = QLabel("CONFIRM")
        clabel.setProperty("role", "kv-label")
        clabel.setFixedWidth(80)
        confirm_row.addWidget(clabel)
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.Password)
        self.confirm_edit.setPlaceholderText("confirm password")
        self.confirm_edit.setFont(_mono_font())
        self.confirm_edit.textChanged.connect(self._update_state)
        confirm_row.addWidget(self.confirm_edit, stretch=1)
        layout.addWidget(self._confirm_row_widget)

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
        self._hint_lbl = QLabel("")
        self._hint_lbl.setStyleSheet(
            f"font-family: '{theme.FONT_MONO}', monospace;"
            f"font-size: 11px; background: transparent;"
        )
        actions.addWidget(self._hint_lbl)
        actions.addStretch(1)
        self.show_folder_btn = make_button("Show folder", icon="upload", kind="outline")
        self.show_folder_btn.setMinimumHeight(36)
        self.show_folder_btn.clicked.connect(self._on_show_folder)
        self.show_folder_btn.hide()
        actions.addWidget(self.show_folder_btn)
        self.run_btn = make_button("Apply", icon="protect", kind="primary")
        self.run_btn.clicked.connect(self._on_run)
        self.run_btn.setMinimumHeight(36)
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
        self._mode_lbl = QLabel("mode: add")
        self._mode_lbl.setStyleSheet(self._status_lbl.styleSheet())
        layout.addWidget(self._mode_lbl)
        return bar

    # ----- Mode + show ------------------------------------------------

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        is_add = mode == "add"
        self.add_pill.setChecked(is_add)
        self.remove_pill.setChecked(not is_add)
        self._sub_lbl.setText(
            "Set a password on each PDF" if is_add
            else "Remove the password from protected PDFs"
        )
        self._dropzone.set_headline(
            "Drop PDFs to protect" if is_add else "Drop PDFs to unlock"
        )
        self._confirm_row_widget.setVisible(is_add)
        self.password_edit.setPlaceholderText(
            "new password" if is_add else "current password"
        )
        self._mode_lbl.setText(f"mode: {mode}")
        self._update_state()

    def _on_show_toggled(self, checked: bool) -> None:
        self._show_pw = checked
        mode = QLineEdit.Normal if checked else QLineEdit.Password
        self.password_edit.setEchoMode(mode)
        self.confirm_edit.setEchoMode(mode)
        self.show_btn.setText(" Hide" if checked else " Show")
        self.show_btn.setIcon(_icon("eye_off" if checked else "eye"))

    # ----- File mgmt --------------------------------------------------

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
        if self._running:
            # The batch is locked once we kick off — silently dropping any
            # new files keeps progress counts honest and prevents the
            # active password from being applied to whatever happens to
            # land mid-run via drag/drop.
            self.statusMessage.emit(
                f"Skipped {path.name} — batch in progress", 3000,
            )
            return
        if path.suffix.lower() != ".pdf":
            self.statusMessage.emit(f"Skipped {path.name} (not a PDF)", 3000)
            return
        if path in self._sources:
            return
        try:
            pages = 0 if is_encrypted(path) else read_page_count(path)
        except Exception:  # noqa: BLE001
            pages = 0
        encrypted = is_encrypted(path)
        suffix = " (encrypted)" if encrypted else ""
        self._sources.append(path)
        self._items.append(FileItem(
            name=path.name + suffix,
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

    # ----- Run --------------------------------------------------------

    def _on_run(self) -> None:
        password = self.password_edit.text()
        if not password:
            QMessageBox.warning(self, "Password required", "Enter a password first.")
            return
        if self._mode == "add" and password != self.confirm_edit.text():
            QMessageBox.warning(self, "Passwords don't match",
                                "Confirmation password doesn't match.")
            return
        if not self._sources:
            return

        self._running = True
        self.show_folder_btn.hide()
        self._last_out_dir = self._sources[0].parent if self._sources else None
        self._update_state()
        self._file_list.set_removable(False)
        # Snapshot the source list and the active mode so the batch is
        # immune to mid-run mutation (drag-drops, manual additions, etc.).
        self._batch_sources: list[Path] = list(self._sources)
        self._batch_mode = self._mode
        self.progress.setRange(0, len(self._batch_sources))
        self.progress.setValue(0)
        self._prog_label.setText("Working")
        self._pct_lbl.setText("0%")
        for i in range(len(self._items)):
            self._file_list.update_status(i, "run" if i == 0 else "queued")

        self._batch_pw = password
        self._batch_idx = 0
        self._batch_successes: list[str] = []
        self._batch_failures: list[str] = []
        self._run_next()

    def _run_next(self) -> None:
        i = self._batch_idx
        # Use the snapshotted batch (fixed at run start) so any
        # additions that slip through after _running is set still don't
        # change which files we touch.
        if i >= len(self._batch_sources):
            self._finalize_run()
            return
        src = self._batch_sources[i]
        mode = self._batch_mode
        self._file_list.update_status(i, "run")
        self._status_lbl.setText(
            f"{'Encrypting' if mode == 'add' else 'Decrypting'} {src.name}…"
        )
        suffix = "-protected" if mode == "add" else "-unprotected"
        dst = src.with_name(f"{src.stem}{suffix}.pdf")

        # Dispatch the blocking I/O to a fresh background QThread.
        worker = _CryptWorker(mode, src, dst, self._batch_pw)
        thread = QThread(self)
        worker.moveToThread(thread)
        worker.succeeded.connect(self._on_file_done, Qt.QueuedConnection)
        worker.failed.connect(self._on_file_failed, Qt.QueuedConnection)
        thread.started.connect(worker.run)
        # Clean up thread once the worker slot returns.
        worker.succeeded.connect(thread.quit, Qt.QueuedConnection)
        worker.failed.connect(thread.quit, Qt.QueuedConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._crypt_thread = thread
        self._crypt_worker = worker
        thread.start()

    def _on_file_done(self, out_name: str) -> None:
        i = self._batch_idx
        self._batch_successes.append(out_name)
        self._file_list.update_status(i, "done")
        self._advance_batch()

    def _on_file_failed(self, err: str) -> None:
        i = self._batch_idx
        self._batch_failures.append(err)
        self._file_list.update_status(i, "idle")
        self._advance_batch()

    def _advance_batch(self) -> None:
        self._batch_idx += 1
        self.progress.setValue(self._batch_idx)
        total = max(1, len(self._batch_sources))
        pct = int(round(self._batch_idx / total * 100))
        self._pct_lbl.setText(f"{pct}%")
        self._run_next()

    def _finalize_run(self) -> None:
        self._running = False
        self._file_list.set_removable(True)
        self._prog_label.setText("Done")
        self.progress.setValue(self.progress.maximum())
        self._pct_lbl.setText("100%")
        if self._batch_failures:
            QMessageBox.warning(
                self, "Done with errors",
                f"Saved {len(self._batch_successes)} file(s).\n\n"
                "Failed:\n" + "\n".join(self._batch_failures),
            )
        else:
            verb = "protected" if self._mode == "add" else "unlocked"
            self._status_lbl.setText(
                f"{len(self._batch_successes)} files {verb}"
            )
            self.statusMessage.emit(
                f"Saved {len(self._batch_successes)} file(s)", 6000,
            )
        if self._batch_successes and self._last_out_dir is not None:
            self.show_folder_btn.show()
        self._update_state()

    def _on_show_folder(self) -> None:
        if self._last_out_dir is not None:
            reveal_in_file_manager(self._last_out_dir)

    def _reset_progress(self) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._prog_label.setText("Idle")
        self._pct_lbl.setText("—")
        self._hint_lbl.setText("")

    # ----- State ------------------------------------------------------

    def _update_state(self, *_a, **_kw) -> None:  # noqa: ANN001
        n = len(self._items)
        self._stack.setCurrentIndex(1 if n > 0 else 0)
        password = self.password_edit.text() if hasattr(self, "password_edit") else ""
        confirm = self.confirm_edit.text() if hasattr(self, "confirm_edit") else ""

        # Match the underlying pikepdf.Encryption() contract: any
        # non-empty password is acceptable. (An earlier draft forced a
        # 4-char minimum, which silently blocked short-but-valid PDF
        # passwords without aligning with any documented policy.)
        if self._mode == "add":
            valid_pw = len(password) > 0 and password == confirm
        else:
            valid_pw = len(password) > 0

        self.run_btn.setEnabled(not self._running and n > 0 and valid_pw)
        self.run_btn.setText(
            "Apply" if not self._running else (
                "Encrypting…" if self._mode == "add" else "Decrypting…"
            )
        )
        self.add_btn.setEnabled(not self._running)
        self.clear_btn.setEnabled(not self._running and n > 0)
        self.password_edit.setEnabled(not self._running)
        self.confirm_edit.setEnabled(not self._running)
        self.show_btn.setEnabled(not self._running)
        self.add_pill.setEnabled(not self._running)
        self.remove_pill.setEnabled(not self._running)

        # Hint text — only the mismatch warning, since any non-empty
        # password is acceptable.
        if (self._mode == "add" and len(password) > 0
                and len(confirm) > 0 and password != confirm):
            self._hint_lbl.setText("Passwords don't match")
            self._hint_lbl.setStyleSheet(
                f"color: {theme.DANGER};"
                f"font-family: '{theme.FONT_MONO}', monospace;"
                f"font-size: 11px; background: transparent;"
            )
        else:
            self._hint_lbl.setText("")

        if not self._running:
            self._status_lbl.setText(
                "Ready" if n == 0 else f"{n} file{'s' if n != 1 else ''} ready"
            )
        self.itemsChanged.emit(n)

    # ----- Drag-drop --------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        # Refuse drops while the batch is running. _add() also guards this
        # path, but rejecting the drag-enter early gives the user the
        # standard "no-drop" cursor instead of a deceptive "accepted, then
        # silently skipped" experience.
        if self._running:
            event.ignore()
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        if self._running:
            event.ignore()
            return
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p:
                self._add(Path(p))


def _fmt_bytes(n: int) -> str:
    kb = n / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    return f"{kb/1024:.2f} MB"


def _mono_font():
    from PySide6.QtGui import QFont
    return QFont(theme.FONT_MONO, 10)


def _icon(name: str):
    from PySide6.QtGui import QIcon
    return QIcon(make_pixmap(name, 14, theme.TEXT_DIM, 1.8))
