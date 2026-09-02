// 标签流 composable: 仅负责 input + 候选补全 + 标签字符串推导。
//
// 设计原则 (2026-08 重构):
// - **单源头**: tag 列表归 caller 所有 (例如 PolaroidTagsEditor.props.modelValue);
//   composable 不再持有自己的 modelValue 副本, 因此不存在"两个 stream 各自去重"
//   导致的跨区重复。dedup 走 getSelected() 统一在源头判断。
// - **computeTag**: 给定 raw 输入返回最终写入的完整 tag (含前缀); 空/重复返回 null.
//   caller 自己负责把结果追加到源头并 emit.
// - 候选 popup UI 由 caller 用 NAutoComplete 包装, 本 composable 只暴露 suggestItems.
//
// 用法:
//   const cs = useChipStream({
//     autoPrefix: 'char',
//     allowFreeform: false,
//     suggestions: () => props.suggestions,
//     getSelected: () => props.modelValue,
//   })
//   const tag = cs.computeTag('my_push')  // → 'char:my_push' | null
//   cs.clearQuery()                       // 添加成功后清空输入 + 候选
//   cs.onInput()                          // 输入时重算 suggestItems

import { ref, computed } from 'vue'

export interface ChipStreamOptions {
  /** 自动补全前缀 (输入 'my_push' 时补为 'char:my_push') */
  autoPrefix?: string
  /** 是否允许自由格式 (无前缀). 设为 true 时: 输入必须带冒号, 否则返回 null. */
  allowFreeform?: boolean
  /** 候选集 (带前缀的 tag 全集) */
  suggestions: () => string[]
  /** 当前已选 chip 列表 (单源头调用方传入). 用于 add dedup + onInput 过滤. */
  getSelected: () => string[]
}

export function useChipStream(opts: ChipStreamOptions) {
  const query = ref('')
  const suggestItems = ref<string[]>([])

  /** 候选前置过滤: char 模式只显示 char:* (严格,不再混入 legacy 无冒号 tag,
   * 也不混入其他 prefix 的 tag); freeform 模式全显示. */
  const filteredSuggestions = computed(() => {
    if (opts.allowFreeform) return opts.suggestions()
    const prefix = opts.autoPrefix
    return opts.suggestions().filter((s) => s.startsWith(`${prefix}:`))
  })

  /** 给定 raw 输入, 返回应当写入的完整 tag (含前缀); 空输入或重复返回 null. */
  function computeTag(raw: string): string | null {
    const trimmed = (raw || '').trim()
    if (!trimmed) return null

    let tag = trimmed
    if (opts.autoPrefix && !tag.includes(':')) {
      // char 模式: 无冒号自动补前缀
      tag = `${opts.autoPrefix}:${tag}`
    } else if (opts.allowFreeform && !tag.includes(':')) {
      // freeform 模式: 拒绝无前缀 (约定 tag 必须带 prefix)
      return null
    }
    if (opts.getSelected().includes(tag)) return null
    return tag
  }

  function onInput(): void {
    const q = query.value.trim().toLowerCase()
    if (!q) {
      suggestItems.value = []
      return
    }
    // 输入含 ':' (如 'event:' / 'shot:p') → 只取同 prefix 的候选 (prefix-aware).
    // 输入无 ':' (如 'sh' / 'abc')  → 走全集 includes 匹配.
    const colonIdx = q.indexOf(':')
    const matches = (colonIdx > 0
      ? filteredSuggestions.value.filter((s) => s.toLowerCase().startsWith(`${q.slice(0, colonIdx)}:`))
      : filteredSuggestions.value
    )
      .filter((s) => s.toLowerCase().includes(q))
      .filter((s) => !opts.getSelected().includes(s))

    // 无 prefix 输入: round-robin by prefix, 防止 char 等高频 prefix 堆叠
    // 把 shot / event 等挤掉 (e.g. 输入 'sh' 时仍能看到 shot:xxx / event:xxx).
    // 含 prefix 输入已限定同 prefix, 直接 slice.
    suggestItems.value = colonIdx > 0
      ? matches.slice(0, 8)
      : roundRobinByPrefix(matches, 8)
  }

  /** 按 prefix 轮转取候选项, 每个 prefix 取一项再循环, 直到填满 limit.
   *  输入假定已按 prefix group 顺序排列 (后端 /api/all-tags flatten 后保持此序);
   *  这里不重新排序, 只在原序基础上交错抽样. */
  function roundRobinByPrefix(items: string[], limit: number): string[] {
    const groups = new Map<string, string[]>()
    for (const it of items) {
      const c = it.indexOf(':')
      const p = c > 0 ? it.slice(0, c) : ''
      let g = groups.get(p)
      if (!g) {
        g = []
        groups.set(p, g)
      }
      g.push(it)
    }
    const out: string[] = []
    while (out.length < limit) {
      let added = false
      for (const g of groups.values()) {
        if (g.length > 0) {
          out.push(g.shift() as string)
          added = true
          if (out.length >= limit) break
        }
      }
      if (!added) break
    }
    return out
  }

  function clearQuery(): void {
    query.value = ''
    suggestItems.value = []
  }

  return {
    query,
    suggestItems,
    filteredSuggestions,
    computeTag,
    onInput,
    clearQuery,
  }
}