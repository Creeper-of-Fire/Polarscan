# SPEC: by-path-thumb-route（/thumb?path=&hash= + /img?path= 路由契约）

- **STATUS**: IMPLEMENTED
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- 路由实现：`apps/web/server.py:310-339`（`thumb_by_path`、`img_by_path`）
- 底层网关：`polarscan/core/cold.py`（cold-data-gateway）
- 测试：`tests/e2e_test.py:201-210`（`test_thumb_endpoint`）

## 1. 背景

原契约 `/thumb/{pid}/{idx}`、`/img/{pid}/{idx}` 要求服务端先按 pid 找 polaroid，再按 idx 找 asset——这导致 NewView 拖入后 polaroid 未索引时无法预览。新契约以 `(path, hash)` 为入口，**polaroid 是否索引与缩略图可用性解耦**——拖入即可预览，无需"先创建再预览"分支。

## 2. 设计

### `/thumb?path=&hash=`

- 缩略图路径由 `polarscan.core.index.thumb_path_for` 派生（单源真值）
- thumb 命中 → 直接返回（零 IO）
- thumb 缺失 + 源文件存在 → 经 cold gate 单次冷盘读生成
- thumb 缺失 + 源文件不存在 → 404
- hash 长度 < `SHORT_HASH_LEN`（6） → 400

### `/img?path=`

- 仅 lightbox 主动点击时调用
- 经 cold gate 的 `open_full` 流式打开（扫描大图 + NAS 友好）
- 源文件不存在 → 404

## 3. 接口契约

| 路由 | 入参 | 出参 | 行为 |
|---|---|---|---|
| `GET /thumb` | `path`, `hash` | JPEG 文件（200）或 404 | thumb 命中零 IO；缺则 cold gate 单次冷盘读 |
| `GET /img` | `path` | PNG 流（200）或 404 | cold gate `open_full` 流式 |

不允许：
- 直接 `Image.open(path)` / `Path.read_bytes()` / `open(path, 'rb')`——必须经 cold gate
- 在路由内做 path 白名单外的额外校验（白名单约束见 security TODO）

## 4. 验证

- `tests/e2e_test.py:201-210 test_thumb_endpoint`：以 `(path, hash)` 生成 thumb 并断言 content-type
- `tests/test_no_direct_disk_io.py`：AST 守卫保证路由层不裸调冷盘

## 5. 不变量

- thumb 命中零冷盘 IO（仅 stat SSD）
- thumb 缺失时 cold gate 单次读冷盘 + 写 SSD
- `/img` 仅在 lightbox 主动点击时调用（不预读）

## 6. 演进约束

- 未来 NAS / 网络共享：cold gate 内部加缓存策略；路由不变
- thumb 命名公式变更会触发 `.thumbs/` 集体失效——见 [thumb-naming](thumb-naming.md)

## 7. 引用

- [cold-data-gateway](cold-data-gateway.md)：冷盘接触唯一面
- [thumb-naming](thumb-naming.md)：缩略图命名公式
- [asset-hash](asset-hash.md)：hash 算法