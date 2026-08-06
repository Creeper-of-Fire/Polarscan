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

  /** 候选前置过滤: char 模式只显示 char:* (或 legacy 无冒号); freeform 模式全显示. */
  const filteredSuggestions = computed(() => {
    if (opts.allowFreeform) return opts.suggestions()
    const prefix = opts.autoPrefix
    return opts.suggestions().filter(
      (s) => s.startsWith(`${prefix}:`) || !s.includes(':'),
    )
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
    suggestItems.value = filteredSuggestions.value
      .filter((s) => s.toLowerCase().includes(q))
      .filter((s) => !opts.getSelected().includes(s))
      .slice(0, 8)
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