"""id_gen 派生的回归测试。

重点：派生 id 必须允许中文等 Unicode 字符（现实工作流中用户大量使用中文角色）。
"""
from __future__ import annotations

import re
import unittest

from polarscan.core.id_gen import make_polaroid_id, parse_primary_char


_HEX_SUFFIX = re.compile(r"_[a-f0-9]{6}$")


class MakePolaroidIdTest(unittest.TestCase):
    def test_ascii_basic(self) -> None:
        """老例子：ASCII 路径继续按原格式工作。"""
        pid = make_polaroid_id("2025-10-18", "Ayako")
        self.assertTrue(pid.startswith("2025-10-18_ayako_"))
        self.assertRegex(pid, _HEX_SUFFIX)

    def test_chinese_primary_char_preserved(self) -> None:
        """中文角色名应原样保留在 id 中，不被吞成 -。"""
        pid = make_polaroid_id("2026-08-04", "电电")
        self.assertTrue(pid.startswith("2026-08-04_电电_"), msg=f"got {pid!r}")
        self.assertRegex(pid, _HEX_SUFFIX)

    def test_chinese_only(self) -> None:
        """纯中文 char + 缺日期也要保留中文。"""
        pid = make_polaroid_id(None, "小薰Ayako")
        self.assertTrue(pid.startswith("nostamp_小薰ayako_"), msg=f"got {pid!r}")

    def test_punctuation_replaced_with_dash(self) -> None:
        """标点和空白仍要替换为 -，保证可读。"""
        pid = make_polaroid_id("2026-08-04", "my char!")
        self.assertTrue(pid.startswith("2026-08-04_my-char_"), msg=f"got {pid!r}")

    def test_empty_inputs_use_fallbacks(self) -> None:
        """空输入 → nostamp / nochar 占位。"""
        pid = make_polaroid_id()
        self.assertTrue(pid.startswith("nostamp_nochar_"), msg=f"got {pid!r}")

    def test_suffix_is_unique_hex(self) -> None:
        """6 位 hex 后缀每次都不一样。"""
        seen = {make_polaroid_id("2026-08-04", "Ayako") for _ in range(20)}
        self.assertEqual(len(seen), 20)


class ParsePrimaryCharTest(unittest.TestCase):
    def test_explicit_char_tag(self) -> None:
        self.assertEqual(parse_primary_char(["char:电电", "shot:solo"]), "电电")

    def test_fallback_when_no_prefix(self) -> None:
        self.assertEqual(parse_primary_char(["北北鱼", "shot:solo"]), "北北鱼")

    def test_returns_none(self) -> None:
        self.assertIsNone(parse_primary_char([]))


if __name__ == "__main__":
    unittest.main()
