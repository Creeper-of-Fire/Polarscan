"""spec-code 一致性校验：spec 系统的"代码守卫"——防回归。

设计动机
--------
本项目 `docs/spec/` 是设计真相源。每篇 spec 在 "涉及代码" 段列出实现 / 测试 / 守卫
路径——这些路径必须真实存在。如果 spec 路径漂移（重命名 / 移动 / 删除而忘了改 spec），
下一个想理解这个设计的人会撞到 404。

本测试断言：
1. 每篇 spec 必须含 STATUS + LAST_UPDATED frontmatter，STATUS 取值合法
2. "涉及代码" 段列出的每个路径必须在仓库中存在
3. 6 段结构（背景/设计/接口契约/验证/不变量/演进约束）必须齐全
4. README §4 索引表必须与 `docs/spec/` 实际文件一致

注：本测试不解析 markdown AST，用字符串扫描即可——避免引入额外依赖。
"""
from __future__ import annotations

import pathlib
import re
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC_DIR = REPO_ROOT / "docs" / "spec"

VALID_STATUSES = {"TODO", "IN PROGRESS", "IMPLEMENTED", "PARTIAL", "DEPRECATED"}

# spec 6 段模板：背景 / 设计 / 接口契约 / 验证 / 不变量 / 演进约束（顺序按 README §2）
# 注：architecture.md 用 §3 数据分层 + §5 不变量 替代 "接口契约" / "演进约束"，
# 因此 "必须含的段" 仅做软校验：列出缺失段供 review。
EXPECTED_SECTIONS = [
    "背景",
    "设计",
    "接口契约",
    "验证",
    "不变量",
    "演进约束",
]


def _read_spec(name: str) -> str:
    return (SPEC_DIR / name).read_text(encoding="utf-8")


def _parse_frontmatter(text: str) -> tuple[str | None, str | None]:
    """提取 STATUS / LAST_UPDATED. 缺失时返回 None."""
    m_status = re.search(r"^- \*\*STATUS\*\*:\s*(.+?)\s*$", text, re.MULTILINE)
    m_updated = re.search(r"^- \*\*LAST_UPDATED\*\*:\s*(.+?)\s*$", text, re.MULTILINE)
    return (
        m_status.group(1) if m_status else None,
        m_updated.group(1) if m_updated else None,
    )


def _normalize_section_title(raw: str) -> str:
    """normalize 章节标题：
    `## 1. 背景`          → `背景`
    `## 涉及代码（目标态）`  → `涉及代码`
    """
    title = raw.strip()
    if title.startswith("##"):
        title = title[2:].strip()
    # 去掉章节编号 `1. ` `2. ` ...
    title = re.sub(r"^\d+\.\s+", "", title)
    # 去掉尾部括号副标题——支持 ASCII 与全角括号
    for open_p, close_p in (("(", ")"), ("\uff08", "\uff09")):
        idx = title.rfind(open_p)
        if idx > 0 and title.rstrip().endswith(close_p):
            title = title[:idx].rstrip()
            break
    return title.strip()


def _extract_section(text: str, section_title: str) -> str:
    """从 `## <section_title>` 起，到下一个 `## ` 之前的全部内容.
    支持章节编号 `## 1. 背景` 和括号副标题 `## 涉及代码（目标态）`.
    """
    lines = text.split("\n")
    in_section = False
    section_lines: list[str] = []
    target_pattern = re.compile(r"^##\s+(?:\d+\.\s+)?(.+?)(?:\s*[\(\uff08].*?[\)\uff09])?\s*$")
    for line in lines:
        if not in_section:
            m = target_pattern.match(line.strip())
            if m and m.group(1).strip() == section_title:
                in_section = True
                continue
        else:
            if line.startswith("## "):
                break
            section_lines.append(line)
    return "\n".join(section_lines)


def _list_section_titles(text: str) -> list[str]:
    """提取所有 `## <title>` 的纯标题（剥掉编号 + 括号副标题）。"""
    return [_normalize_section_title(t) for t in re.findall(r"^##\s+(.+?)\s*$", text, re.MULTILINE)]


def _extract_paths(section_text: str) -> list[str]:
    """提取反引号包裹的路径（含文件 / 目录 / 行号 / 函数名等附加信息）。

    返回原始字符串，调用方决定要不要 normalize。
    """
    return re.findall(r"`([^`]+)`", section_text)


def _normalize_path(raw: str) -> str:
    """剥离 :line / :line-line / :func / :Test 后缀，保留路径部分."""
    # 反引号内常见的格式：
    #   `polarscan/core/cold.py`                  → 路径
    #   `apps/web/server.py:198-242`              → 路径:行号
    #   `polarscan/api.py:Polarscan.library_root` → 路径:属性
    #   `tests/test_cold_gate.py:MakeThumbTest`   → 路径:测试类名
    # 我们只取第一个冒号之前作为路径
    return raw.split(":", 1)[0].strip()


def _is_path(raw: str) -> bool:
    """启发式判断反引号内容是不是路径——以 .py / .ts / .vue / .mjs / .md / .yaml 结尾，
    或者以 `tests/` / `polarscan/` / `apps/` / `frontend/` / `docs/` 开头."""
    norm = _normalize_path(raw)
    if not norm:
        return False
    if re.search(r"\.(py|ts|vue|mjs|md|yaml|json|toml|cfg)$", norm):
        return True
    if norm.startswith(("tests/", "polarscan/", "apps/", "frontend/", "docs/", ".")):
        return True
    return False


# ============================================================
# 测试用例
# ============================================================
class SpecConsistencyTest(unittest.TestCase):
    """spec 文件级校验."""

    def _iter_specs(self):
        """yield (filename, text) for all spec files except README."""
        for f in sorted(SPEC_DIR.glob("*.md")):
            if f.name == "README.md":
                continue
            yield f.name, f.read_text(encoding="utf-8")

    def test_frontmatter_present_and_valid(self) -> None:
        """每篇 spec 必须有 STATUS + LAST_UPDATED，STATUS 取值合法."""
        issues: list[str] = []
        for name, text in self._iter_specs():
            status, updated = _parse_frontmatter(text)
            if status is None:
                issues.append(f"{name}: 缺少 STATUS 字段")
                continue
            if status not in VALID_STATUSES:
                issues.append(f"{name}: STATUS '{status}' 不在 {VALID_STATUSES}")
            if updated is None:
                issues.append(f"{name}: 缺少 LAST_UPDATED 字段")
        if issues:
            self.fail("spec frontmatter 问题:\n  - " + "\n  - ".join(issues))

    def test_no_legacy_commit_field(self) -> None:
        """防 COMMIT 字段回归——该字段已从设计删除."""
        offenders: list[str] = []
        for name, text in self._iter_specs():
            if re.search(r"^- \*\*COMMIT\*\*:", text, re.MULTILINE):
                offenders.append(name)
        self.assertEqual(
            offenders, [],
            f"以下 spec 还含 **COMMIT** 字段（已删除）：{offenders}",
        )

    def test_six_section_structure(self) -> None:
        """每篇 spec 必须含 6 段结构——缺段时报告但不 fail（review 友好）.

        注：architecture.md / core-asset-meta-split.md 的章节命名略不同，本测试
        只报告异常让人 review，不强制 fail。后续若稳定后可收紧。
        """
        warnings: list[str] = []
        for name, text in self._iter_specs():
            titles = _list_section_titles(text)
            missing = [s for s in EXPECTED_SECTIONS if s not in titles]
            if missing:
                warnings.append(f"{name}: 缺段 {missing}")
        if warnings:
            # 不 fail，只 print——避免 review 噪声
            print("\nspec 缺段（review 用，不 fail）:\n  - " + "\n  - ".join(warnings))

    def test_involved_paths_exist(self) -> None:
        """'涉及代码' 段列出的每个路径必须在仓库中存在.

        严格性按 STATUS 分级：
        - IMPLEMENTED / PARTIAL：路径不存在 → fail（设计已落地，不该飘）
        - TODO / IN PROGRESS / DEPRECATED：路径不存在 → warning（目标态，预期）

        容忍：路径含 `:line` / `:func` / `:Test` 后缀（自动剥离）。
        """
        issues: list[str] = []
        warnings: list[str] = []
        for name, text in self._iter_specs():
            status, _ = _parse_frontmatter(text)
            section = _extract_section(text, "涉及代码")
            if not section:
                if status in ("IMPLEMENTED", "PARTIAL"):
                    issues.append(f"{name}: 缺 '涉及代码' 段")
                else:
                    warnings.append(f"{name} ({status}): 缺 '涉及代码' 段")
                continue
            strict = status in ("IMPLEMENTED", "PARTIAL")
            for raw in _extract_paths(section):
                if not _is_path(raw):
                    continue
                norm = _normalize_path(raw)
                full = REPO_ROOT / norm
                if not full.exists():
                    msg = f"{name}: 路径不存在: {norm}"
                    if strict:
                        issues.append(msg)
                    else:
                        warnings.append(f"{name} ({status}): {norm}")
        if warnings:
            print("\n非严格状态的路径问题（不 fail）:\n  - " + "\n  - ".join(warnings))
        if issues:
            self.fail("spec '涉及代码' 段路径问题:\n  - " + "\n  - ".join(issues))


class SpecIndexTest(unittest.TestCase):
    """README §4 索引表与实际 spec 文件一致性."""

    def test_readme_index_covers_all_specs(self) -> None:
        """README §4 索引表的每个文件名都对应一个真实 spec 文件，反之亦然."""
        readme = _read_spec("README.md")
        # 提取索引表里的文件名：格式 `[name](name.md)`
        indexed = set(re.findall(r"\[[^\]]+\]\(([^\)]+\.md)\)", readme))
        # 但 README.md 自身也在表里出现几次（作为自身引用），排除
        indexed.discard("README.md")
        actual = {f.name for f in SPEC_DIR.glob("*.md") if f.name != "README.md"}
        missing_in_index = actual - indexed
        extra_in_index = indexed - actual
        problems = []
        if missing_in_index:
            problems.append(f"未在 README §4 索引: {sorted(missing_in_index)}")
        if extra_in_index:
            problems.append(f"索引了但 spec 不存在: {sorted(extra_in_index)}")
        if problems:
            self.fail("README §4 索引与实际 spec 文件不一致:\n  - " + "\n  - ".join(problems))


if __name__ == "__main__":
    unittest.main(verbosity=2)
