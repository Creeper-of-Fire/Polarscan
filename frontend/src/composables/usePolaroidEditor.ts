// usePolaroidEditor: 拍立得编辑 session 的适配层
//
// 职责:
// - 持有 polaroid 状态 (单一来源) + page-local UI session 状态
// - 提供 actions: load / save / appendFiles / suggestId
// - 所有变更走 store (即所有底层修改都过 store action, 不直接调 api)
// - 不依赖 watcher (watcher 容易藏 stale closure / 隐性同步错位)
//
// 设计要点:
// - C 和 U 合并: 单一 `save(polaroid)`, 走 store.savePolaroid (PUT /polaroid/{pid}).
// - assets[].hash 由调用方负责 (dropzone 已经在浏览器算好).
// - 新增 path 走 dropzone → store.appendFiles (server 算 hash); 不要 PUT 里夹新 path.

import { ref, computed } from 'vue'
import { usePolarscanStore, type SavePolaroidResult } from '@/stores/polarscan'
import { newApi } from '@/api'
import type { Polaroid } from '@/types'

// 透传 store 的 SavePolaroidResult 给 view 层.
export type { SavePolaroidResult }

export interface PolaroidEditorOptions {
  /** 初始 pid (可选) */
  initialPid?: string | null
}

export function usePolaroidEditor(options: PolaroidEditorOptions = {}) {
  const { initialPid = null } = options
  const store = usePolarscanStore()

  // 当前编辑的 polaroid id (writable;page 在 mount/route change 时设)
  const pid = ref<string | null>(initialPid)
  // polaroid 状态 (单一来源,page 直接 v-model)
  const polaroid = ref<Polaroid>(emptyPolaroid())
  // UI session 状态
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
      const data = await store.loadPolaroid(p)
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

  /** 单一保存入口: 幂等 PUT, 创建或替换 (C+U 合并)
   *  调用方传整个 polaroid; 后端验证 body.id 与 url pid 一致、assets 非空、hash 长度.
   *  返回 SavePolaroidResult 含 created 标志, view 层可用于提示文案. */
  async function save(target?: Polaroid): Promise<SavePolaroidResult> {
    const p = target ?? polaroid.value
    isSaving.value = true
    error.value = null
    try {
      const result = await store.savePolaroid(p)
      // polaroid 已经在内存里跟服务端一致了; 显式赋值以触发 refs 更新
      polaroid.value = { ...p }
      return result
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      isSaving.value = false
    }
  }

  /** 增量添加文件到现有 polaroid (append_files 走 server 算 hash)
   *  store.appendFiles 成功后已 refreshSummaries, 这里再 refetch 当前 polaroid 拿最新 assets. */
  async function appendFiles(paths: string[]): Promise<void> {
    const p = pid.value
    if (!p) throw new Error('appendFiles 需要已存在的拍立得')
    isSaving.value = true
    error.value = null
    try {
      await store.appendFiles(p, paths)
      const data = await store.loadPolaroid(p)
      if (pid.value === p) {
        polaroid.value = data
      }
    } catch (e) {
      if (pid.value === p) {
        error.value = e instanceof Error ? e.message : String(e)
      }
      throw e
    } finally {
      if (pid.value === p) {
        isSaving.value = false
      }
    }
  }

  /** 派生一个建议 pid (NewView 表单预览用, 不写入) */
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
    save,
    appendFiles,
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
    metadata: {},
  }
}