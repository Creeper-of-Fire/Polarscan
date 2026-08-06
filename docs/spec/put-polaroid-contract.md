# SPEC: put-polaroid-contract（PUT /polaroid C+U 合并契约）

- **STATUS**: IMPLEMENTED
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- 路由：`apps/web/server.py:198-242`（`PUT /polaroid/{pid}`）
- 写入：`polarscan/api.py:upsert_polaroid`
- 测试：`tests/test_import_append_save.py:PutPolaroidTest`、`tests/e2e_test.py:test_create_polaroid_via_put` / `test_update_polaroid_via_put`

## 1. 背景

2026-08 重构：原 contract 是 `POST /new` / `POST /bench/{pid}/autosave` / `POST /bench/{pid}/save-assets` 三个端点——C 和 U 分裂。新 contract 合并为单一 `PUT /polaroid/{pid}`：

- **幂等**：PUT 同一 polaroid 状态两次 → 同一最终状态
- **C+U 合并**：pid 不存在 → 创建；存在 → 整体替换（含 assets）
- **assets[].hash 由前端提供**：浏览器 dropzone 算好后传入，服务端不再读冷盘重算

## 2. 设计

### 请求

```
PUT /polaroid/{pid}
Content-Type: application/json

{
  "id": "<pid>",
  "shot_date": "YYYY-MM-DD" | null,
  "tags": ["char:xxx", ...],
  "notes": "...",
  "assets": [
    {
      "role": "front" | "back" | "additional" | <任意字符串>,
      "path": "<绝对路径>",
      "device": "..." | null,
      "hash": "<128 hex>",   # 必填
      "metadata": {}          # 任意 JSON 透传
    },
    ...
  ],
  "metadata": {}              # 任意 JSON 透传
}
```

### 校验

| 条件 | 行为 |
|---|---|
| body 不是合法 JSON | 400 |
| body 不是 dict | 400 |
| `body.id != url pid` | 400 |
| `assets` 为空 | 400 |
| 任一 asset 缺 `hash` 或 `len(hash) != 128` | 400 |

### 响应

```json
{"ok": true, "pid": "...", "asset_count": N, "created": true | false}
```

`created`：`pid` 之前不存在 → true；已存在 → false（幂等）

## 3. 接口契约

- C+U 合并：整体替换 polaroid + 整体替换 assets
- 路径不限制：可以加新 path（旧 save-assets 不允许）
- 省略 asset = 删除该 asset（隐式删）
- hash 必填 + 128 hex：服务端**信任**前端 hash，不读冷盘重算
- 服务端不校验 `path` 是否在 F 盘存在——这是 cold gate 之外的不变量，详见 TODO

## 4. 验证

- `tests/test_import_append_save.py:PutPolaroidTest`：
  - 整体替换 role / metadata / device
  - 通过全列表重排
  - 允许新 path
  - 省略 = 删除
  - 空 assets → 400
  - 缺 hash → 400
  - 幂等（同一 body 两次 PUT → 第二次 created=false）
  - 创建新 polaroid
  - url pid 与 body.id 不一致 → 400
- `tests/e2e_test.py`：create / update / put_rejects_* 三组

## 5. 不变量

- PUT 不读冷盘——hash 完全由前端提供
- 整体替换语义：body 缺什么 = 删什么
- 幂等：相同 body 两次 PUT → 状态不变
- 服务端信任 hash：trust-but-verify 在客户端（dropzone 算 hash 时已 verify）

## 6. 演进约束

- 未来加字段：扩展 body schema；服务端不破坏旧字段（透传 `metadata` 模式）
- PATCH 端点（部分更新）暂不提供——前端 v-model 编辑器已是整体替换语义

## 7. 引用

- [api-facade](api-facade.md)：写入走 Polarscan.upsert_polaroid + save
- [asset-hash](asset-hash.md)：hash 算法 + 长度校验
- [yaml-atomic-write](yaml-atomic-write.md)：save 走 atomic write