"""公开接口。应用层必须通过这里访问，不能直接调用 core。

本层只保证一件事：所有修改先缓存在内存中，仅在调用 `save()` 时写入磁盘。
应用层不能直接写入 YAML。
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

class Polarscan:
    """单个资料库的访问句柄，在内存中持有 `_index.yaml` 的副本。

    路径约定：
        data_dir — 存放 `_index.yaml` 与 `.thumbs/` 的目录，通常位于 SSD。

    注意：`_index.yaml` 中的资产路径使用绝对路径，例如
    `F:\\相册\\...\\img.png`，因此运行时不需要 `library_root`。
    只有执行一次性扫描的初始化脚本时，才需要提供原图根目录作为扫描起点。
    """

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self._data: dict[str, Any] = read_index(self.data_dir)

    # ---- 生命周期 ----
    def reload(self) -> None:
        self._data = read_index(self.data_dir)

    def save(self) -> None:
        write_index(self.data_dir, self._data)

    # ---- 查询 ----
    def polaroids(self) -> list[Polaroid]:
        return list_polaroids(self._data)

    def polaroid(self, pid: str) -> Optional[Polaroid]:
        for p in self.polaroids():
            if p.id == pid:
                return p
        return None

    def query_by_tag(self, tag: str) -> list[Polaroid]:
        """返回 `tags` 列表中精确包含指定标签的拍立得。"""
        return [p for p in self.polaroids() if tag in p.tags]

    def query_by_prefix(self, prefix: str) -> list[Polaroid]:
        """返回至少包含一个指定前缀标签的拍立得。"""
        return [
            p for p in self.polaroids()
            if any(tag_prefix(t) == prefix for t in p.tags)
        ]

    # ---- 修改 ----
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

    # ---- 资产 ----
    def thumb_path_for(self, p: Polaroid, asset_idx: int = 0) -> Optional[Path]:
        """确保 `p.assets[asset_idx]` 的缩略图存在，并返回路径；失败时返回 None。

        `asset_idx` 必须显式位于 0 到 `len(p.assets) - 1`；越界或资产列表为空时返回 None。

        设计：
        - 缩略图文件名为 `{stem}_{asset.hash[:6]}.jpg`，完全由 `asset.hash` 派生。
        - 浏览时不访问 F 盘：缩略图已存在则直接返回，只检查 SSD 文件状态。
        - 缩略图缺失时按需调用 `Asset.ensure_thumb`，只访问一次 F 盘。
        - 哈希缺失表示旧资产尚未迁移，此时返回 None，由界面提示运行迁移脚本。
        """
        if not p.assets or asset_idx < 0 or asset_idx >= len(p.assets):
            return None
        asset = p.assets[asset_idx]
        tp = asset.thumb_path(self.data_dir)
        if tp is None:
            return None  # 哈希缺失：资产尚未迁移
        if tp.exists():
            return tp   # 浏览时不访问 F 盘
        # 缩略图缺失：按需生成，只访问一次 F 盘
        return asset.ensure_thumb(self.data_dir)

    # ---- 标签注册表（按需补充元数据） ----
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
        """返回所有拍立得已使用且前缀匹配的标签值，不解析元数据。

        结果用于界面自动补全：先按使用频率降序排列，同频次再按键名字母序升序，
        让工作台的快捷添加按钮与候选列表优先显示常用项。
        """
        counts: dict[str, int] = {}
        for p in self.polaroids():
            for t in p.tags:
                if tag_prefix(t) == prefix:
                    v = tag_value(t)
                    counts[v] = counts.get(v, 0) + 1
        return sorted(counts.keys(), key=lambda k: (-counts[k], k))

    # ---- id 派生（工作台使用） ----
    def suggest_id(self, shot_date: str | None, tags: list[str]) -> str:
        """派生 id，不查重也不写入，仅供工作台表单预览。"""
        primary = parse_primary_char(tags)
        return make_polaroid_id(shot_date, primary)

    # ---- 浏览与工作台 ----
    def first_polaroid(self) -> Polaroid | None:
        polaroids = self.polaroids()
        return polaroids[0] if polaroids else None

    def polaroid_index_of(self, pid: str) -> int:
        """未找到时返回 -1，否则返回从 0 开始的索引。"""
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
        """返回下一张没有标签的拍立得，并跳过已经打标的记录。"""
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

    # ---- 标签池元数据的增删改查 ----
    def tag_info(self, prefix: str, key: str) -> dict[str, Any]:
        return self.tag_metadata(prefix).get(key, {}) or {}

    def set_tag_info(self, prefix: str, key: str, info: dict[str, Any]) -> None:
        """写入标签元数据；传入空字典时删除该键。"""
        if not info:
            self._data.setdefault("tags", {}).setdefault(prefix, {}).pop(key, None)
            # 清空后保留空的前缀字典也是允许的
            return
        self.upsert_tag(prefix, key, info)

    def delete_tag(self, prefix: str, key: str) -> None:
        tags_root = self._data.setdefault("tags", {})
        bucket = tags_root.get(prefix)
        if isinstance(bucket, dict):
            bucket.pop(key, None)

    def all_tags_in_pool(self, prefix: str) -> dict[str, dict[str, Any]]:
        """列出指定前缀下所有已注册标签及其元数据。"""
        return dict(self.tag_metadata(prefix))

    def polaroids_with_tag(self, prefix: str, value: str) -> list[Polaroid]:
        target = f"{prefix}:{value}"
        return [p for p in self.polaroids() if target in p.tags]  # noqa: E501
