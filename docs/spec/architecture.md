# SPEC: architecture（顶层架构）

- **STATUS**: IN PROGRESS
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- 核心引擎：`polarscan/core/`
- 应用层：`polarscan/api.py`、`apps/web/`
- 前端：`frontend/`

## 1. 背景

Polarscan 是拍立得扫描件元数据管理系统。架构按两层切分：

1. **按职责**：core（算法 + schema 真相源） / apps（业务装配） / frontend（UI）
2. **按数据性质**：热层（SSD yaml + 缩略图）/ 冷层（F 盘 / NAS 原图）

两层互补——core 同时是"算法真相源"和"实物/元数据分界线"。

## 2. 模块清单

| 模块 | 路径 | 角色 |
|---|---|---|
| core | `polarscan/core/` | 算法 + schema 真相源（含 cold gate / find_candidates facade / library_resolver） |
| api | `polarscan/api.py` | 写入入口（Polarscan 单例 + RLock + `data` 只读视图） |
| server | `apps/web/server.py` | FastAPI 装配层 |
| frontend | `frontend/` | Vue SPA |

## 3. 数据分层

| 层 | 介质 | 内容 | 何时读 |
|---|---|---|---|
| 热 | SSD | `_index.yaml` + `.thumbs/` + in-memory 副本 | 全程；启动 1 次；浏览 zero 冷盘 IO |
| 冷 | F 盘 / NAS | 原始扫描图 | 用户 explicit gesture：drop / PUT / lightbox / append_files |

冷热分层不变量详见 [cold-data-gateway](cold-data-gateway.md)。

## 4. 顶层架构图

```
                  ┌────────────────────────────────────────────────┐
                  │           _index.yaml  (single truth)           │
                  │  {library_root, version, tags, polaroids[]}    │
                  └────────────────────────────────────────────────┘
                                    ▲      │
                                    │原子写  │ 启动读 (read_index)
                                    │       ▼
┌───────┐  drop Files  ┌──────────────────┐  init   ┌───────────────────────────────┐
│Browser│─────────────►│ useDropzone      │────────►│ Polarscan(data_dir)           │
│ (Vue) │  Phase1      │  Phase1:candidates│         │   _data = read_index(...)     │
│       │  zero-hash   │  (POST /api/drop/identify)   │   RLock = threading.RLock()  │
│       │  Phase2      │  Phase2:hash(blake2b 128h)  └───────────────────────────────┘
│       │  bytes-hash  │   + identify                 │
│       │              │                              │
│       │              │ importable candidates ──►    │ append_files(pid, paths)
│       │              │                              │   └ Asset.from_path (hash)
│       │              │                              │   └ ensure_thumb (按需)
│       │              │                              │   └ upsert_polaroid + save()
│       │              │                              │
│       │ v-model      │ appendFiles ──►              │ append-files API
│       │ (usePolaroidEditor.save)                    │   POST /api/polaroids/{pid}/append-files
│       │ ───────────► │ PUT /polaroid/{pid}          │   PUT 走 core.Polarscan.upsert_polaroid
│       │   完整 polaroid                              │   + save()
│       │   (assets[].hash 必填)                       │
│       │              │                              │
│       │ GET          │                              │
│       │ /api/polaroids ───────────────────────────► │ list_polaroids(_data) → summary[]
│       │ /api/polaroids/{pid} ─────────────────────► │ polaroid(pid) → dict
│       │ /thumb?path&hash ──────────────────────────►│ cold.make_thumb_if_missing(...)
│       │ /img?path     ────────────────────────────► │ cold.open_full(...)
└───────┘              └──────────────────┘           │
       ▲                                                ▼
       └─────── SPA (Vue Router) ──────► frontend/dist ──── StaticFiles
```

## 5. 不变量

- `_index.yaml` 是项目唯一真相源——所有修改必须经 [api-facade](api-facade.md)
- 冷盘接触面只有一个——[cold-data-gateway](cold-data-gateway.md)
- 浏览路径只 stat SSD——[cold-data-gateway § 2](cold-data-gateway.md)

## 6. 引用

本文是其他 spec 的入口。具体子 spec：
- 实物层：[cold-data-gateway](cold-data-gateway.md) / [asset-hash](asset-hash.md) / [thumb-naming](thumb-naming.md) / [drop-identify](drop-identify.md) / [library-root-semantics](library-root-semantics.md)
- 元数据层：[api-facade](api-facade.md) / [yaml-atomic-write](yaml-atomic-write.md) / [tag-pool](tag-pool.md) / [polaroid-id-generation](polaroid-id-generation.md) / [put-polaroid-contract](put-polaroid-contract.md) / [append-files](append-files.md)
- 路由层：[by-path-thumb-route](by-path-thumb-route.md)
- TODO：[core-asset-meta-split](core-asset-meta-split.md)