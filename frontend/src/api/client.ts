// API 客户端：fetch 封装，统一处理 JSON / FormData / 错误
// 所有路径与后端 JSON API 对齐；GET 路由返回 JSON，POST 路由接收 form-encoded 或 JSON

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const t = await r.text().catch(() => '')
    throw new ApiError(r.status, t || `HTTP ${r.status}`)
  }
  const ct = r.headers.get('content-type') || ''
  if (ct.includes('application/json')) return r.json() as Promise<T>
  return (r.text() as unknown) as T
}

export const api = {
  // GET JSON
  async get<T>(url: string): Promise<T> {
    return handle<T>(await fetch(url, { method: 'GET' }))
  },

  // POST form-encoded（与后端现有 form-encoded 端点兼容）
  async postForm<T>(url: string, data: Record<string, string | undefined>): Promise<T> {
    const body = new URLSearchParams()
    for (const [k, v] of Object.entries(data)) {
      if (v !== undefined && v !== null) body.set(k, String(v))
    }
    return handle<T>(
      await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      }),
    )
  },

  // POST JSON
  async postJson<T>(url: string, data: unknown): Promise<T> {
    return handle<T>(
      await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    )
  },

  // PUT JSON (幂等创建/替换)
  async putJson<T>(url: string, data: unknown): Promise<T> {
    return handle<T>(
      await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    )
  },

  // DELETE (返回 JSON {ok} 或抛 ApiError)
  async deleteJson<T>(url: string): Promise<T> {
    return handle<T>(await fetch(url, { method: 'DELETE' }))
  },

  // GET 资源（thumb / img / index.html），返回 blob URL
  async getBlobUrl(url: string): Promise<string> {
    const r = await fetch(url)
    if (!r.ok) throw new ApiError(r.status, `HTTP ${r.status}`)
    const blob = await r.blob()
    return URL.createObjectURL(blob)
  },
}