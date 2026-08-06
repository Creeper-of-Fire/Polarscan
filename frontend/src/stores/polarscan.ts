// Polarscan store: 全局缓存 + 写操作的单一入口。
//
// 设计原则:
// - 所有对底层(server / _index.yaml)的修改都经由此 store 的 action, 不绕道.
// - summaries 等缓存由 action 内部维护一致性, 调用方无感.
// - refreshSummaries / refreshTagSuggestions 是 store 内部细节, 不 export,
//   调用方永远不应该手动调"刷新".
// - 视图层(views)只读 summaries / tagSuggestions, 改数据走 action.
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { polaroidsApi, tagsApi } from '@/api'
import type { Polaroid, PolaroidSummary } from '@/types'

export interface SavePolaroidResult {
  ok: boolean
  pid: string
  asset_count: number
  created: boolean
}

export interface AppendFilesResult {
  pid: string
  asset_count: number
}

export const usePolarscanStore = defineStore('polarscan', () => {
  // ===== state (公开读, 仅 action 内部写) =====
  const summaries = ref<PolaroidSummary[]>([])
  const summariesLoaded = ref(false)
  const tagSuggestions = ref<string[]>([])

  // ===== private: 缓存维护, 不 export =====
  // 失败安全: refreshSummaries 抛错时 caller (action) 不会更新 summaries,
  // 下次 listSummaries() 会基于 summariesLoaded=false 重新拉.
  async function refreshSummaries(): Promise<void> {
    const list = await polaroidsApi.list()
    summaries.value = list
    summariesLoaded.value = true
  }

  async function refreshTagSuggestions(): Promise<void> {
    const grouped = await tagsApi.all()
    tagSuggestions.value = ([] as string[]).concat(...Object.values(grouped))
  }

  // ===== actions (公开入口, 内部维护 cache) =====

  /** 拉全表 summaries (首次拉, 之后返回 cache). */
  async function listSummaries(): Promise<PolaroidSummary[]> {
    if (!summariesLoaded.value) {
      await refreshSummaries()
    }
    return summaries.value
  }

  /** 强制重拉全表 (用于 by-tag 切回 all 之类需要刷新 cache 的场景). */
  async function reloadSummaries(): Promise<PolaroidSummary[]> {
    await refreshSummaries()
    return summaries.value
  }

  /** 按 tag 过滤拉取, 覆盖 cache. 与 listSummaries 互斥 (最后一次调用为准). */
  async function listSummariesByTag(tag: string): Promise<PolaroidSummary[]> {
    const list = await polaroidsApi.byTag(tag)
    summaries.value = list
    summariesLoaded.value = true
    return list
  }

  /** 拉 tag 候选. 首次拉, 之后返回 cache. */
  async function listAllTags(): Promise<string[]> {
    if (tagSuggestions.value.length === 0) {
      await refreshTagSuggestions()
    }
    return tagSuggestions.value
  }

  /** 拉单个 polaroid 详情. 不进 cache (详情走 editor 自己的 ref). */
  async function loadPolaroid(pid: string): Promise<Polaroid> {
    return polaroidsApi.get(pid)
  }

  /** 幂等创建或替换 polaroid (PUT /polaroid/{pid}).
   *  成功后才 refreshSummaries — 失败时 cache 不动, 用户可重试. */
  async function savePolaroid(polaroid: Polaroid): Promise<SavePolaroidResult> {
    const result = await polaroidsApi.save(polaroid)
    await refreshSummaries()
    return result
  }

  /** 追加文件到现有 polaroid. 成功后才 refresh. */
  async function appendFiles(pid: string, paths: string[]): Promise<AppendFilesResult> {
    const result = await polaroidsApi.appendFiles(pid, paths)
    await refreshSummaries()
    return result
  }

  /** 删除 polaroid. 成功后才 refresh. */
  async function deletePolaroid(pid: string): Promise<void> {
    await polaroidsApi.delete(pid)
    await refreshSummaries()
  }

  return {
    // state
    summaries,
    summariesLoaded,
    tagSuggestions,
    // actions
    listSummaries,
    reloadSummaries,
    listSummariesByTag,
    listAllTags,
    loadPolaroid,
    savePolaroid,
    appendFiles,
    deletePolaroid,
  }
})