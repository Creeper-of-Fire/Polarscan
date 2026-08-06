# SPEC: asset-hash（资产 hash 算法）

- **STATUS**: IMPLEMENTED
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- 常量与算法：`polarscan/core/asset_thumb.py`（`HASH_ALGO` / `HASH_HEX_LEN`）
- 实现：`polarscan/core/cold.py:compute_hash`
- 短哈希派生：`polarscan/core/asset_thumb.py:_thumb_filename`（`SHORT_HASH_LEN`）
- 前端算法对齐：`frontend/src/composables/useDropzone.ts:25-37`（`hash-wasm` blake2b 512）
- 校验：`apps/web/server.py:227-232`（PUT /polaroid 校验 128 字符）

## 1. 背景

资产必须有一个稳定、不变的"内容指纹"——基于此 hash 派生缩略图文件名、未来可做离线路径修复、按内容查重（drop 时 by_hash 反查）。hash 算法一旦落地**不可变**——已生成的 `_index.yaml` 里所有 `asset.hash` 都是按此算法算的，改算法或长度会让全部资产校验失败。

## 2. 设计

- 算法：`blake2b(digest_size=64)` —— 64 字节输出
- 字符串长度：128 个十六进制字符（`HASH_HEX_LEN = 128`）
- 短哈希：`hash[:6]` 用于缩略图文件名（`SHORT_HASH_LEN = 6`，约 1600 万种组合）
- 流式分块：1 MB / 块，大文件不会一次占满内存

前后端对齐：
- Python：`hashlib.blake2b(digest_size=64)` + 流式 `f.read(1024*1024)`
- JS：`hash-wasm` 的 `blake2b(bytes, 512)`（512 bit = 64 byte digest）

## 3. 接口契约

| 层 | 入口 | 输出 |
|---|---|---|
| 后端 | `cold.compute_hash(src)` | 128 hex 字符串 |
| 前端 | `useDropzone.readFileData(file)` 返回 `hash` | 128 hex 字符串 |

约束：
- 算法 / digest_size / 输出长度**不可变**——任何变更需要 schema migration
- 缩略图文件名只能由 `hash[:SHORT_HASH_LEN]` 派生，禁止硬编码

## 4. 验证

- `tests/test_polarscan_find.py:FindByHashTest`：hash 命中 / miss / 空输入 / 多 asset 同 hash
- `tests/test_cold_gate.py:ComputeHashTest`：与标准 `hashlib.blake2b(digest_size=64)` 实现一致；128 hex 长度
- 跨语言一致：浏览器 dropzone 算的 hash 与后端 `compute_hash` 一致（隐式测试——前端 PUT body 包含 hash，后端信任）

## 5. 不变量

- 任何已生成的 `asset.hash` 都必须能由 `compute_hash(asset.path)` 重新算出
- hash 缺失（`None` 或空）= 旧资产未迁移，由 UI 提示运行迁移脚本
- hash 长度非 128 = 数据损坏，必须 fail-fast

## 6. 演进约束

- 算法升级需要**双 hash 过渡期**（旧 hash 保留作 secondary），不在本 spec 范围
- 短哈希长度调整会让 `.thumbs/` 集体失效

## 7. 引用

- [cold-data-gateway](cold-data-gateway.md)：hash 计算的冷盘接触面
- [thumb-naming](thumb-naming.md)：缩略图命名依赖 `hash[:SHORT_HASH_LEN]`
- [put-polaroid-contract](put-polaroid-contract.md)：PUT 时 hash 必填 + 长度校验