// 兼容层：把文件夹名解析成「候选拍摄日」。
//
// ── 这是什么 ────────────────────────────────────────────────────────────
// 它**不是**项目规则，是对个人命名习惯的适配器。主业务只认「候选日数组」，
// 根本不知道 YYYY.MM.DD 这种东西存在。以后要大量改命名习惯，改这一个文件即可，
// 整块替换也行——其他代码一行都不用动。
//
// 候选日只是**推荐值**：分析得出的可能的合理值。一张拍立得只有一个确定的拍摄日期，
// 所以这里永远不做选择，由用户点按钮填入。
//
// ── 已确认的规则 ────────────────────────────────────────────────────────
//   2026.07.25                 单日
//   2026.07.25-26              同月连续，逐日包含中间
//   2026.02.28-03.01           异月连续（同年）
//   2026.12.28-2027.01.03      跨年连续（年份必须显式写）
//   2026.08.14&16&18           「和」：只列出的这几天，不补中间
//
// ── 明确不做 ────────────────────────────────────────────────────────────
//   - 不猜年份：`2026.12.28-01.03` 拒绝。跨年要写 `2026.12.28-2027.01.03`。
//   - 不看文件名：文件名里的日期是**扫描日**，不是拍摄日（拍完过一阵才扫），
//     拿它当拍摄日是在推另一个量。没有第二条兜底。
//   - 不替用户选：没有「取首日」「取末日」之类的规则。
//   - 不推断拍摄日：一个文件夹里放了哪些天，不等于这批拍立得是哪天拍的。

const pad2 = (n: number): string => String(n).padStart(2, '0')

/** YYYY[.|-]MM[.|-]DD — 日期内部允许 `.` 或 `-` 分隔 */
const YMD = String.raw`(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})`

/** 校验并规范化成一个 ISO 日；日期不存在（如 2026-13-45）返回 null。 */
function toIso(year: string, month: number, day: number): string | null {
  const y = Number(year)
  const ms = Date.UTC(y, month - 1, day)
  if (Number.isNaN(ms)) return null
  const t = new Date(ms)
  if (t.getUTCFullYear() !== y || t.getUTCMonth() !== month - 1 || t.getUTCDate() !== day) return null
  return `${year.padStart(4, '0')}-${pad2(month)}-${pad2(day)}`
}

/** 从 from 逐日到 to（含两端）。end < start 返回空数组。 */
function eachDay(from: string, to: string): string[] {
  const [y1, m1, d1] = from.split('-').map(Number)
  const [y2, m2, d2] = to.split('-').map(Number)
  let t = Date.UTC(y1, m1 - 1, d1)
  const end = Date.UTC(y2, m2 - 1, d2)
  const out: string[] = []
  while (t <= end) {
    const d = new Date(t)
    out.push(`${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`)
    t += 86400000
  }
  return out.length > 400 ? [] : out // 防御：错乱的目录名不该产出几百个按钮
}

/**
 * 解析规则表。**新增规则往后加一条即可**，前面的先匹配上就不再看后面。
 * 每条 = [正则, 从捕获组构造候选日]。
 */
const RULES: ReadonlyArray<[RegExp, (m: RegExpExecArray) => string[] | null]> = [
  // 「和」：YYYY.MM.DD & D [& D ...] —— 离散列出，不补中间。放最前，
  // 因为后面的连续区间写法要求 `-` 开头，理论上不会撞；放前面是为了让
  // 「和」这个语义在任何扩展之前都被明确识别。
  [new RegExp(String.raw`^${YMD}((?:&\d{1,2})+)$`), (m) => {
    const month = Number(m[2])
    const out: string[] = []
    // 基日本身也是候选：`14&16` = 14 号和 16 号。
    const base = toIso(m[1], month, Number(m[3]))
    if (!base) return null
    out.push(base)
    // 注意:不能 split('&') 再 slice —— '&16'.split('&') 得到 ['', '16']，
    // 空串 Number('') = 0 会被判成非法日期，整条规则就废了。
    for (const d of m[4].matchAll(/&(\d{1,2})/g)) {
      const day = toIso(m[1], month, Number(d[1]))
      if (!day) return null
      out.push(day)
    }
    return out
  }],

  // 跨年连续：YYYY.MM.DD-YYYY.MM.DD（年份必须显式，不猜）
  [new RegExp(String.raw`^${YMD}-(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})$`), (m) => {
    const from = toIso(m[1], Number(m[2]), Number(m[3]))
    const to = toIso(m[4], Number(m[5]), Number(m[6]))
    if (!from || !to) return null
    return eachDay(from, to)
  }],

  // 异月连续：YYYY.MM.DD-MM.DD（同年）。月变小 = 跨年 → 那必须显式写年份，
  // 所以这里直接拒绝，不替用户补 +1。
  [new RegExp(String.raw`^${YMD}-(\d{1,2})[.\-](\d{1,2})$`), (m) => {
    const startMonth = Number(m[2])
    const endMonth = Number(m[4])
    if (endMonth < startMonth) return null // 形如 2026.12.28-01.03：拒绝
    const from = toIso(m[1], startMonth, Number(m[3]))
    const to = toIso(m[1], endMonth, Number(m[5]))
    if (!from || !to) return null
    return eachDay(from, to)
  }],

  // 同月连续：YYYY.MM.DD-DD（年 + 月继承开头）
  [new RegExp(String.raw`^${YMD}-(\d{1,2})$`), (m) => {
    const from = toIso(m[1], Number(m[2]), Number(m[3]))
    const to = toIso(m[1], Number(m[2]), Number(m[4]))
    if (!from || !to) return null
    return eachDay(from, to)
  }],

  // 单日：YYYY.MM.DD
  [new RegExp(String.raw`^${YMD}$`), (m) => {
    const d = toIso(m[1], Number(m[2]), Number(m[3]))
    return d ? [d] : null
  }],
]

/**
 * 把一个文件夹名解析成候选拍摄日。
 *
 * @param name 文件夹名（只取名字本身，不含路径）
 * @returns 升序候选日数组；这个命名不认识、或解析失败，返回 null
 */
export function parseFolderDays(name: string | null | undefined): string[] | null {
  if (!name) return null
  const s = String(name).trim()
  if (!s) return null
  for (const [re, build] of RULES) {
    const m = re.exec(s)
    if (!m) continue
    const days = build(m)
    if (!days || days.length === 0) return null
    return [...new Set(days)].sort()
  }
  return null
}