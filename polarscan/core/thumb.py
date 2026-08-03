"""Thumbnail generation + cache. UI reads thumbs, never the original 50MB PNG."""
from __future__ import annotations

from pathlib import Path

from PIL import Image


THUMBS_DIRNAME = ".thumbs"
LONG_EDGE = 1024
QUALITY = 85


def thumb_path(library_root: Path, polaroid_id: str) -> Path:
    return Path(library_root) / THUMBS_DIRNAME / f"{polaroid_id}.jpg"


def make_thumb(src: Path, dst: Path) -> Path:
    """Generate thumb from src into dst (skips if dst already exists)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return dst
    with Image.open(src) as im:
        im.thumbnail((LONG_EDGE, LONG_EDGE), Image.LANCZOS)
        if im.mode in ("RGBA", "P", "LA"):
            im = im.convert("RGB")
        im.save(dst, "JPEG", quality=QUALITY, optimize=True)
    return dst


def get_or_make_thumb(
    library_root: str | Path,
    polaroid_id: str,
    src_path: str | Path,
) -> Path | None:
    """If `src_path` exists, ensure thumb exists and return its path; else None."""
    src = Path(src_path)
    if not src.exists():
        return None
    dst = thumb_path(Path(library_root), polaroid_id)
    return make_thumb(src, dst)
