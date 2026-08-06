"""冷数据网关——本项目**唯一**可读冷盘（F 盘 / NAS / 网络共享）的入口。

设计动机
--------
架构原则：冷盘必须保持休眠（机械盘会因唤醒降低寿命 + 增加卡顿；
NAS / 网络共享的网络握手延迟高且不可控）。任何代码路径要读冷盘
必须经过本模块。`Image.open(path)`、`Path.read_*`、`open(path, 'rb')`
等裸 IO 在 cold.py 之外出现视为架构违规（见 tests/test_no_direct_disk_io.py）。

策略
----
- `compute_hash(src)`: 隐式 explicit——调用方把读源哈希视为已达成 explicit gesture
  （drop 后端 hash / append 追加）。只读一次。大文件流式分块。
- `make_thumb_if_missing(data_dir, src_path, hash)`: 浏览路径——thumb 命中零冷盘读
  （只 stat SSD 上的 .thumbs），缺则单次冷盘读 → 生成并存。
- `open_full(src_path)` / `read_full(src_path)`: **必须**视为 explicit gesture——
  任何位置读原图都走这两个之一。`open_full` 流式句柄用于 `/img?path=` 路由；
  `read_full` 一次性字节用于 hash 校验 / 小图拷贝。

未来扩展
--------
- 升级 NAS / 网络共享时，本模块内部可加缓存策略（如 fragment-level preload）
  但调用方不应重建缓存或绕过本模块。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO, Optional

from PIL import Image

from .asset_thumb import (
    HASH_ALGO,            # noqa: F401  保留公开常量以兼容 core.__init__ 转发导出
    HASH_HEX_LEN,
    encode_thumb,
    thumb_path_for,
)


__all__ = [
    "compute_hash",
    "make_thumb_if_missing",
    "open_full",
    "read_full",
]


# ============================================================
# 流式哈希：cold disk read #1
# ============================================================
def compute_hash(src: str | Path) -> str:
    """以流式方式计算 blake2b 哈希（128 字符十六进制）。

    调用方应保证本函数在 explicit gesture 上下文中被调用，例如：
      - drop 工作流（用户拖入文件触发）
      - append_files（用户在工作台追加资产）
    多次对同一路径调用按需由调用方缓存（src -> hash）。
    """
    h = hashlib.blake2b(digest_size=HASH_HEX_LEN // 2)
    with open(src, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================
# 按需生成缩略图：cold disk read #2（仅在 thumb 缺失时）
# ============================================================
def make_thumb_if_missing(
    data_dir: str | Path, src_path: str | Path, hash: str | None,
) -> Optional[Path]:
    """Thumb 命中：仅 stat SSD（零冷盘读）；缺则单次冷盘读 + 生成 + 存。

    返回缩略图完整路径。下列任一条件返回 None：
      - hash 缺失或长度不足（无效命名）
      - 源文件不存在（按 explicit gesture 评估，调用方可决定如何处理）
    """
    tp = thumb_path_for(data_dir, src_path, hash)
    if tp is None:
        return None
    if tp.exists():
        return tp  # thumb 命中：零 IO
    src = Path(src_path)
    if not src.exists():
        return None
    # 单次冷盘读 + 生成
    with Image.open(src) as im:
        # Image.open 是惰性的，进入 context manager 等价 im.load()
        return encode_thumb(im, tp)


# ============================================================
# 打开 / 读原图：cold disk read #3（仅 explicit gesture）
# ============================================================
def open_full(src_path: str | Path) -> BinaryIO:
    """打开原图文件并返回流式句柄。**必须**视为 explicit gesture 调用。

    适用于大文件（扫描图 / NAS）的流式场景——返回的文件对象由调用方负责 close
    或用 `with cold.open_full(path) as f:` 上下文管理。
    """
    return Path(src_path).open("rb")


def read_full(src_path: str | Path) -> bytes:
    """读原图全文字节。**必须**视为 explicit gesture 调用。

    小图（数 MB）或一次性拷贝场景适用。大文件请用 `open_full` 流式，避免内存爆。
    任何"自动 / 嗅探 / 验真 / 校验"等目的都不应经此——应走 make_thumb_if_missing。
    """
    return Path(src_path).read_bytes()
