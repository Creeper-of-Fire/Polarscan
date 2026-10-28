"""存储区扫描（ingest）：发现 library_root 下未入库的 PNG，产出 hash 与缩略图。

explicit gesture 语义：由用户点击"扫描"触发（HTTP `POST /api/ingest/scan`），
与 drop-identify 的单次 rglob 先例一致。本模块：

- **不写 yaml**——只发现与产出（hash / 缩略图），不修改索引；落库由前端逐卡 PUT 完成
- 冷盘接触全部走 cold gate（`compute_hash` + `make_thumb_if_missing`）
- path 对比用 `resolve()` 后的绝对路径——与 yaml 中既有资产 path 的存储形式对齐
- 正反判定不在这里：判定由前端围绕缩略图完成（见 docs/spec/ingest-scan.md § 2.3）
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cold import compute_hash, make_thumb_if_missing
from .library_resolver import PATTERNS


@dataclass(frozen=True)
class IngestNewItem:
    """一个未入库文件：path + hash（128 hex）+ 缩略图已生成。

    `dup_pid`：库中已有同 hash 资产的第一个 polaroid id（重扫件提示），
    没有则为 None。由前端展示并由用户决定跳过还是挂为该条的资产。
    """
    path: str
    hash: str
    dup_pid: str | None


@dataclass(frozen=True)
class IngestError:
    """单个文件处理失败（hash / 缩略图产出阶段），不阻塞其他文件。"""
    path: str
    reason: str


@dataclass(frozen=True)
class IngestScanResult:
    new: list[IngestNewItem]
    skipped_known: int      # path 已在 yaml 中的数量（幂等：重复扫描恒增此计数）
    errors: list[IngestError]


def scan_library(data: dict[str, Any], data_dir: str | Path) -> IngestScanResult:
    """单次扫描 library_root，返回未入库文件清单（explicit gesture，不写 yaml）。

    行为：
    - `library_root` 缺失 / 不是目录 → 空结果（优雅降级，同 drop-identify）
    - 仅 `*.png`（OTA 硬约束，PATTERNS 单源）
    - 对每个新文件：`compute_hash`（cold gate 读 #1）→ `make_thumb_if_missing`
      （cold gate 读 #2）→ 报告 `dup_pid`
    - 单文件失败只进 errors，不中断整批
    """
    library_root = data.get("library_root")
    if not library_root:
        return IngestScanResult(new=[], skipped_known=0, errors=[])
    root = Path(library_root)
    if not root.is_dir():
        return IngestScanResult(new=[], skipped_known=0, errors=[])

    # yaml 现有资产的 path 集合 + hash → pid 索引（首个命中）
    known_paths: set[str] = set()
    hash_to_pid: dict[str, str] = {}
    for p in data.get("polaroids", []):
        pid = str(p.get("id", ""))
        for a in p.get("assets", []):
            apath = a.get("path")
            if apath:
                known_paths.add(apath)
            ahash = a.get("hash")
            if ahash and ahash not in hash_to_pid:
                hash_to_pid[ahash] = pid

    new_items: list[IngestNewItem] = []
    errors: list[IngestError] = []
    skipped = 0
    for pattern in PATTERNS:
        for png in root.rglob(pattern):
            try:
                s = str(png.resolve())
            except OSError as e:
                errors.append(IngestError(path=str(png), reason=f"resolve 失败: {e}"))
                continue
            if s in known_paths:
                skipped += 1
                continue
            try:
                h = compute_hash(s)
                make_thumb_if_missing(data_dir, s, h)
            except OSError as e:
                errors.append(IngestError(path=s, reason=str(e)))
                continue
            new_items.append(IngestNewItem(path=s, hash=h, dup_pid=hash_to_pid.get(h)))
    return IngestScanResult(new=new_items, skipped_known=skipped, errors=errors)
