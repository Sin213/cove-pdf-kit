"""Protect tool: add or remove a password from one or more PDFs.

Both operations run on the UI thread — they're fast (pikepdf just
rewrites the PDF trailer, not the content) and the user sees immediate
results.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from .pdf_ops import decrypt, encrypt, is_encrypted


class ProtectView(QWidget):
    statusMessage = Signal(str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sources: list[Path] = []
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header = QLabel("Protect / Unprotect PDFs")
        header.setStyleSheet("font-size:18px; font-weight:600; color:#cfd0d4;")
        root.addWidget(header)

        mode_row = QHBoxLayout()
        self.encrypt_radio = QRadioButton("Add password")
        self.encrypt_radio.setChecked(True)
        self.decrypt_radio = QRadioButton("Remove password")
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.encrypt_radio)
        self._mode_group.addButton(self.decrypt_radio)
        self.encrypt_radio.toggled.connect(self._on_mode_change)
        mode_row.addWidget(self.encrypt_radio)
        mode_row.addWidget(self.decrypt_radio)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

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
        self.list.setMinimumHeight(200)
        root.addWidget(self.list, stretch=1)

        form = QFormLayout()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("password")
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.Password)
        self.confirm_edit.setPlaceholderText("confirm password")
        self.show_check = QPushButton("Show")
        self.show_check.setCheckable(True)
        self.show_check.setFixedWidth(72)
        self.show_check.toggled.connect(self._on_show_toggled)

        pw_row = QHBoxLayout()
        pw_row.addWidget(self.password_edit, stretch=1)
        pw_row.addWidget(self.show_check)
        pw_container = QWidget()
        pw_container.setLayout(pw_row)

        form.addRow("Password", pw_container)
        form.addRow("Confirm", self.confirm_edit)
        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.run_btn = QPushButton("Apply")
        self.run_btn.setStyleSheet(
            "QPushButton { background:#2563eb; color:white; font-weight:600; "
            "border:none; border-radius:6px; padding:8px 16px; }"
            "QPushButton:hover { background:#1d4ed8; }"
            "QPushButton:disabled { background:#3a4150; color:#9aa0ad; }"
        )
        self.run_btn.clicked.connect(self._on_run)
        buttons.addWidget(self.run_btn)
        root.addLayout(buttons)

        self._update_controls()

    # --- mode / password visibility --------------------------------

    def _on_mode_change(self) -> None:
        encrypt_mode = self.encrypt_radio.isChecked()
        self.confirm_edit.setVisible(encrypt_mode)
        self.password_edit.setPlaceholderText("new password" if encrypt_mode else "current password")
        self.run_btn.setText("Add password" if encrypt_mode else "Remove password")

    def _on_show_toggled(self, checked: bool) -> None:
        mode = QLineEdit.Normal if checked else QLineEdit.Password
        self.password_edit.setEchoMode(mode)
        self.confirm_edit.setEchoMode(mode)

    # --- file list -------------------------------------------------

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
        tag = " (encrypted)" if is_encrypted(path) else ""
        QListWidgetItem(f"{path.name}{tag}", self.list)
        self._update_controls()

    def _on_clear(self) -> None:
        self._sources.clear()
        self.list.clear()
        self._update_controls()

    # --- run -------------------------------------------------------

    def _on_run(self) -> None:
        password = self.password_edit.text()
        if not password:
            QMessageBox.warning(self, "Password required", "Enter a password first.")
            return
        if self.encrypt_radio.isChecked():
            if password != self.confirm_edit.text():
                QMessageBox.warning(self, "Passwords don't match",
                                    "Confirmation password doesn't match.")
                return
        if not self._sources:
            return

        successes: list[str] = []
        failures: list[str] = []
        for src in self._sources:
            suffix = "-protected" if self.encrypt_radio.isChecked() else "-unprotected"
            dst = src.with_name(f"{src.stem}{suffix}.pdf")
            try:
                if self.encrypt_radio.isChecked():
                    encrypt(src, dst, user_password=password)
                else:
                    decrypt(src, dst, password=password)
                successes.append(dst.name)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{src.name}: {exc}")

        msg = ""
        if successes:
            msg += f"Saved {len(successes)} file(s).\n"
        if failures:
            msg += "Failed:\n" + "\n".join(failures)
        if failures:
            QMessageBox.warning(self, "Done with errors", msg)
        else:
            self.statusMessage.emit(f"Saved {len(successes)} file(s)", 6000)

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
