// 后端 API 调用层：按业务域分组
import { api } from './client'
import {
  charOshiColorFromMeta,
  type Asset,
  type CharOshiColor,
  type IdentifyResult,
  type Polaroid,
  type PolaroidSummary,
  type PoolItem,
} from '@/types'

export const polaroidsApi = {
  list(): Promise<PolaroidSummary[]> {
    return api.get<PolaroidSummary[]>('/api/polaroids')
  },
  byTag(tag: string): Promise<PolaroidSummary[]> {
    return api.get<PolaroidSummary[]>(`/api/polaroids?tag=${encodeURIComponent(tag)}`)
  },
  get(pid: string): Promise<Polaroid> {
    return api.get<Polaroid>(`/api/polaroids/${encodeURIComponent(pid)}`)
  },
  /** 单一保存入口: 幂等 PUT, 创建或替换 polaroid 全部状态.
   *  Assets 每项必须含 hash (128 字符 blake2b), 后端信任不读 F: 盘. */
  save(polaroid: Polaroid): Promise<{ ok: boolean; pid: string; asset_count: number; created: boolean }> {
    return api.putJson(
      `/polaroid/${encodeURIComponent(polaroid.id)}`,
      polaroid,
    )
  },
  delete(pid: string): Promise<{ ok: boolean }> {
    return api.deleteJson(`/polaroid/${encodeURIComponent(pid)}`)
  },
  goto(pid: string, direction: 'prev' | 'next' | 'untagged'): Promise<{ target: string | null }> {
    return api.get<{ target: string | null }>(
      `/api/polaroids/${encodeURIComponent(pid)}/goto/${direction}`,
    )
  },
  appendFiles(pid: string, paths: string[]): Promise<{ pid: string; asset_count: number }> {
    return api.postJson(
      `/api/polaroids/${encodeURIComponent(pid)}/append-files`,
      { path: paths },
    )
  },
}

export const newApi = {
  /** 派生一个 pid 候选 (不写入) - NewView 表单用 */
  suggestId(shot_date?: string, primary_char?: string): Promise<{ pid: string }> {
    const params = new URLSearchParams()
    if (shot_date) params.set('shot_date', shot_date)
    if (primary_char) params.set('primary_char', primary_char)
    return api.get<{ pid: string }>(`/api/suggest-id?${params.toString()}`)
  },
}

export const poolApi = {
  index(prefix: string): Promise<PoolItem[]> {
    return api.get<PoolItem[]>(`/api/pool/${encodeURIComponent(prefix)}`)
  },
  edit(prefix: string, key: string): Promise<{
    prefix: string
    key: string
    info: Record<string, unknown>
    used_by: PolaroidSummary[]
  }> {
    return api.get(`/api/pool/${encodeURIComponent(prefix)}/${encodeURIComponent(key)}`)
  },
  save(
    prefix: string,
    key: string,
    fields: {
      canonical_name?: string
      aliases?: string[]
      notes?: string
      /** 应援色文字 (例: "黄色"). 空字符串视为清空. */
      color_name?: string
      /** 应援色 RGB (hex #RRGGBB). 空字符串视为清空. */
      color_rgb?: string
      extra_json?: string
      return_to?: string
    },
  ): Promise<{ ok: boolean }> {
    return api.postForm(
      `/pool/${encodeURIComponent(prefix)}/${encodeURIComponent(key)}/edit`,
      {
        canonical_name: fields.canonical_name,
        aliases: fields.aliases ? fields.aliases.join(', ') : undefined,
        notes: fields.notes,
        color_name: fields.color_name,
        color_rgb: fields.color_rgb,
        extra_json: fields.extra_json,
        return_to: fields.return_to,
      },
    )
  },
  delete(prefix: string, key: string): Promise<{ ok: boolean }> {
    return api.postForm(
      `/pool/${encodeURIComponent(prefix)}/${encodeURIComponent(key)}/delete`,
      {},
    )
  },
  /** 拉取指定 prefix 下所有条目的应援色映射 (key → 应援色). 走 /api/pool/{prefix} 全表后前端筛字段. */
  async colorMap(prefix: string): Promise<Record<string, CharOshiColor>> {
    const items = await api.get<PoolItem[]>(`/api/pool/${encodeURIComponent(prefix)}`)
    const out: Record<string, CharOshiColor> = {}
    for (const it of items) {
      const c = charOshiColorFromMeta(it.meta as Record<string, unknown>)
      if (c.name || c.rgb) out[it.key] = c
    }
    return out
  },
}

export const tagsApi = {
  prefixValues(prefix: string): Promise<string[]> {
    return api.get<string[]>(`/api/all-tags?prefix=${encodeURIComponent(prefix)}`)
  },
  all(): Promise<Record<string, string[]>> {
    return api.get<Record<string, string[]>>('/api/all-tags')
  },
}

export const dropApi = {
  identify(item: {
    name: string
    size: number
    lastModified_ms: number
    hash: string
  }): Promise<IdentifyResult> {
    return api.postJson<IdentifyResult>('/api/drop/identify', item)
  },
}

export const systemApi = {
  reload(): Promise<{ ok: boolean }> {
    return api.postForm('/reload', {})
  },
}