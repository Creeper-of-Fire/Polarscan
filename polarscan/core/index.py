"""Data model: Polaroid (with assets) and tag helpers."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from .asset_thumb import (
    THUMBS_DIRNAME,
    SHORT_HASH_LEN,
    compute_hash,
    make_thumb_image,
)


@dataclass
class Asset:
    """A single scanned file belonging to a polaroid.

    `role` is a free-form tag (e.g. front / back / back_signature / front_v2).
    Same role can have multiple assets -- only `supersedes` decides which is current.

    `hash` is blake2b hex 128 char. Written once at asset creation time, never
    recomputed on browse. Enables:
    - Path-derivable thumb filename (`{stem}_{hash[:6]}.jpg`) — zero F-disk
      lookup on browse.
    - Future offline path-repair tool: relocate assets in LIBRARY_ROOT, then
      re-match by hash and rewrite paths in yaml.
    """

    role: str
    path: str
    captured_at: Optional[str] = None  # ISO datetime string
    device: Optional[str] = None
    hash: Optional[str] = None  # blake2b hex (128 char), null until first written

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Asset":
        return cls(
            role=str(d.get("role", "front")),
            path=str(d["path"]),
            captured_at=d.get("captured_at"),
            device=d.get("device"),
            hash=d.get("hash"),
        )

    # ------------------------------------------------------------------
    # 工厂: 算 hash + 创建 asset 实例
    # ------------------------------------------------------------------
    @classmethod
    def from_path(cls, src: str | Path, role: str = "front",
                  captured_at: Optional[str] = None,
                  device: Optional[str] = None) -> "Asset":
        """Read src, compute hash, return Asset with hash field populated.

        这是写新 asset 的入口. 一次性访问 F 盘算 hash.
        """
        return cls(
            role=role,
            path=str(src),
            captured_at=captured_at,
            device=device,
            hash=compute_hash(src),
        )

    # ------------------------------------------------------------------
    # thumb 派生 (零 F 盘访问)
    # ------------------------------------------------------------------
    def thumb_filename(self) -> Optional[str]:
        """Return thumb filename like `img20260728_17185555_a3b4c5.jpg`.

        Returns None if hash is missing (legacy asset not yet migrated).
        """
        if not self.hash:
            return None
        stem = Path(self.path).stem
        return f"{stem}_{self.hash[:SHORT_HASH_LEN]}.jpg"

    def thumb_path(self, data_dir: str | Path) -> Optional[Path]:
        """Full thumb path under data_dir/.thumbs/. Returns None if hash missing."""
        fn = self.thumb_filename()
        if not fn:
            return None
        return Path(data_dir) / THUMBS_DIRNAME / fn

    def has_thumb(self, data_dir: str | Path) -> bool:
        """True if thumb file exists on disk. Pure SSD check, zero F-disk."""
        tp = self.thumb_path(data_dir)
        return tp is not None and tp.exists()

    def ensure_thumb(self, data_dir: str | Path,
                     src_path: str | Path | None = None) -> Optional[Path]:
        """生成 thumb 文件 (已存在跳过). 写入路径, 一次性访问 F 盘.

        src_path 缺省用 self.path. Returns None if hash missing or src missing.
        """
        tp = self.thumb_path(data_dir)
        if tp is None:
            return None
        if tp.exists():
            return tp
        src = Path(src_path or self.path)
        if not src.exists():
            return None
        return make_thumb_image(src, tp)


@dataclass
class Polaroid:
    """A physical polaroid. May have 1..N scanned assets.

    Identity is the immutable `id`. Everything else is metadata.
    """

    id: str
    shot_date: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    assets: list[Asset] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Polaroid":
        return cls(
            id=str(d["id"]),
            shot_date=d.get("shot_date"),
            tags=[str(t) for t in d.get("tags", [])],
            notes=str(d.get("notes", "")),
            assets=[Asset.from_dict(a) for a in d.get("assets", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "shot_date": self.shot_date,
            "tags": list(self.tags),
            "notes": self.notes,
            "assets": [asdict(a) for a in self.assets],
        }


def tag_prefix(tag: str) -> str:
    """Return prefix part of a `prefix:value` tag. Empty string if no prefix."""
    if ":" in tag:
        return tag.split(":", 1)[0]
    return ""


def tag_value(tag: str) -> str:
    """Return value part of a `prefix:value` tag. Full string if no prefix."""
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag
