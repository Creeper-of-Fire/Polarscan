"""Load/save the single _index.yaml file. Source of truth."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .index import Polaroid


INDEX_FILENAME = "_index.yaml"


def _default() -> dict[str, Any]:
    return {
        "library_root": None,  # 自己就是数据目录
        "version": 1,
        "tags": {},           # 按 prefix nested 的 metadata 池 (lazy)
        "polaroids": [],
    }


def read_index(library_root: str | Path) -> dict[str, Any]:
    """Load _index.yaml from `library_root`. Returns empty structure if missing.

    Schema is dict with keys: library_root, version, tags, polaroids.
    """
    path = Path(library_root) / INDEX_FILENAME
    if not path.exists():
        d = _default()
        d["library_root"] = str(library_root)
        return d
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # backfill missing top-level keys
    defaults = _default()
    for k, v in defaults.items():
        data.setdefault(k, v)
    if not data.get("library_root"):
        data["library_root"] = str(library_root)
    if not isinstance(data.get("tags"), dict):
        data["tags"] = {}
    if not isinstance(data.get("polaroids"), list):
        data["polaroids"] = []
    # tags 内部 None / 非 dict 值清掉 (历史 bootstrap 残留)
    for prefix in list(data["tags"].keys()):
        if not isinstance(data["tags"][prefix], dict):
            data["tags"][prefix] = {}
    return data


def write_index(library_root: str | Path, data: dict[str, Any]) -> None:
    """Atomic save of _index.yaml. tmp + rename."""
    path = Path(library_root) / INDEX_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=4096,
        )
    tmp.replace(path)


def list_polaroids(data: dict[str, Any]) -> list[Polaroid]:
    return [Polaroid.from_dict(p) for p in data.get("polaroids", [])]
