"""缩略图 Pillow 像素处理 + 算法常量 + 缩略图命名公式（无冷盘 IO）。

冷盘 IO 由 `cold.py` 接管：本模块只接受已打开的 PIL Image 完成缩放与 JPEG 写入。
任何路径要接触冷盘源文件（`Image.open(path)`、`open(path, 'rb')` 等）必须经过 cold.py。

本模块内容：
- 算法常量（HASH_ALGO/HASH_HEX_LEN/LONG_EDGE/QUALITY/SHORT_HASH_LEN/THUMBS_DIRNAME）
- `encode_thumb(im, dst)`：纯 Pillow 处理
- `_thumb_filename(path, hash)`：缩略图文件名公式 `{stem}_{hash[:6]}.jpg`（单源真值）
- `thumb_path_for(data_dir, path, hash)`：纯 SSD 路径派生，避免任何冷盘接触

设计动机：让 AST 守卫 `tests/test_no_direct_disk_io.py` 能用"裸 IO 只能出现在 cold.py"
作为唯一硬约束。本模块无任何冷盘接触保证。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

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
# Pillow-only 处理（无冷盘 IO）
# ============================================================
def encode_thumb(im: Image.Image, dst: Path) -> Path:
    """将 PIL Image 缩放并以 JPEG 写盘。无冷盘 IO 读——src 已被 cold.py 打开。

    调用方已通过 cold.make_thumb_if_missing 决定是否需要读源文件；
    本函数只做"已读取像素 → 缩放 → 写 SSD"三步。
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return dst
    im2 = im.copy()
    im2.thumbnail((LONG_EDGE, LONG_EDGE), Image.LANCZOS)
    if im2.mode in ("RGBA", "P", "LA"):
        im2 = im2.convert("RGB")
    im2.save(dst, "JPEG", quality=QUALITY, optimize=True)
    return dst


# ============================================================
# 缩略图命名（单源真值）—— 纯 SSD 路径派生，零冷盘接触
# ============================================================
def _thumb_filename(path: str | Path, hash: str) -> str:
    """缩略图文件名公式：`{Path(path).stem}_{hash[:SHORT_HASH_LEN]}.jpg`。

    所有缩略图派生都走这里——Asset / cold / server / api 都不可硬编码公式。
    """
    return f"{Path(path).stem}_{hash[:SHORT_HASH_LEN]}.jpg"


def thumb_path_for(
    data_dir: str | Path,
    path: str | Path,
    hash: str | None,
) -> Optional[Path]:
    """根据 `(data_dir, path, hash)` 派生 `.thumbs/` 下完整路径；返回 None 当无效。

    纯 SSD 路径派生，无冷盘接触——被 Asset.thumb_path 与 cold.make_thumb_if_missing 复用。
    """
    if not hash or len(hash) < SHORT_HASH_LEN:
        return None
    return Path(data_dir) / THUMBS_DIRNAME / _thumb_filename(path, hash)
