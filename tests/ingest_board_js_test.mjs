// ingest_board_js_test.mjs — 连连看画布状态机（纯函数）测试
//
// 跑法 (项目根):
//   node --experimental-strip-types --no-warnings --test tests/ingest_board_js_test.mjs
//
// 覆盖 docs/spec/ingest-scan.md § 2.4–2.6 的状态机不变量：
//   卡=正面 chip / 翻转升降级 / 挂载互斥 / 日期区两来源 / 跳过不入库 / 载荷组装
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  initBoard,
  flipChip,
  pairBack,
  unpairBack,
  addZone,
  removeZone,
  moveCard,
  addTag,
  removeTag,
  poolChips,
  committableCards,
  cardPayload,
  removeCards,
  removeChips,
  addItems,
  unsortedByBatch,
  ZONE_UNSORTED,
} from '../frontend/src/lib/ingestBoard.ts'

/** 造 scan 项 */
function item(path, face, tier = 'auto', batch = 'B1') {
  return { path, hash: `h-${path}`, thumbUrl: `/thumb?path=${path}`, batch, face, tier, dupPid: null }
}

/** 标准开局：2 正 2 背 1 未知 */
function fresh() {
  return initBoard(
    [
      item('f1.png', 'front'),
      item('f2.png', 'front'),
      item('b1.png', 'back'),
      item('b2.png', 'back'),
      item('u1.png', 'unknown', 'suspect'),
    ],
    ['2026-10-17', '2026-10-18'],
  )
}

// ───────────────────────── initBoard ─────────────────────────

test('init: 正面自动成卡进未分类，back/unknown 留反面区', () => {
  const b = fresh()
  assert.deepEqual(Object.keys(b.cards).sort(), ['f1.png', 'f2.png'])
  assert.equal(b.cards['f1.png'].zone, ZONE_UNSORTED)
  assert.equal(b.cards['f1.png'].backChipId, null)
  // 反面区 3 个自由 chip（b1/b2/u1）
  const pool = poolChips(b)
  assert.deepEqual(pool.map((c) => c.id).sort(), ['b1.png', 'b2.png', 'u1.png'])
  assert.deepEqual(b.zones, ['2026-10-17', '2026-10-18'])
})

test('init: 候选日期去重', () => {
  const b = initBoard([], ['2026-10-17', '2026-10-17', '2026-10-18'])
  assert.deepEqual(b.zones, ['2026-10-17', '2026-10-18'])
})

// ───────────────────────── 翻转 ─────────────────────────

test('翻转 back→front：升级成新卡（未分类），autoFace 保留', () => {
  const b = fresh()
  flipChip(b, 'b1.png')
  assert.equal(b.chips['b1.png'].face, 'front')
  assert.equal(b.chips['b1.png'].autoFace, 'back')
  assert.ok(b.cards['b1.png'], '应生成新卡')
  assert.equal(b.cards['b1.png'].zone, ZONE_UNSORTED)
  assert.ok(!poolChips(b).some((c) => c.id === 'b1.png'))
})

test('翻转 unknown→front：同背面（第一次翻成正面）', () => {
  const b = fresh()
  flipChip(b, 'u1.png')
  assert.equal(b.chips['u1.png'].face, 'front')
  assert.ok(b.cards['u1.png'])
})

test('翻转 front→back：卡解散，挂载背面弹回反面区', () => {
  const b = fresh()
  assert.equal(pairBack(b, 'b1.png', 'f1.png'), true)
  flipChip(b, 'f1.png') // f1 的正面翻成背面
  assert.equal(b.chips['f1.png'].face, 'back')
  assert.ok(!b.cards['f1.png'], '卡应解散')
  // b1 自动弹回反面区
  const pool = poolChips(b).map((c) => c.id)
  assert.ok(pool.includes('b1.png'))
  assert.ok(pool.includes('f1.png'))
})

test('翻转 back→front 时若挂在别的卡上：先解除原挂载', () => {
  const b = fresh()
  pairBack(b, 'b1.png', 'f1.png')
  flipChip(b, 'b1.png') // 挂在 f1 上的 b1 翻成正面
  assert.equal(b.cards['f1.png'].backChipId, null, 'f1 的挂载应被解除')
  assert.ok(b.cards['b1.png'], 'b1 应成为新卡')
})

// ───────────────────────── 配对 ─────────────────────────

test('配对成功：卡获得背面', () => {
  const b = fresh()
  assert.equal(pairBack(b, 'b1.png', 'f1.png'), true)
  assert.equal(b.cards['f1.png'].backChipId, 'b1.png')
  assert.ok(!poolChips(b).some((c) => c.id === 'b1.png'), 'b1 不再是自由 chip')
})

test('配对互斥：已有背面再挂 → false', () => {
  const b = fresh()
  pairBack(b, 'b1.png', 'f1.png')
  assert.equal(pairBack(b, 'b2.png', 'f1.png'), false)
  assert.equal(b.cards['f1.png'].backChipId, 'b1.png')
})

test('配对非法：正面 chip 不可挂载 / 卡不存在', () => {
  const b = fresh()
  assert.equal(pairBack(b, 'f2.png', 'f1.png'), false, '正面 chip 不能当背面挂')
  assert.equal(pairBack(b, 'b1.png', 'nope.png'), false)
})

test('配对换卡：已挂的 chip 拖到新卡 = 换绑', () => {
  const b = fresh()
  pairBack(b, 'b1.png', 'f1.png')
  assert.equal(pairBack(b, 'b1.png', 'f2.png'), true)
  assert.equal(b.cards['f1.png'].backChipId, null)
  assert.equal(b.cards['f2.png'].backChipId, 'b1.png')
})

test('解除挂载：背面回反面区', () => {
  const b = fresh()
  pairBack(b, 'b1.png', 'f1.png')
  unpairBack(b, 'f1.png')
  assert.equal(b.cards['f1.png'].backChipId, null)
  assert.ok(poolChips(b).some((c) => c.id === 'b1.png'))
})

// ───────────────────────── 日期区 ─────────────────────────

test('moveCard: 合法区成功；不存在的区拒绝（不隐式建区）', () => {
  const b = fresh()
  assert.equal(moveCard(b, 'f1.png', '2026-10-17'), true)
  assert.equal(b.cards['f1.png'].zone, '2026-10-17')
  assert.equal(moveCard(b, 'f2.png', '2026-10-99'), false, '不存在的区必须拒绝')
  assert.equal(b.cards['f2.png'].zone, ZONE_UNSORTED)
  assert.equal(moveCard(b, 'f2.png', ZONE_UNSORTED), true, '拖回未分类合法')
})

test('addZone: 合法 ISO 成功；格式错 / 重复拒绝', () => {
  const b = fresh()
  assert.equal(addZone(b, '2026-10-07'), true)
  assert.equal(b.zones.includes('2026-10-07'), true)
  assert.equal(addZone(b, '2026-10-07'), false, '重复拒绝')
  assert.equal(addZone(b, '20261007'), false, '格式拒绝')
  assert.equal(addZone(b, ZONE_UNSORTED), false, '不能与固定区重名')
})

test('removeZone: 区内卡弹回未分类', () => {
  const b = fresh()
  moveCard(b, 'f1.png', '2026-10-17')
  removeZone(b, '2026-10-17')
  assert.equal(b.cards['f1.png'].zone, ZONE_UNSORTED)
  assert.ok(!b.zones.includes('2026-10-17'))
})

// ───────────────────────── tag / 跳过 ─────────────────────────

test('tag: 增删 + 去重', () => {
  const b = fresh()
  assert.equal(addTag(b, 'f1.png', 'char:小薰'), true)
  assert.equal(addTag(b, 'f1.png', 'char:小薰'), false, '重复 tag 拒绝')
  addTag(b, 'f1.png', 'event:偶活')
  removeTag(b, 'f1.png', 'char:小薰')
  assert.deepEqual(b.cards['f1.png'].tags, ['event:偶活'])
})

test('提交范围: 未分类（左栏）不参与提交，进日期区才可提交', () => {
  const b = fresh()
  // 初始全在未分类 → 无可提交卡
  assert.equal(committableCards(b).length, 0)
  moveCard(b, 'f1.png', '2026-10-17')
  assert.deepEqual(committableCards(b).map((c) => c.id), ['f1.png'])
})

// ───────────────────────── 提交载荷 ─────────────────────────

test('cardPayload: role 显式 front/back + 判定元数据透传 + shot_date 从区派生', () => {
  const b = fresh()
  pairBack(b, 'b1.png', 'f1.png')
  moveCard(b, 'f1.png', '2026-10-18')
  addTag(b, 'f1.png', 'char:小薰')

  const p = cardPayload(b, 'f1.png')
  assert.ok(p)
  assert.equal(p.shot_date, '2026-10-18')
  assert.deepEqual(p.tags, ['char:小薰'])
  assert.equal(p.assets.length, 2)
  assert.equal(p.assets[0].role, 'front')
  assert.equal(p.assets[0].path, 'f1.png')
  assert.equal(p.assets[1].role, 'back')
  assert.equal(p.assets[1].path, 'b1.png')
  // 判定元数据随资产透传
  assert.deepEqual(p.assets[1].metadata, {
    ingest: { auto_face: 'back', tier: 'auto', manual_flip: false },
  })
})

test('cardPayload: 未分类（左栏）的卡 → null；不存在的卡 → null', () => {
  const b = fresh()
  assert.equal(cardPayload(b, 'f1.png'), null, '未分类不提交')
  moveCard(b, 'f1.png', '2026-10-17')
  assert.ok(cardPayload(b, 'f1.png'))
  assert.equal(cardPayload(b, 'nope.png'), null)
})

test('removeChips: 忽略自由背面 = 直接消失', () => {
  const b = fresh()
  removeChips(b, ['b1.png'])
  assert.ok(!b.chips['b1.png'])
  assert.ok(!poolChips(b).some((c) => c.id === 'b1.png'))
})

test('removeChips: 忽略挂载中的背面 = 解除挂载，宿主卡保留', () => {
  const b = fresh()
  pairBack(b, 'b1.png', 'f1.png')
  removeChips(b, ['b1.png'])
  assert.ok(!b.chips['b1.png'])
  assert.ok(b.cards['f1.png'], '宿主卡保留')
  assert.equal(b.cards['f1.png'].backChipId, null)
})

test('removeChips: 忽略卡本体 = 卡解散，挂载背面弹回自由池', () => {
  const b = fresh()
  pairBack(b, 'b1.png', 'f1.png')
  removeChips(b, ['f1.png'])
  assert.ok(!b.cards['f1.png'])
  assert.ok(!b.chips['f1.png'])
  assert.ok(b.chips['b1.png'], '背面保留')
  assert.ok(poolChips(b).some((c) => c.id === 'b1.png'), '背面回自由池')
})

test('addItems: 增量合并保留现有状态——已配对 / 已分区 / 手动区不动', () => {
  const b = fresh()
  pairBack(b, 'b1.png', 'f1.png')          // f1 配对
  moveCard(b, 'f2.png', '2026-10-17')      // f2 进日期区
  addZone(b, '2026-10-07')                 // 手动区

  // 增量：一个新正面（其批次带来新候选日）+ 一个已在画布的路径（应跳过）
  addItems(
    b,
    [
      item('nf1.png', 'front', 'auto', 'B2'),
      item('f1.png', 'front', 'auto', 'B1'), // 已存在 → 跳过，不得覆盖
    ],
    ['2026-10-20', '2026-10-17'], // 一个新区 + 一个已有区
  )

  // 现有状态保留
  assert.equal(b.cards['f1.png'].backChipId, 'b1.png', '配对保留')
  assert.equal(b.cards['f2.png'].zone, '2026-10-17', '分区保留')
  assert.ok(b.zones.includes('2026-10-07'), '手动区保留')
  // 新内容加入
  assert.ok(b.cards['nf1.png'], '新正面成卡')
  assert.equal(b.cards['nf1.png'].zone, ZONE_UNSORTED)
  assert.ok(b.zones.includes('2026-10-20'), '新候选日合并')
  assert.equal(b.zones.filter((z) => z === '2026-10-17').length, 1, '已有区不重复')
  // 已存在路径不覆盖（f1 仍挂 b1）
  assert.equal(b.cards['f1.png'].backChipId, 'b1.png')
})

test('cardPayload: 人工翻转被记录（manual_flip）', () => {
  const b = fresh()
  flipChip(b, 'b1.png') // 机器判背面，人工翻成正面成卡
  moveCard(b, 'b1.png', '2026-10-17') // 进日期区才可提交
  const p = cardPayload(b, 'b1.png')
  assert.ok(p)
  assert.deepEqual(p.assets[0].metadata, {
    ingest: { auto_face: 'back', tier: 'auto', manual_flip: true },
  })
})

test('removeCards: 删卡连同其正反面 chip；反面区剩余不受影响', () => {
  const b = fresh()
  pairBack(b, 'b1.png', 'f1.png')
  removeCards(b, ['f1.png'])
  assert.ok(!b.cards['f1.png'])
  assert.ok(!b.chips['f1.png'])
  assert.ok(!b.chips['b1.png'], '挂载背面应随卡删除')
  // f2 卡与 b2/u1 自由 chip 保留
  assert.ok(b.cards['f2.png'])
  const pool = poolChips(b).map((c) => c.id).sort()
  assert.deepEqual(pool, ['b2.png', 'u1.png'])
})

// ───────────────────────── 批次分组（摆放，不是配对） ─────────────────────────

test('unsortedByBatch: 卡按正面批次、自由背面按自身批次归组', () => {
  const b = initBoard(
    [
      item('a-f1.png', 'front', 'auto', '2026.10.24-25'),
      item('a-b1.png', 'back', 'auto', '2026.10.24-25'),
      item('b-f1.png', 'front', 'auto', '2026.10.17-18'),
      item('b-b1.png', 'back', 'auto', '2026.10.17-18'),
    ],
    [],
  )
  const groups = unsortedByBatch(b)
  assert.equal(groups.length, 2)
  assert.deepEqual(groups.map((g) => g.batch), ['2026.10.17-18', '2026.10.24-25'], '按名称排序')
  for (const g of groups) {
    assert.equal(g.cards.length, 1)
    assert.equal(g.chips.length, 1)
  }
})

test('unsortedByBatch: 配对后 chip 离开批次框；进日期区的卡离开批次框', () => {
  const b = initBoard(
    [
      item('f1.png', 'front', 'auto', 'B1'),
      item('b1.png', 'back', 'auto', 'B1'),
      item('f2.png', 'front', 'auto', 'B1'),
    ],
    ['2026-10-17'],
  )
  pairBack(b, 'b1.png', 'f1.png')      // b1 挂到 f1 上
  moveCard(b, 'f2.png', '2026-10-17')  // f2 进日期区
  const groups = unsortedByBatch(b)
  assert.equal(groups.length, 1)
  assert.equal(groups[0].batch, 'B1')
  assert.deepEqual(groups[0].cards.map((c) => c.id), ['f1.png'])
  assert.deepEqual(groups[0].chips.map((c) => c.id), [], '已挂载的背面不在自由 chip 里')
})
