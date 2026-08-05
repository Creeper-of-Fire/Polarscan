// chip_stream_js_test.mjs — Node 内置 test runner 验证 useChipStream 的纯逻辑
//
// 跑法 (项目根):
//   node --experimental-strip-types --no-warnings --test tests/chip_stream_js_test.mjs
import { useChipStream } from '../frontend/src/composables/useChipStream.ts'
import test from 'node:test'
import assert from 'node:assert/strict'

test('useChipStream: char 流自动加前缀', () => {
  const cs = useChipStream({ autoPrefix: 'char', allowFreeform: false, suggestions: () => [] })
  assert.equal(cs.addChip('my_push'), true)
  assert.deepEqual(cs.modelValue.value, ['char:my_push'])
  assert.equal(cs.query.value, '')
})

test('useChipStream: 已带前缀则不重复', () => {
  const cs = useChipStream({ autoPrefix: 'char', allowFreeform: false, suggestions: () => [] })
  cs.addChip('char:my_push')
  assert.equal(cs.addChip('char:my_push'), false)
  assert.deepEqual(cs.modelValue.value, ['char:my_push'])
})

test('useChipStream: freeform 流不加前缀', () => {
  const cs = useChipStream({ allowFreeform: true, suggestions: () => [] })
  cs.addChip('event:foo')
  cs.addChip('shot:pair')
  assert.deepEqual(cs.modelValue.value, ['event:foo', 'shot:pair'])
})

test('useChipStream: 空字符串 / 空白返回 false', () => {
  const cs = useChipStream({ autoPrefix: 'char', suggestions: () => [] })
  assert.equal(cs.addChip(''), false)
  assert.equal(cs.addChip('   '), false)
  assert.deepEqual(cs.modelValue.value, [])
})

test('useChipStream: 去重 (char 模式含前缀)', () => {
  const cs = useChipStream({ autoPrefix: 'char', suggestions: () => [] })
  cs.addChip('alice')
  cs.addChip('char:alice') // 应被识别为已存在
  assert.equal(cs.modelValue.value.length, 1)
})

test('useChipStream: removeChip', () => {
  const cs = useChipStream({ autoPrefix: 'char', suggestions: () => [] })
  cs.addChip('alice')
  cs.addChip('bob')
  cs.removeChip('char:alice')
  assert.deepEqual(cs.modelValue.value, ['char:bob'])
})

test('useChipStream: onInput 重算 suggestItems', () => {
  const cs = useChipStream({
    autoPrefix: 'char',
    suggestions: () => ['char:strawberry', 'char:my_push', 'event:foo'],
  })
  cs.query.value = 'push'
  cs.onInput()
  assert.deepEqual(cs.suggestItems.value, ['char:my_push'])
})

test('useChipStream: onInput 排除已选 chip', () => {
  const cs = useChipStream({
    autoPrefix: 'char',
    suggestions: () => ['char:strawberry', 'char:my_push'],
  })
  cs.addChip('strawberry')
  cs.query.value = 's' // 同时匹配 strawberry + my_push
  cs.onInput()
  // strawberry 已经在 modelValue, 应被过滤; my_push 留下
  assert.deepEqual(cs.suggestItems.value, ['char:my_push'])
})

test('useChipStream: setTags 全量替换', () => {
  const cs = useChipStream({ autoPrefix: 'char', suggestions: () => [] })
  cs.addChip('alice')
  cs.setTags(['char:bob', 'char:carol'])
  assert.deepEqual(cs.modelValue.value, ['char:bob', 'char:carol'])
})

test('useChipStream: freeform 流 onInput 不过滤带前缀的', () => {
  const cs = useChipStream({
    allowFreeform: true,
    suggestions: () => ['event:shenshan', 'shot:pair', 'sig:foo'],
  })
  cs.query.value = 'shen'
  cs.onInput()
  assert.deepEqual(cs.suggestItems.value, ['event:shenshan'])
})