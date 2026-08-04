"""Polarscan 反向查找方法的隔离测试。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from polarscan.api import Polarscan
from polarscan.core import Asset, Polaroid


def _make_png(path: Path, color: str = "white") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=color).save(path)


class LibraryRootTest(unittest.TestCase):
    """library_root property 直接读 yaml schema 字段。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_default_value(self) -> None:
        """新 data_dir 没有 _index.yaml 时，library_root 默认为 data_dir 自身。"""
        ps = Polarscan(self.data_dir)
        self.assertEqual(ps.library_root, str(self.data_dir))

    def test_reflects_yaml_field(self) -> None:
        """reload 后 library_root 反映 yaml 内容。"""
        ps = Polarscan(self.data_dir)
        ps._data["library_root"] = r"F:\相册\偶活"
        self.assertEqual(ps.library_root, r"F:\相册\偶活")


class FindByHashTest(unittest.TestCase):
    """find_by_hash 行为验证。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.img_a = self.data_dir / "a.png"
        self.img_b = self.data_dir / "b.png"
        self.img_c = self.data_dir / "c.png"
        # 用不同颜色保证 hash 互不相同
        _make_png(self.img_a, color="red")
        _make_png(self.img_b, color="green")
        _make_png(self.img_c, color="blue")
        # 三个真实 hash
        self.hash_a = Asset.from_path(self.img_a).hash
        self.hash_b = Asset.from_path(self.img_b).hash
        self.hash_c = Asset.from_path(self.img_c).hash
        assert self.hash_a and self.hash_b and self.hash_c
        # 三张拍立得：p1=[a], p2=[a, b], p3=[c]
        self.ps = Polarscan(self.data_dir)
        self.ps.upsert_polaroid(
            Polaroid(id="p1", assets=[Asset(role="front", path=str(self.img_a), hash=self.hash_a)])
        )
        self.ps.upsert_polaroid(
            Polaroid(
                id="p2",
                assets=[
                    Asset(role="front", path=str(self.img_a), hash=self.hash_a),  # 重复 hash
                    Asset(role="back", path=str(self.img_b), hash=self.hash_b),
                ],
            )
        )
        self.ps.upsert_polaroid(
            Polaroid(id="p3", assets=[Asset(role="front", path=str(self.img_c), hash=self.hash_c)])
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_match(self) -> None:
        self.assertEqual(self.ps.find_by_hash("nonexistent_hash"), [])

    def test_empty_input(self) -> None:
        self.assertEqual(self.ps.find_by_hash(""), [])
        self.assertEqual(self.ps.find_by_hash(None), [])  # type: ignore[arg-type]

    def test_single_match(self) -> None:
        """hash_c 只在 p3 中 → 单条结果。"""
        result = self.ps.find_by_hash(self.hash_c)
        self.assertEqual(result, [("p3", 0)])

    def test_multiple_matches_same_hash(self) -> None:
        """hash_a 同时在 p1 (idx=0) 和 p2 (idx=0) → 两条结果。"""
        result = self.ps.find_by_hash(self.hash_a)
        self.assertEqual(set(result), {("p1", 0), ("p2", 0)})

    def test_multiple_assets_in_one_polaroid(self) -> None:
        """hash_b 在 p2 中位置 idx=1 → 单条。"""
        result = self.ps.find_by_hash(self.hash_b)
        self.assertEqual(result, [("p2", 1)])

    def test_after_reload_still_works(self) -> None:
        """reload 后索引重建（无缓存），行为一致。"""
        self.ps.save()
        self.ps.reload()
        self.assertEqual(set(self.ps.find_by_hash(self.hash_a)),
                         {("p1", 0), ("p2", 0)})


class FindByPathTest(unittest.TestCase):
    """find_by_path 行为验证。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.path_a = str(self.data_dir / "a.png")
        self.path_b = str(self.data_dir / "b.png")
        _make_png(Path(self.path_a), color="red")
        _make_png(Path(self.path_b), color="green")
        self.ps = Polarscan(self.data_dir)
        self.ps.upsert_polaroid(
            Polaroid(id="p1", assets=[Asset(role="front", path=self.path_a)])
        )
        self.ps.upsert_polaroid(
            Polaroid(
                id="p2",
                assets=[
                    Asset(role="front", path=self.path_a),  # 重复路径
                    Asset(role="back", path=self.path_b),
                ],
            )
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_match(self) -> None:
        self.assertEqual(self.ps.find_by_path("Z:/nonexistent.png"), [])

    def test_empty_input(self) -> None:
        self.assertEqual(self.ps.find_by_path(""), [])
        self.assertEqual(self.ps.find_by_path(None), [])  # type: ignore[arg-type]

    def test_single_match(self) -> None:
        result = self.ps.find_by_path(self.path_b)
        self.assertEqual(result, [("p2", 1)])

    def test_multiple_matches_same_path(self) -> None:
        result = self.ps.find_by_path(self.path_a)
        self.assertEqual(set(result), {("p1", 0), ("p2", 0)})

    def test_strict_equality_no_normalize(self) -> None:
        """不同形式路径不视为相等（不做 normalize）。"""
        # 大小写不同 / 分隔符不同 / 末尾斜杠 — 都不命中
        result = self.ps.find_by_path(self.path_a.upper())
        self.assertEqual(result, [])
        result = self.ps.find_by_path(self.path_a.replace("\\", "/"))
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)