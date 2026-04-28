"""Thin wrappers around pypdf/pikepdf for the operations the UI needs.

The UI deals in :class:`PageRef` values — (source path, page index inside
that source, accumulated rotation delta). Write-out converts a sequence of
them to a new PDF using pypdf, which is fast and preserves page content.
Password + compression go through pikepdf because pypdf's crypto story is
weaker and its stream-level compression isn't as good.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

import pikepdf
from PIL import Image
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


# ---- Compression ---------------------------------------------------------
#
# Strategy:
#   1. If Ghostscript is on PATH, use `pdfwrite` with -dPDFSETTINGS. That's
#      the same backend paperweight, minimalpdfcompress, and similar tools
#      use — image-heavy PDFs get downsampled, fonts get subset, duplicate
#      resources get merged.
#   2. Always also run the pikepdf + Pillow pass: walk every embedded image,
#      re-encode it as a quality-capped JPEG, and regenerate object streams.
#      It's the second opinion that catches PDFs Ghostscript can't shrink
#      (e.g. JPEG2000-heavy artbooks where /ebook actually grows the file).
#   3. After running the available backends, pick the smallest output that's
#      smaller than the source. If neither result helps — for example, the
#      input is already at the best practical bitrate — copy the source to
#      `dst` so the user always gets a file no larger than the input.

_GS_SETTINGS = {
    "high":   "/printer",   # 300 dpi, image-faithful
    "medium": "/ebook",     # 150 dpi, balanced
    "low":    "/screen",    # 72 dpi, smallest
}

_PIL_PROFILES = {
    "high":   {"jpeg_q": 85, "max_dim": 2400, "min_size": 96},
    "medium": {"jpeg_q": 70, "max_dim": 1600, "min_size": 64},
    "low":    {"jpeg_q": 50, "max_dim": 1100, "min_size": 32},
}


def _bundle_root() -> Path:
    """Return the on-disk root of the running app.

    For a PyInstaller-frozen executable this is ``sys._MEIPASS`` (the
    onefile temp-extracted dir) or the directory of ``sys.executable``
    (onedir). For source runs we fall back to the package's parent so
    devs can drop a ``gs/`` tree next to ``src/`` for testing.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _bundled_ghostscript() -> tuple[str, Path] | None:
    """Locate Ghostscript bundled with the application.

    Returns ``(executable_path, bundle_root)`` so the caller can also set
    GS_LIB / GS_RESOURCE_DIR — Ghostscript needs them to find its
    PostScript libraries when run from a non-standard install location.
    """
    root = _bundle_root()
    candidates = [
        root / "gs" / "bin" / "gswin64c.exe",
        root / "gs" / "bin" / "gswin32c.exe",
        root / "gs" / "bin" / "gs",
        root / "gswin64c.exe",
        root / "gswin32c.exe",
    ]
    for exe in candidates:
        if exe.is_file():
            # Bundle root is the parent of `bin/` when present, else exe's parent.
            gs_root = exe.parent.parent if exe.parent.name == "bin" else exe.parent
            return (str(exe), gs_root)
    return None


def _ghostscript_executable() -> str | None:
    """Return the Ghostscript binary path, or None if not installed.

    Bundled-with-app copy wins over PATH so a frozen Windows build is
    self-contained even on machines that have never seen Ghostscript.
    """
    bundled = _bundled_ghostscript()
    if bundled is not None:
        return bundled[0]
    for name in ("gs", "gswin64c", "gswin32c"):
        path = shutil.which(name)
        if path:
            return path
    return None


def compress(
    src: Path,
    dst: Path,
    quality: str = "medium",
    password: str | None = None,
) -> Path:
    """Compress ``src`` and write the result to ``dst``.

    ``quality`` is "high" / "medium" / "low" — mapped to Ghostscript
    /printer, /ebook, /screen respectively.

    Each backend is run into a temp file; the smallest result that beats
    the source wins. If neither output is smaller (already-optimal source,
    JPEG2000 imagery, ICC-profile-heavy artbooks, etc.), the source is
    copied to ``dst`` so callers always end up with a usable file no
    larger than the input.

    Errors:
        * Same-path src/dst is rejected up front — this function must
          never overwrite the input.
        * Open / decrypt / parse failures (wrong password, corrupt PDF)
          propagate as ``pikepdf.PdfError`` / ``pikepdf.PasswordError``;
          the silent copy-source fallback only fires when both backends
          *succeeded* but didn't beat the source size.

    Security:
        * When ``password`` is supplied, the source is decrypted into an
          isolated temp directory and Ghostscript runs against that copy
          without ``-sPDFPassword=`` on argv (which would otherwise be
          visible to other local processes).
    """
    src = Path(src)
    dst = Path(dst)

    # ---- Issue #3: reject src == dst ----------------------------------
    try:
        same_path = src.resolve(strict=False) == dst.resolve(strict=False)
    except OSError:
        same_path = src == dst
    if same_path:
        raise ValueError(
            f"compress(): src and dst resolve to the same path ({src}); "
            "in-place compression isn't supported — use a different "
            "destination."
        )

    src_size = src.stat().st_size
    dst.parent.mkdir(parents=True, exist_ok=True)

    # ---- Up-front validation + password-free GS input ----------------
    #
    # Open the source once with pikepdf. This validates the file (catches
    # corrupt PDFs and wrong/missing passwords *before* we report success
    # via the copy-source fallback), records whether the source was
    # encrypted (so we can re-apply protection to the output), and, when a
    # password is supplied, produces an unencrypted temp copy so
    # Ghostscript never sees the password on its argv.
    plain_holder: tempfile.TemporaryDirectory[str] | None = None
    try:
        if password:
            plain_holder = tempfile.TemporaryDirectory(prefix="cove-pdf-kit-")
            plain_input = Path(plain_holder.name) / "decrypted.pdf"
            with pikepdf.open(src, password=password) as pdf:
                src_was_encrypted = bool(pdf.is_encrypted)
                pdf.save(plain_input)
        else:
            with pikepdf.open(src) as pdf:
                # Will normally be False here — pikepdf.open without a
                # password raises PasswordError on encrypted input. Record
                # the value defensively in case of zero-password sources.
                src_was_encrypted = bool(pdf.is_encrypted)
            plain_input = src

        _compress_with_validated_input(
            plain_input=plain_input, dst=dst,
            quality=quality, src_size=src_size,
        )

        # ---- Preserve the source's encryption state on the output -----
        #
        # The user supplied the password to *read* the input — they did
        # not implicitly authorise us to publish an unprotected copy.
        # When the source carried encryption, re-apply it now using the
        # same password as both user- and owner-password (the owner
        # password is generally not knowable from the user-side workflow,
        # so this is the most-honest reproduction we can offer).
        #
        # Re-encryption adds an encryption dictionary and per-stream
        # overhead, so the post-encryption size can creep above the
        # source. The "no larger than input" contract has to be enforced
        # against the *exact bytes we publish*, not the unencrypted
        # candidate, so we re-check after the swap and fall back to a
        # bit-perfect copy of the original if the re-encrypted output
        # ended up bigger.
        if src_was_encrypted and password:
            _reencrypt_in_place(dst, password)
            try:
                final_size = dst.stat().st_size
            except OSError:
                final_size = src_size + 1  # treat unreadable result as oversized
            if final_size > src_size:
                if dst.exists():
                    dst.unlink()
                shutil.copy2(src, dst)

        return dst
    finally:
        if plain_holder is not None:
            plain_holder.cleanup()


def _make_unique_tmp(dst: Path, hint: str) -> Path:
    """Allocate a unique temp file in ``dst.parent``.

    Predictable side-by-side names like ``<dst>.gs.tmp`` could collide
    with a user file of that exact name. ``mkstemp`` reserves a unique
    path atomically, returning a private placeholder we then overwrite
    with the backend's output.
    """
    fd, name = tempfile.mkstemp(
        dir=str(dst.parent),
        prefix=f".cove-pdf-{hint}-",
        suffix=".pdf",
    )
    os.close(fd)
    return Path(name)


def _reencrypt_in_place(path: Path, password: str) -> None:
    """Re-emit ``path`` with user/owner encryption set to ``password``."""
    tmp = _make_unique_tmp(path, "enc")
    try:
        with pikepdf.open(path) as pdf:
            pdf.save(tmp, encryption=pikepdf.Encryption(
                owner=password, user=password, R=6,
            ))
        # Atomic-ish replace: the destination is a path we already own,
        # so swapping in the encrypted copy is safe.
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _compress_with_validated_input(
    *, plain_input: Path, dst: Path,
    quality: str, src_size: int,
) -> Path:
    """Run both backends on ``plain_input`` and pick the best output.

    Caller has already verified the source is openable; this helper only
    deals with backend execution and candidate selection. Temp files use
    `mkstemp` for unique names so a user file named e.g.
    ``foo.pdf.gs.tmp`` can never be overwritten or deleted as collateral.
    """
    candidates: list[Path] = []
    gs = _ghostscript_executable()

    gs_tmp = _make_unique_tmp(dst, "gs")
    if gs is not None:
        try:
            _compress_ghostscript(gs, plain_input, gs_tmp, quality)
        except subprocess.CalledProcessError:
            gs_tmp.unlink(missing_ok=True)
        else:
            if gs_tmp.exists() and gs_tmp.stat().st_size > 0:
                candidates.append(gs_tmp)
            else:
                gs_tmp.unlink(missing_ok=True)
    else:
        # Drop the placeholder we reserved.
        gs_tmp.unlink(missing_ok=True)

    pp_tmp = _make_unique_tmp(dst, "pp")
    try:
        _compress_pikepdf(plain_input, pp_tmp, quality)
    except (pikepdf.PdfError, OSError):
        # Backend-specific failure on this particular input — the *other*
        # backend's candidate may still win. Genuine open/decrypt errors
        # were already caught in the up-front pikepdf.open() in compress().
        pp_tmp.unlink(missing_ok=True)
    else:
        if pp_tmp.exists() and pp_tmp.stat().st_size > 0:
            candidates.append(pp_tmp)
        else:
            pp_tmp.unlink(missing_ok=True)

    best: Path | None = None
    best_size = src_size
    for path in candidates:
        try:
            sz = path.stat().st_size
        except OSError:
            continue
        if sz < best_size:
            best = path
            best_size = sz

    if best is not None:
        if dst.exists():
            dst.unlink()
        best.replace(dst)
    else:
        # Both backends ran but couldn't beat the source. Copy the
        # validated plain input so the result is consistent with the
        # success path (caller will re-apply encryption afterwards if the
        # source was protected).
        shutil.copy2(plain_input, dst)

    for path in candidates:
        try:
            if path != dst and path.exists():
                path.unlink()
        except OSError:
            pass

    return dst


def _compress_ghostscript(gs: str, src: Path, dst: Path, quality: str) -> None:
    """Run Ghostscript ``pdfwrite`` against an already-decrypted source.

    The caller is responsible for decrypting password-protected sources
    into a temp file before invoking this — that keeps the password off
    the Ghostscript command line.

    When ``gs`` lives inside the application bundle (frozen Windows
    build), ``GS_LIB`` / ``GS_RESOURCE_DIR`` are pointed at the bundled
    PostScript libraries so the binary can find them on any host — not
    just hosts that already have Ghostscript installed system-wide.
    """
    setting = _GS_SETTINGS.get(quality, "/ebook")
    cmd = [
        gs,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.5",
        f"-dPDFSETTINGS={setting}",
        "-dNOPAUSE", "-dQUIET", "-dBATCH", "-dSAFER",
        "-dDetectDuplicateImages=true",
        "-dCompressFonts=true",
        "-dSubsetFonts=true",
        f"-sOutputFile={dst}",
        str(src),
    ]

    env = None
    bundled = _bundled_ghostscript()
    if bundled is not None and Path(bundled[0]) == Path(gs):
        # Point the bundled gs at its bundled libraries.
        env = os.environ.copy()
        gs_root = bundled[1]
        lib = gs_root / "lib"
        res = gs_root / "Resource"
        icc = gs_root / "iccprofiles"
        if lib.is_dir():
            env["GS_LIB"] = str(lib)
        if res.is_dir():
            env["GS_RESOURCE_DIR"] = str(res)
        if icc.is_dir():
            env.setdefault("GS_ICC_PROFILES", str(icc))

    subprocess.run(cmd, check=True, capture_output=True, env=env)


def _compress_pikepdf(src: Path, dst: Path, quality: str) -> None:
    profile = _PIL_PROFILES.get(quality, _PIL_PROFILES["medium"])
    jpeg_q   = profile["jpeg_q"]
    max_dim  = profile["max_dim"]
    min_size = profile["min_size"]

    with pikepdf.open(src, allow_overwriting_input=False) as pdf:
        for page in pdf.pages:
            try:
                images = list(page.images.items())
            except Exception:  # noqa: BLE001
                continue
            for _name, raw in images:
                _shrink_image(raw, jpeg_q=jpeg_q, max_dim=max_dim, min_size=min_size)
        pdf.save(
            dst,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            compress_streams=True,
            recompress_flate=True,
            normalize_content=True,
            linearize=False,
        )


# pikepdf dictionaries key everything by canonical Name objects ("/Decode",
# "/SMask", …); bare strings without the leading slash silently miss, so
# we use pikepdf.Name.* throughout this module.
_SKIP_IMAGE_KEYS = (
    pikepdf.Name.ImageMask,
    pikepdf.Name.SMask,
    pikepdf.Name.Mask,
    pikepdf.Name.Decode,
)
_SKIP_IMAGE_FILTERS = frozenset({"/JPXDecode", "/JBIG2Decode"})
_POST_REPLACE_CLEAR_KEYS = (
    pikepdf.Name.DecodeParms,
    pikepdf.Name.Decode,
    pikepdf.Name.SMask,
    pikepdf.Name.Mask,
    pikepdf.Name.SMaskInData,
    pikepdf.Name.Alternates,
    pikepdf.Name.OPI,
)


def _image_has_incompatible_metadata(raw_image: pikepdf.Object) -> bool:
    """Return True when re-encoding the image to a vanilla 3-channel JPEG
    would silently desynchronise the image dictionary.

    The PDF image dictionary carries entries that depend on the image's
    color components, bit depth, transparency, and filter chain:

    * ``/ImageMask``       — the stream is a 1-bpc stencil mask, not pixel
      data. Rewriting as RGB JPEG would corrupt the mask and break the
      page's painting model.
    * ``/SMask`` / ``/Mask`` — companion soft / stencil mask that
      references this stream's geometry. Resizing or re-encoding the main
      image breaks alignment with the mask.
    * ``/Decode``          — explicit decode array maps source samples to
      color values. The array length depends on component count; an
      ``[1 0 1 0 1 0]`` array on a CMYK source becomes invalid (and
      misrenders) when the same dictionary points at an RGB JPEG.
    * ``/JPXDecode`` / ``/JBIG2Decode`` filter — JPEG2000 / JBIG2 streams
      have their own color and bit-depth encoding. Replacing the stream
      with DCT-encoded bytes without rebuilding the entire dictionary
      yields invalid output.
    """
    for key in _SKIP_IMAGE_KEYS:
        if key in raw_image:
            return True
    flt = raw_image.get(pikepdf.Name.Filter)
    if flt is not None:
        names = [flt] if isinstance(flt, pikepdf.Name) else list(flt)
        for n in names:
            try:
                if str(n) in _SKIP_IMAGE_FILTERS:
                    return True
            except Exception:  # noqa: BLE001
                # Defensive — unknown object types in /Filter just opt out
                # of recompression rather than crashing the batch.
                return True
    return False


def _shrink_image(
    raw_image: pikepdf.Object, *,
    jpeg_q: int, max_dim: int, min_size: int,
) -> None:
    """Re-encode a pikepdf image XObject as a quality-capped JPEG."""
    # Bail out on images whose dictionary entries would no longer match
    # the rewritten stream. Cheaper to skip than to chase a list of
    # exceptions after the fact.
    if _image_has_incompatible_metadata(raw_image):
        return

    try:
        pdfimage = pikepdf.PdfImage(raw_image)
        pil = pdfimage.as_pil_image()
    except Exception:  # noqa: BLE001
        return

    # Skip tiny images (icons, masks). They rarely save anything and the
    # JPEG roundtrip can make them look worse.
    if pil.width < min_size or pil.height < min_size:
        return

    # Downscale large images to the target dimension cap.
    if pil.width > max_dim or pil.height > max_dim:
        pil.thumbnail((max_dim, max_dim), Image.LANCZOS)

    # Flatten alpha against white — JPEG can't carry transparency.
    if pil.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", pil.size, (255, 255, 255))
        alpha = pil.split()[-1]
        bg.paste(pil.convert("RGB"), mask=alpha)
        pil = bg
    elif pil.mode == "P":
        pil = pil.convert("RGB")
    elif pil.mode == "1":
        # 1-bit images are already very small via CCITT — skip.
        return
    elif pil.mode != "RGB":
        pil = pil.convert("RGB")

    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=jpeg_q, optimize=True, progressive=True)
    new_data = buf.getvalue()

    # If the round-trip would actually grow the stream, skip.
    try:
        old_size = len(bytes(raw_image.read_raw_bytes()))
    except Exception:  # noqa: BLE001
        old_size = 0
    if old_size and len(new_data) >= old_size:
        return

    try:
        raw_image.write(new_data, filter=pikepdf.Name.DCTDecode)
        raw_image.Width = pil.width
        raw_image.Height = pil.height
        raw_image.ColorSpace = pikepdf.Name.DeviceRGB
        raw_image.BitsPerComponent = 8
        # Strip any lingering metadata that referenced the previous
        # filter/colorspace/transparency layout. The skip pre-flight
        # already rejects images that *currently* have these keys, but a
        # belt-and-braces clear keeps the dictionary self-consistent
        # against future code paths that bypass the pre-flight.
        for key in _POST_REPLACE_CLEAR_KEYS:
            if key in raw_image:
                del raw_image[key]
    except Exception:  # noqa: BLE001
        # Some image dictionaries reject in-place mutation; safest path is
        # to leave the original alone and continue.
        return


def has_compression_backend() -> tuple[bool, str]:
    """Return (True, "ghostscript"|"pikepdf") describing the active backend."""
    if _ghostscript_executable() is not None:
        return True, "ghostscript"
    return True, "pikepdf"


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
