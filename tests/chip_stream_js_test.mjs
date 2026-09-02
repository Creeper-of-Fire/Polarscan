// chip_stream_js_test.mjs — Node 内置 test runner 验证 useChipStream 的纯逻辑
//
// 跑法 (项目根):
//   node --experimental-strip-types --no-warnings --test tests/chip_stream_js_test.mjs
//
// API (2026-08 重构后):
//   useChipStream({ autoPrefix?, allowFreeform?, suggestions, getSelected })
//   - computeTag(raw):  返回新 tag 字符串 (含前缀) 或 null (空 / 重复 / freeform 无冒号)
//   - clearQuery():     清空 query + suggestItems
//   - query / suggestItems / onInput()  (不变)
//
// **单源头**: composable 不再持有 modelValue 副本; dedup 走 getSelected() 在源头判断,
// 因此跨 stream 的重复天然消失 (B1 fix).

import { useChipStream } from '../frontend/src/composables/useChipStream.ts'
import test from 'node:test'
import assert from 'node:assert/strict'

function emptySelected() { return [] }

test('useChipStream: char 流自动加前缀', () => {
  const cs = useChipStream({
    autoPrefix: 'char',
    suggestions: emptySelected,
    getSelected: emptySelected,
  })
  assert.equal(cs.computeTag('北北鱼'), 'char:北北鱼')
})

test('useChipStream: 已带前缀则不重复', () => {
  const sel = []
  const cs = useChipStream({
    autoPrefix: 'char',
    suggestions: emptySelected,
    getSelected: () => sel,
  })
  assert.equal(cs.computeTag('char:北北鱼'), 'char:北北鱼')
  sel.push('char:北北鱼')
  assert.equal(cs.computeTag('char:北北鱼'), null)
})

test('useChipStream: freeform 流不加前缀, 接受带冒号输入', () => {
  const cs = useChipStream({
    allowFreeform: true,
    suggestions: emptySelected,
    getSelected: emptySelected,
  })
  assert.equal(cs.computeTag('event:ayako_birthday'), 'event:ayako_birthday')
  assert.equal(cs.computeTag('shot:pair'), 'shot:pair')
})

test('useChipStream: 空字符串 / 空白返回 null', () => {
  const cs = useChipStream({
    autoPrefix: 'char',
    suggestions: emptySelected,
    getSelected: emptySelected,
  })
  assert.equal(cs.computeTag(''), null)
  assert.equal(cs.computeTag('   '), null)
})

test('useChipStream: freeform 流拒绝无冒号输入 (B2 fix)', () => {
  const cs = useChipStream({
    allowFreeform: true,
    suggestions: emptySelected,
    getSelected: emptySelected,
  })
  assert.equal(cs.computeTag('myevent'), null)
})

test('useChipStream: 去重看 getSelected 源头 (B1 fix)', () => {
  const sel = ['char:aki']
  const cs = useChipStream({
    autoPrefix: 'char',
    suggestions: emptySelected,
    getSelected: () => sel,
  })
  // 即便 stream 内部不持有, 也正确识别源头已有
  assert.equal(cs.computeTag('aki'), null)
  assert.equal(cs.computeTag('char:aki'), null)
})

test('useChipStream: 跨 stream 去重 (B1 fix, 双 stream 共享同一个源头)', () => {
  // 模拟 PolaroidTagsEditor: 两个 stream 都从同一个 props.modelValue 读 getSelected
  const model = ['char:yusa']
  const sharedSelected = () => model

  const charStream = useChipStream({
    autoPrefix: 'char',
    suggestions: emptySelected,
    getSelected: sharedSelected,
  })
  const otherStream = useChipStream({
    allowFreeform: true,
    suggestions: emptySelected,
    getSelected: sharedSelected,
  })

  // char 流加 char:yusa → 已在源头, 应返回 null
  assert.equal(charStream.computeTag('yusa'), null)
  // other 流尝试加 char:yusa (freeform 接受) → 已在源头, 应返回 null
  assert.equal(otherStream.computeTag('char:yusa'), null)
  // other 流加新 event:ayako_sp → 应返回 'event:ayako_sp'
  assert.equal(otherStream.computeTag('event:ayako_sp'), 'event:ayako_sp')
})

test('useChipStream: onInput 重算 suggestItems', () => {
  const cs = useChipStream({
    autoPrefix: 'char',
    suggestions: () => ['char:小薰', 'char:北北鱼', 'event:ayako_birthday'],
    getSelected: emptySelected,
  })
  cs.query.value = '北'
  cs.onInput()
  assert.deepEqual(cs.suggestItems.value, ['char:北北鱼'])
})

test('useChipStream: onInput 排除已选 chip (通过 getSelected)', () => {
  // 用英文别名 ayako + aki 模拟"两候选都含 a, 排除已选"——CJK 字符里需要找公共子串,
  // 英文别名天然适合 substring 过滤测试.
  const cs = useChipStream({
    autoPrefix: 'char',
    suggestions: () => ['char:ayako', 'char:aki'],
    getSelected: () => ['char:ayako'],
  })
  cs.query.value = 'a' // ayako + aki 都包含 'a'
  cs.onInput()
  assert.deepEqual(cs.suggestItems.value, ['char:aki'])
})

test('useChipStream: clearQuery 清空 query + suggestItems', () => {
  const cs = useChipStream({
    autoPrefix: 'char',
    suggestions: () => ['char:小薰', 'char:北北鱼'],
    getSelected: emptySelected,
  })
  cs.query.value = '北' // 命中 'char:北北鱼'
  cs.onInput()
  assert.equal(cs.suggestItems.value.length, 1)
  cs.clearQuery()
  assert.equal(cs.query.value, '')
  assert.deepEqual(cs.suggestItems.value, [])
})

test('useChipStream: freeform 流 onInput 不过滤带前缀的', () => {
  const cs = useChipStream({
    allowFreeform: true,
    suggestions: () => ['event:ayako_birthday', 'shot:pair', 'sig:有签名'],
    getSelected: emptySelected,
  })
  cs.query.value = 'birth'
  cs.onInput()
  assert.deepEqual(cs.suggestItems.value, ['event:ayako_birthday'])
})