// 数据模型：与后端 polarscan.core.index.Polaroid / Asset 对齐
export interface Asset {
  role: string
  path: string
  captured_at?: string | null
  device?: string | null
}

export interface Polaroid {
  id: string
  shot_date?: string | null
  tags: string[]
  notes: string
  assets: Asset[]
}

export interface PolaroidSummary {
  id: string
  shot_date: string | null
}

export interface PoolItem {
  key: string
  meta: Record<string, unknown>
  count: number
}

export interface TagSuggestion {
  prefix: string
  values: string[]
}

export interface IdentifyResult {
  by_hash: Array<{ pid: string; asset_idx: number }>
  candidates: Array<{ path: string; in_yaml_pid: string | null }>
}

export type SaveState = 'idle' | 'dirty' | 'saving' | 'error'

export type DropzoneStatus =
  | 'idle'
  | 'hashing'
  | 'identifying'
  | 'ready'
  | 'submitting'
  | 'error'

export interface DroppedFile {
  name: string
  size: number
  mtime: number
  hash: string
  thumb?: string
  identify: IdentifyResult
}