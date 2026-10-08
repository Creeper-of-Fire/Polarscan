// 浏览页状态 ↔ URL query 的序列化契约。
//
// 抽出来的理由跟 lib/grouping.ts 一样: 这层最容易出"静默不一致" ——
// URL 写的是 A、界面显示的是 B, 两者都不报错, 只有分享链接的人会发现不对。
//
// 为什么全用 query 而不是 path 段: 筛选不是资源, 拿不到一棵有意义的资源树;
// path 段还会被 server.py:485 先拿去试 frontend/dist 下的同名文件。
// server.py:474 的 catch-all 只吃 path 不吃 query, 所以 query 方案后端完全无感。
//
// 为什么永远写全四个参数 + 路由层重定向到规范形态（而不是只写偏离默认的部分）:
//   规范化是横切关注点, 不该由视图负责 —— 视图只该渲染已经规范化的状态。
//   规范化放在 router.beforeEach, 于是:
//     - 一个状态恰好一条规范 URL, /list 与 /list?dim=char&sort=count&dir=desc 不再
//       是两个同义链接
//     - 任何非规范形态（裸 /list、手改的非法值、旧链接）都自动收敛
//     - URL 自描述, 粘到任何地方都知道在看什么
//     - 将来改默认值时, 已分享的链接是钉死的完整形态, 只有裸 /list 会跟着漂
//
// 规范位置: docs/spec/browse-grouping.md § 2.6 / § 3

import { DATE_DIM, naturalDir, type SortBasis, type SortDir } from './grouping'

export { DATE_DIM }

/** prefix 顺序: char 放最前（审查主战场）, 其余按 schema 顺序。 */
export const PREFIX_ORDER = [
  'char',
  'shot',
  'event',
  'theme',
  'collection',
  'composite',
  'moment',
  'sig',
]

export const DEFAULT_DIM = 'char'

/** 默认依据是数量而不是名称。2026-10-06 对真实索引 (_index.yaml, 483 条) 盘过:
 *  角色维度分布高度倾斜 —— 一档 23%、次三档各约 10%、其余 40 多个名字各 1~2 张。
 *  按名称进落地是一串 1 张卡的组, 找不到实际在用的角色。 */
export const DEFAULT_BASIS: SortBasis = 'count'

/** 规范化用的三个枚举型参数 —— 这几个的取值是封闭的。 */
export const ENUM_KEYS = ['dim', 'sort', 'dir'] as const

export interface BrowseState {
  dim: string
  basis: SortBasis
  dir: SortDir
  tags: string[]
}

/** 一个 query 值可能是 string、string[] 或 null/undefined（重复键 → 数组）。 */
export type QueryValue = string | string[] | null | undefined
export type RawQuery = Record<string, QueryValue>

function toStringArray(raw: QueryValue): string[] {
  if (Array.isArray(raw)) return raw.filter((t): t is string => typeof t === 'string' && t.length > 0)
  return typeof raw === 'string' && raw.length > 0 ? [raw] : []
}

/** 当前数据下真实存在的维度: date 恒在, 其余按 tag 池里出现过的 prefix。 */
export function validDimsFrom(tagGroups: Record<string, string[]>): string[] {
  const known = PREFIX_ORDER.filter((p) => p in tagGroups)
  const extra = Object.keys(tagGroups).filter((p) => !PREFIX_ORDER.includes(p))
  return [DATE_DIM, ...known, ...extra]
}

/** URL → 状态。结构层：非法值一律回退默认，不抛错（URL 是外部输入）。
 *  dir 缺省时由 naturalDir 派生 —— 正常路径下路由守卫已经把它写全了，
 *  这个回退只是给手改 / 粘贴残缺链接时的防御。 */
export function parseBrowseQuery(query: RawQuery): BrowseState {
  const rawDim = query.dim
  const dim = typeof rawDim === 'string' && rawDim.length > 0 ? rawDim : DEFAULT_DIM
  const rawSort = query.sort
  const basis: SortBasis = rawSort === 'key' || rawSort === 'count' ? rawSort : DEFAULT_BASIS
  const rawDir = query.dir
  const dir: SortDir = rawDir === 'asc' || rawDir === 'desc' ? rawDir : naturalDir(dim, basis)
  return {
    dim,
    basis,
    dir,
    // 规范化: 选中顺序不同但集合相同 → 同一条 URL, 不产生同义链接
    tags: toStringArray(query.tag).sort(),
  }
}

/** 状态 → URL。三个枚举参数永远写全；tags 有值才写。 */
export function serializeBrowseQuery(state: BrowseState): Record<string, string | string[]> {
  const q: Record<string, string | string[]> = {
    dim: state.dim,
    sort: state.basis,
    dir: state.dir,
  }
  if (state.tags.length > 0) q.tag = state.tags
  return q
}

/** 把任意形态的 query 收敛到规范形态。
 *
 *  这里**只**修 dim，因为只有 dim 的合法性取决于数据（tag 池）；sort / dir 的取值
 *  空间是封闭的，parseBrowseQuery 已经兜住了。
 *
 *  特别注意：**不要**在这里用 naturalDir 覆盖 dir。URL 上写了 dir 就是用户的显式选择
 *  （方向按钮点出来的），覆盖它会让方向切换"点了没反应" —— 守卫把它改回自然默认，
 *  用户看到的就是按钮失灵。naturalDir 只在 dir 缺失或非法时由 parseBrowseQuery 兜底。
 *  切维度 / 切依据时方向要回到自然默认，那是 handler（setDim / setBasis）的职责，
 *  它会显式把新的 dir 写进 URL。
 *
 *  `validDims` 为空表示还不知道有哪些真实维度（tag 池还没加载 / 加载失败），
 *  此时完全不动 dim —— 把未知维度一律打成默认值会在 tag 池到达时误伤合法链接。
 *
 *  tag 不做存在性校验：已删除的 tag 仍然保留并照常过滤出 0 张。静默丢弃更糟，
 *  那样界面上 chip 还在却看不出它在起作用。 */
export function canonicalizeBrowseQuery(
  query: RawQuery,
  validDims: readonly string[],
): Record<string, string | string[]> {
  const state = parseBrowseQuery(query)
  if (validDims.length === 0 || validDims.includes(state.dim)) return serializeBrowseQuery(state)
  // 无效维度 → 回退默认维度；dir 仍尊重 URL 上写的值
  return serializeBrowseQuery({ ...state, dim: DEFAULT_DIM })
}

/** 判定一个 query 是否已经是规范形态（供路由守卫决定要不要重定向）。
 *  比较必须忽略键序与 `tag` 的 string/数组形态差异，否则会把已经规范的链接
 *  判成需要重定向，形成死循环。 */
export function isCanonicalBrowseQuery(
  query: RawQuery,
  canonical: Record<string, string | string[]>,
): boolean {
  const rawTags = toStringArray(query.tag).sort()
  const canonTags = Array.isArray(canonical.tag) ? (canonical.tag as string[]) : []
  if (rawTags.length !== canonTags.length) return false
  for (let i = 0; i < rawTags.length; i++) if (rawTags[i] !== canonTags[i]) return false
  for (const key of ENUM_KEYS) {
    if (query[key] !== canonical[key]) return false
  }
  // 不得有多余的键
  const known = new Set<string>([...ENUM_KEYS, 'tag'])
  return Object.keys(query).every((k) => known.has(k))
}