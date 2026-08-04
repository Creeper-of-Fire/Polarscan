// 自动保存 composable: 防抖 + 状态机
// 用法:
//   const { state, schedule, flush, cancel } = useAutosave(async (payload) => { ... })
//   watch(() => form.value, () => schedule({ ... }), { deep: true })

import { ref, readonly } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import type { SaveState } from '@/types'

export interface AutosaveOptions {
  debounceMs?: number
  onError?: (e: unknown) => void
}

export function useAutosave<T>(
  saver: (payload: T) => Promise<{ ok: boolean; error?: string }>,
  options: AutosaveOptions = {},
) {
  const { debounceMs = 600, onError } = options

  const state = ref<SaveState>('idle')
  const lastSaved = ref<T | null>(null)
  const lastError = ref<string | null>(null)

  // tags 立即保存路径：绕过防抖
  async function save(payload: T): Promise<void> {
    state.value = 'saving'
    lastError.value = null
    try {
      const r = await saver(payload)
      if (r.ok) {
        lastSaved.value = payload
        state.value = 'idle'
      } else {
        lastError.value = r.error ?? 'unknown error'
        state.value = 'error'
        onError?.(new Error(lastError.value))
      }
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : String(e)
      state.value = 'error'
      onError?.(e)
    }
  }

  const debouncedSave = useDebounceFn(save, debounceMs)

  function schedule(payload: T): void {
    state.value = 'dirty'
    debouncedSave(payload)
  }

  async function flush(payload: T): Promise<void> {
    debouncedSave.cancel()
    await save(payload)
  }

  function cancel(): void {
    debouncedSave.cancel()
    state.value = lastSaved.value ? 'idle' : 'idle'
  }

  return {
    state: readonly(state),
    lastSaved: readonly(lastSaved),
    lastError: readonly(lastError),
    schedule,
    flush,
    save,
    cancel,
  }
}