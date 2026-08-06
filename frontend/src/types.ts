// 数据模型：与后端 polarscan.core.index.Polaroid / Asset 对齐
export interface Asset {
  role: string
  path: string
  device?: string | null
  /** 128 位十六进制 blake2b；首次写入前为空 (旧资产未迁移)。后端用 asdict 直出。 */
  hash?: string | null
  /** 任意 JSON 透传字典：core 不解析内部结构, 由前端 MetadataEditor 直接编辑。
   *  使用 `any` 而非 `unknown` 是因为 Pinia 的 _DeepPartial 无法 partial 顶层 unknown. */
  metadata?: Record<string, any>
}

export interface Polaroid {
  id: string
  shot_date?: string | null
  tags: string[]
  notes: string
  assets: Asset[]
  /** 任意 JSON 透传字典：core 不解析内部结构, 由前端 MetadataEditor 直接编辑。 */
  metadata?: Record<string, any>
}

export interface PolaroidSummary {
  id: string
  shot_date: string | null
  /** ListView 客户端 chip 过滤 (AND) 需要 tags；summary 也带这一份。 */
  tags?: string[]
  /** 首张资产 (用于列表卡片显示);拍立得无资产时为 null。
   *  含 hash 字段, 给 SingleImagePreview 做 ?v= cache-bust 用, 不暴露给业务。
   */
  cover_asset?: Asset | null
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

export interface IdentifyHit {
  pid: string
  asset_idx: number
  /** 命中来源: 'hash' = Blake2b 字节相同; 'path' = F: 盘绝对路径已在 yaml 中 */
  via: 'hash' | 'path'
}

export interface IdentifyCandidate {
  path: string
  /** 兼容字段: 第一个 in_yaml 命中的 pid (旧版用). 新代码优先用 in_yaml_hits */
  in_yaml_pid: string | null
  /** 完整路径命中位置 (pid + asset_idx); 与 by_hash 走同样的"是否命中"判断 */
  in_yaml_hits: Array<{ pid: string; asset_idx: number }>
}

export interface IdentifyResult {
  by_hash: Array<{ pid: string; asset_idx: number }>
  candidates: IdentifyCandidate[]
}

export type SaveState = 'idle' | 'dirty' | 'saving' | 'error'

export type DropzoneStatus =
  | 'idle'
  | 'candidates-checking'
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