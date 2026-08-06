# SPEC: append-files（追加资产到现有 polaroid）

- **STATUS**: IMPLEMENTED
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- 路由：`apps/web/server.py:390-416`（`POST /api/polaroids/{pid}/append-files`）
- 写入：`polarscan/api.py:append_files`
- 冷盘接触：`polarscan/core/cold.py:compute_hash` + `make_thumb_if_missing`
- 测试：`tests/test_import_append_save.py:AppendFilesTest`

## 1. 背景

工作台追加资产：用户在工作台视图追加 F 盘路径集合到现有 polaroid。**与 PUT /polaroid 互补**：

- PUT：整体替换（hash 必填、前端算好）——适合编辑器
- append-files：增量追加（hash 服务端算、thumb 服务端按需生成）——适合 dropzone 增量

## 2. 设计

### 请求

```
POST /api/polaroids/{pid}/append-files
Content-Type: application/json

{
  "path": ["<绝对路径>", ...],
  "role": ["front" | "back" | "additional" | ..., ...]   // 可选
}
```

约束：
- `path` 非空列表
- `role` 若提供，长度 = `len(path)`；不提供则默认派生

### 默认 role 派生

```python
def _default_role_for_index(index: int) -> str:
    if index == 0: return "front"
    if index == 1: return "back"
    return "additional"
```

追加角色从 polaroid 已有资产数开始计数：
- 已有 0 个 → 新加为 front
- 已有 1 个 → 新加为 back
- 已有 2+ → 新加为 additional

### 服务端流程

```
1. pid 查找（不存在 → 404）
2. 已有 assets 数 = N
3. 对每个 path:
   - role = role[i] if provided else _default_role_for_index(N + i)
   - hash = cold.compute_hash(path)          # 单次冷盘读
   - ensure_thumb(data_dir, path, hash)      # 按需生成
4. upsert_polaroid + save (atomic write)
```

## 3. 接口契约

| 条件 | 行为 |
|---|---|
| `path` 空列表 | 400 |
| `role` 长度 ≠ `len(path)` | 400 |
| `pid` 不存在 | 404 |
| `path` 不可读（OSError） | 409 |

响应：`{"pid": "...", "asset_count": N + len(path)}`

约束：
- 服务端算 hash：冷盘接触走 cold gate
- 服务端按需生成 thumb：单次冷盘读（thumb 缺失时）
- 追加不删除已有资产

## 4. 验证

- `tests/test_import_append_save.py:AppendFilesTest`：
  - 默认 role 派生（已有 1 个 → back；已有 2 个 → additional）
  - 显式 role 覆盖默认
  - 未知 pid → 404

## 5. 不变量

- append_files 在 RLock 内执行——多个 append 不能并发修改同一 polaroid
- 冷盘接触全部经 cold gate（hash + ensure_thumb）
- 追加不丢资产（不删除已有）

## 6. 演进约束

- 锁内 F 盘 IO 串行化：N 张资产时是 N 次 F 盘读 + 单锁持有——可改进为并行（但需保证单机械盘不并发唤醒；目前保留串行）
- 增量追加 vs PUT 整体替换语义不同——前端编辑器不要混用

## 7. 引用

- [cold-data-gateway](cold-data-gateway.md)：冷盘接触面
- [api-facade](api-facade.md)：append_files 走 Polarscan
- [put-polaroid-contract](put-polaroid-contract.md)：PUT 互补端点