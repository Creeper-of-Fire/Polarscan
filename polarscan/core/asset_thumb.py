"""资产级哈希与缩略图生成基础函数。

本模块只负责计算哈希和生成 JPEG，不依赖 Asset 数据类或 Polaroid。

设计动机：
- 缩略图命名规则与业务耦合，放在 `index.py` 的 Asset 类方法中。
- 本模块只计算哈希和写入图像，不决定存放位置与文件名。
- 因而更便于测试和复用。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image


# ============================================================
# 常量
# ============================================================
LONG_EDGE = 1024          # 缩略图长边像素
QUALITY = 85              # JPEG 质量
HASH_ALGO = "blake2b"     # 速度快于 sha256，个人资料库无需额外抗冲突能力
HASH_HEX_LEN = 128        # blake2b(digest_size=64)：64 字节，即 128 个十六进制字符
SHORT_HASH_LEN = 6        # 缩略图文件名使用的十六进制短哈希长度
THUMBS_DIRNAME = ".thumbs"


# ============================================================
# 哈希计算
# ============================================================
def compute_hash(src: str | Path) -> str:
    """以流式方式计算 blake2b 哈希，处理大文件时不会一次占满内存。

    返回 128 个十六进制字符。
    """
    h = hashlib.blake2b(digest_size=64)
    with open(src, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================
# 缩略图生成
# ============================================================
def make_thumb_image(src: Path, dst: Path) -> Path:
    """将 JPEG 缩略图生成到 `dst`；目标已存在时直接返回。

    注意：这里不检测命名冲突，同名目标可能被覆盖。调用方应保证目标文件名
    由哈希派生；6 位十六进制短哈希共有约 1600 万种组合。
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
