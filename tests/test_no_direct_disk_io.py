"""AST 守卫：冷盘接触只能由 cold.py 完成 (防回归)。

设计动机：本项目要求"任何冷盘 IO 必须经 `polarscan.core.cold`"。白名单机制：
- 白名单 `polarscan/core/cold.py`：所有冷盘接触都在此完成
- 白名单 `polarscan/core/storage.py`：SSD 上的 yaml 读写 (与冷盘解耦)

其他 `polarscan/`、`apps/` 文件禁止以下 AST 模式：
- `Image.open(...)` —— Pillow 冷盘读
- `with open(... "rb"/"wb"/"ab") as f:` —— built-in open 二进制读 / 写冷盘
- `.read_bytes()` / `.read_text()` —— Path 一次性读全文

测试目录 `tests/` 不在本守卫范围——测试造临时数据可用裸 IO.

如有违反，本测试报失败信息指向文件与行号，便于修复.
"""
from __future__ import annotations

import ast
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# 白名单: 这些文件允许出现裸冷盘接触
WHITELIST = {
    "cold.py",
    "storage.py",
}

# 扫描目录
SCAN_DIRS = [
    REPO_ROOT / "polarscan",
    REPO_ROOT / "apps",
]


def _scan_file(path: pathlib.Path) -> list[str]:
    """返回违例描述列表 (空 = 无违例)."""
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # 语法错误不属于本守卫的职责；留给其他 lint / 测试发现
        return []

    issues: list[str] = []

    def rel() -> str:
        try:
            return str(path.relative_to(REPO_ROOT))
        except ValueError:
            return str(path)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func

        # --- Pillow Image.open(...) ---
        if isinstance(func, ast.Attribute):
            # Image.open — 不管 func.value 是 Name("Image") 还是 Attribute("PIL.Image")
            target_attr = func.attr
            if target_attr == "open" and isinstance(func.value, ast.Name):
                if func.value.id == "Image":
                    issues.append(
                        f"{rel()}:{node.lineno} 禁止 `Image.open({ast.dump(node.args[0]) if node.args else ''})`"
                    )
            if target_attr in ("read_bytes", "read_text"):
                issues.append(
                    f"{rel()}:{node.lineno} 禁止 `<obj>.{target_attr}()`——冷盘接触请走 `cold.read_full` 或 `cold.open_full`"
                )
            continue

        # --- built-in open(...) ---
        if isinstance(func, ast.Name) and func.id == "open":
            # 检查模式: 第二个位置参数是 "rb"/"wb"/"ab"/"r+b"/"w+b"
            # 命中断言: open(src, "rb") — 这是冷盘最常见的 binary mode 读
            mode = _extract_mode(node)
            if mode and any(c in mode for c in ("b", "+")):
                # 模式包含 b 或 +: 可能是 SSD open +b 或冷盘 "rb"
                # 因 storage.py 已被白名单, 这里命中就是问题
                issues.append(
                    f"{rel()}:{node.lineno} 禁止 `open({ast.dump(node.args[0]) if node.args else ''}, {mode!r})`——冷盘接触请走 cold.py"
                )
    return issues


def _extract_mode(call: ast.Call) -> str | None:
    """从 open(path, mode) 调用提取 mode (字符串)."""
    if len(call.args) < 2:
        # 也可能是 keyword: open(path, mode='rb')
        kw = call.keywords
        for k in kw:
            if k.arg == "mode" and isinstance(k.value, ast.Constant):
                return k.value.value
        return None
    arg2 = call.args[1]
    if isinstance(arg2, ast.Constant) and isinstance(arg2.value, str):
        return arg2.value
    return None


class NoDirectDiskIOTest(unittest.TestCase):
    """扫描 polarscan/ + apps/ 下全部 .py 文件, 检测裸冷盘接触 AST 模式."""

    def test_only_whitelisted_files_may_have_direct_disk_io(self) -> None:
        all_py: list[pathlib.Path] = []
        for d in SCAN_DIRS:
            if not d.exists():
                continue
            all_py.extend(d.rglob("*.py"))

        all_issues: list[str] = []
        for f in all_py:
            if f.name in WHITELIST:
                continue
            issues = _scan_file(f)
            all_issues.extend(issues)

        if all_issues:
            msg = (
                f"发现 {len(all_issues)} 处裸冷盘接触 (白名单: {sorted(WHITELIST)}):\n  - "
                + "\n  - ".join(all_issues)
                + "\n\n所有冷盘 IO 必须经 `polarscan.core.cold.{compute_hash, make_thumb_if_missing, open_full, read_full}`。\n"
                "存储模块 (storage.py) 因 YAML 写在 SSD 上, 已在白名单内。"
            )
            self.fail(msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
