"""Data model: Polaroid (with assets) and tag helpers."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class Asset:
    """A single scanned file belonging to a polaroid.

    `role` is a free-form tag (e.g. front / back / back_signature / front_v2).
    Same role can have multiple assets -- only `supersedes` decides which is current.
    """

    role: str
    path: str
    captured_at: Optional[str] = None  # ISO datetime string
    device: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Asset":
        return cls(
            role=str(d.get("role", "front")),
            path=str(d["path"]),
            captured_at=d.get("captured_at"),
            device=d.get("device"),
        )


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
