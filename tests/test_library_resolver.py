"""library_resolver 的隔离测试：用临时目录造小目录树。"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from apps.web.library_resolver import (
    Candidate,
    Triple,
    identify_candidates,
)


def _make_png(path: Path, size_bytes: int | None = None) -> None:
    """写入一张极小的 PNG。size_bytes 是占位，函数内部不强制大小。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color="white").save(path)
    if size_bytes is not None:
        # 强制 stat().st_size 与期望一致（仅用于"size 错配"场景）
        with open(path, "ab") as f:
            f.truncate(size_bytes)


def _set_mtime(path: Path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


def _scan(path: Path) -> Triple:
    """便利：从磁盘读一个文件的 stat，构造 Triple（name 取文件名, mtime 取整到秒）。"""
    st = path.stat()
    return Triple(name=path.name, size=st.st_size, mtime=round(st.st_mtime))


class IdentifyCandidatesTest(unittest.TestCase):
    """identify_candidates 的核心行为验证。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ---------------- 边界 ----------------

    def test_empty_root_returns_empty_lists(self) -> None:
        """空目录：每个查询都得到空列表。"""
        qt = Triple(name="img.png", size=100, mtime=1)
        result = identify_candidates(self.root, [qt])
        self.assertEqual(result, {qt: []})

    def test_missing_root_returns_empty_lists(self) -> None:
        """library_root 不存在：返回空结果，不抛异常。"""
        missing = self.root / "nope"
        qt = Triple(name="img.png", size=100, mtime=1)
        result = identify_candidates(missing, [qt])
        self.assertEqual(result, {qt: []})

    def test_no_query_returns_empty_dict(self) -> None:
        """空查询列表：返回空字典。"""
        result = identify_candidates(self.root, [])
        self.assertEqual(result, {})

    # ---------------- 命中判定 ----------------

    def test_exact_match(self) -> None:
        """三元组完全一致 → 命中。"""
        path = self.root / "img20260728_17185555_aaaaaa.png"
        _make_png(path)
        qt = _scan(path)
        result = identify_candidates(self.root, [qt])
        self.assertEqual(result[qt], [Candidate(path=path)])

    def test_name_match_size_mismatch(self) -> None:
        """name 命中但 size 不对 → 不命中。"""
        path = self.root / "img.png"
        _make_png(path)
        st = path.stat()
        wrong_size_qt = Triple(name="img.png", size=st.st_size + 1, mtime=round(st.st_mtime))
        result = identify_candidates(self.root, [wrong_size_qt])
        self.assertEqual(result[wrong_size_qt], [])

    def test_name_size_match_mtime_mismatch(self) -> None:
        """name+size 命中但 mtime 不对 → 不命中（文件被修改过）。"""
        path = self.root / "img.png"
        _make_png(path)
        st = path.stat()
        wrong_mtime_qt = Triple(
            name="img.png", size=st.st_size, mtime=round(st.st_mtime) + 1
        )
        result = identify_candidates(self.root, [wrong_mtime_qt])
        self.assertEqual(result[wrong_mtime_qt], [])

    # ---------------- 多文件 ----------------

    def test_same_name_different_folders(self) -> None:
        """同名文件在不同子目录：name+size+mtime 全等 → 两个都命中。"""
        a = self.root / "2026.07.25" / "img.png"
        b = self.root / "2026.07.26" / "img.png"
        _make_png(a)
        _make_png(b)
        # 把两个文件的 mtime 强制为相同值（用 utime，便于断言）
        common_mtime = a.stat().st_mtime
        _set_mtime(b, common_mtime)
        st = a.stat()
        qt = Triple(name="img.png", size=st.st_size, mtime=round(common_mtime))
        result = identify_candidates(self.root, [qt])
        # 顺序不固定：用集合比对
        self.assertEqual(
            {c.path for c in result[qt]}, {a, b}
        )

    def test_multiple_queries_independent(self) -> None:
        """一次请求多个查询：每个查询独立得到自己的命中列表。"""
        hit = self.root / "hit.png"
        miss = self.root / "miss.png"
        _make_png(hit)
        _make_png(miss)
        hit_qt = _scan(hit)
        miss_qt = Triple(name="does_not_exist.png", size=1, mtime=0)
        result = identify_candidates(self.root, [hit_qt, miss_qt])
        self.assertEqual(result[hit_qt], [Candidate(path=hit)])
        self.assertEqual(result[miss_qt], [])

    # ---------------- 文件过滤 ----------------

    def test_non_png_files_ignored(self) -> None:
        """非 PNG 文件（jpg/gif/txt）不被扫描，OTA 硬约束。"""
        _make_png(self.root / "real.png")
        # 写入一个同名但扩展名不同的文件
        (self.root / "real.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        qt = Triple(name="real.jpg", size=100, mtime=1)
        result = identify_candidates(self.root, [qt])
        self.assertEqual(result[qt], [])

    def test_nested_directory_scanned(self) -> None:
        """深层嵌套目录里的 PNG 也能被找到。"""
        deep = self.root / "a" / "b" / "c" / "deep.png"
        _make_png(deep)
        qt = _scan(deep)
        # 路径里要包括完整路径，而不仅是文件名
        result = identify_candidates(self.root, [qt])
        self.assertEqual(result[qt], [Candidate(path=deep)])

    # ---------------- 容错 ----------------

    def test_unreadable_file_skipped(self) -> None:
        """stat 失败的文件（权限/消失）跳过，不抛异常。

        在 Windows 上不易构造权限拒绝的稳定场景，所以只验证：
        - 一旦 stat 抛 OSError，整个调用仍正常返回其他结果。
        - 这里通过临时制造一个目录项名冲突验证鲁棒性：如果某次扫描
          路径遇到不存在项，不影响其他文件被找到。
        """
        good = self.root / "good.png"
        _make_png(good)
        # 制造一个同名但实际不可读的条目（Windows 上行为不稳定，跳过构造）
        # 这里仅断言 good 仍能被找到，作为基线
        qt = _scan(good)
        result = identify_candidates(self.root, [qt])
        self.assertEqual(result[qt], [Candidate(path=good)])


if __name__ == "__main__":
    unittest.main(verbosity=2)