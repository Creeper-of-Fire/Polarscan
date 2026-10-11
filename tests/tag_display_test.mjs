// tag_display_test.mjs — 展示名规则 (canonical_name || key) 的单测
//
// 这条规则是本次改动引入的核心不变量: 全站所有 tag 展示面 (CharTag / 标签 chip /
// 浏览页组头与筛选 chip / char 候选选项) 都必须走 lib/tagDisplay.ts,
// 且**只影响渲染** —— 分组 / 排序 / URL 仍然用裸 tag。
//
// 跑法 (项目根):
//   node --experimental-strip-types --no-warnings --test tests/tag_display_test.mjs

import { tagDisplayFrom } from '../frontend/src/lib/tagDisplay.ts'
import test from 'node:test'
import assert from 'node:assert/strict'

test('canonical 存在 → display_name = canonical_name (不是 key)', () => {
  // 真实数据里的反例: 用户叫"雪雪", 但 id 是他不常用的那个名字
  const d = tagDisplayFrom('char:绿岛条雪', { canonical_name: '雪雪Yuki' })
  assert.equal(d.display_name, '雪雪Yuki')
  assert.equal(d.key, '绿岛条雪')
})

test('canonical 缺失 → display_name 回退 key', () => {
  const d = tagDisplayFrom('char:未注册角色', undefined)
  assert.equal(d.display_name, '未注册角色')
  assert.equal(d.canonical_name, null)
})

test('canonical 是空串 / 纯空白 → 同样回退 key (不显示空白 chip)', () => {
  assert.equal(tagDisplayFrom('char:小薰', { canonical_name: '' }).display_name, '小薰')
  assert.equal(tagDisplayFrom('char:小薰', { canonical_name: '   ' }).display_name, '小薰')
})

test('canonical 非字符串 → 回退 key, 不抛错', () => {
  const d = tagDisplayFrom('char:小薰', { canonical_name: 123 })
  assert.equal(d.canonical_name, null)
  assert.equal(d.display_name, '小薰')
})

test('canonical 前后空白被 trim', () => {
  assert.equal(tagDisplayFrom('char:x', { canonical_name: ' 雪雪Yuki ' }).display_name, '雪雪Yuki')
})

test('规则与 prefix 无关: 非 char prefix 同样生效', () => {
  const d = tagDisplayFrom('collection:塔罗牌-大阿卡纳牌-小薰', { canonical_name: '大阿卡纳-小薰' })
  assert.equal(d.prefix, 'collection')
  assert.equal(d.display_name, '大阿卡纳-小薰')
})

test('key 含冒号时只切第一个 (key 理论上可含冒号)', () => {
  const d = tagDisplayFrom('event:ayako:birthday:3rd', undefined)
  assert.equal(d.prefix, 'event')
  assert.equal(d.key, 'ayako:birthday:3rd')
  assert.equal(d.display_name, 'ayako:birthday:3rd')
})

test('无冒号的 legacy tag → prefix 空, 整体当 key', () => {
  const d = tagDisplayFrom('小薰', undefined)
  assert.equal(d.prefix, '')
  assert.equal(d.key, '小薰')
  assert.equal(d.display_name, '小薰')
})

test('meta 为空对象 / null → 安全降级', () => {
  for (const meta of [{}, null, undefined]) {
    const d = tagDisplayFrom('char:aki', meta)
    assert.equal(d.canonical_name, null)
    assert.deepEqual(d.aliases, [])
    assert.equal(d.color_rgb, null)
    assert.equal(d.color_name, null)
    assert.equal(d.display_name, 'aki')
  }
})

test('aliases 过滤非字符串与空白项', () => {
  const d = tagDisplayFrom('char:aki', { aliases: ['Aki', '', '  ', 42, null, '电电'] })
  assert.deepEqual(d.aliases, ['Aki', '电电'])
})

test('color_rgb 只接受 #RRGGBB', () => {
  const ok = tagDisplayFrom('char:a', { color_rgb: '#F9A7D6' })
  assert.equal(ok.color_rgb, '#F9A7D6')
  // 命名色 / rgb() / 短 hex / 脏值一律降级为 null (spec tag-pool §5)
  for (const bad of ['pink', 'rgb(1,2,3)', '#FFF', '#GGGGGG', '']) {
    assert.equal(tagDisplayFrom('char:a', { color_rgb: bad }).color_rgb, null, bad)
  }
})

test('tag 原样保留 (调用方拿它发回后端)', () => {
  assert.equal(tagDisplayFrom('char:小薰', {}).tag, 'char:小薰')
})