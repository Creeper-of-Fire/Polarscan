"""公开接口。应用层必须通过这里访问，不能直接调用 core。

本层只保证一件事：所有修改先缓存在内存中，仅在调用 `save()` 时写入磁盘。
应用层不能直接写入 YAML。

并发：本类实例会被多个请求共享（FastAPI sync 端点跑在线程池里）。
所有 mutator 与 reader 都通过 `self._lock` 串行化，确保 `_data` 在迭代时
不被并发修改。使用 `threading.RLock` 以允许方法间互相调用（如 `tag_info` 内部
调 `tag_metadata`）而不会死锁。锁的粒度是粗的——本应用写吞吐低，争用不是问题。
"""
from __future__ import annotations

import threading
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

# 默认 role 派生规则: 1st = front, 2nd = back, 其余 additional
def _default_role_for_index(index: int) -> str:
    if index == 0:
        return "front"
    if index == 1:
        return "back"
    return "additional"

class Polarscan:
    """单个资料库的访问句柄，在内存中持有 `_index.yaml` 的副本。

    路径约定：
        data_dir — 存放 `_index.yaml` 与 `.thumbs/` 的目录，通常位于 SSD。

    注意：`_index.yaml` 中的资产路径使用绝对路径，例如
    `F:\\相册\\...\\img.png`，因此运行时不需要 `library_root`。
    只有执行一次性扫描的初始化脚本时，才需要提供原图根目录作为扫描起点。

    `library_root` 字段是 yaml schema 现成的——bootstrap 时由 `_bootstrap.py`
    写入，运行时被 `apps/web/` 用于路径发现。
    """

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self._data: dict[str, Any] = read_index(self.data_dir)
        self._lock = threading.RLock()

    # ---- yaml 字段直读 ----
    @property
    def library_root(self) -> Optional[str]:
        """返回 yaml 中 `library_root` 字段；未设置时返回 None。

        这是 yaml schema 字段，不是派生数据——直接读 `_data`，无锁。
        路径发现模块会读这个字段。
        """
        v = self._data.get("library_root")
        return str(v) if v else None

    # ---- 生命周期 ----
    def reload(self) -> None:
        with self._lock:
            self._data = read_index(self.data_dir)

    def save(self) -> None:
        with self._lock:
            write_index(self.data_dir, self._data)

    # ---- 反向查找 (drop 流程专用, 不缓存) ----
    def find_by_hash(self, target_hash: str) -> list[tuple[str, int]]:
        """返回所有 hash == target_hash 的 asset 位置，列表项为 (pid, asset_idx)。

        - target_hash 为空字符串或 None 时返回 []。
        - 没有命中时返回 []。
        - 不缓存：每次调用 walk 整个 `_data["polaroids"]`。
          N=千级别 polaroid × ~5 asset 的规模下，毫秒级，不值得加缓存。
        """
        with self._lock:
            if not target_hash:
                return []
            out: list[tuple[str, int]] = []
            for p in self._data.get("polaroids", []):
                pid = str(p.get("id", ""))
                for i, a in enumerate(p.get("assets", [])):
                    if a.get("hash") == target_hash:
                        out.append((pid, i))
            return out

    def find_by_path(self, target_path: str) -> list[tuple[str, int]]:
        """返回所有 path == target_path 的 asset 位置，列表项为 (pid, asset_idx)。

        - target_path 为空字符串或 None 时返回 []。
        - 路径比较走严格字符串相等，不做 normalize（path 已经是 yaml 里的绝对路径）。
        - 不缓存，理由同 `find_by_hash`。
        """
        with self._lock:
            if not target_path:
                return []
            out: list[tuple[str, int]] = []
            for p in self._data.get("polaroids", []):
                pid = str(p.get("id", ""))
                for i, a in enumerate(p.get("assets", [])):
                    if a.get("path") == target_path:
                        out.append((pid, i))
            return out

    # ---- 查询 ----
    def polaroids(self) -> list[Polaroid]:
        with self._lock:
            return list_polaroids(self._data)

    def polaroid(self, pid: str) -> Optional[Polaroid]:
        with self._lock:
            for p in list_polaroids(self._data):
                if p.id == pid:
                    return p
            return None

    def query_by_tag(self, tag: str) -> list[Polaroid]:
        """返回 `tags` 列表中精确包含指定标签的拍立得。"""
        with self._lock:
            return [p for p in list_polaroids(self._data) if tag in p.tags]

    def query_by_prefix(self, prefix: str) -> list[Polaroid]:
        """返回至少包含一个指定前缀标签的拍立得。"""
        with self._lock:
            return [
                p for p in list_polaroids(self._data)
                if any(tag_prefix(t) == prefix for t in p.tags)
            ]

    # ---- 修改 ----
    def upsert_polaroid(self, p: Polaroid) -> None:
        with self._lock:
            for i, existing in enumerate(self._data["polaroids"]):
                if existing.get("id") == p.id:
                    self._data["polaroids"][i] = p.to_dict()
                    return
            self._data["polaroids"].append(p.to_dict())

    def delete_polaroid(self, pid: str) -> bool:
        with self._lock:
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
        # 不读 _data, 只用入参 polaroid 对象；不需要锁
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
        with self._lock:
            return self._data.get("tags", {}).get(prefix, {}) or {}

    def upsert_tag(self, prefix: str, key: str, meta: dict[str, Any]) -> None:
        with self._lock:
            tags_root = self._data.setdefault("tags", {})
            bucket = tags_root.get(prefix)
            if not isinstance(bucket, dict):
                bucket = {}
                tags_root[prefix] = bucket
            bucket[key] = meta

    def set_tag_metadata(self, prefix: str, registry: dict[str, Any]) -> None:
        with self._lock:
            self._data.setdefault("tags", {})[prefix] = registry

    def all_tags_with_prefix(self, prefix: str) -> list[str]:
        """返回所有拍立得已使用且前缀匹配的标签值，不解析元数据。

        结果用于界面自动补全：先按使用频率降序排列，同频次再按键名字母序升序，
        让工作台的快捷添加按钮与候选列表优先显示常用项。
        """
        with self._lock:
            counts: dict[str, int] = {}
            for p in list_polaroids(self._data):
                for t in p.tags:
                    if tag_prefix(t) == prefix:
                        v = tag_value(t)
                        counts[v] = counts.get(v, 0) + 1
            return sorted(counts.keys(), key=lambda k: (-counts[k], k))

    # ---- id 派生（工作台使用） ----
    def suggest_id(self, shot_date: str | None, tags: list[str]) -> str:
        """派生 id，不查重也不写入，仅供工作台表单预览。"""
        with self._lock:
            primary = parse_primary_char(tags)
            return make_polaroid_id(shot_date, primary)

    # ---- 浏览与工作台 ----
    def first_polaroid(self) -> Polaroid | None:
        with self._lock:
            polaroids = list_polaroids(self._data)
            return polaroids[0] if polaroids else None

    def polaroid_index_of(self, pid: str) -> int:
        """未找到时返回 -1，否则返回从 0 开始的索引。"""
        with self._lock:
            for i, p in enumerate(list_polaroids(self._data)):
                if p.id == pid:
                    return i
            return -1

    def next_polaroid(self, current_pid: str | None) -> Polaroid | None:
        with self._lock:
            polaroids = list_polaroids(self._data)
            if not polaroids:
                return None
            if current_pid is None:
                return polaroids[0]
            idx = self.polaroid_index_of(current_pid)
            if idx < 0 or idx + 1 >= len(polaroids):
                return None
            return polaroids[idx + 1]

    def prev_polaroid(self, current_pid: str | None) -> Polaroid | None:
        with self._lock:
            polaroids = list_polaroids(self._data)
            if not polaroids or current_pid is None:
                return None
            idx = self.polaroid_index_of(current_pid)
            if idx <= 0:
                return None
            return polaroids[idx - 1]

    def next_untagged(self, current_pid: str | None) -> Polaroid | None:
        """返回下一张没有标签的拍立得，并跳过已经打标的记录。"""
        with self._lock:
            polaroids = list_polaroids(self._data)
            for i, p in enumerate(polaroids):
                if current_pid is not None and p.id == current_pid:
                    for q in polaroids[i + 1:]:
                        if not q.tags:
                            return q
                    return None
                if current_pid is None and not p.tags:
                    return p
            return None

    # ---- 标签池元数据的增删改查 ----
    def tag_info(self, prefix: str, key: str) -> dict[str, Any]:
        with self._lock:
            return self.tag_metadata(prefix).get(key, {}) or {}

    def set_tag_info(self, prefix: str, key: str, info: dict[str, Any]) -> None:
        """写入标签元数据；传入空字典时删除该键。"""
        with self._lock:
            if not info:
                self._data.setdefault("tags", {}).setdefault(prefix, {}).pop(key, None)
                return
            self.upsert_tag(prefix, key, info)

    def delete_tag(self, prefix: str, key: str) -> None:
        with self._lock:
            tags_root = self._data.setdefault("tags", {})
            bucket = tags_root.get(prefix)
            if isinstance(bucket, dict):
                bucket.pop(key, None)

    def all_tags_in_pool(self, prefix: str) -> dict[str, dict[str, Any]]:
        """列出指定前缀下所有已注册标签及其元数据。"""
        with self._lock:
            return dict(self.tag_metadata(prefix))

    def polaroids_with_tag(self, prefix: str, value: str) -> list[Polaroid]:
        with self._lock:
            target = f"{prefix}:{value}"
            return [p for p in list_polaroids(self._data) if target in p.tags]  # noqa: E501

    # ---- drop 工作流: 追加 / 编辑 (/new 走 form 提交, 不走 API) ----

    def append_files(
        self,
        pid: str,
        paths: list[str],
        roles: list[str] | None = None,
    ) -> Polaroid:
        """把 F:盘路径集合追加到现有 polaroid。

        角色默认从现有 polaroid 的资产数开始计数: 若 polaroid 已有 0 个资产
        则新加的为 front; 已有 1 个则新加的为 back; 已有 2+ 则为 additional。
        roles 不为空时覆盖默认, 长度必须与 paths 一致。
        """
        if not paths:
            raise ValueError("paths 不能为空")
        if roles is not None and len(roles) != len(paths):
            raise ValueError("roles 数量必须与 paths 一致")

        with self._lock:
            polaroid = None
            for p_dict in self._data.get("polaroids", []):
                if p_dict.get("id") == pid:
                    polaroid = Polaroid.from_dict(p_dict)
                    break
            if polaroid is None:
                raise ValueError(f"未找到拍立得: {pid}")

            existing_count = len(polaroid.assets)
            for i, raw_path in enumerate(paths):
                if roles is not None:
                    role = roles[i]
                else:
                    # 已有 N 个: 下一个从 N 开始计数
                    role = _default_role_for_index(existing_count + i)
                asset = Asset.from_path(raw_path, role=role)
                asset.ensure_thumb(self.data_dir)
                polaroid.assets.append(asset)

            self.upsert_polaroid(polaroid)
            self.save()
            return polaroid