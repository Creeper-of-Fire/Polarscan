"""Polaroid id 派生.

id 格式: {shot_date or 'nostamp'}_{primary_char or 'nochar'}_{6hex}

性质:
- id 一旦派生并写入 yaml 后就"冻结", 后续改 shot_date / char 都不变.
- 6 位 hex 不做 collision retry; 撞了用户手动改 yaml.
- 派生函数是 pure (除了随机部分), 可以对相同输入产生不同 id; 真随机就够了.
"""
from __future__ import annotations

import re
import secrets


# 容许的 id 字符 (slug-like)
_ID_OK = re.compile(r"[^a-z0-9_\-]+")


def _safe(s: str | None, fallback: str) -> str:
    """Sanitize string for use in id. Lowercase, keep alnum/-/_."""
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
    """生成 6 位 hex 后缀的派生 id. 不做 collision retry.

    Examples:
        make_polaroid_id("2025-10-18", "strawberry")
            → '2025-10-18_strawberry_4a7b1c'
        make_polaroid_id()
            → 'nostamp_nochar_9e3d2a'
    """
    date_part = _safe(shot_date, "nostamp")
    char_part = _safe(primary_char, "nochar")
    suffix = secrets.token_hex(3)  # 6 chars
    return f"{date_part}_{char_part}_{suffix}"


def parse_primary_char(tags: list[str]) -> str | None:
    """从 polaroid 的 tag 列表里取第一个 'char:' tag 的 value. 用于 id 派生."""
    for t in tags:
        if t.startswith("char:"):
            return t[len("char:"):]
        if ":" not in t and not t.startswith(("event:", "theme:", "collection:", "composite:", "moment:", "shot:", "sig:")):
            # bare tag, 没前缀, 也当作 char (按"统一约定")
            return t
    return None
