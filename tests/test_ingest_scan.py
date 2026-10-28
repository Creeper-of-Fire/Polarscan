"""ingest_scan facade 测试：存储区扫描的发现 / 幂等 / dup / 降级行为。

测试造临时 library_root + data_dir（tests/ 不受 AST 守卫约束），
全部断言走 `polarscan.api.Polarscan.ingest_scan`（facade 层，与 server 同路径）。

覆盖（docs/spec/ingest-scan.md § 4）：
- library_root 缺失 / 不存在 → 空结果（优雅降级）
- 新文件 → new 含 path + 128hex hash + 缩略图已生成
- 幂等：入库后重扫 → new 空，skipped_known 计数
- dup_pid：库中已有同 hash（不同 path）→ 指向该 pid
- 仅 *.png 参与；单文件失败不阻塞
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from polarscan.api import Polarscan
from polarscan.core.storage import write_index


def make_png(path: Path, color: str = "white", size: tuple[int, int] = (60, 90)) -> None:
    Image.new("RGB", size, color).save(path, "PNG")


class IngestScanTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="polarscan_ingest_")
        base = Path(self._tmp.name)
        self.library = base / "library"
        self.data_dir = base / "data"
        (self.library / "2026.10.17-18").mkdir(parents=True)
        self.data_dir.mkdir()
        write_index(self.data_dir, {
            "library_root": str(self.library),
            "version": 1,
            "tags": {},
            "polaroids": [],
        })

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _ps(self) -> Polarscan:
        return Polarscan(self.data_dir)

    # ------------------------------------------------------------------
    def test_library_root_missing_graceful(self) -> None:
        """library_root 缺失 → 空结果，不抛错（同 drop-identify 降级）。"""
        write_index(self.data_dir, {
            "library_root": None, "version": 1, "tags": {}, "polaroids": [],
        })
        result = self._ps().ingest_scan()
        self.assertEqual(result.new, [])
        self.assertEqual(result.skipped_known, 0)
        self.assertEqual(result.errors, [])

    def test_empty_library(self) -> None:
        """空目录 → 空结果。"""
        result = self._ps().ingest_scan()
        self.assertEqual(result.new, [])

    def test_new_files_hash_and_thumb(self) -> None:
        """新文件 ×2 → new 两项；hash 128 hex；缩略图已生成在 data_dir/.thumbs/。"""
        d = self.library / "2026.10.17-18"
        make_png(d / "a.png", "white")
        make_png(d / "b.png", "black")

        result = self._ps().ingest_scan()

        self.assertEqual(len(result.new), 2)
        self.assertEqual(result.skipped_known, 0)
        self.assertEqual(result.errors, [])
        for item in result.new:
            self.assertEqual(len(item.hash), 128)
            self.assertIsNone(item.dup_pid)
            thumb = self.data_dir / ".thumbs" / f"{Path(item.path).stem}_{item.hash[:6]}.jpg"
            self.assertTrue(thumb.exists(), f"缩略图未生成: {thumb}")

    def test_idempotent_after_ingest(self) -> None:
        """入库后重扫 → new 空、skipped_known=2（幂等）。"""
        d = self.library / "2026.10.17-18"
        make_png(d / "a.png", "white")
        make_png(d / "b.png", "black")

        ps = self._ps()
        first = ps.ingest_scan()
        self.assertEqual(len(first.new), 2)

        # 模拟前端 PUT 落库：把两个 asset 挂到某 polaroid
        data = ps.data
        data["polaroids"].append({
            "id": "2026-10-17_x_ab12cd",
            "shot_date": None,
            "tags": [],
            "notes": "",
            "assets": [
                {"role": "front", "path": it.path, "device": None,
                 "hash": it.hash, "metadata": {}}
                for it in first.new
            ],
            "metadata": {},
        })
        write_index(self.data_dir, data)
        ps.reload()

        second = ps.ingest_scan()
        self.assertEqual(second.new, [])
        self.assertEqual(second.skipped_known, 2)

    def test_dup_pid_for_rescanned_content(self) -> None:
        """库中已有同 hash（重扫换文件名）→ dup_pid 指向该 pid。"""
        d = self.library / "2026.10.17-18"
        make_png(d / "a.png", "white")
        ps = self._ps()
        first = ps.ingest_scan()
        self.assertEqual(len(first.new), 1)

        data = ps.data
        data["polaroids"].append({
            "id": "2026-10-17_y_ff9900",
            "shot_date": None, "tags": [], "notes": "",
            "assets": [{"role": "front", "path": first.new[0].path, "device": None,
                        "hash": first.new[0].hash, "metadata": {}}],
            "metadata": {},
        })
        write_index(self.data_dir, data)

        # 同内容新文件名（不同像素尺寸会产生不同 hash，所以复制同文件）
        dup_file = d / "a_rescan.png"
        dup_file.write_bytes((d / "a.png").read_bytes())
        ps.reload()

        result = ps.ingest_scan()
        self.assertEqual(len(result.new), 1)
        self.assertEqual(result.new[0].dup_pid, "2026-10-17_y_ff9900")

    def test_only_png_participates(self) -> None:
        """仅 *.png 参与（OTA 硬约束）；jpg 不出现在结果里。"""
        d = self.library / "2026.10.17-18"
        make_png(d / "a.png", "white")
        Image.new("RGB", (60, 90), "white").save(d / "b.jpg", "JPEG")

        result = self._ps().ingest_scan()
        self.assertEqual(len(result.new), 1)
        self.assertTrue(result.new[0].path.endswith("a.png"))

    def test_missing_library_root_dir(self) -> None:
        """library_root 指向不存在的目录 → 空结果。"""
        write_index(self.data_dir, {
            "library_root": str(self.library / "nope"),
            "version": 1, "tags": {}, "polaroids": [],
        })
        result = self._ps().ingest_scan()
        self.assertEqual(result.new, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
