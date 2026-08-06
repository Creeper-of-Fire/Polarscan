# AGENTS.md — Polarscan

> 本文件是项目的**演进导航**，不是现状描述。
>
> - 现状（项目结构 / 安装 / 启动 / API / 标签语义）→ `README.md`
> - 行为真值 → `polarscan/` 与 `apps/` 的源码
> - 派生数据与一次性脚本 → `.gitignore`
>
> 本文件承担 **README 与代码都不会承担的职责**：
>
> 1. **core 的设计意图**——为什么这么分
> 2. **真正不可破坏的不变量**——改了会让现有数据崩的
>
> 这两段都是**未来导向**——给下一次重构 / 加字段 / 改 schema 的 agent 看。
> 已完成的事在 commit message；待办的事在 issue tracker；不在这里。

## 一、Core 的设计意图

### 角色：无知即力量

core 是 Polarscan 的算法 + schema 真相源。它的"无知"是刻意的、**高贵的无知**：

- **资产**：core 必须理解——因为是数字资产的物理生存（原图 / 缩略图 / hash）。
- **标签**：core 必须理解——因为是唯一通用的、无模式的关联机制。
- **其他一切**：core 不解析、不校验、不截断。原样存，原样读。

事实优于解释。`member:Alice` 是"指一个人"还是"指一个角色"——这是应用层的解释权，core 不管。

### 已否决的设计

- **`Asset` 持有 `captured_at`**：被否决。Asset 描述的是一组拍立得的一个文件，不是事件；日期属于 Polaroid 层级（`shot_date`）。
- **业务字段进 dataclass schema**（人名 / 事件名 / 评分等）：被否决。一律塞进 `metadata` 字典透传，core 不解析其内部结构。
- **core 引入数据库 / ORM / 复杂校验**：被否决。core 是单文件 YAML + 透传，保持极简。

### 演进原则

任何字段调整都遵循：稳定字段硬编码进 dataclass schema，任意扩展字段一律走 metadata 字典透传。详见上文"已否决的设计"。

## 二、真正的不变量（改了会让现有数据崩）

1. **`_index.yaml` 原子写入**：先写 `.yaml.tmp`，再 `tmp.replace(path)`。  
   直接 `open + write` 会在崩溃时产生半截文件。
   - 来源：`polarscan/core/storage.py:write_index`

2. **资产哈希 = `blake2b(digest_size=64)`，128 字符十六进制**。  
   已生成的 `_index.yaml` 里所有 `asset.hash` 都是按此算法算的，改算法或长度会让全部资产校验失败。
   - 来源：`polarscan/core/asset_thumb.py:HASH_ALGO` / `HASH_HEX_LEN`，后端 `server.py:PUT /polaroid` 校验 128 字符。

3. **缩略图文件名 = `{stem}_{hash[:6]}.jpg`，完全由 `asset.hash` 派生**。  
   缺 `hash` = 旧资产未迁移。改公式或短哈希长度会让 `.thumbs/` 集体失效。
   - 来源：`polarscan/core/index.py:thumb_filename`

## 不在本文件

| 你想知道 | 去哪里 |
|---|---|
| 项目是什么 / 怎么装 / 怎么跑 / API 表 / 标签前缀 | `README.md` |
| 哪些文件不进 git / 一次性脚本位置 | `.gitignore` |
| 行为真值（字段定义 / 路由逻辑） | `polarscan/core/` + `apps/` |
