// Dropzone composable: 5 态状态机 + 2-phase identify
//
// 流程:
//   drop ──► candidates-checking (server: 空 hash,只查 candidates)
//        ├─► hashing + identifying (browser: 算 hash + server: by_hash 查询)
//            [仅对需要 hash 的文件: 有 candidates 但无 path 命中]
//        └─► ready
//
// 优化:
// - candidates 为空 → 跳过 hash (浪费)
// - 路径命中 (in_yaml_hits 非空) → 跳过 hash (短路)
//
// path 命中与 hash 命中走相同 UX (force-add dialog), 透过 `hitFiles` /
// `appendEligible` 暴露。

import { ref, computed } from 'vue'
import { blake2b } from 'hash-wasm'
import { dropApi } from '@/api'
import type { DroppedFile, DropzoneStatus, IdentifyHit, IdentifyResult } from '@/types'

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

// 单一来源: 把 by_hash 和 in_yaml_hits 合并成统一 hit 列表 (via 区分来源)
// 命中路径 = hash 命中 OR 路径命中 (F: 盘绝对路径已在 yaml 中)
function collectHits(f: DroppedFile): IdentifyHit[] {
  const out: IdentifyHit[] = []
  for (const h of f.identify.by_hash) {
    out.push({ pid: h.pid, asset_idx: h.asset_idx, via: 'hash' })
  }
  for (const c of f.identify.candidates) {
    for (const h of c.in_yaml_hits) {
      out.push({ pid: h.pid, asset_idx: h.asset_idx, via: 'path' })
    }
  }
  return out
}

function classify(f: DroppedFile): 'hash-hit' | 'candidate-in-yaml' | 'new' | 'no-match' | 'no-f-path' {
  const cands = f.identify.candidates || []
  if (cands.length === 0) return 'no-f-path'
  if (f.identify.by_hash.length > 0) return 'hash-hit'
  if (cands.some((c) => c.in_yaml_pid || c.in_yaml_hits.length > 0)) return 'candidate-in-yaml'
  return 'new'
}

const LABELS: Record<ReturnType<typeof classify>, string> = {
  'hash-hit': '已存在 (hash 命中)',
  'candidate-in-yaml': '已存在 (路径命中)',
  'new': '新文件',
  'no-match': 'F:盘未找到',
  'no-f-path': '无 F: 盘匹配',
}

export interface DropzoneOptions {
  withThumb?: boolean
  /** 文件列表 ready (identify 完成) 时的回调 */
  onReady?: (files: DroppedFile[]) => void
}

/** 一个 append-eligible 条目: 至少有一个候选 F: 盘路径 (不论 hash 状态) */
export interface AppendEligibleEntry {
  path: string
  role: string
}

export function useDropzone(options: DropzoneOptions = {}) {
  const { withThumb = true, onReady } = options

  const files = ref<DroppedFile[]>([])
  const status = ref<DropzoneStatus>('idle')
  const errorMsg = ref<string>('')

  // 拖拽高亮: 用 counter 处理 dragenter/dragleave 在子元素间穿梭时的嵌套事件,
  // 用 dataTransfer.types 过滤掉非文件拖拽 (e.g. 文本选中 drag).
  const isDragging = ref(false)
  let dragCounter = 0

  function isFileDrag(e: DragEvent): boolean {
    return !!e.dataTransfer && Array.from(e.dataTransfer.types ?? []).includes('Files')
  }

  function onDragEnter(e: DragEvent) {
    e.preventDefault()
    if (!isFileDrag(e)) return
    dragCounter++
    if (dragCounter === 1) isDragging.value = true
  }

  function onDragOver(e: DragEvent) {
    e.preventDefault()
    if (e.dataTransfer && isFileDrag(e)) e.dataTransfer.dropEffect = 'copy'
  }

  function onDragLeave(e: DragEvent) {
    e.preventDefault()
    if (!isFileDrag(e)) return
    dragCounter--
    if (dragCounter <= 0) {
      dragCounter = 0
      isDragging.value = false
    }
  }

  function resetDrag() {
    dragCounter = 0
    isDragging.value = false
  }

  /**
   * create 流用: 没 hash 命中, 且有 F: 盘候选路径
   * (创建新拍立得时, 只要不在 hash 库里 + F: 盘存在, 就可作为资产)
   * 注: 路径命中 (in_yaml_hits) 不排除 — 一个文件可能只是 F: 盘路径被别人用过,
   *     字节不同也不冲突, 用户也许是想创建一张新拍立得引用该路径.
   */
  const importable = computed(() =>
    files.value
      .filter((f) => f.identify.by_hash.length === 0)
      .filter((f) => (f.identify.candidates || []).length > 0)
      .map((f, i) => ({
        path: (f.identify.candidates || [])[0].path,
        role: defaultRole(i),
      })),
  )

  /** 任意类型的命中 (hash OR 路径): 用于 force-add dialog */
  const hitFiles = computed(() =>
    files.value.filter((f) => collectHits(f).length > 0),
  )

  /** append 流用: 至少有候选 F: 盘路径, 即可 append (不管是否命中) */
  const appendEligible = computed<AppendEligibleEntry[]>(() =>
    files.value
      .filter((f) => (f.identify.candidates || []).length > 0)
      .map((f, i) => ({
        path: (f.identify.candidates || [])[0].path,
        role: defaultRole(i),
      })),
  )

  /** 没有候选 (路径匹配的 F: 盘文件找不到), 既不能 append 也不能 force-add */
  const noFPathFiles = computed(() =>
    files.value.filter((f) => (f.identify.candidates || []).length === 0),
  )

  function getHits(f: DroppedFile): IdentifyHit[] {
    return collectHits(f)
  }

  function defaultRole(index: number): string {
    if (index === 0) return 'front'
    if (index === 1) return 'back'
    return 'additional'
  }

  async function handleDrop(event: DragEvent): Promise<void> {
    event.preventDefault()
    resetDrag()
    const dt = event.dataTransfer
    if (!dt || !dt.files || dt.files.length === 0) return

    status.value = 'candidates-checking'
    errorMsg.value = ''
    files.value = []

    const fileList = Array.from(dt.files)
    try {
      // Phase 1: 只查 candidates, hash 为空 → server 跳过 find_by_hash
      const metaOnly: IdentifyResult[] = await Promise.all(
        fileList.map((f) =>
          dropApi.identify({
            name: f.name,
            size: f.size,
            lastModified_ms: fileMtimeSeconds(f) * 1000,
            hash: '',
          }),
        ),
      )

      // 分类:
      //   skip       = candidates 为空 (文件不在 F: 盘, 没有 path 可 append)
      //   pathHit    = candidates 非空, 有 in_yaml_hits (路径在库中, 跳过 hash)
      //   needHash   = candidates 非空, 无 in_yaml_hits (需要 hash 字节比较)
      type Decision = { skip: boolean; pathHit: boolean }
      const decisions: Decision[] = fileList.map((_f, i) => {
        const cands = metaOnly[i].candidates
        if (cands.length === 0) return { skip: true, pathHit: false }
        const hasPathHit = cands.some((c) => c.in_yaml_hits.length > 0)
        return { skip: false, pathHit: hasPathHit }
      })
      const needHashIdxs: number[] = []
      decisions.forEach((d, i) => {
        if (!d.skip && !d.pathHit) needHashIdxs.push(i)
      })

      // Phase 2: hash + 完整 identify (仅对需要 hash 的文件)
      let phase2Hashes: Array<{ hash: string; dataUrl: string }> = []
      let phase2Identify: IdentifyResult[] = []
      if (needHashIdxs.length > 0) {
        status.value = 'hashing'
        phase2Hashes = await Promise.all(
          needHashIdxs.map((i) => readFileData(fileList[i])),
        )

        status.value = 'identifying'
        phase2Identify = await Promise.all(
          needHashIdxs.map((j) =>
            dropApi.identify({
              name: fileList[j].name,
              size: fileList[j].size,
              lastModified_ms: fileMtimeSeconds(fileList[j]) * 1000,
              hash: phase2Hashes[j].hash,
            }),
          ),
        )
      }

      // 合并 → 暴露给 page 的最终 files
      files.value = fileList.map((f, i): DroppedFile => {
        const d = decisions[i]
        if (d.skip) {
          // 没 F: 盘候选 → 啥都没, 给空壳
          return {
            name: f.name,
            size: f.size,
            mtime: fileMtimeSeconds(f),
            hash: '',
            thumb: undefined,
            identify: metaOnly[i],
          }
        }
        if (d.pathHit) {
          // 路径命中, 跳过 hash (但 path 信息保留在 candidates[*].in_yaml_hits)
          return {
            name: f.name,
            size: f.size,
            mtime: fileMtimeSeconds(f),
            hash: '',
            thumb: undefined,
            identify: metaOnly[i],
          }
        }
        // 需要 hash: 用 phase2 结果
        const k = needHashIdxs.indexOf(i)
        const hd = phase2Hashes[k]
        return {
          name: f.name,
          size: f.size,
          mtime: fileMtimeSeconds(f),
          hash: hd.hash,
          thumb: withThumb ? hd.dataUrl : undefined,
          identify: phase2Identify[k],
        }
      })

      status.value = 'ready'
      onReady?.(files.value)
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
    isDragging,
    importable,
    hitFiles,
    appendEligible,
    noFPathFiles,
    getHits,
    handleDrop,
    onDragEnter,
    onDragOver,
    onDragLeave,
    removeFile,
    reset,
    fileStatus,
    fileStatusLabel,
    firstCandidatePath,
  }
}
