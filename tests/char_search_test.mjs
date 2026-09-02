// char_search_test.mjs — Node 内置 test runner 验证 scoreCharMatch 的纯逻辑
//
// 跑法 (项目根):
//   node --experimental-strip-types --no-warnings --test tests/char_search_test.mjs

import { scoreCharMatch } from '../frontend/src/lib/charSearch.ts'
import test from 'node:test'
import assert from 'node:assert/strict'

// Fixture A: 完整 meta, 三个字段都包含 'aki' (key 'aki', canonical '电电Aki', aliases 含 'Aki')
const akiFull = {
  tag: 'char:aki',
  key: 'aki',
  canonical_name: '电电Aki',
  aliases: ['电电Aki', 'Aki'],
  color_rgb: '#FFFF00',
  color_name: '黄色',
}

// Fixture B: 完整 meta, 只有 key 包含 'aki' (其他字段用北北鱼的 meta, 都不含 'aki')
const akiOnlyKey = {
  tag: 'char:aki',
  key: 'aki',
  canonical_name: '北北鱼Honomi',
  aliases: ['北北鱼', 'Honomi'],
  color_rgb: '#F9A7D6',
  color_name: '粉色',
}

// Fixture C: 三个字段都包含 '小' (与用户截图同结构)
const xun = {
  tag: 'char:小薰',
  key: '小薰',
  canonical_name: '小薰Ayako',
  aliases: ['小薰', '小薰Ayako', 'Ayako'],
  color_rgb: null,
  color_name: null,
}

// Fixture D: undefined char, 用于和 xun 对比验证多字段加成
// 稀疏 meta (canonical null, aliases [])
const yusaSparse = {
  tag: 'char:语纱',
  key: '语纱',
  canonical_name: null,
  aliases: [],
  color_rgb: '#E1FDFF',
  color_name: '水色',
}

test('完全匹配 key → 100 (单字段, 不被多命中稀释)', () => {
  const m = scoreCharMatch('aki', akiFull)
  assert.equal(m.score, 100)
  assert.equal(m.field, 'key')
  assert.equal(m.hitCount, 1)
})

test('完全匹配 canonical → 90', () => {
  const m = scoreCharMatch('电电Aki', akiFull)
  assert.equal(m.score, 90)
  assert.equal(m.field, 'canonical')
})

test('完全匹配 alias (key 不同时) → 85', () => {
  // 构造 key 不命中, alias 完全匹配的场景
  const d = {
    tag: 'char:yusa',
    key: 'yusa',
    canonical_name: null,
    aliases: ['Aki'],
    color_rgb: null,
    color_name: null,
  }
  const m = scoreCharMatch('Aki', d)
  assert.equal(m.score, 85)
  assert.equal(m.field, 'alias')
})

test('单字段 key 包含 → 50, 无加成', () => {
  const m = scoreCharMatch('ki', akiOnlyKey)
  // key 'aki' 包含 'ki' → 50; canonical '北北鱼Honomi' 不包含; alias '北北鱼'/'Honomi' 不包含
  // hits=1, no bonus
  assert.equal(m.score, 50)
  assert.equal(m.field, 'key')
  assert.equal(m.hitCount, 1)
})

test('多字段命中 → 累加 + 加成 (用户截图场景)', () => {
  // xun 输入 '小': key '小薰' 前缀命中 (80), canonical '小薰Ayako' 前缀命中 (70),
  // alias '小薰'/'小薰Ayako' 前缀命中 (60, max=60); 三字段命中 hits=3, bonus=(3-1)*20=40
  // total = 80 + 70 + 60 + 40 = 250
  const m = scoreCharMatch('小', xun)
  assert.equal(m.hitCount, 3)
  assert.equal(m.score, 250)
  assert.equal(m.field, 'key')
})

test('多字段加成 > 单字段 key 命中', () => {
  // xun 输入 '小': 三字段命中 (80+70+60) + bonus 40 = 250
  // yusaSparse 输入 '语': key 单字段前缀命中 (80), canonical null, aliases []
  //   → ks=80, cs=0, as=0, hits=1, bonus=0 → 80
  // 验证 xun.score > yusaSparse.score (用户截图的反例修复)
  const multi = scoreCharMatch('小', xun)
  const single = scoreCharMatch('语', yusaSparse)
  assert.ok(multi.score > single.score, `multi ${multi.score} should > single ${single.score}`)
  assert.equal(single.score, 80)
  assert.equal(single.hitCount, 1)
})

test('两字段命中 → 加成 +20', () => {
  // 构造: key 包含 'ak' + canonical 包含 'ak'
  const d = {
    tag: 'char:aki',
    key: 'aki',
    canonical_name: 'akimoto',
    aliases: [],
    color_rgb: null,
    color_name: null,
  }
  const m = scoreCharMatch('ak', d)
  // ks = 80 (前缀), cs = 70 (前缀), hits=2, bonus = 20
  // total = 80 + 70 + 20 = 170
  assert.equal(m.score, 170)
  assert.equal(m.hitCount, 2)
})

test('canonical 完全匹配早返回 (priority)', () => {
  const d = {
    tag: 'char:aki',
    key: 'aki',
    canonical_name: 'ak',
    aliases: [],
    color_rgb: null,
    color_name: null,
  }
  // 输入 'ak' → canonical 完全匹配 → 早返回 90 (即使 key 是前缀)
  const m = scoreCharMatch('ak', d)
  assert.equal(m.field, 'canonical')
  assert.equal(m.score, 90)
})

test('alias 命中但 key/canonical 不命中 → field=alias', () => {
  const d = {
    tag: 'char:yusa',
    key: 'yusa',
    canonical_name: '北北鱼Honomi',
    aliases: ['hello'],
    color_rgb: null,
    color_name: null,
  }
  const m = scoreCharMatch('hel', d)
  assert.equal(m.field, 'alias')
  assert.equal(m.score, 60) // alias 前缀
})

test('大小写不敏感 (完全匹配)', () => {
  assert.equal(scoreCharMatch('AKI', akiFull).score, 100)
})

test('大小写不敏感 (前缀)', () => {
  // 'AK' → 'ak' (lowercase); key 'aki' 前缀命中 (80), canonical '电电aki' includes 'ak' (40),
  // alias 'aki' → 'aki' startsWith 'ak' (60). 三字段命中 hits=3, bonus=(3-1)*20=40.
  // total = 80 + 40 + 60 + 40 = 220
  assert.equal(scoreCharMatch('AK', akiFull).score, 220)
})

test('空 query / whitespace → score 0', () => {
  assert.equal(scoreCharMatch('', akiFull).score, 0)
  assert.equal(scoreCharMatch('   ', akiFull).score, 0)
})

test('无命中 → score 0', () => {
  const m = scoreCharMatch('zzz_nope', akiFull)
  assert.equal(m.score, 0)
  assert.equal(m.field, null)
  assert.equal(m.hitCount, 0)
})

test('undef (无 meta) 仍能按 key 搜索', () => {
  const undef = {
    tag: 'char:aki_unReg',
    key: 'aki_unReg',
    canonical_name: null,
    aliases: [],
    color_rgb: null,
    color_name: null,
  }
  const m = scoreCharMatch('aki_u', undef)
  assert.equal(m.score, 80)
  assert.equal(m.field, 'key')
})

test('undef 无 meta 时搜其他字段返回 0', () => {
  const undef = {
    tag: 'char:aki_unReg',
    key: 'aki_unReg',
    canonical_name: null,
    aliases: [],
    color_rgb: null,
    color_name: null,
  }
  const m = scoreCharMatch('电电Aki', undef)
  assert.equal(m.score, 0)
})

test('alias 列表里有多个 alias 都能命中, 取 max', () => {
  const d = {
    tag: 'char:aki',
    key: 'aki',
    canonical_name: null,
    aliases: ['电电Aki', '电电'],
    color_rgb: null,
    color_name: null,
  }
  // 输入 '电电' → 完全匹配第二个 alias '电电' → 85 (完全 alias 早返回)
  const m1 = scoreCharMatch('电电', d)
  assert.equal(m1.score, 85)

  // 输入 '电电Aki' → 完全匹配第一个 alias '电电Aki' → 85 (完全 alias 早返回)
  const m2 = scoreCharMatch('电电Aki', d)
  assert.equal(m2.score, 85)
})

test('同分时 key 升序 (排序由 caller 决定, 但分数应相同)', () => {
  // 两个 undef 同样分数
  const o1 = { tag: 'c:a', key: 'a', canonical_name: null, aliases: [], color_rgb: null, color_name: null }
  const o2 = { tag: 'c:b', key: 'b', canonical_name: null, aliases: [], color_rgb: null, color_name: null }
  const q = 'x'
  // 都不命中
  assert.equal(scoreCharMatch(q, o1).score, 0)
  assert.equal(scoreCharMatch(q, o2).score, 0)
})
