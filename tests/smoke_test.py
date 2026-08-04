"""核心数据读写与标签查询的隔离冒烟测试。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from polarscan.api import Polarscan
from polarscan.core import Asset, Polaroid


class PolarscanSmokeTest(unittest.TestCase):
    """验证核心接口只在临时目录中读写。"""

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._temp_dir.name)
        self.image_path = self.data_dir / "sample.png"
        Image.new("RGB", (32, 24), color="white").save(self.image_path)
        self.ps = Polarscan(self.data_dir)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_core_workflow(self) -> None:
        """验证新建、持久化、查询、缩略图与删除流程。"""
        asset = Asset.from_path(self.image_path, role="front")
        polaroid = Polaroid(
            id="sample_001",
            shot_date="2026-08-04",
            tags=["char:strawberry", "shot:solo"],
            notes="隔离冒烟测试",
            assets=[asset],
        )

        self.ps.upsert_polaroid(polaroid)
        self.ps.set_tag_info(
            "char",
            "strawberry",
            {"canonical_name": "草莓", "aliases": ["strawberry"]},
        )
        self.ps.save()
        self.ps.reload()

        loaded = self.ps.polaroid("sample_001")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.notes, "隔离冒烟测试")
        self.assertEqual(self.ps.query_by_tag("shot:solo"), [loaded])
        self.assertEqual(self.ps.query_by_prefix("char"), [loaded])
        self.assertEqual(self.ps.tag_info("char", "strawberry")["canonical_name"], "草莓")

        thumb_path = self.ps.thumb_path_for(loaded)
        self.assertIsNotNone(thumb_path)
        assert thumb_path is not None
        self.assertTrue(thumb_path.is_file())
        self.assertEqual(thumb_path.suffix, ".jpg")

        self.assertTrue(self.ps.delete_polaroid("sample_001"))
        self.ps.save()
        self.ps.reload()
        self.assertIsNone(self.ps.polaroid("sample_001"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
