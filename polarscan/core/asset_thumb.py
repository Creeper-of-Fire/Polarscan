"""Asset-level hash + thumb image primitives.

底层: hash 计算 + jpg 生成. 不依赖 Asset dataclass / Polaroid.

设计动机:
- 命名规则 (thumb 文件名) 跟业务耦合, 放到 index.py 的 Asset 类方法.
- 这里只做"算 hash"和"画 jpg", 不做"放哪里叫什么名字".
- 这样测试和复用都干净.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image


# ============================================================
# 常量
# ============================================================
LONG_EDGE = 1024          # thumb 长边像素
QUALITY = 85              # jpg 质量
HASH_ALGO = "blake2b"     # 比 sha256 快, 个人库不需要 collision 抵抗
HASH_HEX_LEN = 128        # blake2b(digest_size=64) -> 64 bytes -> 128 hex chars
SHORT_HASH_LEN = 6        # thumb 文件名用的短哈希位数 (hex)
THUMBS_DIRNAME = ".thumbs"


# ============================================================
# Hash
# ============================================================
def compute_hash(src: str | Path) -> str:
    """流式算 blake2b hash. 大文件不会爆内存.

    Returns: 128 char hex string.
    """
    h = hashlib.blake2b(digest_size=64)
    with open(src, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================
# Thumb image
# ============================================================
def make_thumb_image(src: Path, dst: Path) -> Path:
    """生成 thumb jpg 到 dst. dst 已存在直接返回 (skip).

    注意: 不做 collision 检测 — 同名 dst 会被覆盖. 调用方应保证
    dst 文件名基于 hash 派生, 实际撞的概率极低 (16M 种).
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return dst
    with Image.open(src) as im:
        im.thumbnail((LONG_EDGE, LONG_EDGE), Image.LANCZOS)
        if im.mode in ("RGBA", "P", "LA"):
            im = im.convert("RGB")
        im.save(dst, "JPEG", quality=QUALITY, optimize=True)
    return dst
