"""Resolve a possibly-relative asset path against library_root."""
from __future__ import annotations

from pathlib import Path


def resolve_asset_path(library_root: str | Path, asset_path: str) -> Path:
    p = Path(asset_path)
    if p.is_absolute():
        return p
    return Path(library_root) / p
