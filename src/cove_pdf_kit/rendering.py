"""Async PDF page rendering via pypdfium2, wrapped for Qt.

PDFium is thread-safe for rendering as long as each document handle
stays on one thread. We hold one document per open PDF on a background
thread, queue render requests across a signal, and emit :class:`QImage`
results back to the UI. Thumbnails are cached by (path, page, rotation,
target_width).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QImage


@dataclass(frozen=True)
class ThumbRequest:
    token: int
    source: Path
    page_index: int
    rotation: int
    target_width: int


def _pil_to_qimage(img: Image.Image) -> QImage:
    img = img.convert("RGB")
    data = img.tobytes("raw", "RGB")
    qi = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
    return qi.copy()


class _Worker(QObject):
    rendered = Signal(int, QImage)
    failed = Signal(int, str)

    def __init__(self) -> None:
        super().__init__()
        self._docs: dict[Path, pdfium.PdfDocument] = {}

    @Slot(object)
    def render(self, req: ThumbRequest) -> None:
        try:
            doc = self._docs.get(req.source)
            if doc is None:
                doc = pdfium.PdfDocument(str(req.source))
                self._docs[req.source] = doc
            page = doc[req.page_index]
            w_pt = page.get_width()  # in PDF points
            scale = max(0.2, min(4.0, req.target_width / max(1.0, w_pt)))
            pil = page.render(scale=scale, rotation=req.rotation).to_pil()
            self.rendered.emit(req.token, _pil_to_qimage(pil))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(req.token, str(exc))

    @Slot(object)
    def close_source(self, source: Path) -> None:
        doc = self._docs.pop(source, None)
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass

    @Slot()
    def close_all(self) -> None:
        for doc in list(self._docs.values()):
            try:
                doc.close()
            except Exception:
                pass
        self._docs.clear()


class ThumbnailService(QObject):
    """UI-side handle. Starts a worker thread, ships render requests to
    it via a queued signal, caches results."""

    rendered = Signal(int, QImage)
    _submit = Signal(object)
    _close_source = Signal(object)
    _close_all = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._worker = _Worker()
        self._worker.moveToThread(self._thread)
        self._submit.connect(self._worker.render, Qt.QueuedConnection)
        self._close_source.connect(self._worker.close_source, Qt.QueuedConnection)
        self._close_all.connect(self._worker.close_all, Qt.QueuedConnection)
        self._worker.rendered.connect(self._on_rendered, Qt.QueuedConnection)
        self._thread.start()

        self._cache: dict[tuple, QImage] = {}
        self._pending: dict[int, tuple] = {}
        self._next_token = 1

    def request(self, source: Path, page_index: int, rotation: int, target_width: int) -> int:
        key = (source, page_index, rotation, target_width)
        token = self._next_token
        self._next_token += 1
        cached = self._cache.get(key)
        if cached is not None:
            self.rendered.emit(token, cached)
            return token
        self._pending[token] = key
        self._submit.emit(ThumbRequest(token, source, page_index, rotation, target_width))
        return token

    def close_source(self, source: Path) -> None:
        self._cache = {k: v for k, v in self._cache.items() if k[0] != source}
        self._close_source.emit(source)

    def shutdown(self) -> None:
        self._close_all.emit()
        self._thread.quit()
        self._thread.wait(2000)

    def _on_rendered(self, token: int, image: QImage) -> None:
        key = self._pending.pop(token, None)
        if key is not None:
            self._cache[key] = image
        self.rendered.emit(token, image)
