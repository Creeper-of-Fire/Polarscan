# SPEC: polaroid-id-generation（拍立得 id 派生）

- **STATUS**: IMPLEMENTED
- **LAST_UPDATED**: 2026-08-06

## 涉及代码

- id 派生：`polarscan/core/id_gen.py:make_polaroid_id`
- primary char 解析：`polarscan/core/id_gen.py:parse_primary_char`
- API 入口：`polarscan/api.py:Polarscan.suggest_id`
- 路由预览：`apps/web/server.py:179-182`（`GET /api/suggest-id`）
- 测试：`tests/test_id_gen.py`

## 1. 背景

拍立得 `id` 是身份标识——写库后冻结。它有两类来源：

- **手动派生**：NewView 工作台表单预览（GET /api/suggest-id，不写入）
- **程序派生**：dropzone / 自动化场景（如未来"批量检测新 Asset 并建立"）

id 派生逻辑必须可独立测试——本 spec 定义派生规则。

## 2. 设计

### 格式

```
{shot_date or 'nostamp'}_{primary_char or 'nochar'}_{6hex}
```

示例：
- `make_polaroid_id("2025-10-18", "strawberry")` → `2025-10-18_strawberry_4a7b1c`
- `make_polaroid_id("2026-08-04", "中文名")` → `2026-08-04_中文名_4a7b1c`
- `make_polaroid_id()` → `nostamp_nochar_9e3d2a`

### 性质

- 派生并写入 YAML 后即冻结，后续修改 `shot_date` 或 `char` 不会改变它
- 6 位十六进制后缀**不做冲突重试**——若发生冲突，由用户手动修改 YAML
- 除随机后缀外派生逻辑是纯函数——相同输入可以生成不同 id

### 清洗规则

`_ID_OK = re.compile(r"[^\w\-]+", re.UNICODE)`

- 接受 Unicode 字母/数字（包括中文）
- 空白 / 标点 / 控制字符 / 路径分隔符 → 替换为 `-`
- 截短到 32 字符
- 空输入 → fallback（`nostamp` / `nochar`）

### primary char 解析

`parse_primary_char(tags)`：从拍立得标签列表取第一个 `char:` 标签的值。

fallback：无前缀标签按统一约定视为角色标签（即返回裸标签字符串）。

## 3. 接口契约

| 入口 | 行为 |
|---|---|
| `make_polaroid_id(shot_date, primary_char)` | 纯函数；返回派生 id |
| `parse_primary_char(tags)` | 纯函数；返回 primary char 或 None |
| `Polarscan.suggest_id(shot_date, tags)` | 锁内调用；不写入 |
| `GET /api/suggest-id?shot_date=&primary_char=` | 路由预览 |

约束：
- id 一旦写入 YAML 不可变
- 6 hex 后缀用 `secrets.token_hex(3)`（密码学随机，非冲突重试）

## 4. 验证

- `tests/test_id_gen.py:MakePolaroidIdTest`：
  - ASCII / 中文 / 纯中文 + 缺日期
  - 标点替换 `-`
  - 空输入 fallback
  - 后缀唯一性（20 次不重复）
- `tests/test_id_gen.py:ParsePrimaryCharTest`：显式 `char:` / fallback / 无前缀

## 5. 不变量

- 派生规则：format string = `f"{date_part}_{char_part}_{suffix}"`
- 字符清洗：保留 `\w` (Unicode) + `-` + `_`
- 长度：每段最长 32 字符

## 6. 演进约束

- 格式变更需要 schema migration——已生成的 id 不能改变
- primary char fallback（裸标签视为 char）可能在未来需要去掉——目前的"统一约定"是过渡

## 7. 引用

- [api-facade](api-facade.md)：suggest_id 走 Polarscan