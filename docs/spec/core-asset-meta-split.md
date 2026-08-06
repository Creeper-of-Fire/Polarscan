# SPEC: core-asset-meta-split（core 拆 asset / meta 子包）

- **STATUS**: TODO
- **LAST_UPDATED**: 2026-08-06

## 涉及代码（目标态）

```
polarscan/core/
  asset/                      # 实物层
    __init__.py               # 入口；冷盘网关 + Asset 模型 + thumb
    cold.py                   # 冷盘网关（从 polarscan/core/cold.py 移入）
    asset.py                  # Asset dataclass（从 polarscan/core/index.py 拆出）
    thumb.py                  # thumb 命名 + Pillow 处理（从 asset_thumb.py 拆出）
    library_resolver.py       # identify_candidates（从 apps/web/ 移入）
  meta/                       # 元数据层
    __init__.py               # 入口；Polaroid + yaml IO + 标签池
    polaroid.py               # Polaroid dataclass（从 index.py 拆出）
    storage.py                # _index.yaml IO（从 core/storage.py 移入）
    tags.py                   # 标签池元数据（从 api.py 拆出）
    id_gen.py                 # id 派生（从 core/id_gen.py 移入）
  __init__.py                 # 转发导出（旧路径向后兼容）
```

迁移路径由 `polarscan/core/__init__.py` 在过渡期内转发——见 §6 演进约束。

## 1. 背景

当前 `polarscan/core/` 是 flat 目录：实物相关（cold / asset_thumb / index.Asset）+ 元数据相关（storage / id_gen / index.Polaroid）混在一起。这导致：

- "实物 vs 元数据"两类不变量散落
- 升级 NAS 时改实物层要小心不动元数据层
- `library_root` 语义不清（实物根 vs 元数据字段）

按"数据性质"切分：实物层（冷盘 + 缩略图）/ 元数据层（yaml + 标签池）。两层各自独立演进，耦合点仅在 `Polaroid.assets: list[Asset]` 引用。

## 2. 设计

### 实物层 `core/asset/`

- 职责：冷盘接触唯一面 + Asset 模型 + 缩略图 + library_root 派生 + 路径反查
- 暴露：`Asset` dataclass + 4 个 cold 函数 + `thumb_path_for` + `identify_candidates`
- 不接触 yaml schema（仅 Polaroid 引用 Asset）

### 元数据层 `core/meta/`

- 职责：Polaroid 模型 + yaml IO + 标签池 + id 派生
- 暴露：`Polaroid` dataclass + `read_index` / `write_index` + 标签池方法 + `make_polaroid_id`
- 不接触冷盘（仅 in-memory + yaml SSD IO）

### 耦合点

- 元数据层 `Polaroid.assets: list[Asset]` 引用实物层 `Asset`（dataclass 字段，非 schema 直读）
- 元数据层 `_index.yaml` 的 `assets[].hash` 通过 `core.asset.thumb_path_for` 反查实物层缩略图
- 两层 IO 都走 cold gate（实物层）或 atomic write（元数据层）

## 3. 接口契约

迁移后：

- 旧 import：`from polarscan.core import Asset, Polaroid, cold, storage` 仍可用（`__init__.py` 转发）
- 新 import（推荐）：`from polarscan.core.asset import Asset, cold` / `from polarscan.core.meta import Polaroid, storage`

约束：
- 实物层不导入 yaml schema 字段（除 bootstrap 时读取 `library_root`）
- 元数据层不导入冷盘接触面（除 `Polaroid.assets` 类型引用）
- `apps/web/server.py` 优先用新 import（明示拆分边界）

## 4. 验证

- TODO（commit 3）：
  - 现有 73 个 unittest 全过（迁移无 regression）
  - 新增：实物层单独测试（cold / asset / thumb）
  - 新增：元数据层单独测试（polaroid / storage / tags / id_gen）
  - AST 守卫更新：`tests/test_no_direct_disk_io.py` 扫描新目录结构

## 5. 不变量

- 实物层 / 元数据层边界不可破坏（见 §3 接口契约）
- 现有不变量全部继承：[cold-data-gateway](cold-data-gateway.md) / [yaml-atomic-write](yaml-atomic-write.md) / [api-facade](api-facade.md) / [thumb-naming](thumb-naming.md) / [asset-hash](asset-hash.md)

## 6. 演进约束

### 迁移策略

过渡期策略（commit 3 期间）：
1. 新建 `core/asset/` + `core/meta/` 子包，**只放**新代码
2. 旧 `core/cold.py` / `core/storage.py` / `core/index.py` / `core/asset_thumb.py` / `core/id_gen.py` 仍保留，**重新 export from 子包**（不再有内联实现）
3. 所有 caller 仍可走旧路径；新 caller 走新路径
4. 后续 PR 逐步删除旧文件实现（仅保留 `__init__.py` 转发 / 弃用）

### library_root 归位

[library-root-semantics](library-root-semantics.md) § 3 描述的目标态在本 spec 落地：
- `apps/web/server.py` 不再 `ps.library_root` 直读
- 改为 `core.asset.find_candidates_by_path(queries)`

## 7. 引用

- [cold-data-gateway](cold-data-gateway.md)：实物层核心 spec
- [yaml-atomic-write](yaml-atomic-write.md)：元数据层核心 spec
- [library-root-semantics](library-root-semantics.md)：本 spec 的伴随目标
- [architecture § 2](architecture.md)：当前模块清单（迁移后更新）