// path_parse_js_test.mjs — Node 内置 test runner 验证两个纯函数模块
//
// 跑法 (项目根):
//   node --experimental-strip-types --no-warnings --test tests/path_parse_js_test.mjs
//
// 无额外依赖。覆盖:
//   lib/folderDateCompat.ts   兼容层 —— 命名语法 (可改可替换，改这里)
//   composables/usePathParse.ts 通用层 —— 路径工具 + 候选日收集
//
// 前端组件不在这里。
import test from 'node:test'
import assert from 'node:assert/strict'
import { parseFolderDays } from '../frontend/src/lib/folderDateCompat.ts'
import { parentDirName, collectCandidateDays } from '../frontend/src/composables/usePathParse.ts'

// ───────────────────────── 兼容层：命名语法 ─────────────────────────

test('单日', () => {
  assert.deepEqual(parseFolderDays('2026.07.25'), ['2026-07-25'])
  assert.deepEqual(parseFolderDays('2026-07-25'), ['2026-07-25'])
})

test('同月连续：逐日包含中间', () => {
  assert.deepEqual(parseFolderDays('2026.07.25-26'), ['2026-07-25', '2026-07-26'])
  assert.deepEqual(parseFolderDays('2026.07.24-28'), [
    '2026-07-24', '2026-07-25', '2026-07-26', '2026-07-27', '2026-07-28',
  ])
})

test('异月连续（同年）', () => {
  assert.deepEqual(parseFolderDays('2026.02.28-03.01'), ['2026-02-28', '2026-03-01'])
})

test('跨年连续：年份必须显式写', () => {
  assert.deepEqual(parseFolderDays('2026.12.28-2027.01.03'), [
    '2026-12-28', '2026-12-29', '2026-12-30', '2026-12-31',
    '2027-01-01', '2027-01-02', '2027-01-03',
  ])
})

test('跨年不猜年份：2026.12.28-01.03 必须拒绝', () => {
  // 月变小是跨年的信号，但年份要显式写。这里若接受，就等于替用户猜了 +1。
  assert.equal(parseFolderDays('2026.12.28-01.03'), null)
})

test('「和」：只列出的几天，不补中间', () => {
  // 关键回归：曾经 & 被当成连续区间，会凭空造出 08-15。
  assert.deepEqual(parseFolderDays('2026.08.14&16'), ['2026-08-14', '2026-08-16'])
})

test('「和」：可以连三个以上', () => {
  assert.deepEqual(parseFolderDays('2026.08.14&16&18'), [
    '2026-08-14', '2026-08-16', '2026-08-18',
  ])
})

test('「和」：某一天不存在则整条拒绝', () => {
  assert.equal(parseFolderDays('2026.02.14&30'), null)
})

test('拒绝的形态', () => {
  assert.equal(parseFolderDays('2026.07.25-'), null, '悬空 dash')
  assert.equal(parseFolderDays('2026.13.45'), null, '非法月日')
  assert.equal(parseFolderDays('宿题'), null, '非日期名')
  assert.equal(parseFolderDays(''), null, '空串')
  assert.equal(parseFolderDays(null), null, 'null')
  assert.equal(parseFolderDays(undefined), null, 'undefined')
})

test('起止倒序不产出候选', () => {
  assert.equal(parseFolderDays('2026.07.28-24'), null)
})

// ───────────────────────── 通用层：路径工具 ─────────────────────────

test('parentDirName', () => {
  assert.equal(parentDirName('F:\\photo\\2026.07.25\\img.jpg'), '2026.07.25')
  assert.equal(parentDirName('/F/photo/2026.07.25/img.jpg'), '2026.07.25')
  assert.equal(parentDirName(null), null)
  assert.equal(parentDirName(''), null)
  assert.equal(parentDirName('ayako.jpg'), null, '无父目录')
})

test('collectCandidateDays: 合并去重并升序', () => {
  assert.deepEqual(
    collectCandidateDays([
      { path: 'F:/photo/2026.07.25-26/a.jpg' },
      { path: 'F:/photo/2026.07.25-26/b.jpg' },
      { path: 'F:/photo/2026.08.14&16/c.jpg' },
    ]),
    ['2026-07-25', '2026-07-26', '2026-08-14', '2026-08-16'],
  )
})

test('collectCandidateDays: 只看父目录名，忽略文件名', () => {
  // 文件名里的日期是扫描日，不是拍摄日，不参与。
  assert.deepEqual(
    collectCandidateDays([{ path: 'F:/photo/宿题/img20260401_c.jpg' }]),
    [],
  )
})

test('collectCandidateDays: 空 / nullish / 不可解析', () => {
  assert.deepEqual(collectCandidateDays([]), [])
  assert.deepEqual(collectCandidateDays([{}, { path: null }, { path: '' }]), [])
  assert.deepEqual(collectCandidateDays([null, undefined]), [])
  assert.deepEqual(collectCandidateDays([{ path: '/photos/no-date/x.jpg' }]), [])
})