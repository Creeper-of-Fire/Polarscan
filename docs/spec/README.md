# SPEC: spec-system（spec 文档系统）

- **STATUS**: IN PROGRESS（首批 spec 落地中）
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- spec 目录：`docs/spec/`
- 顶层入口：本文档（README）+ `docs/spec/architecture.md`
- 项目：`polarscan/`、`apps/`、`frontend/`

## 1. 背景

Polarscan 后端有相当数量的"已决策但散落在代码 / AGENTS.md / README.md 的设计"——
每次重构都要重新摸代码，缺乏统一归档。本项目引入 **spec-driven 工作流**：

- **spec 是独立的 .md 文档**，放在 `docs/spec/`
- 每个 spec 描述一个**完整的设计概念**，跨多个 .py 文件
- **不靠文件系统分类**——代码保持 flat，spec 通过路径文字指向代码
- spec 与代码**同步演化**：commit 改 spec 时改一段，改代码时同步改路径

## 2. spec 文档结构（约定）

每篇 `docs/spec/xxx.md` 一律使用以下结构：

```markdown
# SPEC: <标题>

- **STATUS**: TODO | IN PROGRESS | IMPLEMENTED | DEPRECATED
- **LAST_UPDATED**: <YYYY-MM-DD>

## 涉及代码
<路径列表——实现 / 测试 / 守卫>

## 1. 背景
## 2. 设计
## 3. 接口契约
## 4. 验证
## 5. 演进约束
## 6. 引用
```

## 3. 同步迭代规则

| commit 类型 | 动作 |
|---|---|
| 新增设计概念 | 起新 spec + 涉及代码 + 测试 + STATUS: TODO → IN PROGRESS → IMPLEMENTED |
| 改不变量 / 接口 | spec 段 2 + 段 3 + 实现 + 测试 同步改；STATUS 保持 |
| 重构 | spec 文件名不动；涉及代码段路径文字随之更新 |
| 弃用 | STATUS: DEPRECATED；保留一个 commit 周期后归档 |

## 4. 索引

| spec | 概念 | STATUS |
|---|---|---|
| [architecture](architecture.md) | 顶层架构 | IN PROGRESS |
| [cold-data-gateway](cold-data-gateway.md) | 冷盘接触网关 | IMPLEMENTED |
| [by-path-thumb-route](by-path-thumb-route.md) | /thumb?path=&hash= + /img?path= | IMPLEMENTED |
| [asset-hash](asset-hash.md) | 资产 hash 算法 | IMPLEMENTED |
| [thumb-naming](thumb-naming.md) | 缩略图命名公式 | IMPLEMENTED |
| [library-root-semantics](library-root-semantics.md) | library_root 字段 | PARTIAL |
| [drop-identify](drop-identify.md) | drop 工作流 | IMPLEMENTED |
| [yaml-atomic-write](yaml-atomic-write.md) | _index.yaml 原子写 | PARTIAL |
| [api-facade](api-facade.md) | Polarscan 写入入口 | IMPLEMENTED |
| [put-polaroid-contract](put-polaroid-contract.md) | PUT C+U 合并 | IMPLEMENTED |
| [append-files](append-files.md) | 追加资产 | IMPLEMENTED |
| [tag-pool](tag-pool.md) | 标签池 | IMPLEMENTED |
| [polaroid-id-generation](polaroid-id-generation.md) | id 派生 | IMPLEMENTED |
| [core-asset-meta-split](core-asset-meta-split.md) | core 拆 asset/meta | TODO |

## 5. 不变量

- 每篇 spec 必须含 6 段结构；不写 spec 等同于"该设计未文档化"
- spec 改动与代码改动在同一 commit 内同步完成
- 索引表（本文 §4）必须随 spec 增删更新

## 6. 引用

本文是 spec 系统的入口；其他 spec 在 §4 列出。