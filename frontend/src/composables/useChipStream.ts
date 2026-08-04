// 标签流 composable: 管理一组 chip（添加 / 删除 / 自动补全 / 快捷）
// 移植旧 bench.html 的 setupStream 行为
// 用法:
//   const cs = useChipStream({ autoPrefix: 'char', allowFreeform: false, suggestions })
//   cs.add('my_push')           // 添加
//   cs.remove(tag)              // 删除
//   v-model="cs.modelValue"     // 双向绑定 chip 列表

import { ref, computed, watch } from 'vue'

export interface ChipStreamOptions {
  /** 自动补全前缀（输入 "my_push" 时补为 "char:my_push"） */
  autoPrefix?: string
  /** 是否允许自由格式（无前缀） */
  allowFreeform?: boolean
  /** 候选集（带前缀的 tag 全集，ref 或 getter） */
  suggestions: () => string[]
}

export function useChipStream(opts: ChipStreamOptions) {
  const modelValue = ref<string[]>([])

  const query = ref('')
  const showSuggest = ref(false)
  const suggestItems = ref<string[]>([])

  const filteredSuggestions = computed(() => {
    const prefix = opts.autoPrefix
    if (opts.allowFreeform) return opts.suggestions()
    return opts.suggestions().filter((s) => s.startsWith(`${prefix}:`) || !s.includes(':'))
  })

  function addChip(raw: string): boolean {
    const trimmed = (raw || '').trim()
    if (!trimmed) return false

    let tag = trimmed
    if (opts.autoPrefix && !tag.includes(':')) {
      tag = `${opts.autoPrefix}:${tag}`
    }
    if (modelValue.value.includes(tag)) return false

    modelValue.value = [...modelValue.value, tag]
    query.value = ''
    showSuggest.value = false
    return true
  }

  function removeChip(tag: string): void {
    modelValue.value = modelValue.value.filter((t) => t !== tag)
  }

  function onInput(): void {
    const q = query.value.trim().toLowerCase()
    if (!q) {
      showSuggest.value = false
      suggestItems.value = []
      return
    }
    const suggests = filteredSuggestions.value
      .filter((s) => s.toLowerCase().includes(q))
      .filter((s) => !modelValue.value.includes(s))
      .slice(0, 8)
    suggestItems.value = suggests
    showSuggest.value = suggests.length > 0
  }

  function pickSuggest(tag: string): void {
    addChip(tag)
  }

  /** 外部同步：把指定数组作为当前 chip 流 */
  function setTags(tags: string[]): void {
    modelValue.value = [...tags]
  }

  return {
    modelValue,
    query,
    showSuggest,
    suggestItems,
    filteredSuggestions,
    addChip,
    removeChip,
    onInput,
    pickSuggest,
    setTags,
  }
}