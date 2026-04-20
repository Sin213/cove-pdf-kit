# Cove PDF Kit

A focused, offline PDF toolkit for **Linux** and **Windows**. No cloud,
no uploads, no account — drop your PDFs in, rearrange them, compress
them, protect them, done.

![icon](cove_icon.png)

## Download (v1.0.0)

| Platform | File |
| -------- | ---- |
| Windows (installer) | `cove-pdf-kit-1.0.0-Setup.exe` |
| Windows (portable) | `cove-pdf-kit-1.0.0-Portable.exe` |
| Linux (AppImage) | `Cove-PDF-Kit-1.0.0-x86_64.AppImage` |
| Linux (Debian / Ubuntu) | `cove-pdf-kit_1.0.0_amd64.deb` |

Grab the artifacts from the [Releases page](https://github.com/Sin213/cove-pdf-kit/releases).

## Three tools, one app

### Organize
The flagship view. Drop one or more PDFs in and see every page as a
thumbnail in a grid. From here you can:

- **Merge** — every page of every dropped file lines up in order. Hit
  *Export PDF…* and you get a single merged document.
- **Reorder** — drag pages around the grid (multi-select with Ctrl /
  Shift). Build a new table-of-contents order without leaving the app.
- **Rotate** — right-click or use the toolbar to rotate selected pages
  90° left / right.
- **Delete** — pull pages you don't want before exporting.
- **Split** — select the pages you *do* want, hit *Export selection…*.
  Any subset becomes a brand-new PDF.

### Compress
Drop any number of PDFs, pick *High / Balanced / Aggressive*, hit
*Compress*. Each file is rewritten with pikepdf's stream-level
compression and saved next to the source as `<name>-compressed.pdf`.

### Protect
Add a password to one or more PDFs, or remove it. Pure pikepdf; the
content is rewritten in AES-256 when encrypting.

## Requirements

- Python 3.10+ (only for running from source)
- `PySide6`, `Pillow`, `pypdf`, `pikepdf`, `pypdfium2` — installed
  automatically by `pip`

**No ffmpeg, no ML models, no internet access at runtime.**

## Running from source

```bash
pip install -e .
cove-pdf-kit
```

Or without installing:

```bash
PYTHONPATH=src python -m cove_pdf_kit
```

## Building release artifacts

### Linux (AppImage + .deb)

```bash
VERSION=1.0.0 ./scripts/build-release.sh
```

Produces `Cove-PDF-Kit-<version>-x86_64.AppImage` and
`cove-pdf-kit_<version>_amd64.deb` under `release/`.

### Windows (Setup.exe + Portable.exe)

```powershell
.\build.ps1 -Version 1.0.0
```

Requires Python 3.12+ and [Inno Setup 6](https://jrsoftware.org/isdl.php).

### GitHub Actions

Tagging a commit `vX.Y.Z` triggers `.github/workflows/release.yml`, which
produces all four artifacts and attaches them to a GitHub release.

## License

MIT — see [LICENSE](LICENSE).
