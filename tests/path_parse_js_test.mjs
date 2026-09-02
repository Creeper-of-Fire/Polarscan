// path_parse_js_test.mjs — Node 内置 test runner 验证 usePathParse 的纯函数
//
// 跑法 (项目根):
//   node --experimental-strip-types --no-warnings --test tests/path_parse_js_test.mjs
//
// 这是纯 TS -> JS 测试,前端组件不在这里. 任何路径解析改动 (regex, 跨月, …) 必须跑通过.
// 参考 scratch/verify_thumb_endpoint.py 的同类一次性 .py 验证做法, 这里保持 "无需额外依赖".
import {
  parseFolderDateRange, parseFilenameDate, parentDirName,
  idDateRange, shotDateHint, assetsDateRange,
} from '../frontend/src/composables/usePathParse.ts'
import test from 'node:test'
import assert from 'node:assert/strict'

test('parseFolderDateRange: 单日', () => {
  assert.deepEqual(parseFolderDateRange('2026.07.25'), { start: '2026-07-25', end: '2026-07-25' })
})

test('parseFolderDateRange: 同月范围', () => {
  assert.deepEqual(parseFolderDateRange('2026.07.25-26'), { start: '2026-07-25', end: '2026-07-26' })
})

test('parseFolderDateRange: 同月范围(dash 分隔)', () => {
  assert.deepEqual(parseFolderDateRange('2026-07-25-26'), { start: '2026-07-25', end: '2026-07-26' })
})

test('parseFolderDateRange: 跨月 (2026.02.28-03.01)', () => {
  assert.deepEqual(parseFolderDateRange('2026.02.28-03.01'), { start: '2026-02-28', end: '2026-03-01' })
})

test('parseFolderDateRange: 跨月 (dash 分隔 2026-02-28-03-01)', () => {
  assert.deepEqual(parseFolderDateRange('2026-02-28-03-01'), { start: '2026-02-28', end: '2026-03-01' })
})

test('parseFolderDateRange: 跨月 7 天 (2026.12.28-01.03)', () => {
  assert.deepEqual(parseFolderDateRange('2026.12.28-01.03'), { start: '2026-12-28', end: '2027-01-03' })
})

test('parseFolderDateRange: 悬空 dash 返回 null', () => {
  assert.equal(parseFolderDateRange('2026.07.25-'), null)
})

test('parseFolderDateRange: 非法日期返回 null', () => {
  assert.equal(parseFolderDateRange('2026.13.45'), null)
})

test('parseFolderDateRange: 完全非日期返回 null', () => {
  assert.equal(parseFolderDateRange('dandan_xyz'), null)
})

test('parseFolderDateRange: 半跨月(2026.07.25-26.03)返回 null', () => {
  // 形态: YYYY.MM.DD-DD.MM 语义模糊, 拒绝
  assert.equal(parseFolderDateRange('2026.07.25-26.03'), null)
})

test('parseFilenameDate: 标准 img20260725_…', () => {
  assert.equal(parseFilenameDate('img20260725_xyz.jpg'), '2026-07-25')
})

test('parseFilenameDate: 不匹配返回 null', () => {
  assert.equal(parseFilenameDate('IMG_20260725.jpg'), null)
})

test('parentDirName: Windows 路径', () => {
  assert.equal(parentDirName('F:\\photo\\2026.07.25\\img.jpg'), '2026.07.25')
})

test('parentDirName: POSIX 路径', () => {
  assert.equal(parentDirName('/F/photo/2026.07.25/img.jpg'), '2026.07.25')
})

test('parentDirName: null / 空 / 无父目录', () => {
  assert.equal(parentDirName(null), null)
  assert.equal(parentDirName(''), null)
  assert.equal(parentDirName('ayako.jpg'), null)
})

test('idDateRange: 单日 pid', () => {
  assert.deepEqual(idDateRange('2026-07-25--img_001'), ['2026-07-25'])
})

test('idDateRange: 范围 pid 跨日', () => {
  assert.deepEqual(idDateRange('2026-07-25-26--img_001'), ['2026-07-25', '2026-07-26'])
})

test('idDateRange: 非日期 pid', () => {
  assert.deepEqual(idDateRange('dandan_xxx'), [])
})

test('shotDateHint: 取首日', () => {
  assert.equal(shotDateHint('2026-07-25-26--img_001'), '2026-07-25')
  assert.equal(shotDateHint('dandan_xxx'), '')
})

test('assetsDateRange: 单个跨月', () => {
  assert.deepEqual(
    assetsDateRange([{ path: 'F:/photo/2026.02.28-03.01/a.jpg' }]),
    ['2026-02-28', '2026-03-01'],
  )
})

test('assetsDateRange: 多个范围 + filename 混合', () => {
  assert.deepEqual(
    assetsDateRange([
      { path: 'F:/photo/2026.02.28-03.01/a.jpg' },
      { path: 'F:/photo/2026.03.02/b.jpg' },
      { path: 'F:/photo/misc/img20260401_c.jpg' },
    ]),
    ['2026-02-28', '2026-03-01', '2026-03-02', '2026-04-01'],
  )
})

test('assetsDateRange: 同范围去重', () => {
  assert.deepEqual(
    assetsDateRange([
      { path: 'F:/photo/2026.07.25-26/a.jpg' },
      { path: 'F:/photo/2026.07.25-26/b.jpg' },
    ]),
    ['2026-07-25', '2026-07-26'],
  )
})

test('assetsDateRange: 空 / 无路径 / 全部不可解析', () => {
  assert.deepEqual(assetsDateRange([]), [])
  assert.deepEqual(assetsDateRange([{}, { path: null }, { path: '' }]), [])
  assert.deepEqual(assetsDateRange([{ path: '/photos/no-date/x.jpg' }]), [])
})

test('assetsDateRange: 跳过 nullish 项', () => {
  assert.deepEqual(
    assetsDateRange([null, undefined, { path: 'F:/photo/2026.07.25/a.jpg' }]),
    ['2026-07-25'],
  )
})
