# SPEC: drop-identify（drop 工作流）

- **STATUS**: IMPLEMENTED
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- 后端端点：`apps/web/server.py`（`POST /api/drop/identify`）
- 路径反查 facade：`polarscan/core/find_candidates.py:find_candidates_by_path`
- 路径反查实现：`polarscan/core/library_resolver.py:identify_candidates`
- `Triple` / `Candidate` 数据类：`polarscan/core/library_resolver.py`
- yaml 数据视图：`polarscan/api.py:Polarscan.data`
- hash 反查：`polarscan/api.py:find_by_hash`
- 路径反查 yaml 命中：`polarscan/api.py:find_by_path`
- 前端状态机：`frontend/src/composables/useDropzone.ts`
- 测试：`tests/test_drop_identify.py`、`tests/test_library_resolver.py`

## 1. 背景

浏览器沙箱拿不到 `File.path`，只能从 `(name, size, lastModified)` 反查 F 盘候选路径。本 spec 定义 drop 时浏览器 / 后端协同的两阶段工作流。

## 2. 设计

### Phase 1（zero-hash candidates）

浏览器发送 `(name, size, lastModified_ms, hash="")`：

- 后端 `identify_candidates(library_root, [qt])`：单次 rglob 全库，按 `(name, size, mtime)` 分桶，过滤 mtime
- 返回 F 盘候选路径列表（每个含 `in_yaml_pid` / `in_yaml_hits` 命中信息）
- 后端 **跳过** hash 反查（`hash=""`）

### Phase 2（hash + 完整 identify）

仅对 Phase 1 后**无路径命中**的文件：

- 浏览器 `hash-wasm` 流式算 blake2b 128 hex
- 浏览器发送 `(name, size, lastModified_ms, hash)` 完整三元组
- 后端 `find_by_hash(h)` + 完整 `identify_candidates`

### 状态机

```
drop ──► candidates-checking (server: 空 hash, 只查 candidates)
     ├─► hashing + identifying (browser: 算 hash + server: by_hash 查询)
     │   [仅对需要 hash 的文件: 有 candidates 但无 path 命中]
     └─► ready
```

优化：
- candidates 为空 → 跳过 hash
- 路径命中（`in_yaml_hits` 非空）→ 跳过 hash（短路）

## 3. 接口契约

### HTTP

```
POST /api/drop/identify
Content-Type: application/json

{
  "name": "img20260728_17185555.png",
  "size": 12345,
  "lastModified_ms": 1785990000000,
  "hash": "" | "<128 hex>"
}

→ 200 {
  "by_hash": [{"pid": "...", "asset_idx": 0}, ...],
  "candidates": [
    {
      "path": "F:\\相册\\...",
      "in_yaml_pid": "..." | null,
      "in_yaml_hits": [{"pid": "...", "asset_idx": 0}, ...]
    }, ...
  ]
}
```

约束：
- `library_root` 为空 / None → `candidates` 永远为空（仍返回 `by_hash`）
- 缺 `name` / `size` / `lastModified_ms` → 400
- `lastModified_ms` 必须为数字

### rglob 行为

- 一次扫描整个 `library_root`，按 `(name, size)` 分桶 → 按 mtime 过滤
- 仅扫 `*.png`（OTA 硬约束；不接受 JPG/JPEG 等有损源文件）
- 不可读文件（权限 / 临时消失）跳过

## 4. 验证

- `tests/test_drop_identify.py`：8 个场景——缺字段 / 非法 JSON / by_hash 命中/miss/空 hash / candidate 三元组命中 / 候选不在 yaml / 无 library_root
- `tests/test_library_resolver.py`：边界（空目录 / 不存在根 / 空查询 / 文件过滤 / 多查询独立）
- 隐式测试：前端 `useDropzone.ts` 的 5 态状态机

## 5. 不变量

- 仅 `*.png` 文件参与反查（OTA 硬约束）
- Phase 1 总是先发；Phase 2 仅对需要 hash 的文件
- `candidates` 按 mtime 严格相等（避免浮点误差截断到秒——见 Triple.mtime 注释）
- 一次扫描不缓存 / 不预扫 / 不监听——explicit gesture 触发的单次 rglob 合法

## 6. 演进约束

- 未来 NAS / 网盘：`identify_candidates` 内部加缓存策略（fragment-level），调用方不变
- 多库支持：每个 data_dir 独立 `library_root`——`find_by_path` / `find_by_hash` 隔离
- 监听 F 盘 = 架构违规——见 [cold-data-gateway § 5](cold-data-gateway.md)

## 7. 引用

- [library-root-semantics](library-root-semantics.md)：library_root 字段（当前半违规）
- [cold-data-gateway](cold-data-gateway.md)：冷盘接触唯一面
- [asset-hash](asset-hash.md)：hash 算法