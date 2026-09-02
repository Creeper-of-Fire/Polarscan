// 路径/文件名解析 composable
// 接受文件夹名 "2026.07.25-26" / 文件名 "img20260725_..." 推断日期
//
// 接受的文件夹日期模式:
//   "2026.07.25"            → 单日 { start: 2026-07-25, end: 2026-07-25 }
//   "2026.07.25-26"         → 同月 2 日 { start: 2026-07-25, end: 2026-07-26 }
//   "2026.02.28-03.01"      → 跨月   { start: 2026-02-28, end: 2026-03-01 }
//   "2026.08.14&16"         → `&` 连接两天 (14 日 和 16 日)
//   "2026-07-25"            → 单日 (. 也可换 -)
//   "2026-07-25-26"         → 同月 2 日
//   "2026-02-28-03-01"      → 跨月
//   "2026-08-14&16"         → `&` 连接两天
// 不接受: "2026.07.25-" (悬空), "2026.07.25-26.03" (半跨月),
//         "2026.08.14&09.16" (`&` 后面只能跟 DD, 跨月请用 `-`)
//
// ⚠ 这是字符串解析,不是日期运算: "2026.02.28-29" 在平年会自动延到 3/1,此处严格解析后两者
//   都没"日期范围",调用方按需扩展。

// `&` 后只跟 DD (连接两天); 跨月仍走 `-MM.DD` 形式.
// 单独 OR 分支, 不把分隔符泛化为 `[-&]`, 避免 `2026.08.14&09.16` 这类半跨月被接受.
const RANGE_RE = /^(\d{4})[\.\-](\d{1,2})[\.\-](\d{1,2})(?:-(?:(\d{1,2})(?:[\.\-](\d{1,2}))?)|&(\d{1,2}))?$/
const FN_DATE_RE = /^img(\d{4})(\d{2})(\d{2})_/i

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

function toIso(year: string, month: number, day: number): string | null {
  const y = parseInt(year, 10)
  const m = month
  const d = day
  // 用 UTC 检查日期是否有效 (避免 2026-02-30 在本地时区被推到 03-02)
  const utcMs = Date.UTC(y, m - 1, d)
  if (isNaN(utcMs)) return null
  const check = new Date(utcMs)
  if (check.getUTCFullYear() !== y
    || check.getUTCMonth() !== m - 1
    || check.getUTCDate() !== d) return null
  return `${year.padStart(4, '0')}-${pad2(m)}-${pad2(d)}`
}

/**
 * 从文件夹名推断日期范围
 * 返回 { start, end } 均为 YYYY-MM-DD,失败返回 null。
 *
 * 跨月场景: endMonth < startMonth 时 year 自动 +1 (例 2026.12.28-01.03 → end 2027-01-03).
 *
 * `&` (group 6): 连接两天. 跟 `-` 分支互斥, seg1/seg2 必空.
 */
export function parseFolderDateRange(name: string): { start: string; end: string } | null {
  const m = RANGE_RE.exec(name)
  if (!m) return null
  const yearNum = parseInt(m[1], 10)
  const startMonth = parseInt(m[2], 10)
  const startDay = parseInt(m[3], 10)
  const startIso = toIso(String(yearNum), startMonth, startDay)
  if (!startIso) return null

  // m[4] = `-` 分支第一段 (单月: endDay; 跨月: endMonth);
  // m[5] = `-` 分支第二段 (仅跨月使用: endDay);
  // m[6] = `&` 分支: 连接两天 (跟 m[4]/m[5] 互斥).
  const seg1 = m[4]
  const seg2 = m[5]
  const ampSeg = m[6]
  // `&` 连接两天 (ampSeg 单独出现, seg1/seg2 必为空)
  if (ampSeg) {
    const e = toIso(String(yearNum), startMonth, parseInt(ampSeg, 10))
    if (!e) return null
    return { start: startIso, end: e }
  }
  // 单日
  if (!seg1 && !seg2) return { start: startIso, end: startIso }
  // 跨月: YYYY.MM.DD-MM.DD
  if (seg1 && seg2) {
    const endMonth = parseInt(seg1, 10)
    const endDay = parseInt(seg2, 10)
    // 跨年: endMonth < startMonth 时, endYear = startYear + 1
    const endYearNum = endMonth < startMonth ? yearNum + 1 : yearNum
    const e = toIso(String(endYearNum), endMonth, endDay)
    if (!e) return null
    return { start: startIso, end: e }
  }
  // 同月: YYYY.MM.DD-DD (seg1 为 endDay, seg2 缺失)
  if (seg1 && !seg2) {
    const e = toIso(String(yearNum), startMonth, parseInt(seg1, 10))
    if (!e) return null
    return { start: startIso, end: e }
  }
  return null
}

/**
 * 从文件名 "imgYYYYMMDD_..." 推断单日。
 * 接受 path (含父目录) 或纯 basename;只对 basename 部分匹配。
 */
export function parseFilenameDate(name: string): string | null {
  if (!name) return null
  const base = String(name).split(/[\\/]/).pop() ?? ''
  const m = FN_DATE_RE.exec(base)
  if (!m) return null
  return `${m[1]}-${m[2]}-${m[3]}`
}

/**
 * 从绝对路径中提取父目录名 (例如 "/F/photo/2026.07.25/img.jpg" → "2026.07.25")
 */
export function parentDirName(path: string | null | undefined): string | null {
  if (!path) return null
  const parts = String(path).split(/[\\/]/)
  if (parts.length < 2) return null
  return parts[parts.length - 2]
}

/**
 * 从 polaroid id 解析日期范围 (legacy / 当前 shot_date hint)
 * '2026-07-25-26--img...' → ['2026-07-25', '2026-07-26']
 * '2026-07-25--img...'    → ['2026-07-25']
 * 'dandan_xxx'            → []
 * @deprecated 用 assetsDateRange 替换; 此函数保留仅给 ListView shotDateHint
 */
export function idDateRange(pid: string): string[] {
  if (!pid) return []
  // 范围 pid: YYYY-MM-DD-DD--, 单日 pid: YYYY-MM-DD-- (没有 -DD 那段)
  const range = /^(\d{4})-(\d{2})-(\d{2})-(\d{2})--/.exec(pid)
  const single = range ? null : /^(\d{4})-(\d{2})-(\d{2})--/.exec(pid)
  if (!range && !single) return []
  const y = parseInt((range ?? single!)[1], 10)
  const mo = parseInt((range ?? single!)[2], 10)
  const d = parseInt((range ?? single!)[3], 10)
  const endDay = range ? parseInt(range[4], 10) : d
  if (endDay < d) return []
  const a = Date.UTC(y, mo - 1, d)
  const b = Date.UTC(y, mo - 1, endDay)
  const out: string[] = []
  for (let t = a; t <= b; t += 86400000) {
    const dt = new Date(t)
    out.push(`${dt.getUTCFullYear()}-${pad2(dt.getUTCMonth() + 1)}-${pad2(dt.getUTCDate())}`)
  }
  return out
}

/** 返回单日推荐值；日期范围取首日 */
export function shotDateHint(pid: string): string {
  const rng = idDateRange(pid)
  return rng[0] ?? ''
}

/**
 * 把一对 {start, end} 展开成 ['YYYY-MM-DD', ...] (包含首末两端).
 * 用 UTC 步进 (24h * 86400000 ms) 保证跨月跨年不走形,不依赖本地时区。
 */
function expandRange(start: string, end: string): string[] {
  if (start === end) return [start]
  const [sy, sm, sd] = start.split('-').map(Number)
  const [ey, em, ed] = end.split('-').map(Number)
  if (!sy || !sm || !sd || !ey || !em || !ed) return [start, end]
  const a = Date.UTC(sy, sm - 1, sd)
  const b = Date.UTC(ey, em - 1, ed)
  if (a > b) return [start, end]
  const out: string[] = []
  for (let t = a; t <= b; t += 86400000) {
    const dt = new Date(t)
    out.push(`${dt.getUTCFullYear()}-${pad2(dt.getUTCMonth() + 1)}-${pad2(dt.getUTCDate())}`)
  }
  return out
}

/**
 * 从一组 asset 路径推断所有可能的拍摄日期。
 *
 * 推断策略:
 *  1. 优先看父目录名 → parseFolderDateRange → 展开 start..end
 *  2. 父目录无法解析时 → 看文件名 → parseFilenameDate
 *  3. 都没有的 asset 跳过
 *
 * 返回按 YYYY-MM-DD 升序去重的字符串数组。
 */
export function assetsDateRange(assets: ReadonlyArray<{ path?: string | null } | null | undefined>): string[] {
  const set = new Set<string>()
  for (const a of assets) {
    if (!a?.path) continue
    const dir = parentDirName(a.path)
    if (dir) {
      const r = parseFolderDateRange(dir)
      if (r) {
        for (const d of expandRange(r.start, r.end)) set.add(d)
        continue
      }
    }
    const fn = parseFilenameDate(a.path)
    if (fn) set.add(fn)
  }
  return [...set].sort()
}
