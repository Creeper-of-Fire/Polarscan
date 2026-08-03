"""Public API. Apps must use this, not core directly.

The single guarantee this layer enforces: every mutation is buffered in memory
and persisted only via `save()`. Apps cannot write the YAML directly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .core import (
    Asset,
    Polaroid,
    get_or_make_thumb,
    list_polaroids,
    read_index,
    resolve_asset_path,
    tag_prefix,
    tag_value,
    thumb_path,
    write_index,
)


class Polarscan:
    """Single library handle. Holds an in-memory copy of _index.yaml.

    Typical flow:
        ps = Polarscan("/path/to/library")
        for p in ps.polaroids():
            ...
        p = ps.polaroid("some_id")
        ps.upsert_polaroid(p)
        ps.save()
    """

    def __init__(self, library_root: str | Path):
        self.library_root = Path(library_root)
        self._data: dict[str, Any] = read_index(self.library_root)

    # ---- lifecycle ----
    def reload(self) -> None:
        self._data = read_index(self.library_root)

    def save(self) -> None:
        write_index(self.library_root, self._data)

    # ---- query ----
    def polaroids(self) -> list[Polaroid]:
        return list_polaroids(self._data)

    def polaroid(self, pid: str) -> Optional[Polaroid]:
        for p in self.polaroids():
            if p.id == pid:
                return p
        return None

    def query_by_tag(self, tag: str) -> list[Polaroid]:
        """Match any polaroid whose `tags` list contains `tag` exactly."""
        return [p for p in self.polaroids() if tag in p.tags]

    def query_by_prefix(self, prefix: str) -> list[Polaroid]:
        """All polaroids that have at least one tag with the given prefix."""
        return [
            p for p in self.polaroids()
            if any(tag_prefix(t) == prefix for t in p.tags)
        ]

    # ---- mutate ----
    def upsert_polaroid(self, p: Polaroid) -> None:
        for i, existing in enumerate(self._data["polaroids"]):
            if existing.get("id") == p.id:
                self._data["polaroids"][i] = p.to_dict()
                return
        self._data["polaroids"].append(p.to_dict())

    def delete_polaroid(self, pid: str) -> bool:
        before = len(self._data["polaroids"])
        self._data["polaroids"] = [
            p for p in self._data["polaroids"] if p.get("id") != pid
        ]
        return len(self._data["polaroids"]) < before

    # ---- assets ----
    def first_asset_path(self, p: Polaroid) -> Optional[Path]:
        if not p.assets:
            return None
        ap = resolve_asset_path(self.library_root, p.assets[0].path)
        return ap if ap.exists() else None

    def thumb_path_for(self, p: Polaroid) -> Optional[Path]:
        """Ensure thumb exists for the polaroid's first asset, return path or None."""
        if not p.assets:
            return None
        ap = self.first_asset_path(p)
        if ap is None:
            return None
        return get_or_make_thumb(self.library_root, p.id, ap)

    # ---- tag registry (metadata enrichment, lazy) ----
    def tag_metadata(self, prefix: str) -> dict[str, Any]:
        return self._data.get("tags", {}).get(prefix, {}) or {}

    def upsert_tag(self, prefix: str, key: str, meta: dict[str, Any]) -> None:
        self._data.setdefault("tags", {}).setdefault(prefix, {})[key] = meta

    def set_tag_metadata(self, prefix: str, registry: dict[str, Any]) -> None:
        self._data.setdefault("tags", {})[prefix] = registry

    def all_tags_with_prefix(self, prefix: str) -> list[str]:
        """Return all tags (id form, no value resolution) used by any polaroid,
        filtered by prefix. Useful for autocomplete in UI."""
        seen: set[str] = set()
        for p in self.polaroids():
            for t in p.tags:
                if tag_prefix(t) == prefix:
                    seen.add(tag_value(t))
        return sorted(seen)
