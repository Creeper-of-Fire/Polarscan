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
    list_polaroids,
    make_polaroid_id,
    parse_primary_char,
    read_index,
    tag_prefix,
    tag_value,
    write_index,
)
from .core.id_gen import parse_primary_char as _parse_primary_char  # noqa: F401


class Polarscan:
    """Single library handle. Holds an in-memory copy of _index.yaml.

    Single path:
        data_dir  — where _index.yaml + .thumbs/ live (typically SSD, code repo)

    NOTE: asset paths in _index.yaml are stored as ABSOLUTE paths (e.g.
    `F:\\相册\\...\\img.png`), so we never need a 'library_root' at runtime.
    Only the bootstrap (one-shot scan) script needs a library root as
    a scan starting point.
    """

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self._data: dict[str, Any] = read_index(self.data_dir)

    # ---- lifecycle ----
    def reload(self) -> None:
        self._data = read_index(self.data_dir)

    def save(self) -> None:
        write_index(self.data_dir, self._data)

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
    def thumb_path_for(self, p: Polaroid, asset_idx: int = 0) -> Optional[Path]:
        """Ensure thumb exists for p.assets[asset_idx], return path or None.

        asset_idx 显式指定: 0..len(p.assets)-1. 越界或 p.assets 空 → None.

        设计:
        - Thumb 文件名 = `{stem}_{asset.hash[:6]}.jpg`, 完全基于 asset.hash 字段派生.
        - 浏览零 F 盘: thumb 已存在 → 直接返回 (纯 SSD stat).
        - Thumb 缺失 → lazy 调用 Asset.ensure_thumb (一次性访问 F 盘).
        - Hash 缺失 (老资产未迁移) → 返回 None, UI 提示用户跑迁移脚本.
        """
        if not p.assets or asset_idx < 0 or asset_idx >= len(p.assets):
            return None
        asset = p.assets[asset_idx]
        tp = asset.thumb_path(self.data_dir)
        if tp is None:
            return None  # hash 缺失: 资产未迁移
        if tp.exists():
            return tp   # 浏览零 F 盘
        # thumb 缺失: lazy 生成 (一次性 F 盘访问)
        return asset.ensure_thumb(self.data_dir)

    # ---- tag registry (metadata enrichment, lazy) ----
    def tag_metadata(self, prefix: str) -> dict[str, Any]:
        return self._data.get("tags", {}).get(prefix, {}) or {}

    def upsert_tag(self, prefix: str, key: str, meta: dict[str, Any]) -> None:
        tags_root = self._data.setdefault("tags", {})
        bucket = tags_root.get(prefix)
        if not isinstance(bucket, dict):
            bucket = {}
            tags_root[prefix] = bucket
        bucket[key] = meta

    def set_tag_metadata(self, prefix: str, registry: dict[str, Any]) -> None:
        self._data.setdefault("tags", {})[prefix] = registry

    def all_tags_with_prefix(self, prefix: str) -> list[str]:
        """Return all tags (id form, no value resolution) used by any polaroid,
        filtered by prefix. Useful for autocomplete in UI.

        按使用频率降序, 同频次按 key 字母序升序. 让 bench quick-add 按钮
        和 autocomplete 候选里最常用的排最前.
        """
        counts: dict[str, int] = {}
        for p in self.polaroids():
            for t in p.tags:
                if tag_prefix(t) == prefix:
                    v = tag_value(t)
                    counts[v] = counts.get(v, 0) + 1
        return sorted(counts.keys(), key=lambda k: (-counts[k], k))

    # ---- id 派生 (GUI 工作台用) ----
    def suggest_id(self, shot_date: str | None, tags: list[str]) -> str:
        """派生 id (不查重, 不写入). GUI 工作台表单预览使用."""
        primary = parse_primary_char(tags)
        return make_polaroid_id(shot_date, primary)

    # ---- 浏览 / 工作台 ----
    def first_polaroid(self) -> Polaroid | None:
        polaroids = self.polaroids()
        return polaroids[0] if polaroids else None

    def polaroid_index_of(self, pid: str) -> int:
        """-1 if not found, else 0-based index."""
        for i, p in enumerate(self.polaroids()):
            if p.id == pid:
                return i
        return -1

    def next_polaroid(self, current_pid: str | None) -> Polaroid | None:
        polaroids = self.polaroids()
        if not polaroids:
            return None
        if current_pid is None:
            return polaroids[0]
        idx = self.polaroid_index_of(current_pid)
        if idx < 0 or idx + 1 >= len(polaroids):
            return None
        return polaroids[idx + 1]

    def prev_polaroid(self, current_pid: str | None) -> Polaroid | None:
        polaroids = self.polaroids()
        if not polaroids or current_pid is None:
            return None
        idx = self.polaroid_index_of(current_pid)
        if idx <= 0:
            return None
        return polaroids[idx - 1]

    def next_untagged(self, current_pid: str | None) -> Polaroid | None:
        """下一张没打过 tag 的 polaroid. 跳过已打标的."""
        polaroids = self.polaroids()
        for i, p in enumerate(polaroids):
            if current_pid is not None and p.id == current_pid:
                # 从当前位置往后找
                for q in polaroids[i + 1:]:
                    if not q.tags:
                        return q
                return None
            if current_pid is None and not p.tags:
                return p
        return None

    # ---- 池 (tag metadata) CRUD ----
    def tag_info(self, prefix: str, key: str) -> dict[str, Any]:
        return self.tag_metadata(prefix).get(key, {}) or {}

    def set_tag_info(self, prefix: str, key: str, info: dict[str, Any]) -> None:
        """写入 tag 元数据. 空 dict 删除该 key."""
        if not info:
            self._data.setdefault("tags", {}).setdefault(prefix, {}).pop(key, None)
            # 清空再空 dict 的 prefix 也是允许的
            return
        self.upsert_tag(prefix, key, info)

    def delete_tag(self, prefix: str, key: str) -> None:
        tags_root = self._data.setdefault("tags", {})
        bucket = tags_root.get(prefix)
        if isinstance(bucket, dict):
            bucket.pop(key, None)

    def all_tags_in_pool(self, prefix: str) -> dict[str, dict[str, Any]]:
        """列出某 prefix 下所有已注册的 tag + 它们的元数据."""
        return dict(self.tag_metadata(prefix))

    def polaroids_with_tag(self, prefix: str, value: str) -> list[Polaroid]:
        target = f"{prefix}:{value}"
        return [p for p in self.polaroids() if target in p.tags]  # noqa: E501
