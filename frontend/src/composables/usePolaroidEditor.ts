// usePolaroidEditor: 拍立得编辑 session 的适配层
//
// 职责:
// - 持有 polaroid 状态 (单一来源)
// - 提供 actions: load / save / appendFiles / suggestId
// - 提供 loading / saving / error 状态
//
// 状态传递:
// - pid 是 writable ref,page 在 mount / route change 时设
// - polaroid 是 ref,page 直接 v-model 编辑
// - 不依赖 watcher (watcher 容易藏 stale closure / 隐性同步错位)
//
// 设计要点 (2026-08 重构):
// - C 和 U 合并: 单一 `save(polaroid)`, 走 PUT /polaroid/{pid}.
//   这样不论"新建"还是"已存在", 都是同一份代码路径.
// - assets[].hash 由调用方负责 (dropzone 已经在浏览器算好).
// - 新增 path 走 dropzone → append_files (server 算 hash); 不要 PUT 里夹新 path.

import { ref, computed } from 'vue'
import { polaroidsApi, newApi } from '@/api'
import type { Polaroid } from '@/types'

export interface PolaroidEditorOptions {
  /** 初始 pid (可选) */
  initialPid?: string | null
}

export interface SaveResult {
  ok: boolean
  pid: string
  asset_count: number
  created: boolean
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
   *  调用方传整个 polaroid; 后端验证 body.id 与 url pid 一致、assets 非空、hash 长度. */
  async function save(target?: Polaroid): Promise<SaveResult> {
    const p = target ?? polaroid.value
    isSaving.value = true
    error.value = null
    try {
      const r = await polaroidsApi.save(p)
      pid.value = r.pid
      // polaroid 已经在内存里跟服务端一致了; 显式赋值以触发 refs 更新
      polaroid.value = { ...p }
      return r
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      isSaving.value = false
    }
  }

  /** 增量添加文件到现有 polaroid (append_files 走 server 算 hash)
   *  完成后 refetch. 注意: append 仍然不改保存语义 (PUT 才是), 算两条不同路. */
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
  }
}
