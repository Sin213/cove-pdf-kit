"""Thin wrappers around pypdf/pikepdf for the operations the UI needs.

The UI deals in :class:`PageRef` values — (source path, page index inside
that source, accumulated rotation delta). Write-out converts a sequence of
them to a new PDF using pypdf, which is fast and preserves page content.
Password + compression go through pikepdf because pypdf's crypto story is
weaker and its stream-level compression isn't as good.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pikepdf
from pypdf import PdfReader, PdfWriter


@dataclass(frozen=True)
class PageRef:
    """Identifies a single page in a source PDF, plus any in-UI rotation.

    ``rotation`` is a multiple of 90 and is added on top of whatever the
    page's built-in /Rotate value says.
    """
    source: Path
    index: int         # 0-based
    rotation: int = 0  # degrees clockwise, multiple of 90

    def rotated(self, delta: int) -> "PageRef":
        return replace(self, rotation=(self.rotation + delta) % 360)


def read_page_count(path: Path, password: str | None = None) -> int:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        if password is None:
            raise PermissionError("encrypted PDF")
        reader.decrypt(password)
    return len(reader.pages)


def is_encrypted(path: Path) -> bool:
    return PdfReader(str(path)).is_encrypted


def write_merged(pages: list[PageRef], out: Path, password: str | None = None) -> Path:
    """Build a new PDF containing ``pages`` in order, applying rotations.

    The same source PDF is opened at most once — pypdf's ``PdfReader`` is
    expensive to construct for large documents.
    """
    if not pages:
        raise ValueError("no pages to write")
    readers: dict[Path, PdfReader] = {}
    writer = PdfWriter()
    for ref in pages:
        reader = readers.get(ref.source)
        if reader is None:
            reader = PdfReader(str(ref.source))
            if reader.is_encrypted:
                if password is None:
                    raise PermissionError(f"{ref.source.name} is encrypted")
                reader.decrypt(password)
            readers[ref.source] = reader
        page = reader.pages[ref.index]
        if ref.rotation:
            page.rotate(ref.rotation)
        writer.add_page(page)
    with open(out, "wb") as f:
        writer.write(f)
    return out


def compress(
    src: Path,
    dst: Path,
    quality: str = "medium",
    password: str | None = None,
) -> Path:
    """Rewrite the PDF with pikepdf's compression switches.

    ``quality`` maps to a set of pikepdf save flags. We don't re-encode
    embedded images (that would need Pillow + per-image decisions) — this
    pass gets you the stream-level wins: object streams regenerated,
    content streams recompressed, garbage collected.
    """
    profiles = {
        "high":   {"compress_streams": True, "recompress_flate": True},
        "medium": {"compress_streams": True, "recompress_flate": True},
        "low":    {"compress_streams": True, "recompress_flate": True},
    }
    flags = profiles.get(quality, profiles["medium"])
    with pikepdf.open(src, password=password or "") as pdf:
        pdf.save(
            dst,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            normalize_content=True,
            linearize=False,
            **flags,
        )
    return dst


def encrypt(src: Path, dst: Path, user_password: str, owner_password: str | None = None) -> Path:
    owner = owner_password or user_password
    with pikepdf.open(src) as pdf:
        pdf.save(
            dst,
            encryption=pikepdf.Encryption(owner=owner, user=user_password, R=6),
        )
    return dst


def decrypt(src: Path, dst: Path, password: str) -> Path:
    with pikepdf.open(src, password=password) as pdf:
        pdf.save(dst)
    return dst
