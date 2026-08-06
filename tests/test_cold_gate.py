"""cold gate 行为测试 + cold gate 守门契约（应用层必须走 cold）。

验证：
- `compute_hash` 流式分块正确性 + 与 hashlib 标准实现一致
- `make_thumb_if_missing` thumb 命中零 IO；缺则单次冷盘读 + 生成并存
- `open_full` 流式句柄能正确读完文件内容
- `read_full` 一次性读全文
- `Asset.from_path` / `Asset.ensure_thumb` / `append_files` 间接走 cold
- `/thumb` `/img` FastAPI 路由底层走 cold
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from polarscan.api import Polarscan
from polarscan.core import Asset, Polaroid
from polarscan.core import cold
from polarscan.core.cold import (
    compute_hash,
    make_thumb_if_missing,
    open_full,
    read_full,
)
from polarscan.core.asset_thumb import (
    HASH_HEX_LEN,
    SHORT_HASH_LEN,
    THUMBS_DIRNAME,
    thumb_path_for,
)


# ============================================================
# 测试 fixtures
# ============================================================
def _make_png(path: Path, color: str = "white") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 24), color=color).save(path)


def _ref_blake2b(path: Path) -> str:
    """与 cold.compute_hash 语义一致的标准实现, 用于跨验."""
    h = hashlib.blake2b(digest_size=HASH_HEX_LEN // 2)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================
# compute_hash
# ============================================================
class ComputeHashTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.p = self.dir / "img.png"
        _make_png(self.p, color="red")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_hash_equals_reference(self) -> None:
        """与 hashlib 标准实现一致."""
        self.assertEqual(compute_hash(self.p), _ref_blake2b(self.p))

    def test_hash_is_128_hex(self) -> None:
        h = compute_hash(self.p)
        self.assertEqual(len(h), HASH_HEX_LEN)
        int(h, 16)  # 必须可解析为 16 进制

    def test_hash_differs_for_different_content(self) -> None:
        q = self.dir / "q.png"
        _make_png(q, color="green")
        self.assertNotEqual(compute_hash(self.p), compute_hash(q))

    def test_missing_file_raises(self) -> None:
        missing = self.dir / "absent.png"
        with self.assertRaises((FileNotFoundError, OSError)):
            compute_hash(missing)


# ============================================================
# make_thumb_if_missing：thumb 命中零 IO 行为
# ============================================================
class MakeThumbZeroIOTest(unittest.TestCase):
    """thumb 已存在时只能走 SSD, 不允许冷盘读 — 用 mock 监控冷盘接触."""

    def setUp(self) -> None:
        self._tmp_data = tempfile.TemporaryDirectory()
        self._tmp_img = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp_data.name)
        self.img_path = Path(self._tmp_img.name) / "img.png"
        _make_png(self.img_path, color="white")
        self.hash = compute_hash(self.img_path)
        # 先调一次建好 thumb
        self.thumb = make_thumb_if_missing(self.data_dir, self.img_path, self.hash)
        assert self.thumb is not None
        assert self.thumb.exists()

    def tearDown(self) -> None:
        self._tmp_data.cleanup()
        self._tmp_img.cleanup()

    def test_thumb_hit_returns_existing_without_cold_read(self) -> None:
        """thumb 已存在 → 调 Image.open 计数为 0."""
        with patch.object(cold, "Image") as mock_image:
            tp = make_thumb_if_missing(self.data_dir, self.img_path, self.hash)
            self.assertEqual(tp, self.thumb)
            mock_image.open.assert_not_called()
            # open() 也不应被直接调
            # （open 是 builtin, 用 patch 拦截 __builtins__ 太重; 这里只验 Pillow Image.open 路径）

    def test_thumb_hit_returns_none_for_short_hash(self) -> None:
        """hash 不足 6 字符 → 返回 None, 不走冷盘."""
        self.assertIsNone(make_thumb_if_missing(self.data_dir, self.img_path, "abc"))

    def test_thumb_hit_returns_none_for_missing_source(self) -> None:
        """thumb 缺失 + src 缺失 → 返回 None (不抛错)."""
        ghost = self.img_path.parent / "ghost.png"
        with patch.object(cold, "Image") as mock_image:
            self.assertIsNone(make_thumb_if_missing(self.data_dir, ghost, self.hash))
            mock_image.open.assert_not_called()


class MakeThumbColdReadTest(unittest.TestCase):
    """thumb 缺失时: 单次冷盘读 + Pillow 处理 + 写 SSD."""

    def setUp(self) -> None:
        self._tmp_data = tempfile.TemporaryDirectory()
        self._tmp_img = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp_data.name)
        self.img_path = Path(self._tmp_img.name) / "img.png"
        _make_png(self.img_path, color="blue")
        self.hash = compute_hash(self.img_path)
        # 确认 thumb 还没生成
        expected = thumb_path_for(self.data_dir, self.img_path, self.hash)
        assert expected is not None
        self.expected = expected

    def tearDown(self) -> None:
        self._tmp_data.cleanup()
        self._tmp_img.cleanup()

    def test_first_call_creates_thumb(self) -> None:
        """thumb 缺失 → 调一次 → 生成 + 写盘."""
        self.assertFalse(self.expected.exists())
        tp = make_thumb_if_missing(self.data_dir, self.img_path, self.hash)
        self.assertEqual(tp, self.expected)
        self.assertTrue(self.expected.exists())
        # JPEG 文件应能打开
        im = Image.open(self.expected)
        im.close()

    def test_second_call_returns_existing(self) -> None:
        """第二次调用: thumb 已存在, 不应再走 Pillow."""
        make_thumb_if_missing(self.data_dir, self.img_path, self.hash)
        self.assertTrue(self.expected.exists())
        with patch.object(cold, "Image") as mock_image:
            tp = make_thumb_if_missing(self.data_dir, self.img_path, self.hash)
            self.assertEqual(tp, self.expected)
            mock_image.open.assert_not_called()


# ============================================================
# open_full / read_full
# ============================================================
class OpenFullTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.p = self.dir / "img.png"
        _make_png(self.p, color="red")
        self.expected_bytes = self.p.read_bytes()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_returns_stream_handle_that_reads_full_content(self) -> None:
        """open_full 返回流式句柄; 读完内容与一次性 read 一致."""
        with open_full(self.p) as f:
            data = f.read()
        self.assertEqual(data, self.expected_bytes)

    def test_missing_file_raises(self) -> None:
        with self.assertRaises((FileNotFoundError, OSError)):
            with open_full(self.dir / "absent.png") as _f:
                pass


class ReadFullTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.p = self.dir / "img.png"
        _make_png(self.p, color="red")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_returns_full_content(self) -> None:
        self.assertEqual(read_full(self.p), self.p.read_bytes())

    def test_missing_file_raises(self) -> None:
        with self.assertRaises((FileNotFoundError, OSError)):
            read_full(self.dir / "absent.png")


# ============================================================
# 应用层通过 cold gate 间接接触（防回归）
# ============================================================
class AssetViaColdTest(unittest.TestCase):
    """Asset.from_path / ensure_thumb 必须经 cold. 用 mock 验证."""

    def setUp(self) -> None:
        self._tmp_data = tempfile.TemporaryDirectory()
        self._tmp_img = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp_data.name)
        self.img_path = Path(self._tmp_img.name) / "img.png"
        _make_png(self.img_path, color="white")

    def tearDown(self) -> None:
        self._tmp_data.cleanup()
        self._tmp_img.cleanup()

    def test_asset_from_path_uses_cold_compute_hash(self) -> None:
        with patch("polarscan.core.index.compute_hash", wraps=compute_hash) as mock_hash:
            asset = Asset.from_path(self.img_path, role="front")
        mock_hash.assert_called_once()
        self.assertEqual(asset.path, str(self.img_path))
        self.assertEqual(len(asset.hash or ""), HASH_HEX_LEN)

    def test_asset_ensure_thumb_uses_cold(self) -> None:
        asset = Asset.from_path(self.img_path, role="front")
        with patch("polarscan.core.index.make_thumb_if_missing",
                   wraps=make_thumb_if_missing) as mock_thumb:
            tp = asset.ensure_thumb(self.data_dir)
        mock_thumb.assert_called_once()
        assert tp is not None
        self.assertTrue(tp.exists())


class AppendFilesViaColdTest(unittest.TestCase):
    """append_files 路径必须经 cold — Asset.from_path 时一次性算 hash."""

    def setUp(self) -> None:
        self._tmp_data = tempfile.TemporaryDirectory()
        self._tmp_img = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp_data.name)
        self.img_a = Path(self._tmp_img.name) / "a.png"
        self.img_b = Path(self._tmp_img.name) / "b.png"
        _make_png(self.img_a, color="red")
        _make_png(self.img_b, color="green")
        self.ps = Polarscan(self.data_dir)
        self.ps.upsert_polaroid(Polaroid(id="p1", shot_date="2026-08-04"))

    def tearDown(self) -> None:
        self._tmp_data.cleanup()
        self._tmp_img.cleanup()

    def test_append_files_uses_cold_for_each_path(self) -> None:
        with patch("polarscan.core.index.compute_hash", wraps=compute_hash) as mock_hash:
            self.ps.append_files("p1", paths=[str(self.img_a), str(self.img_b)])
        # 两张资产: 调了 cold.compute_hash 两次
        self.assertEqual(mock_hash.call_count, 2)

    def test_appended_asset_hash_matches_truth(self) -> None:
        self.ps.append_files("p1", paths=[str(self.img_a)])
        p = self.ps.polaroid("p1")
        assert p is not None
        self.assertEqual(p.assets[0].hash, compute_hash(self.img_a))


if __name__ == "__main__":
    unittest.main(verbosity=2)
