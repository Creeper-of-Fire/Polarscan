// faceRules — 拍立得扫描件正/反面判定：纯函数管线，像素进、判定出。
//
// ── 这是什么 ────────────────────────────────────────────────────────────
// instax 相纸的物理差异构成了判据：
//   正面 = 白色相纸边框 + 照片（白且低饱和的边框占画面相当比例）
//   背面 = 黑色相纸背 + 灰色警示条（整图暗，几乎没有"白且低饱和"像素）
//
// 旋转性说明（重要）：
//   whiteRatio / cornerWhiteRatio —— 占比类 + 四角对称定义，**旋转不变**
//   midWhiteRatio / midDarkRatio  —— 水平中带（必然横穿左右白框，这是它
//     有效的原因），**方向敏感**：依赖竖构图。中心块定义已被实测否决
//     （正面中心可完全落在照片内部，与背面重叠）。因此横构图由 IO 层
//     （useFaceClassify）负责旋正后再喂入；本模块显式拒绝横构图。
//
// 本文件是唯一算法真相：特征定义、阈值、三档判定都在这里，
// 无参考集、无运行时外部状态。要改判定就整块改这一个文件。
//
// ── 三档容错 ────────────────────────────────────────────────────────────
//   auto    主判明确 且 ≥2 个交叉特征同向 → 直接定 front/back
//   review  主判明确 但交叉特征只剩 1 个同向 → 黄标，等人工瞄一眼
//   suspect 主判落在死区 / 交叉全部反向   → 红标不猜，等人工
// 人工永远优先：界面上的角标翻转直接覆盖判定结果（见 ingest-scan spec § 2.3）。
//
// ── 标定依据（20 张实测，512px 缩略图 JPEG，2026-10-28）─────────────────
//   特征              背面 (6 张)      正面 (14 张)     阈值(取空隙中点)
//   whiteRatio        0.0201 – 0.0328  0.2476 – 0.4656  死区 [0.08, 0.20]
//   midWhiteRatio     0.0000 – 0.0097  0.0771 – 0.3416  0.04
//   midDarkRatio      0.7587 – 0.9984  0.2578 – 0.6813  0.72
//   cornerWhiteRatio  0.0940 – 0.1613  0.7342 – 0.9735  0.45
// 四特征零重叠；20/20 全部落入 auto 档。实测区间同时钉在
// tests/face_rules_js_test.mjs 作为回归边界。

export type Face = 'front' | 'back' | 'unknown'
export type FaceTier = 'auto' | 'review' | 'suspect'

export interface FaceFeatures {
  /** 全图"白且低饱和"像素占比（lum>200 且 sat<0.18）—— 主判 */
  whiteRatio: number
  /** 中带 (y ∈ 30%–70%) 白占比 */
  midWhiteRatio: number
  /** 中带暗像素占比 (lum<80) */
  midDarkRatio: number
  /** 四角并集（每角 8%×8% 块）白占比 */
  cornerWhiteRatio: number
}

export interface FaceVerdict {
  face: Face
  tier: FaceTier
  features: FaceFeatures
}

// ── 阈值（具名常量，人工调校；重标定时同步更新上方注释与测试断言） ──────
export const THRESHOLDS = {
  /** 主判死区沿：whiteRatio ≥ 此值 → 倾向正面（实测正面下界 0.2476） */
  FRONT_WHITE_MIN: 0.20,
  /** 主判死区沿：whiteRatio ≤ 此值 → 倾向背面（实测背面上界 0.0328） */
  BACK_WHITE_MAX: 0.08,
  /** 交叉：中带白占比分界 */
  MID_WHITE: 0.04,
  /** 交叉：中带暗占比分界 */
  MID_DARK: 0.72,
  /** 交叉：四角白占比分界 */
  CORNER_WHITE: 0.45,
} as const

// ── 像素判据 ────────────────────────────────────────────────────────────
const WHITE_LUM = 200   // lum > 200 视为"亮"
const WHITE_SAT = 0.18  // 且饱和度 < 0.18 视为"白"（排除彩色亮部）
const DARK_LUM = 80     // lum < 80 视为"暗"

function luminance(r: number, g: number, b: number): number {
  return 0.299 * r + 0.587 * g + 0.114 * b
}

function saturation(r: number, g: number, b: number): number {
  const mx = Math.max(r, g, b)
  const mn = Math.min(r, g, b)
  return mx === 0 ? 0 : (mx - mn) / mx
}

/**
 * 从 RGBA 像素数据（canvas getImageData 格式，length = w*h*4）提取四特征。
 *
 * 一次遍历完成全图 / 中带 / 四角并集三个口径的统计。
 * 尺寸过小（<10px）或长度不符时抛错——调用方应传缩略图级尺寸。
 */
export function extractFeatures(
  data: Uint8ClampedArray | Uint8Array,
  width: number,
  height: number,
): FaceFeatures {
  if (width < 10 || height < 10) {
    throw new Error(`图像太小，无法提取特征: ${width}x${height}`)
  }
  // mid 特征依赖竖构图（水平中带要横穿左右白框）——横构图请先在 IO 层旋正
  if (width > height) {
    throw new Error(`横构图 (${width}x${height})：请先在 IO 层旋正再提取特征`)
  }
  if (data.length < width * height * 4) {
    throw new Error(`像素数据长度 ${data.length} 与 ${width}x${height} 不符`)
  }

  const midY0 = Math.trunc(0.30 * height)
  const midY1 = Math.trunc(0.70 * height)
  const bx = Math.max(1, Math.trunc(0.08 * width))
  const by = Math.max(1, Math.trunc(0.08 * height))

  let nWhite = 0
  let mAll = 0
  let mWhite = 0
  let mDark = 0
  let cAll = 0
  let cWhite = 0

  for (let y = 0; y < height; y++) {
    const inMid = y >= midY0 && y < midY1
    const inCornerBandY = y < by || y >= height - by
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4
      const r = data[i]
      const g = data[i + 1]
      const b = data[i + 2]
      const lum = luminance(r, g, b)
      const white = lum > WHITE_LUM && saturation(r, g, b) < WHITE_SAT

      if (white) nWhite++
      if (inMid) {
        mAll++
        if (white) mWhite++
        if (lum < DARK_LUM) mDark++
      }
      if (inCornerBandY && (x < bx || x >= width - bx)) {
        cAll++
        if (white) cWhite++
      }
    }
  }

  return {
    whiteRatio: nWhite / (width * height),
    midWhiteRatio: mAll ? mWhite / mAll : 0,
    midDarkRatio: mAll ? mDark / mAll : 0,
    cornerWhiteRatio: cAll ? cWhite / cAll : 0,
  }
}

/**
 * 判定：特征进 → 结论出。
 *
 * 主判 whiteRatio 先定倾向（死区则直接 suspect），
 * 再数交叉特征（midWhite / midDark / cornerWhite）中与倾向同向的个数：
 *   ≥2 同向 → auto；1 同向 → review；0 同向 → suspect（不猜）。
 */
export function classifyFront(features: FaceFeatures): FaceVerdict {
  const { whiteRatio } = features

  let base: Face
  if (whiteRatio >= THRESHOLDS.FRONT_WHITE_MIN) base = 'front'
  else if (whiteRatio <= THRESHOLDS.BACK_WHITE_MAX) base = 'back'
  else {
    // 主判落在死区：连倾向都不给，等人工
    return { face: 'unknown', tier: 'suspect', features }
  }

  const frontSays: boolean[] = [
    features.midWhiteRatio > THRESHOLDS.MID_WHITE,   // 正面：中带仍有白
    features.midDarkRatio < THRESHOLDS.MID_DARK,     // 正面：中带不全黑
    features.cornerWhiteRatio > THRESHOLDS.CORNER_WHITE, // 正面：角是白框
  ]
  const agree = frontSays.filter((says) => says === (base === 'front')).length

  if (agree >= 2) return { face: base, tier: 'auto', features }
  if (agree === 1) return { face: base, tier: 'review', features }
  return { face: 'unknown', tier: 'suspect', features } // 交叉全部反向：不猜
}
