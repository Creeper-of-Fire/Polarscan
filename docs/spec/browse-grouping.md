# SPEC: browse-grouping（浏览页分组与组序）

- **STATUS**: IMPLEMENTED
- **LAST_UPDATED**: 2026-10-06

## 涉及代码

- 纯逻辑（分组 / 组序）：`frontend/src/lib/grouping.ts`
- 纯逻辑（状态 ↔ URL）：`frontend/src/lib/browseQuery.ts`
- URL 规范化守卫：`frontend/src/router/index.ts`（`beforeEach`）
- 视图：`frontend/src/views/ListView.vue`
- 数据来源：`frontend/src/stores/polarscan.ts`（`listSummaries` / `listAllTagGroups`）
- 类型：`frontend/src/types.ts`（`PolaroidSummary`）
- 设计沿革与取舍记录：本次实现前的讨论产物，未入库

## 1. 背景

浏览页原先是「全表单片网格 + 前缀 chip 过滤」，顺序取 `_index.yaml` 的原始顺序
（`list_polaroids` 全程不排序，写入时 `sort_keys=False` 也不动列表顺序）。

这个顺序对使用者近乎无意义：483 条实测有 93 处相邻回退，且几乎全是退一天——是
「人工整理过的、接近时间序但没排干净」。同时 12/13 的年月分组内顺序 ≠ 日期序，
最大一组 273 个逆序对。组规模也到了必须滚动扫的量级（按年月最大 63 张，
按角色最大 112 张）。

所以引入**分组**（把结果切成若干 section）与**组序**（section 之间的先后）。
两件事都在浏览器侧完成：`ListView` 已把全表加载进 store，过滤也一直是纯
computed，不新增任何后端契约、不新增任何字段、不接触冷盘。

## 2. 设计

### 2.1 分组维度选择器（复用已有 chip 行）

原来那排「前缀」 chip 只决定下方「值」那行显示谁，它本身已经是一个维度选择器，
只是没参与排版。现在同一次点击同时决定两件事：

1. 下方值筛选行显示哪个前缀的值
2. 结果按该维度切成 section

`日期` 不是 prefix，但它是唯一撑得起「按时间 / 按名称」之分的维度，所以作为
特殊维度混在同一行排最前。选到日期维度时值筛选整行不渲染——日期没有值可筛。

一张卡在某个维度下可能命中多个值（多个 `char` / `theme`），此时它在每个命中的
section 里各出现一次。这是有意的：每组因此都是完整视图（「某人的所有照片」不会
因为他同时被打了别的标签而缺掉）。

### 2.2 组序：依据 + 方向

「组顺序」只决定 **section 之间的先后**，不影响组内顺序。

依据两档：

- `key` —— 分组键本身该有的排法。显示名跟着维度走：日期维度叫「按时间」，其余叫
  「按名称」。不写「自身」这类实现细节。
- `count` —— 组的大小，「按数量」。

方向由一个按钮切换，按钮**自带当前含义文案**（`↓ 最多在前` / `↑ 最早在前` /
`A → Z` / `Z → A`），旁边不另配一行解释文字。

**自然默认方向是 `(维度, 依据)` 的函数，不是全局常量**：

| 依据 | 自然默认 | 理由 |
|---|---|---|
| 按时间（日期维度） | `desc` | 用户要「最新那批先看到」 |
| 按数量 | `desc` | 用户要「最多那批先看到」 |
| 按名称（其余维度） | `asc` | 名称没有「最有用的那个」，字典序正序才是常规默认，反倒 Z→A 需要特意去选 |

切维度或切依据时方向自动回到该组合的自然默认。正看着「哪个角色最多」，手顺点一下
想看「叫什么」，这时候给 Z→A 是莫名其妙的。

默认维度 `char`、默认依据 `count`——库分布高度倾斜（一档占 23%、次三档各约 10%、
其余 40 多个名字各 1~2 张），按名称落地是一串 1 张卡的组。

### 2.3 组内顺序：固定，无控件

组内固定按 `shot_date` 早→晚，空值沉底，同日按 id 稳定兜底。**不给控件、不给界面说明。**

不给控件的理由：没有任何一个维度天然要求另一种组内顺序——按年月分组时组内按日期
是定义决定的；按角色是读某人的时间线；按主题还是时间线。唯一「组内顺序无所谓」的
情形是组内日期全同的组，而那种情况本来就不需要控件。per-group override 只能是
情境性的需求（此刻想把这组换个扫法），不值得为此在每个 section 上摆一个初始状态
全同的控件。

代价：这条规则没有界面载体，只能落在代码注释里——见 § 4。

### 2.4 缺值组恒沉底

两类 section 是**占位信息不是内容**：`char:—`（该维度下无值）与「未标注日期」
（`shot_date` 为空）。它们不参与排序竞争，两种依据、两个方向下都排在最后。

必须显式实现，不能指望排序函数自己搞定：`—` 是标点，`zh` collation 下排在**所有
文字前面**——不特判就会顶成第一个组当页首，这比排中间更糟。按数量时也不插队：
你在看「哪个主题最多」，置顶一个 `—` 组只会挡路。

### 2.5 不加折叠

折叠减少视觉噪音，但不减少 DOM 节点数。真正卡手是几百张卡一起挂载，那时要的是
懒渲染或虚拟滚动，不是把东西藏起来。当前最坏情况一次渲染 483 张，尚未到需要折叠
的量级。

### 2.6 URL 是状态的唯一真值，且在路由层规范化

浏览页的四项状态（分组维度 / 排序依据 / 排序方向 / 已选 tag）全部编码在 query 里。
**三个枚举参数永远写全**，`tags` 有值才写：

```
/list?dim=char&sort=count&dir=desc                            默认态
/list?dim=date&sort=count&dir=desc                            切到日期维度
/list?dim=char&sort=key&dir=asc                               切到按名称依据
/list?dim=char&sort=count&dir=desc&tag=char:小薰              单个筛选
/list?dim=shot&sort=count&dir=desc&tag=char:小薰&tag=char:电电  多选（重复键 = AND）
```

**全用 query，不用 path 段。** 筛选不是资源，拿不到一棵有意义的资源树；path 段还会被
`server.py:485` 先拿去试 `frontend/dist` 下的同名文件。`server.py:474` 的 catch-all
只吃 path 不吃 query，所以 query 方案**后端完全无感，路由表零改动**。

**规范化放在 `router.beforeEach`，不放在视图里**——它是横切关注点。裸 `/list`、
手改的非法值、历史遗留链接、以及等价但不同写的 tag 形态（单字符串 vs 单元素数组、
顺序不同），全部先收敛成唯一一条规范 URL，再把地址栏重写成它。视图拿到的
`route.query` 已经是规范形态，只负责渲染。

守卫返回 location 会**替换**本次导航，所以历史里不会留下
「/list → /list?dim=char...」这一跳。

**为什么不用"只写偏离默认的部分"**（曾经的方案，已否决）：那样 `/list` 与
`/list?dim=char&sort=count&dir=desc` 会是同一个视图的两个 URL，"哪条才是规范 URL"
变成一个需要额外约定的问题。写成全量 + 重定向之后，一个状态恰好一条链接，URL 自描述，
而且已分享的链接是钉死的完整形态——将来改默认值时只有裸 `/list` 会跟着漂。

**唯一真值的实现形式**：`ListView` 里那 4 个 ref 只是 `route.query` 的渲染缓存，
只有 `watch(() => route.query, ...)` 一处写它们。handler 不直接改 ref，而是
`commit()` 改 URL 再由 watcher 回灌。这样后退 / 前进与分享链接走同一条路径，不存在
"ref 改了但 URL 没跟上" 的不一致态，也不存在 watcher↔handler 的回环。

**历史记录分档**：切维度用 `push`（换视图确实是导航），改筛选 / 排序用 `replace`
（页内细化，别把后退键堵成一长串）。

**非法输入一律回退默认，不抛错**——URL 是外部输入。两个例外：

- **已删除的 tag 保留**，照常过滤出 0 张并留在筛选栏里。静默丢弃更糟（界面上 chip
  还在却看不出它在起作用）。
- **不存在的维度**回退默认。不做这件事的话整页会渲染成一个所有组都叫 `—` 的空视图。
- **`validDims` 未知时不校验维度**：tag 池加载失败会退化成只做结构规范化，
  不阻塞导航；此时把所有未知维度打成默认值反而会在数据到达时误伤合法链接。

**防死循环**：规范形态必须被 `isCanonicalBrowseQuery` 判为"已规范"。判据要忽略键序
与 `tag` 的 string/数组形态差异，否则会把已经规范的链接判成需要重定向。
这一条有单测守着（见 § 4）。

## 3. 接口契约

`frontend/src/lib/grouping.ts` 全部为纯函数，不 import 运行时依赖，对 stores /
naive-ui / router 无感知。

| 导出 | 契约 |
|---|---|
| `naturalDir(dim, basis)` | 返回该 `(维度, 依据)` 的自然默认方向 |
| `keyBasisLabel(dim)` | `date` → `'按时间'`，其余 → `'按名称'` |
| `dirText(dim, basis, dir)` | 方向按钮的完整文案 |
| `groupKeysOf(s, dim)` | 返回该卡在该维度下的全部分组键，**恒非空**；无命中返回 `['—']`，无日期返回 `['未标注日期']` |
| `compareWithin(a, b)` | 组内比较器；空 `shot_date` 恒在最后 |
| `buildGroups(rows, dim, basis, dir)` | 切成排好序的 section 数组 |
| `isAbsenceKey(k)` | `k === '—' \|\| k === '未标注日期'` |

`lib/browseQuery.ts` 是状态与 URL 之间的唯一转换点，同样是纯函数：

| 导出 | 契约 |
|---|---|
| `parseBrowseQuery(query)` | URL → 状态；非法值回退默认，绝不抛错 |
| `serializeBrowseQuery(state)` | 状态 → URL；**枚举参数永远写全** |
| `canonicalizeBrowseQuery(query, validDims)` | 任意形态 → 规范形态；`validDims` 为空表示只做结构规范化 |
| `isCanonicalBrowseQuery(query, canonical)` | 判定是否已规范，**必须忽略键序与 tag 的 string/数组形态差异** |
| `validDimsFrom(tagGroups)` | 当前数据下真实存在的维度；守卫与视图 chip 行共用 |
| `DEFAULT_DIM` / `DEFAULT_BASIS` / `PREFIX_ORDER` | 默认值与维度顺序的单一来源 |

`validDimsFrom` 被 `router.beforeEach` 和 `ListView` 的 chip 行共用——所以
"chip 行显示什么" 与 "守卫认可什么" 永远是同一套口径，不会各说各话。

**输入契约**：`buildGroups` 只依赖 `PolaroidSummary` 的 `id` / `shot_date` / `tags`
三个字段。`tags` 允许缺失（视为无命中 → 缺值组）。不依赖 `cover_asset`、不依赖
资产路径、不解析 id 字符串。

**`dir` 的作用域**：只进 section 比较器，**不进 `compareWithin`**。这是 § 2.3 的
实现形式，改动时不得把两者串起来。

**切维度时收敛筛选**：`ListView.setDim` 会丢弃 tag 前缀不属于新维度的已选项，保证
「看到的筛选 = 看到的维度」。

## 4. 验证

实现期在 483 条真实索引上跑过 8 类分组不变量、5 类 URL 契约，全部通过：

**分组（8 类）**

1. 组内 `shot_date` 早→晚、空值沉底 —— 36 组（9 维度 × 2 依据 × 2 方向）/
   17400 次渲染 / 0 违规
2. 缺值组恒沉底 —— 36/36
3. 组内顺序不受组序方向影响 —— 9/9 维度
4. `naturalDir` 与文案 —— 18/18 + 8/8
5. 无卡片在分组中丢失 —— 9/9 维度
6. 过滤子集下规则不变 —— 16/16（含全空 tags 子集）
7. `groupKeysOf` 恒非空 —— 483 条全查
8. 按数量降序时组大小单调不增

**URL 契约（7 类）**

9. **规范形态不自判非规范（防死循环）** —— 22 组 query 形态，含 `isCanonical(canonical, canonical)`
10. `canonicalize` 幂等 —— 22/22
11. `dim` / `sort` / `dir` 永远写全 —— 22/22
12. 完整规范链接判为规范、裸 `/list` 判为非规范
13. 无效 `dim`：有 `validDims` 时回退默认，无 `validDims` 时不动（不误伤合法链接）
14. tag 保留（含已删除的）且排序规范化
15. `parse(serialize(x))` 幂等 —— 22/22

**浏览器端已验**（真后端 + 真实 483 条索引，地址栏实际发生的重定向）：

| 输入 | 规范化后 |
|---|---|
| `/list` | `/list?dim=char&sort=count&dir=desc` |
| `/list?dim=date` | `/list?dim=date&sort=count&dir=desc` |
| `/list?dim=bogus&sort=weird&zzz=1` | `/list?dim=char&sort=count&dir=desc`（回退 + 丢掉多余键） |
| `/list?tag=char:已删除&dir=asc` | `/list?dim=char&sort=count&dir=desc&tag=char:已删除`（tag 保留，页面显示 `0 / 483 · 0 组` + 空状态） |
| `/list?dim=date&sort=count&dir=asc` | 原样保留（`asc` 是对 `(date, count)` 的手动覆盖） |

**点击 → URL 已验**：在 `?dim=date&sort=count&dir=asc` 下点方向按钮，地址栏变成
`?dim=date&sort=count&dir=desc`，按钮文案从「↑ 最少在前」翻成「↓ 最多在前」，
首组从 `2026-09`（13 张）翻成 `2026-03`（63 张）。

### 4.1 踩过的坑（都已加回归断言）

**守卫覆盖显式 `dir`，导致方向按钮失灵。** `canonicalizeBrowseQuery` 最初写成每次都用
`naturalDir(dim, basis)` 覆盖 `dir`——方向按钮点一下，handler 把 `dir=asc` 写进 URL，
守卫立刻又改回 `dir=desc`，用户看到的就是"点了没反应"。根因是把「`dir` 是派生的」
理解错了：`naturalDir` 只在 `dir` **缺失或非法**时兜底，URL 上写了 `dir` 就是用户的
显式选择，必须尊重。守卫只该修 `dim`（只有它的合法性取决于数据）。

**"卡类 bug"：类型错了但不报错。** `grouping.ts` 抽取的直接原因——先把 row `map`
成 id 字符串，之后又用 `x[1]` 取日期，拿到的是字符串第 2 个字符，对所有 id 都相同，
日期比较**静默失效**，排序退化成「比 id 的某一个字符」。页面完全正常、无任何报错，
是靠逐卡比对才发现的 77 处逆序。

**但仓库里没有留下能跑这些的东西**：`frontend/package.json` 只有
`dev` / `build` / `preview`，无测试 runner，无断言文件。`grouping.ts` 与
`browseQuery.ts` 头部列的是**待复核清单，不是已有测试覆盖**。改动这两个文件后请
自行按那几条复核。

### 4.2 这类代码最易出的错

抽取本模块的直接原因：实现过程中真实踩过一次——先把 row `map` 成 id 字符串，
之后又用 `x[1]` 取日期。字符串第 2 个字符对所有 id 都相同，日期比较**静默失效**，
排序退化成「比 id 的某一个字符」，页面完全正常、无任何报错，靠逐卡比对才发现
77 处逆序。所以 `compareWithin` 一律直接对对象排序，不中途 map 成 id。

## 5. 演进约束

- **id 格式债不得泄漏到排序键**。21/483 的 id 不符合 `{日期}_{角色}_{6hex}`，
  其中 5 条是日期区间（`2026-03-06-15--` = 3/6~3/15）。4 处 `shot_date` 与 id 推导
  冲突，但那是语义性的不是数据错（区间拍的记的是末日）。排序键因此固定用
  `shot_date` 字段而非 id 字典序，「按 id 排序 ≡ 按日期排序」在真实数据上不成立。
- 改任一不变量（组内顺序 / 缺值组规则 / 方向默认值 / 组序作用域 / URL 编码）需同步改
  `grouping.ts` 或 `browseQuery.ts` 的注释、本 spec § 2 与 § 3、以及 `ListView.vue`。
- **`ListView` 里的 4 个 ref 只能是 `route.query` 的缓存**，不得在 handler 里直接赋值。
  一旦绕过 `commit()` 直接改 ref，就会出现"界面变了但 URL 没跟上"的不一致态，
  分享链接与后退键随即失效。
- **规范化只写在 `router.beforeEach` 里，不要往视图里加。** 视图里若再加一层
  "无参数时套默认值" 的逻辑，就等于有了第二个真值来源，两处迟早不同步。
- **`isCanonicalBrowseQuery` 的判据必须忽略键序与 `tag` 的 string/数组形态差异**。
  否则规范链接会被判成需要重定向，`/list` 变成无限重定向——这是这条链路上唯一的
  死循环风险点。
- 新增分组维度时，`keyBasisLabel` 的动态标签与 `naturalDir` 的降/升序取值需要
  显式决定，不要默认套用「非日期即名称」。新维度若不是 prefix，要一并决定它要不要
  参与值筛选行（当前只有 `date` 不参与）。
- 前端目前渲染全部匹配卡片（最坏 483 张 `NCard`）。后端实测很快：页面 75ms、
  API 42ms、单缩略图 39ms、20 并发缩略图 816ms——**目前没有观察到卡顿**。若将来
  量级增长到真的影响使用，优先把 `NCard` 换成普通 `div` 或做懒渲染 / 虚拟滚动，
  **不要**靠加折叠来缓解——折叠不减少 DOM 节点。

## 6. 引用

- [architecture](architecture.md)：frontend 为一等模块；浏览路径只 stat SSD
- [polaroid-id-generation](polaroid-id-generation.md)：id 格式与日期区间的由来
- [cold-data-gateway](cold-data-gateway.md)：浏览页不接触冷盘的原因
