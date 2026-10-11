// tagDisplay: 任意 prefix tag 的展示字段派生 (纯函数)。
//
// 这是"tag 怎么给人看"的唯一规则来源, 全站所有展示面都必须走这里:
//   CharTag / PolaroidTagsEditor 的标签 chip / 浏览页组头与筛选 chip / char 候选选项
// 与 prefix 无关 —— char / event / theme / collection / ... 走同一条路径。
//
// 纯函数 (无副作用, 不 import 运行时依赖), 与 store / naive-ui / router 无感知。
// 放在 lib/ 是因为它是可单测的纯逻辑, 与 lib/grouping.ts、lib/charSearch.ts 同类。

/** tag 的展示字段。 */
export interface TagDisplay {
  /** 完整 tag, 如 'char:小薰'. 就是 polaroid.tags 里存的那个字符串。 */
  tag: string
  /** 前缀, 如 'char'. 无冒号的 legacy tag 为 ''。 */
  prefix: string
  /** 裸标识符, 如 '小薰'. **只用于路由 / 发给后端, 不作展示。**
   *  canonical_name 可以与它完全不同 ('绿岛条雪' → '雪雪Yuki'), 所以凡是
   *  "给人看的名字"都必须走 display_name。 */
  key: string
  /** 展示名 = canonical_name || key. canonical 缺失时回退 key,
   *  保证未注册 tag (tag-pool 的 undefined 子集) 也有名字可显示, 不出现空白。 */
  display_name: string
  canonical_name: string | null
  aliases: string[]
  color_rgb: string | null
  color_name: string | null
}

/** 合法应援色: 仅 #RRGGBB (spec tag-pool §5: 其它形式服务端存空串, 前端再兜一层)。 */
const COLOR_RGB_RE = /^#[0-9a-fA-F]{6}$/

function readTrimmedString(v: unknown): string | null {
  return typeof v === 'string' && v.trim() ? v.trim() : null
}

/** 从池 meta 派生展示字段。
 *
 *  meta 缺失或字段类型异常时**不抛错**, 一律降级: canonical/color 变 null,
 *  aliases 变 [], display_name 回退 key。UI 永远拿得到可显示的字符串。 */
export function tagDisplayFrom(tag: string, meta: Record<string, unknown> | undefined | null): TagDisplay {
  // key 理论上可以含冒号 (PoolIndexView 里有对应注释), 所以只切第一个冒号。
  const c = tag.indexOf(':')
  const prefix = c > 0 ? tag.slice(0, c) : ''
  const key = c > 0 ? tag.slice(c + 1) : tag

  const canonical = readTrimmedString(meta?.canonical_name)
  const aliases = Array.isArray(meta?.aliases)
    ? (meta.aliases as unknown[]).filter((x): x is string => typeof x === 'string' && Boolean(x.trim()))
    : []
  const colorRgbRaw = meta?.color_rgb
  const colorRgb = typeof colorRgbRaw === 'string' && COLOR_RGB_RE.test(colorRgbRaw) ? colorRgbRaw : null

  return {
    tag,
    prefix,
    key,
    display_name: canonical ?? key,
    canonical_name: canonical,
    aliases,
    color_rgb: colorRgb,
    color_name: readTrimmedString(meta?.color_name),
  }
}