// Polarscan store: 全局缓存 + 写操作的单一入口。
//
// 设计原则:
// - 所有对底层(server / _index.yaml)的修改都经由此 store 的 action, 不绕道.
// - summaries 等缓存由 action 内部维护一致性, 调用方无感.
// - refreshSummaries / refreshTagSuggestions 是 store 内部细节, 不 export,
//   调用方永远不应该手动调"刷新".
// - 视图层(views)只读 summaries / tagSuggestions, 改数据走 action.
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { polaroidsApi, tagsApi, poolApi } from '@/api'
import {
  charOshiColorFromMeta,
  type CharOshiColor,
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

/** char tag 的完整展示字段 (供 CharTag / NAutoComplete 选项渲染).
 *  core 不解析 meta 内部结构, 这里做约定的字段读取 (canonical_name / aliases /
 *  color_name / color_rgb). 缺失字段视为 null, UI 降级渲染. */
export interface CharDisplay {
  tag: string
  key: string
  canonical_name: string | null
  aliases: string[]
  color_rgb: string | null
  color_name: string | null
}

/** 从 charMeta dict 里按 key 派生展示字段; 缺失视为 null. */
function charDisplayFromMeta(key: string, meta: Record<string, unknown> | undefined): CharDisplay {
  const m = meta
  const canonical = typeof m?.canonical_name === 'string' && m.canonical_name.trim()
    ? m.canonical_name.trim()
    : null
  const aliases = Array.isArray(m?.aliases)
    ? (m.aliases as unknown[]).filter((x): x is string => typeof x === 'string' && Boolean(x.trim()))
    : []
  const colorRgb = typeof m?.color_rgb === 'string' && /^#[0-9a-fA-F]{6}$/.test(m.color_rgb)
    ? m.color_rgb
    : null
  const colorName = typeof m?.color_name === 'string' && m.color_name.trim()
    ? m.color_name.trim()
    : null
  return { tag: `char:${key}`, key, canonical_name: canonical, aliases, color_rgb: colorRgb, color_name: colorName }
}

export const usePolarscanStore = defineStore('polarscan', () => {
  // ===== state (公开读, 仅 action 内部写) =====
  const summaries = ref<PolaroidSummary[]>([])
  const summariesLoaded = ref(false)
  const tagSuggestions = ref<string[]>([])
  // 分组字典 {prefix: [value, ...]}, ListView 按 prefix chip 切换时用
  const allTagGroups = ref<Record<string, string[]>>({})
  // char 池完整 meta (key → {canonical_name, aliases, color_name, color_rgb, ...}).
  // 这是 char tag 渲染 (CharTag / NAutoComplete 选项) 的元数据真值;
  // charColors 现在只是它的派生 (向后兼容, 不再单独拉一次).
  const charMeta = ref<Record<string, Record<string, unknown>>>({})
  const charMetaLoaded = ref(false)

  // charColors: 派生自 charMeta (只暴露 name+rgb); 旧 API 兼容, 不再单独缓存.
  const charColors = computed<Record<string, CharOshiColor>>(() => {
    const out: Record<string, CharOshiColor> = {}
    for (const [k, m] of Object.entries(charMeta.value)) {
      const c = charOshiColorFromMeta(m)
      if (c.name || c.rgb) out[k] = c
    }
    return out
  })
  // charColorsLoaded: 派生自 charMetaLoaded (computed 反向兼容旧 ref API)
  const charColorsLoaded = computed(() => charMetaLoaded.value)

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

  async function refreshCharMeta(): Promise<void> {
    const items = await poolApi.index('char')
    const out: Record<string, Record<string, unknown>> = {}
    for (const it of items) {
      out[it.key] = (it.meta ?? {}) as Record<string, unknown>
    }
    charMeta.value = out
    charMetaLoaded.value = true
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

  /** 拉 char 完整 meta (key → 完整 pool meta). 首次拉, 之后返回 cache. */
  async function loadCharMeta(): Promise<Record<string, Record<string, unknown>>> {
    if (!charMetaLoaded.value) {
      await refreshCharMeta()
    }
    return charMeta.value
  }

  /** 给定 char key 派生展示字段 (canonical_name / aliases / color_*);
   *  缺失字段视为 null, 不抛错. meta 未加载时返回 null 字段 (UI 降级). */
  function getCharDisplay(key: string): CharDisplay {
    return charDisplayFromMeta(key, charMeta.value[key])
  }

  /** 旧 API 兼容: 拉 char 应援色映射 (派生自 charMeta). */
  async function loadCharColors(): Promise<Record<string, CharOshiColor>> {
    await loadCharMeta()
    return charColors.value
  }

  /** 强制刷新 char meta (PoolEditView 保存后调用, 避免 BenchView 看到 stale). */
  async function refreshCharColorsForce(): Promise<void> {
    await refreshCharMeta()
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
    charMeta,
    charMetaLoaded,
    charColors,
    // actions
    listSummaries,
    reloadSummaries,
    listSummariesByTag,
    listAllTags,
    listAllTagGroups,
    loadCharMeta,
    getCharDisplay,
    loadCharColors,
    refreshCharColorsForce,
    loadPolaroid,
    savePolaroid,
    appendFiles,
    deletePolaroid,
  }
})