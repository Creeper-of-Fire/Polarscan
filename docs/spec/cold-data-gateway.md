# SPEC: cold-data-gateway（冷盘接触网关）

- **STATUS**: IMPLEMENTED
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- 实现：`polarscan/core/cold.py`
- 辅助（Pillow 处理）：`polarscan/core/asset_thumb.py`
- 行为测试：`tests/test_cold_gate.py`
- AST 守卫：`tests/test_no_direct_disk_io.py`

## 1. 背景

冷盘（F 盘 / NAS / 网络共享）必须保持休眠：

- 机械盘会因唤醒降低寿命 + 引入卡顿
- NAS / 网盘的网络握手延迟高且不可控

任何代码路径访问冷盘必须经本 spec 定义的网关——**冷盘接触面只有一个**。

## 2. 设计

冷盘网关暴露 4 个出口（`polarscan.core.cold.__all__`）：

| 函数 | 语义 | 何时调 |
|---|---|---|
| `compute_hash(src) -> str` | 流式 blake2b 128 hex | drop / append_files 后端算 hash |
| `make_thumb_if_missing(data_dir, src_path, hash) -> Path \| None` | thumb 命中零 IO；缺则单次冷盘读 + 编码 + 存 | 浏览路径 |
| `open_full(src_path) -> BinaryIO` | 流式打开原图 | `/img?path=` lightbox 主动点 |
| `read_full(src_path) -> bytes` | 一次性读全文 | 小图 / hash 校验 |

策略：
- thumb 命中 → 仅 stat SSD（零冷盘读）
- thumb 缺失 → 单次冷盘读 + 编码 JPEG + 存 SSD
- `open_full` / `read_full` **必须**在 explicit gesture 上下文被调

## 3. 接口契约

- 入口：`polarscan.core.cold` 模块
- 任何调用方只能通过这 4 个函数接触冷盘
- 其他方式（`Image.open(path)`、`Path.read_bytes()`、`open(path, 'rb')`）仅允许在 `cold.py` 与 `storage.py` 内出现（白名单）

## 4. 验证

- `tests/test_cold_gate.py`：compute_hash 流式正确性 / make_thumb_if_missing thumb 命中零 IO 与缺则生成 / open_full 流式 / read_full 一次性 / Asset.from_path / ensure_thumb / append_files 间接走 cold
- `tests/test_no_direct_disk_io.py`：AST 守卫扫描 `polarscan/` + `apps/` 下 .py 文件，禁止裸 IO AST 模式

## 5. 不变量

- 任何冷盘接触必须经 `cold.py` 暴露的 4 个函数
- `cold.py` 与 `storage.py` 之外不允许 `Image.open(...)` / `.read_bytes()` / `.read_text()` / `open(..., 'rb'|'wb'|'ab'|...)` AST 模式
- 升级 NAS / 网盘时本约束进一步升级（网络握手不算 free）

## 6. 演进约束

- 未来 NAS / 网络共享：缓存策略放在本 spec 涉及的模块内部，调用方不动
- 任何新出口需先改本 spec 段 2 + 加测试再改实现
- AST 守卫白名单新增需在本 spec 显式登记——避免白名单滥用

## 7. 引用

- [asset-hash](asset-hash.md)：hash 算法（被 `compute_hash` 实现）
- [thumb-naming](thumb-naming.md)：缩略图命名公式（被 `make_thumb_if_missing` 调用）
- [by-path-thumb-route](by-path-thumb-route.md)：HTTP 路由层契约
- [architecture § 3 数据分层](architecture.md)：热/冷分层总览