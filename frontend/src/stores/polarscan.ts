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
import { polaroidsApi, tagsApi, poolApi } from '@/api'
import { tagDisplayFrom, type TagDisplay } from '@/lib/tagDisplay'
import {
  type Polaroid,
  type PolaroidSummary,
} from '@/types'

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

/** tag 的展示字段派生规则本体在 lib/tagDisplay.ts —— store 只负责取数据真值,
 *  不重复实现 "canonical || key" 的规则 (两处实现必然漂移)。
 *  类型在这里再导出一次, 是因为 getTagDisplay / displayNameOf 的返回类型就在
 *  这个 store 的公开面上。 */
export type { TagDisplay }

export const usePolarscanStore = defineStore('polarscan', () => {
  // ===== state (公开读, 仅 action 内部写) =====
  const summaries = ref<PolaroidSummary[]>([])
  const summariesLoaded = ref(false)
  const tagSuggestions = ref<string[]>([])
  // 分组字典 {prefix: [value, ...]}, ListView 按 prefix chip 切换时用
  const allTagGroups = ref<Record<string, string[]>>({})
  // 全部 prefix 的池元数据, **以完整 tag 为键** ('char:小薰' -> meta)。
  // 用扁平 tag 键而不是 {prefix: {key: meta}}, 是为了让 display 层一次查表就能
  // 拿到任意 prefix 的展示字段, 调用方不必先剥前缀再决定去哪个桶。
  // 这是所有 tag 渲染 (CharTag / 标签 chip / 浏览页组头) 的元数据真值。
  const tagMeta = ref<Record<string, Record<string, unknown>>>({})
  const tagMetaLoaded = ref(false)

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
    // 后端 all_tags_with_prefix 现在返回带 prefix 的完整 tag (例如 'char:Hoshiro'),
    // 这里 flatten 即得到 useChipStream 期望的形态. allTagGroups 保留 dict 形态给 ListView.
    tagSuggestions.value = ([] as string[]).concat(...Object.values(grouped))
    allTagGroups.value = grouped
  }

  /** 拉全部 prefix 的池元数据。
   *
   *  prefix 集合取自 allTagGroups (/api/all-tags) —— 那已经是"哪些 prefix 被拍立得
   *  用过"的现成真值, 前端不再维护第二份 prefix 名单。没有对应池桶的 prefix
   *  (例如只被用过、从未注册的) 拉回来是空数组, 自然不产生条目。
   *
   *  registered-but-never-used 的桶不在这里: 它们只在池页面出现, 而池页面
   *  自己按 prefix 拉 (PoolIndexView → poolApi.index)。 */
  async function refreshTagMeta(): Promise<void> {
    const groups = await listAllTagGroups()
    const prefixes = Object.keys(groups)
    const buckets = await Promise.all(prefixes.map((p) => poolApi.index(p)))
    const out: Record<string, Record<string, unknown>> = {}
    prefixes.forEach((p, i) => {
      for (const it of buckets[i] ?? []) {
        out[`${p}:${it.key}`] = (it.meta ?? {}) as Record<string, unknown>
      }
    })
    tagMeta.value = out
    tagMetaLoaded.value = true
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

  /** 拉 tag 候选 (扁平). 首次拉, 之后返回 cache. */
  async function listAllTags(): Promise<string[]> {
    if (tagSuggestions.value.length === 0) {
      await refreshTagSuggestions()
    }
    return tagSuggestions.value
  }

  /** 拉 tag 按 prefix 分组 (用于 ListView chip 切换). 首次拉, 之后返回 cache. */
  async function listAllTagGroups(): Promise<Record<string, string[]>> {
    if (Object.keys(allTagGroups.value).length === 0) {
      await refreshTagSuggestions()
    }
    return allTagGroups.value
  }

  /** 拉全部 prefix 的 tag 池元数据 (完整 tag → pool meta). 首次拉, 之后返回 cache. */
  async function loadTagMeta(): Promise<Record<string, Record<string, unknown>>> {
    if (!tagMetaLoaded.value) {
      await refreshTagMeta()
    }
    return tagMeta.value
  }

  /** 给定完整 tag 派生展示字段; 缺失字段视为 null, display_name 回退 key.
   *  meta 未加载时同样返回 display_name = key (UI 降级, 不会显示空白)。 */
  function getTagDisplay(tag: string): TagDisplay {
    return tagDisplayFrom(tag, tagMeta.value[tag])
  }

  /** 只要展示名 (canonical || key) —— 模板里最常见的用法, 免得先取整个对象。 */
  function displayNameOf(tag: string): string {
    return tagDisplayFrom(tag, tagMeta.value[tag]).display_name
  }

  /** 强制刷新 tag 池元数据 (PoolEditView 保存后调用, 避免别处看到 stale). */
  async function refreshTagMetaForce(): Promise<void> {
    await refreshTagMeta()
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
    allTagGroups,
    tagMeta,
    tagMetaLoaded,
    // actions
    listSummaries,
    reloadSummaries,
    listSummariesByTag,
    listAllTags,
    listAllTagGroups,
    loadTagMeta,
    getTagDisplay,
    displayNameOf,
    refreshTagMetaForce,
    loadPolaroid,
    savePolaroid,
    appendFiles,
    deletePolaroid,
  }
})