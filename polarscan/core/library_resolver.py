"""路径发现：从浏览器拖入的文件元数据反查 F:盘候选路径。

零 F:盘读 IO（只 stat），不依赖 yaml 索引，不读文件内容。
浏览器沙箱拿不到 File.path，只能从 name/size/lastModified 反查。

约束：
- 只扫 PNG。无损格式是 OTA 的硬约束，不接受 JPG/JPEG 等有损源文件。
- 命中条件：name AND size AND mtime 三字段全等。
- 不预设有"应跳过"的目录。drop 是用户主动行为，工具不该替用户决定
  "哪些不该被看到"。

本模块历史位置 `apps/web/library_resolver.py`——纯算法无 web 特定逻辑，
迁入 core 是为了配合 [library-root-semantics](../docs/spec/library-root-semantics.md)
收口：实物层逻辑（library_root + 路径反查）由 core 统一封装。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# OTA 硬约束：只接受 PNG。有损格式不入库，理由是照片本身已经是数字化的
# 拍立得源，任何再压缩都是信息损失。
PATTERNS: tuple[str, ...] = ("*.png",)


@dataclass(frozen=True)
class Triple:
    """浏览器 File 的可观察三元组。

    `mtime` 是 **整数 epoch 秒**（UTC）。Windows NTFS 的 st_mtime 有亚秒精度，
    但浏览器 `File.lastModified` 只有毫秒精度，亚秒位对不上会导致 float `==` 失败。
    双方都截断到整数秒即可对齐——秒级精度对"是不是同一张扫描图"已经足够。
    浏览器侧前端需 `round(lastModifiedMs / 1000)` 再传入。
    """
    name: str
    size: int
    mtime: int


@dataclass(frozen=True)
class Candidate:
    """路径发现命中：F:盘上某个真实路径，对应某个查询三元组。"""
    path: Path


def identify_candidates(
    library_root: str | Path,
    queries: Iterable[Triple],
) -> dict[Triple, list[Candidate]]:
    """对每个查询三元组，返回 F:盘上 name AND size AND mtime 全等的候选路径列表。

    行为：
    - 一次 rglob 扫描整个 library_root，按 (name, size) 建内存索引，再按 mtime 过滤。
    - 不可读文件（权限错 / 临时消失）跳过，不抛异常。
    - 同一文件可能多次命中（不应发生，但 defsive）。
    - 多次同名/同 size（不同 mtime）的查询互不干扰。

    返回：{query_triple: [Candidate, ...]}，未命中时值为空列表。
    """
    root = Path(library_root)
    if not root.is_dir():
        # library_root 不存在或不是目录：所有查询返回空。
        return {qt: [] for qt in queries}

    # 一次扫描，按 (name, size) 分桶，每桶存 (mtime, path) 列表。
    bucket: dict[tuple[str, int], list[tuple[int, Path]]] = {}
    for pattern in PATTERNS:
        for p in root.rglob(pattern):
            try:
                st = p.stat()
            except OSError:
                # 文件不可访问（权限 / 临时消失）—— 跳过，不污染结果
                continue
            key = (p.name, st.st_size)
            # 截断到整数秒，与 Triple.mtime 类型对齐
            bucket.setdefault(key, []).append((round(st.st_mtime), p))

    # 查询：对每个 qt 在对应桶里筛 mtime 相等的 path
    result: dict[Triple, list[Candidate]] = {}
    for qt in queries:
        entries = bucket.get((qt.name, qt.size), [])
        result[qt] = [
            Candidate(path=path) for mtime, path in entries if mtime == qt.mtime
        ]
    return result
