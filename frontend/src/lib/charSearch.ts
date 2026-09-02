// charSearch: char tag 的搜索加权.
//
// 候选字段:
//   - key              (去掉前缀的标识, e.g. 'hime')
//   - canonical_name   (规范名, e.g. '姬')
//   - aliases          (别名数组, e.g. ['hime', '小姬'])
//
// 加权原则 (用户视角: "匹配越多越相关"):
// - 每字段独立打基础分 (key > canonical > alias, 完全 > 前缀 > 包含).
// - 多字段同时命中 → 累加 + 加成 (multi-hit bonus), 让"key + canonical + alias
//   三处都命中"的候选明显排在"只 key 命中"前面.
// - 排序: score DESC, 同分按 key 字母升序 (输出稳定, 便于 e2e / snapshot).
//
// 大小写不敏感 (toLowerCase). 空查询由 caller 提前判空.
//
// 纯函数 (无副作用), 与 store / props 解耦 — 便于单测.

import type { CharDisplay } from '@/stores/polarscan'

export type CharMatchField = 'key' | 'canonical' | 'alias'

export interface CharMatch {
  score: number
  /** 主字段 (最高单字段分), 用于 highlight 优先级 / debug. */
  field: CharMatchField | null
  /** 多字段命中计数 (用于 caller 决定是否画 "matches N" 之类). */
  hitCount: number
}

/** 多字段命中时的额外加成: 每个额外字段 +20. 鼓励"多角度都匹配". */
const MULTI_HIT_BONUS = 20

function keyScore(keyL: string, qL: string): number {
  if (keyL === qL) return 100 // 完全匹配 (最高)
  if (keyL.startsWith(qL)) return 80
  if (keyL.includes(qL)) return 50
  return 0
}

function canonicalScore(canonical: string | null, qL: string): number {
  if (!canonical) return 0
  const c = canonical.toLowerCase()
  if (c === qL) return 90
  if (c.startsWith(qL)) return 70
  if (c.includes(qL)) return 40
  return 0
}

function aliasBestScore(aliases: string[], qL: string): number {
  let best = 0
  for (const a of aliases) {
    const al = a.toLowerCase()
    let s = 0
    if (al === qL) s = 85
    else if (al.startsWith(qL)) s = 60
    else if (al.includes(qL)) s = 30
    if (s > best) best = s
  }
  return best
}

export function scoreCharMatch(q: string, d: CharDisplay): CharMatch {
  const qL = q.toLowerCase()
  if (!qL) return { score: 0, field: null, hitCount: 0 }

  const keyL = d.key.toLowerCase()
  const ks = keyScore(keyL, qL)
  const cs = canonicalScore(d.canonical_name, qL)
  const as = aliasBestScore(d.aliases, qL)

  // 完全匹配某字段 → 早返回 (不被多字段加成稀释)
  if (ks === 100) return { score: 100, field: 'key', hitCount: 1 }
  if (cs === 90) return { score: 90, field: 'canonical', hitCount: 1 }
  if (as === 85) return { score: 85, field: 'alias', hitCount: 1 }

  // 多字段命中计数 (用于加成)
  const hits = (ks > 0 ? 1 : 0) + (cs > 0 ? 1 : 0) + (as > 0 ? 1 : 0)
  if (hits === 0) return { score: 0, field: null, hitCount: 0 }

  const baseSum = ks + cs + as
  const bonus = (hits - 1) * MULTI_HIT_BONUS

  // 主字段 (highlight 优先级): key > canonical > alias
  let field: CharMatchField | null = null
  if (ks > 0) field = 'key'
  else if (cs > 0) field = 'canonical'
  else field = 'alias'

  return { score: baseSum + bonus, field, hitCount: hits }
}
