// face_rules_js_test.mjs — Node 内置 test runner 验证正反判定纯函数库
//
// 跑法 (项目根):
//   node --experimental-strip-types --no-warnings --test tests/face_rules_js_test.mjs
//
// 无额外依赖。覆盖:
//   lib/faceRules.ts —— 特征提取 + 固定阈值判定（唯一算法真相）
//
// 真实标定边界（2026-10-28，20 张 512px 缩略图）硬编码在"实测边界"组，
// 改特征定义 / 阈值时这组先红，强制重新标定。
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  extractFeatures,
  classifyFront,
  THRESHOLDS,
} from '../frontend/src/lib/faceRules.ts'

// ───────────────────────── 合成像素工具 ─────────────────────────

/** 造 w*h 的 RGBA 像素；fill(x,y) 返回 [r,g,b] */
function makePixels(w, h, fill) {
  const data = new Uint8ClampedArray(w * h * 4)
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const [r, g, b] = fill(x, y)
      const i = (y * w + x) * 4
      data[i] = r
      data[i + 1] = g
      data[i + 2] = b
      data[i + 3] = 255
    }
  }
  return data
}

const BLACK = [10, 10, 12]
const WHITE = [250, 250, 248]
/** 彩色像素（亮但高饱和 → 不计入"白"） */
const VIVID = [220, 60, 60]

/** 典型正面：白框 width 比例 + 内部彩色照片 */
function frontLike(w, h, frameRatio = 0.12) {
  const fx = Math.round(w * frameRatio)
  const fy = Math.round(h * frameRatio)
  return makePixels(w, h, (x, y) => {
    if (x < fx || x >= w - fx || y < fy || y >= h - fy) return WHITE
    return VIVID
  })
}

/** 典型背面：黑底 + 顶部/底部窄警示条（实测全图白占比仅 2–3%，条必须窄） */
function backLike(w, h) {
  const band = Math.max(1, Math.round(h * 0.015))
  return makePixels(w, h, (x, y) => {
    if (y < band || y >= h - band) return [212, 212, 210]
    return BLACK
  })
}

// ───────────────────────── extractFeatures ─────────────────────────

test('extractFeatures: 参数护栏（太小 / 长度不符 / 横构图）', () => {
  assert.throws(() => extractFeatures(new Uint8ClampedArray(0), 5, 5), /太小/)
  // 竖构图 + 长度不足 → 命中长度检查
  assert.throws(
    () => extractFeatures(new Uint8ClampedArray(50 * 100), 50, 100),
    /像素数据长度/,
  )
  // 横构图：mid 特征依赖竖构图，IO 层负责旋正
  assert.throws(
    () => extractFeatures(new Uint8ClampedArray(200 * 100 * 4), 200, 100),
    /横构图/,
  )
})

test('extractFeatures: 全黑图 → 背面特征', () => {
  const f = extractFeatures(makePixels(100, 160, () => BLACK), 100, 160)
  assert.equal(f.whiteRatio, 0)
  assert.equal(f.midWhiteRatio, 0)
  assert.equal(f.midDarkRatio, 1)
  assert.equal(f.cornerWhiteRatio, 0)
})

test('extractFeatures: 全白图 → 正面特征', () => {
  const f = extractFeatures(makePixels(100, 160, () => WHITE), 100, 160)
  assert.equal(f.whiteRatio, 1)
  assert.equal(f.midWhiteRatio, 1)
  assert.equal(f.midDarkRatio, 0)
  assert.equal(f.cornerWhiteRatio, 1)
})

test('extractFeatures: 白框彩心正面——水平中带必然穿过左右白框', () => {
  const w = 100
  const h = 160
  const f = extractFeatures(frontLike(w, h, 0.12), w, h)
  // 全图白 = 边框面积占比（上下 12% + 左右 12%）
  //   = 1 - (1-0.24)^2 ≈ 0.4224（角块重叠修正后）
  assert.ok(f.whiteRatio > 0.3 && f.whiteRatio < 0.5, `whiteRatio=${f.whiteRatio}`)
  // 中带（30%-70% 高，全宽）必含左右白框
  assert.ok(f.midWhiteRatio > 0.2, `midWhiteRatio=${f.midWhiteRatio}`)
  // 彩心高饱和不计入白
  assert.ok(f.midWhiteRatio < 0.5, `midWhiteRatio=${f.midWhiteRatio}`)
  assert.equal(f.cornerWhiteRatio, 1) // 四角全在白框内
})

test('extractFeatures: 黑底灰条背面——灰条低饱和亮像素计入白', () => {
  const w = 100
  const h = 160
  const f = extractFeatures(backLike(w, h), w, h)
  // 上下各 ~1.5% 警示条计入白（与实测背面 2–3% 对齐）
  assert.ok(Math.abs(f.whiteRatio - 0.025) < 0.01, `whiteRatio=${f.whiteRatio}`)
  // 中带（30%-70%）不含条 → 全黑
  assert.equal(f.midWhiteRatio, 0)
  assert.equal(f.midDarkRatio, 1)
})

// ───────────────────────── classifyFront：实测边界（标定回归） ─────────

test('classifyFront: 实测背面最白的样本（0.0328）→ back/auto', () => {
  // img20261020_11514906：背面里 whiteRatio 最高、midDarkRatio 最低的一张
  const v = classifyFront({
    whiteRatio: 0.0328,
    midWhiteRatio: 0.0097,
    midDarkRatio: 0.7587,
    cornerWhiteRatio: 0.1613,
  })
  assert.equal(v.face, 'back')
  assert.equal(v.tier, 'auto')
})

test('classifyFront: 实测正面最不白的样本（0.2476）→ front/auto', () => {
  // img20261020_11403339：正面里 whiteRatio 最低的一张
  const v = classifyFront({
    whiteRatio: 0.2476,
    midWhiteRatio: 0.0929,
    midDarkRatio: 0.5326,
    cornerWhiteRatio: 0.931,
  })
  assert.equal(v.face, 'front')
  assert.equal(v.tier, 'auto')
})

test('classifyFront: 实测正面 midDark 最高样本（0.6813）→ front/auto', () => {
  // img20261020_11402844：正面里中带最暗的一张，仍低于 MID_DARK 阈值
  const v = classifyFront({
    whiteRatio: 0.2674,
    midWhiteRatio: 0.0934,
    midDarkRatio: 0.6813,
    cornerWhiteRatio: 0.8296,
  })
  assert.equal(v.face, 'front')
  assert.equal(v.tier, 'auto')
})

test('classifyFront: 实测背面 midWhite 最高样本（0.0097）→ back/auto', () => {
  const v = classifyFront({
    whiteRatio: 0.0201,
    midWhiteRatio: 0.0097,
    midDarkRatio: 0.9408,
    cornerWhiteRatio: 0.0945,
  })
  assert.equal(v.face, 'back')
  assert.equal(v.tier, 'auto')
})

// ───────────────────────── classifyFront：三档容错 ─────────────────────────

test('classifyFront: 主判死区 → unknown/suspect（不猜）', () => {
  const v = classifyFront({
    whiteRatio: 0.14, // 落在 [0.08, 0.20] 死区中央
    midWhiteRatio: 0.05,
    midDarkRatio: 0.5,
    cornerWhiteRatio: 0.5,
  })
  assert.equal(v.face, 'unknown')
  assert.equal(v.tier, 'suspect')
})

test('classifyFront: 主判明确但交叉全反向 → unknown/suspect', () => {
  const v = classifyFront({
    whiteRatio: 0.3, // 明确偏正面
    midWhiteRatio: 0.0, // 说背面
    midDarkRatio: 0.95, // 说背面
    cornerWhiteRatio: 0.1, // 说背面
  })
  assert.equal(v.face, 'unknown')
  assert.equal(v.tier, 'suspect')
})

test('classifyFront: 主判明确但交叉只剩 1 个同向 → review', () => {
  const v = classifyFront({
    whiteRatio: 0.3,
    midWhiteRatio: 0.05, // 同向（正面）
    midDarkRatio: 0.95, // 反向
    cornerWhiteRatio: 0.1, // 反向
  })
  assert.equal(v.face, 'front')
  assert.equal(v.tier, 'review')
})

test('classifyFront: 阈值边界恰好压线的行为', () => {
  // 恰在 FRONT_WHITE_MIN 上 → front 倾向；恰在 BACK_WHITE_MAX 下 → back 倾向
  const fEdge = classifyFront({
    whiteRatio: THRESHOLDS.FRONT_WHITE_MIN,
    midWhiteRatio: 0.1,
    midDarkRatio: 0.4,
    cornerWhiteRatio: 0.8,
  })
  assert.equal(fEdge.face, 'front')
  const bEdge = classifyFront({
    whiteRatio: THRESHOLDS.BACK_WHITE_MAX,
    midWhiteRatio: 0.001,
    midDarkRatio: 0.9,
    cornerWhiteRatio: 0.1,
  })
  assert.equal(bEdge.face, 'back')
})

// ───────────────────────── 管线串联（合成图） ─────────────────────────

test('管线：合成正面 → front/auto', () => {
  const w = 100
  const h = 160
  const v = classifyFront(extractFeatures(frontLike(w, h), w, h))
  assert.equal(v.face, 'front')
  assert.equal(v.tier, 'auto')
})

test('管线：合成背面 → back/auto', () => {
  const w = 100
  const h = 160
  const v = classifyFront(extractFeatures(backLike(w, h), w, h))
  assert.equal(v.face, 'back')
  assert.equal(v.tier, 'auto')
})
