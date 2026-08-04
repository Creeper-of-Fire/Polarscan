// Polarscan 全局 store: 全表 polaroids 缓存、当前选中、标签候选
// 替代旧 bench.html → list.html 的 localStorage 跨页通信
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { polaroidsApi } from '@/api'
import type { Polaroid, PolaroidSummary, TagSuggestion } from '@/types'

export const usePolarscanStore = defineStore('polarscan', () => {
  // 全表 summary 缓存（list 页填，bench 页用）
  const summaries = ref<PolaroidSummary[]>([])
  const summariesLoaded = ref(false)

  // 当前选中的 polaroid 详情
  const current = ref<Polaroid | null>(null)
  const currentId = ref<string | null>(null)

  // 全部已用标签（bench 页 chip 流候选）
  const tagSuggestions = ref<TagSuggestion[]>([])

  const currentIdx = computed(() => {
    if (!currentId.value) return -1
    return summaries.value.findIndex((s) => s.id === currentId.value)
  })

  const prevId = computed(() => {
    const i = currentIdx.value
    return i > 0 ? summaries.value[i - 1].id : null
  })

  const nextId = computed(() => {
    const i = currentIdx.value
    return i >= 0 && i < summaries.value.length - 1 ? summaries.value[i + 1].id : null
  })

  const nextUntaggedId = computed(() => {
    // 简单实现：返回第一张 tag 为空的 polaroid
    const i = summaries.value.findIndex((s) => s.id === currentId.value)
    for (let j = i + 1; j < summaries.value.length; j++) {
      const summary = summaries.value[j]
      // 注：summary 不含 tags，需要全表详情判断；这里只做基本 ID 传递
      // 实际跳转逻辑由 bench 页 fetch /goto/untagged 完成
      return summary.id
    }
    return null
  })

  async function ensureSummaries(): Promise<void> {
    if (summariesLoaded.value) return
    await refreshSummaries()
  }

  async function refreshSummaries(): Promise<void> {
    summaries.value = await polaroidsApi.list()
    summariesLoaded.value = true
  }

  async function loadPolaroid(pid: string): Promise<Polaroid> {
    const p = await polaroidsApi.get(pid)
    current.value = p
    currentId.value = pid
    // 同步更新全表中的 shot_date
    const sum = summaries.value.find((s) => s.id === pid)
    if (sum) sum.shot_date = p.shot_date ?? null
    return p
  }

  function patchCurrent(mutator: (p: Polaroid) => void): void {
    if (!current.value) return
    mutator(current.value)
  }

  return {
    summaries,
    summariesLoaded,
    current,
    currentId,
    tagSuggestions,
    currentIdx,
    prevId,
    nextId,
    nextUntaggedId,
    ensureSummaries,
    refreshSummaries,
    loadPolaroid,
    patchCurrent,
  }
})