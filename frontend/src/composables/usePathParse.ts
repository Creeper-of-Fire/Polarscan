// 通用路径工具。
//
// 这个文件**不认识任何文件夹命名语法**。日期怎么从名字里读出来，全部外包给
// `lib/folderDateCompat.ts` —— 那是对个人命名习惯的兼容层，可改可替换。
// 主业务在这里只看到「候选日数组」，看不到语法。

// 用相对路径而非 `@/`：tests/path_parse_js_test.mjs 直接 node 跑这个 .ts，
// Node 的 ESM 解析器不认 tsconfig 的 paths 别名。与 api/index.ts 等保持一致。
import { parseFolderDays } from '../lib/folderDateCompat.ts'

/** 取路径的父目录名，例如 "F:\\photo\\2026.07.25\\img.jpg" → "2026.07.25"。 */
export function parentDirName(path: string | null | undefined): string | null {
  if (!path) return null
  const parts = String(path).split(/[\\/]/)
  if (parts.length < 2) return null
  return parts[parts.length - 2] || null
}

/**
 * 收集一组资产可能对应的拍摄日期，作为**候选日**返回（升序去重）。
 *
 * 注意这是**推荐值，不是判断**：一张拍立得只有一个确定的拍摄日期，这里给出的
 * 只是一组可能值，由用户点选填入。任何情况下都不得据此自动写入 shot_date。
 *
 * 只看父目录名。文件名里的日期是**扫描日**，不是拍摄日，不参与。
 */
export function collectCandidateDays(
  assets: ReadonlyArray<{ path?: string | null } | null | undefined>,
): string[] {
  const set = new Set<string>()
  for (const a of assets) {
    if (!a?.path) continue
    const days = parseFolderDays(parentDirName(a.path))
    if (days) for (const d of days) set.add(d)
  }
  return [...set].sort()
}