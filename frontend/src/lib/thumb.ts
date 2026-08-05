// 缩略图/原图 URL 拼装工具
//
// 设计要点:
// - 后端路由 /thumb/{pid}/{idx} 和 /img/{pid}/{idx} 是 SSE/REST 的约定,
//   由这两条函数集中管理, 任何调用方都不再自己拼.
// - hash[:6] 作为 query-string cache bust. 解决"替换 assets[i] 时 hash 变,
//   但 URL 不变, 浏览器 <img> 缓存返回旧图"的问题.
// - hash 缺失时回退 '0' (避免未迁移 / 编辑中资产拿不到 cache bust, 至少能命中).

export function thumbUrl(
  polaroidId: string,
  assetIdx: number,
  hash?: string | null,
): string {
  const v = hash?.slice(0, 6) ?? '0'
  return `/thumb/${encodeURIComponent(polaroidId)}/${assetIdx}?v=${v}`
}

export function originUrl(
  polaroidId: string,
  assetIdx: number,
  hash?: string | null,
): string {
  const v = hash?.slice(0, 6) ?? '0'
  return `/img/${encodeURIComponent(polaroidId)}/${assetIdx}?v=${v}`
}
