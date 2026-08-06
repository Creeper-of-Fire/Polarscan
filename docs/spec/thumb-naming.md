# SPEC: thumb-naming（缩略图命名公式）

- **STATUS**: IMPLEMENTED
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- 公式与命名：`polarscan/core/asset_thumb.py:_thumb_filename`
- 完整路径派生：`polarscan/core/asset_thumb.py:thumb_path_for`
- Asset 包装：`polarscan/core/index.py:Asset.thumb_filename` / `Asset.thumb_path` / `Asset.has_thumb` / `Asset.ensure_thumb`
- 路由层：`polarscan/core/cold.py:make_thumb_if_missing` / `apps/web/server.py:thumb_by_path`

## 1. 背景

缩略图必须由资产内容派生（不能由用户命名）——这样：
- 同一资产的不同 polaroid 引用共享同一缩略图（避免重复生成）
- 文件替换时 hash 变 → 文件名变 → 旧文件自然孤儿化（不会误命中）

## 2. 设计

**公式**：`{Path(path).stem}_{hash[:SHORT_HASH_LEN]}.jpg`

示例：`img20260728_17185555.png` + hash `a3b4c5d6...` → `img20260728_17185555_a3b4c5.jpg`

参数：
- `SHORT_HASH_LEN = 6`：约 1600 万种组合；冲突概率可接受（小规模个人资料库）
- 后缀：`.jpg`（JPEG 长边 1024，质量 85）

完整路径：`data_dir / .thumbs / {stem}_{hash[:6]}.jpg`

## 3. 接口契约

- 单源真值：`Asset.thumb_filename` 与 `core_thumb_path_for` 共用 `asset_thumb._thumb_filename`
- 任何 caller（cold / Asset / server）禁止硬编码公式
- hash 缺失或长度 < `SHORT_HASH_LEN` → 路径派生返回 None

## 4. 验证

- 隐式测试：`tests/test_cold_gate.py:MakeThumbColdReadTest` 验证 thumb 在 `data_dir/.thumbs/` 下生成
- 隐式测试：`tests/test_polarscan_find.py:FindByHashTest` 验证 has_thumb / thumb_path
- 跨域一致：前端 `useDropzone` 的 thumb 与后端 `Asset.thumb_filename` 派生一致

## 5. 不变量

- 缩略图文件名 = `f"{Path(path).stem}_{hash[:6]}.jpg"`——唯一公式
- 改公式或短哈希长度会让 `.thumbs/` 集体失效——必须 schema migration
- 同一 `(path, hash)` 对应唯一 thumb——多 polaroid 引用共享

## 6. 演进约束

- 公式变更需要重命名 `.thumbs/` 下所有文件 + 一次性迁移脚本
- 冲突重命名（同名 stem + 同前 6 hex）极小概率——可在 v2 引入后缀扩展

## 7. 引用

- [asset-hash](asset-hash.md)：hash 算法（命名依赖 `hash[:SHORT_HASH_LEN]`）
- [cold-data-gateway](cold-data-gateway.md)：缩略图生成的冷盘接触面
- [by-path-thumb-route](by-path-thumb-route.md)：HTTP 路由层契约