"""路径反查 facade：应用层入口，封装 library_root 字段。

设计动机
--------
[library-root-semantics](../docs/spec/library-root-semantics.md) 的 PARTIAL 状态要求：
应用层不应直接读 `Polarscan.library_root` 字段（半违规）。

本模块提供 `find_candidates_by_path(data, queries)`：
- 应用层传 Polarscan 实例的 `data` 视图（公开 facade 接口）
- library_root 字段由 core 内部从 data 提取——应用层不直接接触 schema 字段
- 不重新读 yaml：依赖调用方已加载的内存数据——避免每次调用 IO

这是 spec §3 目标态的落地：[api-facade](../docs/spec/api-facade.md) 不再
暴露 schema 字段，路径反查完全由 core 实物层封装。
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .library_resolver import Candidate, Triple, identify_candidates


def find_candidates_by_path(
    data: Mapping[str, Any],
    queries: Iterable[Triple],
) -> dict[Triple, list[Candidate]]:
    """对每个查询三元组，返回实物根（F:盘 / NAS）上 name AND size AND mtime 全等的候选路径列表.

    Args:
        data: yaml 数据视图（通常来自 `Polarscan.data` 属性）
        queries: 浏览器 File 元数据三元组列表

    Returns:
        {query_triple: [Candidate, ...]}，未命中时值为空列表。

    行为：
    - 直接从传入的 data 提取 library_root——不重新读 yaml，避免每次调用 IO
    - library_root 缺失或为空 → 返回空结果集（不抛错）—— 这是 drop 工作流的
      优雅降级：没 bootstrap 过实物根时仍可工作（仅 by_hash 命中，无路径反查）

    注：本函数不接触冷盘——只 stat 实物根下的 PNG 文件名（不读文件内容）。
    """
    queries_list = list(queries)
    library_root = data.get("library_root")
    if not library_root:
        # library_root 未设置或为空字符串 → 优雅降级：返回空结果集
        return {qt: [] for qt in queries_list}
    return identify_candidates(library_root, queries_list)
