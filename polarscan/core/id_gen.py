"""拍立得 id 派生。

格式：`{shot_date or 'nostamp'}_{primary_char or 'nochar'}_{6hex}`。

性质：
- id 派生并写入 YAML 后即冻结，后续修改 `shot_date` 或 `char` 不会改变它。
- 6 位十六进制后缀不做冲突重试；若发生冲突，由用户手动修改 YAML。
- 除随机后缀外，派生逻辑是纯函数；相同输入可以生成不同 id。
- 允许 Unicode 字母/数字（包括中文）。空白、标点、控制字符等替换为 `-`。
- id 是用户在工作台手输可改的标识，因此仅做"清白"清洗，不做更严限制。
"""
from __future__ import annotations

import re
import secrets


# id 允许的字符：Unicode 字母/数字 + 连字符 + 下划线。
# re.UNICODE 让 \w 匹配中文等 Unicode 字符；其他字符（含空白、标点、路径分隔符）
# 替换为 `-`，既保留可读性又避免破坏 YAML/URL。
_ID_OK = re.compile(r"[^\w\-]+", re.UNICODE)


def _safe(s: str | None, fallback: str) -> str:
    """清理用于 id 的字符串：转小写，仅保留 Unicode 字母/数字 + 连字符/下划线。

    空白、标点、控制字符等替换为 `-`；中文/日文/韩文等 Unicode 字母直接保留。
    """
    if not s:
        return fallback
    s = s.strip().lower()
    s = _ID_OK.sub("-", s)
    s = s.strip("-") or fallback
    # 截短避免太长
    return s[:32] if len(s) > 32 else s


def make_polaroid_id(
    shot_date: str | None = None,
    primary_char: str | None = None,
) -> str:
    """生成带 6 位十六进制后缀的派生 id，不做冲突重试。

    示例：
        make_polaroid_id("2025-10-18", "小薰")
            → '2025-10-18_小薰_4a7b1c'
        make_polaroid_id("2026-08-04", "电电")
            → '2026-08-04_电电_4a7b1c'
        make_polaroid_id()
            → 'nostamp_nochar_9e3d2a'
    """
    date_part = _safe(shot_date, "nostamp")
    char_part = _safe(primary_char, "nochar")
    suffix = secrets.token_hex(3)  # 6 个十六进制字符
    return f"{date_part}_{char_part}_{suffix}"


def parse_primary_char(tags: list[str]) -> str | None:
    """从拍立得标签中取第一个 `char:` 标签的值，用于派生 id。"""
    for t in tags:
        if t.startswith("char:"):
            return t[len("char:"):]
        if ":" not in t and not t.startswith(("event:", "theme:", "collection:", "composite:", "moment:", "shot:", "sig:")):
            # 无前缀标签按统一约定视为角色标签
            return t
    return None
