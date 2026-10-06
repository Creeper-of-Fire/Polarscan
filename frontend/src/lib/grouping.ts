// ListView 的分组 / 组序纯逻辑。
//
// 抽出来的理由: 这类排序代码最容易出的错是"类型错了但不报错"。本轮真实踩过:
// 把 PolaroidSummary 先 map 成 id 字符串, 之后又用 x[1] 取日期 —— 拿到的是
// 字符串第 2 个字符, 对所有 id 都相同, 日期比较静默失效, 排序退化成"比 id 的
// 某一个字符"。页面看起来完全正常, 没有任何报错, 是靠逐卡比对才发现的。
// 所以下面一律直接对对象排序, 不中途 map 成 id; 逻辑也从 .vue 里抽出来,
// 便于这样单点复核。
//
// 改本文件后请自行复核下面 4 条 (仓库里没有跑这套不变量的测试, frontend
// 没有测试 runner, 也没有断言文件; 下面是清单, 不是"已有测试覆盖"):
//   1. 组内 shot_date 早→晚, 空值沉底, 同日按 id 兜底 (compareWithin)
//   2. 组序只决定 section 先后, 不影响组内顺序 (buildGroups 里 dir 只进
//      section 比较器, 不进 compareWithin)
//   3. 缺值组 ('—' / '未标注日期') 在两种 basis、两个方向下都沉底
//      (buildGroups 里的 isAbsenceKey 分支)
//   4. naturalDir(dim, basis) 决定方向默认值; 切 basis / 切 dim 时调用方
//      要重算方向 (ListView.setBasis / setDim)
//
// 纯函数, 不 import 运行时依赖; 对 stores / naive-ui / router 无感知。

import type { PolaroidSummary } from '@/types'

export type SortBasis = 'key' | 'count'
export type SortDir = 'desc' | 'asc'

/** "日期" 不是 prefix, 但它是唯一撑得起"按时间 / 按名称"之分的维度。 */
export const DATE_DIM = 'date'

/** 缺值组: 该维度下没有值的卡 ('—') / 没有日期的卡 ('未标注日期')。
 *  占位信息不是内容 —— 恒沉底, 不参与排序竞争。 */
export const ABSENCE_VALUE = '—'
export const ABSENCE_DATE = '未标注日期'

export function isAbsenceKey(k: string): boolean {
  return k === ABSENCE_VALUE || k === ABSENCE_DATE
}

export function isDateDimOf(dim: string): boolean {
  return dim === DATE_DIM
}

/** 自然默认方向是 (维度, 依据) 的函数, 不是全局常量。
 *  时间 / 数量取降序: 用户要的是"最有用的那批先看到"。
 *  名称取升序: 名称没有"最有用的那个", 字典序正序才是常规默认, Z→A 反而需要特意去选。 */
export function naturalDir(dim: string, basis: SortBasis): SortDir {
  if (basis === 'count') return 'desc'
  return dim === DATE_DIM ? 'desc' : 'asc'
}

/** 依据 key 的显示名跟着维度走 —— 日期维度叫"按时间", 其余叫"按名称"。
 *  不写"自身"这类实现细节。 */
export function keyBasisLabel(dim: string): string {
  return dim === DATE_DIM ? '按时间' : '按名称'
}

/** 方向按钮自带当前含义, 旁边不用再配一行解释文字。 */
export function dirText(dim: string, basis: SortBasis, dir: SortDir): string {
  if (basis === 'count') return dir === 'desc' ? '最多在前' : '最少在前'
  if (dim === DATE_DIM) return dir === 'desc' ? '最新在前' : '最早在前'
  return dir === 'desc' ? 'Z → A' : 'A → Z'
}

/** 一张卡在某个维度下可能命中多个值 (多个 char / theme), 所以返回数组。
 *  一个值都没命中时进 '—' 缺值组。 */
export function groupKeysOf(s: PolaroidSummary, dim: string): string[] {
  if (dim === DATE_DIM) {
    return [s.shot_date ? s.shot_date.slice(0, 7) : ABSENCE_DATE]
  }
  const prefix = `${dim}:`
  const tags = s.tags ?? []
  const hits = tags.filter((t) => t.startsWith(prefix)).map((t) => t.slice(prefix.length))
  return hits.length > 0 ? hits : [ABSENCE_VALUE]
}

/** 组内顺序: shot_date 早→晚, 空值沉底, 同日按 id 稳定兜底。
 *  直接比较对象本身 —— 不要中途 map 成 id 再取字段。 */
export function compareWithin(a: PolaroidSummary, b: PolaroidSummary): number {
  const ad = a.shot_date
  const bd = b.shot_date
  if (!ad && !bd) return a.id < b.id ? -1 : 1
  if (!ad) return 1
  if (!bd) return -1
  if (ad !== bd) return ad < bd ? -1 : 1
  return a.id < b.id ? -1 : 1
}

export interface Group {
  key: string
  items: PolaroidSummary[]
}

/** 把已过滤的行切成按组序排好的 sections。
 *  组序只决定 section 之间的先后, 组内顺序由 compareWithin 定死。 */
export function buildGroups(
  rows: readonly PolaroidSummary[],
  dim: string,
  basis: SortBasis,
  dir: SortDir,
): Group[] {
  const map = new Map<string, PolaroidSummary[]>()
  for (const s of rows) {
    for (const k of groupKeysOf(s, dim)) {
      const bucket = map.get(k)
      if (bucket) bucket.push(s)
      else map.set(k, [s])
    }
  }
  const sign = dir === 'desc' ? -1 : 1
  const out: Group[] = []
  for (const [key, items] of map) {
    out.push({ key, items: [...items].sort(compareWithin) })
  }
  out.sort((a, b) => {
    const aAbs = isAbsenceKey(a.key)
    const bAbs = isAbsenceKey(b.key)
    if (aAbs !== bAbs) return aAbs ? 1 : -1
    if (basis === 'count') {
      if (a.items.length !== b.items.length) return sign * (a.items.length - b.items.length)
      return a.key.localeCompare(b.key, 'zh')
    }
    return sign * (a.key < b.key ? -1 : a.key > b.key ? 1 : 0)
  })
  return out
}
