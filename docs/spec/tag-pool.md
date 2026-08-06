# SPEC: tag-pool（标签池元数据）

- **STATUS**: IMPLEMENTED
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- 内存结构：`polarscan/core/storage.py:_default`（`tags: {}`）
- 读取 / 写入：`polarscan/api.py:tag_metadata` / `upsert_tag` / `set_tag_metadata` / `tag_info` / `set_tag_info` / `delete_tag` / `all_tags_in_pool`
- 路由：`apps/web/server.py:pool_edit_save`（`POST /pool/{prefix}/{key}/edit` + `/delete`）
- 测试：`tests/test_import_append_save.py` / `tests/e2e_test.py:test_pool_edit`

## 1. 背景

标签池是"按前缀分桶的元数据字典"——`_index.yaml` 顶层 `tags: { prefix: { key: meta } }`。标签池**与 polaroid.tags（拍立得上挂的标签）解耦**：

- 拍立得 tags：自由格式列表，每个标签是字符串 `prefix:value`
- 标签池 tags：可选，按需填充，记录标签的元数据

## 2. 设计

### yaml 结构

```yaml
tags:
  char:
    hime:
      canonical_name: "姬"
      aliases: ["hime", "小姬"]
      notes: "角色别名测试"
      color_name: "粉色"          # 应援色: 文字
      color_rgb: "#FFB7C5"        # 应援色: RGB (#RRGGBB)
    strawberry:
      canonical_name: "草莓"
  event:
    ...
```

### 字段约定（**硬编码顶层字段**，与 canonical_name 平级）

| 字段 | 类型 | 适用 prefix | 说明 |
|---|---|---|---|
| `canonical_name` | str | 全部 | 标签的标准名（前端展示用，可留空） |
| `aliases` | list[str] | 全部 | 别名 |
| `notes` | str | 全部 | 备注 |
| `color_name` | str | 仅 char | 应援色文字描述（例 "黄色"） |
| `color_rgb` | str | 仅 char | 应援色 RGB（hex `#RRGGBB`），非法值存为空串 |
| 其它 | any | 全部 | 走 `extra_json` form 字段，任意 key-value |

> **应援色**本身是一个 class (text + rgb)，但为了简化 yaml / form 协议 /
> dropzone / pool 编辑器一致性，两个字段平铺在 meta 顶层而非嵌套。
> 前端 `CharOshiColor` interface 统一表达这两个字段。

## 3. 接口契约

| 方法 | 行为 |
|---|---|
| `tag_metadata(prefix) -> dict[key, meta]` | 整桶读（不存在返回 `{}`） |
| `tag_info(prefix, key) -> meta` | 单 key 读（不存在返回 `{}`） |
| `upsert_tag(prefix, key, meta)` | 单 key 写 |
| `set_tag_info(prefix, key, info)` | 单 key 写；`info == {}` 时删除 key |
| `set_tag_metadata(prefix, registry)` | 整桶替换 |
| `delete_tag(prefix, key)` | 单 key 删除 |
| `all_tags_in_pool(prefix) -> dict[key, meta]` | 整桶拷一份 |

约束：
- 应用层只通过 `Polarscan` 读 / 写
- 桶不存在时 `set_tag_info` 自动创建
- `tags` 字段在 yaml 中持久化（atomic write）

## 4. 验证

- `tests/e2e_test.py:test_pool_edit`：POST /pool/char/hime/edit → info 含 canonical_name + aliases + notes + color_name + color_rgb；非法 RGB 被服务端丢弃
- 隐式测试：`tests/smoke_test.py:set_tag_info` + `tag_info`

## 5. 不变量

- 标签池是 yaml 顶层 `tags` 字段——非 Polaroid 字段
- 桶不存在时写操作自动创建空桶
- `set_tag_info(prefix, key, {})` 等价于删除该 key
- `color_rgb` 仅接受 `#RRGGBB` 格式；其它形式（命名颜色、`rgb()`、短 hex）服务端丢弃为空串

## 6. 演进约束

- 标签池与拍立得 tags 各自独立——删除标签池 key 不影响 polaroid 上挂的 tag 字符串
- 多库隔离：每个 data_dir 独立标签池
- 字段扩展：新增"硬编码顶层字段"必须走 spec 同步 + 服务端 form handler + 前端 poolApi.save 类型 + UI 编辑器四件套；不要悄悄塞 `extra_json`

## 7. 引用

- [api-facade](api-facade.md)：所有 tag 方法在 Polarscan
- [yaml-atomic-write](yaml-atomic-write.md)：写操作走 atomic write