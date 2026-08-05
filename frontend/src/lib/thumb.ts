// 缩略图/原图 URL 拼装工具
//
// 设计要点 (2026-08 重构):
// - 统一 by-path 入口: 后端 /thumb?path=&hash= 直接根据文件路径生成 thumb,
//   不依赖 polaroid 索引. 这样 NewView 拖入后 (asset.path + asset.hash 都已有)
//   即可立即预览, 不需要等服务端索引写库.
//
// - hash[:6] 作为 thumb 文件名一部分, 也是 query-string cache-bust 双保险:
//   文件替换时 hash 变 → 文件名变 (磁盘层新文件) + ?v= 变 (浏览器层强制刷新).
//
// - 前端所有 caller 只关心 (path, hash), 不接触 polaroid id / asset idx.
//   这是 SingleImagePreview 等组件的契约基石.

/** 构造缩略图 URL. path 必填, hash 用于文件名派生 + cache-bust. */
export function thumbUrl(path: string, hash?: string | null): string {
  const v = hash?.slice(0, 6) ?? '0'
  const p = encodeURIComponent(path)
  const h = encodeURIComponent(hash ?? '')
  return `/thumb?path=${p}&hash=${h}&v=${v}`
}

/** 构造原图 URL. lightbox 主动点击时调用 (单次 F: 盘读 IO). */
export function originUrl(path: string): string {
  return `/img?path=${encodeURIComponent(path)}`
}
