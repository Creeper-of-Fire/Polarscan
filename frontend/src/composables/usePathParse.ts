// 路径/文件名解析 composable
// 接受文件夹名 "2026.07.25-26" / 文件名 "img20260725_..." 推断日期
const RANGE_RE = /^(\d{4})[\.\-](\d{1,2})[\.\-](\d{1,2})(?:[-](\d{1,2})(?:[\.\-](\d{1,2}))?)?$/
const FN_DATE_RE = /^img(\d{4})(\d{2})(\d{2})_/i

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

function toIso(year: string, month: number, day: number): string | null {
  const y = year
  const m = pad2(month)
  const d = pad2(day)
  const dt = new Date(`${y}-${m}-${d}T00:00:00`)
  if (isNaN(dt.getTime())) return null
  return `${y}-${m}-${d}`
}

export function parseFolderDateRange(name: string): { start: string; end: string } | null {
  const m = RANGE_RE.exec(name)
  if (!m) return null
  const year = m[1]
  const startMonth = parseInt(m[2], 10)
  const startDay = parseInt(m[3], 10)
  const startIso = toIso(year, startMonth, startDay)
  if (!startIso) return null
  let endIso: string = startIso
  if (m[4]) {
    const endDay = parseInt(m[4], 10)
    const e = toIso(year, startMonth, endDay)
    if (!e) return null
    endIso = e
  } else if (m[5]) {
    // 跨月范围不解析
    return null
  }
  return { start: startIso, end: endIso }
}

export function parseFilenameDate(name: string): string | null {
  const m = FN_DATE_RE.exec(name)
  if (!m) return null
  return `${m[1]}-${m[2]}-${m[3]}`
}

export function parentDirName(path: string | null | undefined): string | null {
  if (!path) return null
  const parts = String(path).split(/[\\/]/)
  if (parts.length < 2) return null
  return parts[parts.length - 2]
}

/**
 * 从 polaroid id 解析日期范围
 * '2026-07-25-26--img...' → ['2026-07-25', '2026-07-26']
 * '2026-07-25--img...'    → ['2026-07-25']
 * 'dandan_xxx'            → []
 */
export function idDateRange(pid: string): string[] {
  if (!pid) return []
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:-(\d{2}))?--/.exec(pid)
  if (!m) return []
  const y = parseInt(m[1], 10)
  const mo = parseInt(m[2], 10) - 1
  const d = parseInt(m[3], 10)
  const endDay = m[4] ? parseInt(m[4], 10) : d
  if (endDay < d) return []
  const out: string[] = []
  const start = new Date(y, mo, d)
  if (isNaN(start.getTime())) return []
  for (let i = 0; i <= endDay - d; i++) {
    const cur = new Date(start)
    cur.setDate(start.getDate() + i)
    out.push(cur.toISOString().slice(0, 10))
  }
  return out
}

/** 返回单日推荐值；日期范围取首日 */
export function shotDateHint(pid: string): string {
  const rng = idDateRange(pid)
  return rng[0] ?? ''
}