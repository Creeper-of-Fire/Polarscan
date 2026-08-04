// 后端 API 调用层：按业务域分组
import { api } from './client'
import type {
  Asset,
  IdentifyResult,
  Polaroid,
  PolaroidSummary,
  PoolItem,
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
  autosave(
    pid: string,
    fields: { tags?: string[]; shot_date?: string; notes?: string },
  ): Promise<{ ok: boolean; error?: string; tags?: string[]; shot_date?: string | null; notes_len?: number }> {
    return api.postForm(
      `/bench/${encodeURIComponent(pid)}/autosave`,
      {
        tags: fields.tags ? fields.tags.join(', ') : undefined,
        shot_date: fields.shot_date,
        notes: fields.notes,
      },
    )
  },
  saveAssets(pid: string, assets: Asset[]): Promise<{ pid: string; asset_count: number }> {
    return api.postJson(
      `/bench/${encodeURIComponent(pid)}/save-assets`,
      { assets },
    )
  },
  delete(pid: string): Promise<{ ok: boolean }> {
    return api.postForm(`/bench/${encodeURIComponent(pid)}/delete`, {})
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
  create(payload: {
    pid: string
    shot_date?: string
    primary_char?: string
    asset_paths: string[]
    tags?: string[]
    notes?: string
  }): Promise<{ ok: boolean; pid?: string; error?: string }> {
    return api.postForm('/new', {
      pid: payload.pid,
      shot_date: payload.shot_date,
      primary_char: payload.primary_char,
      asset_paths: payload.asset_paths.join('\n'),
      tags: payload.tags ? payload.tags.join(', ') : undefined,
      notes: payload.notes,
    })
  },
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