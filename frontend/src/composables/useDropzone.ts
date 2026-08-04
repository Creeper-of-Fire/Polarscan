// Dropzone composable: 5 态状态机 + hash + identify
import { ref, computed } from 'vue'
import { blake2b } from 'hash-wasm'
import { dropApi } from '@/api'
import type { DroppedFile, DropzoneStatus } from '@/types'

function fileMtimeSeconds(file: File): number {
  return Math.round(file.lastModified / 1000)
}

async function readFileData(file: File): Promise<{ hash: string; dataUrl: string }> {
  const buf = await file.arrayBuffer()
  const bytes = new Uint8Array(buf)
  const hash = await blake2b(bytes, 512)
  // base64 for thumbnail
  let binary = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + chunk)))
  }
  const dataUrl = 'data:image/png;base64,' + btoa(binary)
  return { hash, dataUrl }
}

function classify(f: DroppedFile): 'hash-hit' | 'candidate-in-yaml' | 'new' | 'no-match' {
  if (f.identify.by_hash.length > 0) return 'hash-hit'
  const cands = f.identify.candidates || []
  if (cands.some((c) => c.in_yaml_pid)) return 'candidate-in-yaml'
  if (cands.length > 0) return 'new'
  return 'no-match'
}

const LABELS: Record<ReturnType<typeof classify>, string> = {
  'hash-hit': '已存在 (hash 命中)',
  'candidate-in-yaml': 'F:盘找到, 已在库',
  'new': '新文件',
  'no-match': 'F:盘未找到',
}

export interface DropzoneOptions {
  withThumb?: boolean
}

export function useDropzone(options: DropzoneOptions = {}) {
  const { withThumb = true } = options

  const files = ref<DroppedFile[]>([])
  const status = ref<DropzoneStatus>('idle')
  const errorMsg = ref<string>('')

  const importable = computed(() =>
    files.value
      .filter((f) => f.identify.by_hash.length === 0)
      .filter((f) => (f.identify.candidates || []).length > 0)
      .map((f, i) => ({
        path: (f.identify.candidates || [])[0].path,
        role: defaultRole(i),
      })),
  )

  const hashHits = computed(() =>
    files.value.filter((f) => f.identify.by_hash.length > 0),
  )

  function defaultRole(index: number): string {
    if (index === 0) return 'front'
    if (index === 1) return 'back'
    return 'additional'
  }

  async function handleDrop(event: DragEvent): Promise<void> {
    event.preventDefault()
    const dt = event.dataTransfer
    if (!dt || !dt.files || dt.files.length === 0) return

    status.value = 'hashing'
    errorMsg.value = ''
    files.value = []

    const fileList = Array.from(dt.files)
    try {
      // 1) hash + thumb (一次 IO)
      const hashed = await Promise.all(
        fileList.map(async (f) => {
          const data = await readFileData(f)
          return {
            name: f.name,
            size: f.size,
            mtime: fileMtimeSeconds(f),
            hash: data.hash,
            thumb: withThumb ? data.dataUrl : undefined,
          }
        }),
      )

      status.value = 'identifying'

      // 2) identify
      const identified = await Promise.all(
        hashed.map(async (h) => ({
          ...h,
          identify: await dropApi.identify({
            name: h.name,
            size: h.size,
            lastModified_ms: h.mtime * 1000,
            hash: h.hash,
          }),
        })),
      )

      files.value = identified
      status.value = 'ready'
    } catch (e) {
      errorMsg.value = e instanceof Error ? e.message : String(e)
      status.value = 'error'
    }
  }

  function removeFile(i: number): void {
    files.value.splice(i, 1)
    if (files.value.length === 0) status.value = 'idle'
  }

  function reset(): void {
    files.value = []
    status.value = 'idle'
    errorMsg.value = ''
  }

  function fileStatus(f: DroppedFile) {
    return classify(f)
  }

  function fileStatusLabel(f: DroppedFile): string {
    return LABELS[classify(f)]
  }

  function firstCandidatePath(f: DroppedFile): string | null {
    const cands = f.identify.candidates || []
    return cands[0] ? cands[0].path : null
  }

  return {
    files,
    status,
    errorMsg,
    importable,
    hashHits,
    handleDrop,
    removeFile,
    reset,
    fileStatus,
    fileStatusLabel,
    firstCandidatePath,
  }
}