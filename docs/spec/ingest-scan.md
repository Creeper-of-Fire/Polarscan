# SPEC: ingest-scan（存储区扫描 + 连连看批量入库）

- **STATUS**: IN PROGRESS
- **LAST_UPDATED**: 2026-10-28

## 涉及代码

- 扫描端点：`apps/web/server.py`（`POST /api/ingest/scan`）
- 判定规则（纯函数管线）：`frontend/src/lib/faceRules.ts`
- 判定 IO：`frontend/src/composables/useFaceClassify.ts`
- 画布状态机：`frontend/src/composables/useIngestBoard.ts`
- 页面：`frontend/src/views/IngestView.vue`
- 候选日解析（复用）：`frontend/src/lib/folderDateCompat.ts`
- 写入：复用 `PUT /polaroid/{pid}`（无新写入端点）

## 1. 背景

单张 drop 工作流（[drop-identify](drop-identify.md)）一次一张、逐张详填，无法应对一次扫描几十张的批次。
本 spec 定义批量工作流：手动搬运 → 扫描发现 → 正反判定 → 拖拽配对 → 逐卡提交。

## 2. 设计

### 2.1 存储区即 library_root

不存在第二套真相。待入库文件必须先由用户手动放入 library_root（F 盘相册）下的批次文件夹；
yaml 里的资产 path 永远只指向 library_root 内的绝对路径。无库内副本、无多根、无外部路径引用。

### 2.2 scan 端点：纯 IO，无判定

`POST /api/ingest/scan` 是 explicit gesture（用户点击触发；单次 rglob 的先例见 drop-identify）：

1. 单次 rglob library_root 下 `*.png`（仅 png，跳过不可读文件）
2. 与 `_index.yaml` 的 path 集合对比，已入库者跳过（幂等：重复扫描 new 恒空）
3. 对每个新文件：`compute_hash`（cold gate 读 #1）→ `find_by_hash` 查重 →
   `make_thumb_if_missing`（cold gate 读 #2）
4. 返回清单：path / hash / thumb_url / dup_pid（同内容换名的重扫件提示）

判定不在后端——后端只负责产出 hash 与缩略图，正反判定由前端围绕缩略图完成（§ 2.3）。

### 2.3 正反判定：前端 lib 纯函数 + 固定阈值

`faceRules.ts` 是纯函数管线：像素进 → 特征 → 阈值 → 判定出，直接输出
`front | back | unknown` 与档位（自动 / 待确认 / 可疑）。物理含义 = 相纸白框占比（正面）
vs 相纸黑背（背面）。实测（20 张，512px 缩略图 JPEG，2026-10-28 标定）：

| 特征 | 含义 | 角色 | 实测背面（6 张） | 实测正面（14 张） |
|---|---|---|---|---|
| whiteRatio | 全图白低饱和占比 | 主判 | 0.0201–0.0328 | 0.2476–0.4656 |
| midWhiteRatio | 水平中带白占比 | 交叉 | 0.0000–0.0097 | 0.0771–0.3416 |
| midDarkRatio | 水平中带暗占比 | 交叉 | 0.7587–0.9984 | 0.2578–0.6813 |
| cornerWhiteRatio | 四角并集白占比 | 交叉 | 0.0940–0.1613 | 0.7342–0.9735 |

四特征零重叠。whiteRatio / cornerWhiteRatio 旋转不变；mid 系特征**方向敏感**——
水平中带有效的原因是必然横穿左右白框，中心块定义已被实测否决（正面中心可完全
落在照片内部）。横构图由 IO 层（useFaceClassify）旋正后喂入，faceRules 显式拒绝
横构图。

- **无参考集、无运行时外部状态**。阈值是具名常量；实测区间只进单测断言（回归用），不参与运行时
- 三档容错：自动（主判过阈且交叉一致）/ 待确认（过阈但交叉矛盾，黄标）/ 可疑（落在空心区，红标不猜）
- 人工永远优先：chip 角标点击可翻转，翻转直接改变卡结构（§ 2.4），提交以人工结果为准

### 2.4 卡模型：卡 = 正面 chip，背面 = 高级 tag

```
chip.face ∈ {front, back}              // 角标点击翻转
face = front 的 chip ≡ 卡的本体          // 卡 = 本体 + 0..1 挂载背面 + tags
face = back 且未挂载 ≡ 反面区自由 chip
```

- 拖背面 chip 到卡 = 配对。**互斥**：一卡最多一背面；拖回批次框解除
- 翻转 back→front：升级成一张新卡（进未分类区）
- 翻转 front→back：卡解散，原挂载背面（若有）弹回反面区
- **拖正面图 = 拖整张卡**（卡 = 正面 chip，无独立拖拽柄）：拖入日期区 = shot_date
  分组，拖回批次框 = 回未分类；tag 池拖 chip 到卡 = 打标
- **摆放按批次分组**：未分类大框内按批次（父文件夹名）分小框，同批次的卡与
  待配对背面相邻。这只是摆放（文件夹名 = 人类手工分类，合法分组依据），
  **不是配对依据**——配对永远由人的拖拽决定（AGENTS.md 否决时间/文件序配对）

### 2.5 日期区只有两个来源

批次文件夹名解析（folderDateCompat 兼容层）+ 用户手动新建。**任何卡不得自动长出日期区**。
候选日仍是推荐值不是判断（[shot-date-semantics](shot-date-semantics.md)）；拖卡入日期区与点击
候选日按钮等价，均属用户显式手势。

### 2.6 提交范围与忽略区

- **提交范围 = 日期区里的卡**。左栏（未分类）的卡本次不提交——留在画布，下次扫描
  仍在（path 未入库，无断链）。未配对背面同样留在左栏。
- **忽略区**：不要的文件（无关图片、多张重扫中落选的那张）放入忽略区，按内容
  hash 记录在浏览器 localStorage——文件挪动/重命名后过滤仍生效。扫描时自动过滤，
  可随时**移回画布**（增量合并：保留已配对 / 已分区 / 手动日期区，仅单张重新判定
  后加入左栏）。忽略是 chip 级：忽略卡本体 = 卡解散（挂载背面弹回左栏）；
  忽略挂载中的背面 = 解除挂载；忽略自由背面 = 直接消失。
  重扫同理走增量合并，不重建画布。
- 提交逐卡 PUT：role 显式 front / back（不使用按位置序推导），shot_date = 区日期
  （ingest 工作流不产生 null 日期提交；无日期入库走 /new）。
- 双击任意缩略图 = 放大预览（lightbox，完整缩略图，非原图）。

## 3. 接口契约

### POST /api/ingest/scan

```
→ 200 {
  "new": [
    { "path": "F:\\相册\\...\\xxx.png",
      "hash": "<128 hex>",
      "thumb_url": "/thumb?path=..&hash=..",
      "dup_pid": null | "<pid>" }   // 同 hash 已在库 → 提示，由用户决定
  ],
  "skipped_known": 3,               // path 已在 yaml 的数量
  "errors": [ { "path": "...", "reason": "..." } ]
}
```

约束：无请求体必需字段；library_root 缺失 / 为空 → `new` 恒空（同 drop-identify 的优雅降级）。

## 4. 验证

- `faceRules` 单测：20 张实测特征区间作为断言边界（正面 white_ratio 下界 > 主阈值 > 背面上界），
  交叉特征矛盾降档、空心区不猜等行为用例
- scan 端点测试：幂等（二次扫描 new 为空）/ path 跳过 / dup_pid 提示 / library_root 缺失降级
- `useIngestBoard` 状态机测试：翻转的升降级、背面挂载互斥、跳过不入库

## 5. 演进约束

- "把东西放入存储区"作为能力的一部分（上传搬运入口）：后续演化。届时后端只增加
  "写入 library_root"一个动作，下游 scan → 判定 → 配对 → 提交流水线不变
- 正面合并（front + front-alter）：后续演化，挂载规则从互斥扩展为按 role
- 判定自举（人工翻转结果回流阈值/参考集）：**不做**——阈值保持人工调校的具名常量

## 6. 引用

- [cold-data-gateway](cold-data-gateway.md)：scan 的两次读全部走 cold gate
- [drop-identify](drop-identify.md)：单次 rglob = explicit gesture 的先例
- [asset-hash](asset-hash.md) / [thumb-naming](thumb-naming.md)：hash 算法与缩略图命名
- [put-polaroid-contract](put-polaroid-contract.md)：逐卡提交走现成 PUT，hash 由 scan 提供
- [shot-date-semantics](shot-date-semantics.md)：候选日语义 + 显式手势写入
