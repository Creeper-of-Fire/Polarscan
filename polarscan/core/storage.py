"""读写唯一的 `_index.yaml` 真值文件。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .index import Polaroid


INDEX_FILENAME = "_index.yaml"


def _default() -> dict[str, Any]:
    return {
        "library_root": None,  # 自己就是数据目录
        "version": 1,
        "tags": {},           # 按前缀嵌套的元数据池，按需填充
        "polaroids": [],
    }


def read_index(library_root: str | Path) -> dict[str, Any]:
    """从 `library_root` 读取 `_index.yaml`；文件不存在时返回默认结构。

    数据结构包含 `library_root`、`version`、`tags` 和 `polaroids`。
    """
    path = Path(library_root) / INDEX_FILENAME
    if not path.exists():
        d = _default()
        d["library_root"] = str(library_root)
        return d
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # 补齐缺失的顶层字段
    defaults = _default()
    for k, v in defaults.items():
        data.setdefault(k, v)
    if not data.get("library_root"):
        data["library_root"] = str(library_root)
    if not isinstance(data.get("tags"), dict):
        data["tags"] = {}
    if not isinstance(data.get("polaroids"), list):
        data["polaroids"] = []
    # 清理标签池中的空值或非字典值，这是初始化脚本的历史残留
    for prefix in list(data["tags"].keys()):
        if not isinstance(data["tags"][prefix], dict):
            data["tags"][prefix] = {}
    return data


def write_index(library_root: str | Path, data: dict[str, Any]) -> None:
    """原子写入 `_index.yaml`：先写临时文件，再重命名替换。

    `width=4096`：抑制 PyYAML 默认 80 字符的硬换行。资产路径 `F:\\相册\\...`
    是长绝对路径，默认宽度会被强行折成多行，产生看起来像\"改了内容\"的 diff。
    4096 是足以容纳最常见路径的\"实际不限宽度\"——不必再上调。
    """
    path = Path(library_root) / INDEX_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=4096,
        )
    tmp.replace(path)


def list_polaroids(data: dict[str, Any]) -> list[Polaroid]:
    return [Polaroid.from_dict(p) for p in data.get("polaroids", [])]
