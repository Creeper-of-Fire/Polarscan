"""数据模型：包含资产的 Polaroid，以及标签辅助函数。"""
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
    """属于某张拍立得的单个扫描文件。

    `role` 是自由格式标记，例如 `front`、`back`、`back_signature` 或 `front_v2`。
    同一角色可以有多个资产，只有 `supersedes` 用于判断当前版本。

    `hash` 是 128 位十六进制 blake2b 值，在创建资产时写入一次，浏览时不再计算。
    它支持两项能力：
    - 直接由路径与哈希派生缩略图文件名 `{stem}_{hash[:6]}.jpg`，浏览时无需访问 F 盘。
    - 未来的离线路径修复工具可在原图根目录中重定位资产，再按哈希匹配并重写 YAML 路径。

    `metadata` 是任意 JSON 的透传字典——core 不解析、不校验、不截断其内部结构。
    业务字段（人名 / 事件名 / 评分 / 自定义键值）一律塞这里。
    """

    role: str
    path: str
    device: Optional[str] = None
    hash: Optional[str] = None  # 128 位十六进制 blake2b；首次写入前为空
    metadata: dict[str, Any] = field(default_factory=dict)  # 任意 JSON 透传

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Asset":
        return cls(
            role=str(d.get("role", "front")),
            path=str(d["path"]),
            device=d.get("device"),
            hash=d.get("hash"),
            metadata=d.get("metadata") or {},
        )

    # ------------------------------------------------------------------
    # 工厂：计算哈希并创建资产实例
    # ------------------------------------------------------------------
    @classmethod
    def from_path(cls, src: str | Path, role: str = "front",
                  device: Optional[str] = None) -> "Asset":
        """读取源文件并计算哈希，返回已填充 `hash` 字段的 Asset。

        这是写入新资产的入口，只在创建时访问一次 F 盘。
        """
        return cls(
            role=role,
            path=str(src),
            device=device,
            hash=compute_hash(src),
        )

    # ------------------------------------------------------------------
    # 缩略图派生（不访问 F 盘）
    # ------------------------------------------------------------------
    def thumb_filename(self) -> Optional[str]:
        """返回形如 `img20260728_17185555_a3b4c5.jpg` 的缩略图文件名。

        哈希缺失时返回 None，表示旧资产尚未迁移。
        """
        if not self.hash:
            return None
        return _thumb_filename(self.path, self.hash)

    def thumb_path(self, data_dir: str | Path) -> Optional[Path]:
        """返回 `data_dir/.thumbs/` 下的完整路径；哈希缺失时返回 None。"""
        return thumb_path_for(data_dir, self.path, self.hash)

    def has_thumb(self, data_dir: str | Path) -> bool:
        """缩略图文件存在时返回 True；只检查 SSD，不访问 F 盘。"""
        tp = self.thumb_path(data_dir)
        return tp is not None and tp.exists()

    def ensure_thumb(self, data_dir: str | Path,
                     src_path: str | Path | None = None) -> Optional[Path]:
        """生成缩略图文件，已存在时直接跳过；只在生成时访问一次 F 盘。

        `src_path` 省略时使用 `self.path`；哈希或源文件缺失时返回 None。
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
    """一张实体拍立得，可以包含一个或多个扫描资产。

    不可变的 `id` 是身份标识，其余字段均为元数据。

    `metadata` 是任意 JSON 的透传字典——core 不解析、不校验、不截断其内部结构。
    业务字段（人名 / 事件名 / 评分 / 自定义键值）一律塞这里。
    """

    id: str
    shot_date: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    assets: list[Asset] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)  # 任意 JSON 透传

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Polaroid":
        return cls(
            id=str(d["id"]),
            shot_date=d.get("shot_date"),
            tags=[str(t) for t in d.get("tags", [])],
            notes=str(d.get("notes", "")),
            assets=[Asset.from_dict(a) for a in d.get("assets", [])],
            metadata=d.get("metadata") or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "shot_date": self.shot_date,
            "tags": list(self.tags),
            "notes": self.notes,
            "assets": [asdict(a) for a in self.assets],
            "metadata": dict(self.metadata),
        }


def tag_prefix(tag: str) -> str:
    """返回 `prefix:value` 标签的前缀；没有前缀时返回空字符串。"""
    if ":" in tag:
        return tag.split(":", 1)[0]
    return ""


def tag_value(tag: str) -> str:
    """返回 `prefix:value` 标签的值；没有前缀时返回完整字符串。"""
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag


# ============================================================
# 缩略图命名（单源真值）
# ============================================================
def _thumb_filename(path: str | Path, hash: str) -> str:
    """缩略图文件名公式：`{Path(path).stem}_{hash[:SHORT_HASH_LEN]}.jpg`。

    所有缩略图派生都走这里——Asset / server / api 都不可硬编码公式。
    """
    return f"{Path(path).stem}_{hash[:SHORT_HASH_LEN]}.jpg"


def thumb_path_for(
    data_dir: str | Path,
    path: str | Path,
    hash: str | None,
) -> Optional[Path]:
    """根据 `(path, hash)` 派生缩略图完整路径；hash 缺失或太短返回 None。

    纯路径计算，不访问 F 盘——已被 `Asset.thumb_path` 与 `apps/web/server.py:/thumb` 复用。
    """
    if not hash or len(hash) < SHORT_HASH_LEN:
        return None
    return Path(data_dir) / THUMBS_DIRNAME / _thumb_filename(path, hash)
