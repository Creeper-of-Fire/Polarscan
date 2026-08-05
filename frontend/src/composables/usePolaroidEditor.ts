// usePolaroidEditor: 拍立得编辑 session 的适配层
//
// 职责:
// - 持有 polaroid 状态 (单一来源)
// - 提供 actions: load / saveMeta / saveAssets / appendFiles / create / suggestId
// - 提供 loading / saving / error 状态
//
// 状态传递:
// - pid 是 writable ref,page 在 onMounted / onBeforeRouteUpdate 里显式赋值
// - polaroid 是 ref,page 直接 v-model 编辑
// - 不依赖 watcher (watcher 容易藏 stale closure / 隐性同步错位)
//
// 用法:
//   const editor = usePolaroidEditor()
//   onMounted(() => editor.load(props.pid))
//   onBeforeRouteUpdate((to) => editor.load(to.params.pid as string))
//   polaroid.value.tags = [...]   // 直接改
//   await editor.appendFiles(paths)

import { ref, computed } from 'vue'
import { polaroidsApi, newApi } from '@/api'
import type { Asset, Polaroid } from '@/types'

export interface PolaroidEditorOptions {
  /** 初始 pid (可选) */
  initialPid?: string | null
}

export function usePolaroidEditor(options: PolaroidEditorOptions = {}) {
  const { initialPid = null } = options

  // 当前编辑的 polaroid id (writable;page 在 mount/route change 时设)
  const pid = ref<string | null>(initialPid)
  // polaroid 状态 (单一来源,page 直接 v-model)
  const polaroid = ref<Polaroid>(emptyPolaroid())
  // 状态标志
  const isLoading = ref(false)
  const isSaving = ref(false)
  const error = ref<string | null>(null)

  const isNew = computed(() => !pid.value || pid.value === '')

  /** 加载 polaroid。pid 不传时用当前 pid.value */
  async function load(targetPid?: string | null): Promise<void> {
    const p = targetPid !== undefined && targetPid !== null ? targetPid : pid.value
    if (!p) return
    pid.value = p
    isLoading.value = true
    error.value = null
    try {
      const data = await polaroidsApi.get(p)
      // 仅当 pid 仍然是请求时的那个才应用,避免快速切换时旧请求覆盖新数据
      if (pid.value === p) {
        polaroid.value = data
      }
    } catch (e) {
      if (pid.value === p) {
        error.value = e instanceof Error ? e.message : String(e)
      }
    } finally {
      if (pid.value === p) {
        isLoading.value = false
      }
    }
  }

  /** 增量保存 tags / shot_date / notes (autosave 风格) */
  async function saveMeta(payload: {
    tags?: string[]
    shot_date?: string | null
    notes?: string
  }): Promise<void> {
    const p = pid.value
    if (!p) throw new Error('saveMeta 需要已存在的拍立得')
    isSaving.value = true
    error.value = null
    try {
      await polaroidsApi.autosave(p, {
        tags: payload.tags,
        shot_date: payload.shot_date ?? undefined,
        notes: payload.notes,
      })
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      isSaving.value = false
    }
  }

  /** 原子替换 polaroid 的 assets 列表 */
  async function saveAssets(assets: Asset[]): Promise<void> {
    const p = pid.value
    if (!p) throw new Error('saveAssets 需要已存在的拍立得')
    isSaving.value = true
    error.value = null
    try {
      await polaroidsApi.saveAssets(p, assets)
      polaroid.value.assets = assets
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      isSaving.value = false
    }
  }

  /** 追加文件到现有 polaroid,完成后 refetch */
  async function appendFiles(paths: string[]): Promise<void> {
    const p = pid.value
    if (!p) throw new Error('appendFiles 需要已存在的拍立得')
    isSaving.value = true
    error.value = null
    try {
      await polaroidsApi.appendFiles(p, paths)
      // refetch 拿最新 assets(含 hash 等)
      const data = await polaroidsApi.get(p)
      if (pid.value === p) {
        polaroid.value = data
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      if (pid.value === p) {
        isSaving.value = false
      }
    }
  }

  /** 新建 polaroid (NewView 专用) */
  async function create(payload: {
    pid: string
    shot_date?: string
    primary_char?: string
    asset_paths: string[]
    tags?: string[]
    notes?: string
  }): Promise<string> {
    isSaving.value = true
    error.value = null
    try {
      const r = await newApi.create(payload)
      if (!r.ok || !r.pid) {
        error.value = r.error || '创建失败'
        throw new Error(error.value)
      }
      return r.pid
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      isSaving.value = false
    }
  }

  /** 派生一个建议 pid (NewView 用) */
  async function suggestId(
    shot_date: string | null,
    primary_char: string | null,
  ): Promise<string> {
    const r = await newApi.suggestId(shot_date || undefined, primary_char || undefined)
    return r.pid
  }

  return {
    pid,
    polaroid,
    isNew,
    isLoading,
    isSaving,
    error,
    load,
    saveMeta,
    saveAssets,
    appendFiles,
    create,
    suggestId,
  }
}

function emptyPolaroid(): Polaroid {
  return {
    id: '',
    shot_date: null,
    tags: [],
    notes: '',
    assets: [],
  }
}