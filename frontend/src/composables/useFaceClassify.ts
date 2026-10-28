// useFaceClassify — 判定 IO 层：缩略图 URL → 正反判定。
//
// 职责边界（docs/spec/ingest-scan.md § 2.3）：
//   本文件只做 IO（fetch / 解码 / 像素搬运 / 横图旋正），
//   特征与阈值全部在 lib/faceRules（唯一算法真相）。
//
// 横构图旋正：faceRules 的 mid 特征依赖竖构图（水平中带要横穿左右白框），
// 其余特征对方向不敏感，因此顺/逆时针转 90° 均不影响判定正确性。
import { classifyFront, extractFeatures, type FaceVerdict } from '@/lib/faceRules'

async function loadPixels(
  thumbUrl: string,
): Promise<{ data: Uint8ClampedArray; width: number; height: number }> {
  const resp = await fetch(thumbUrl)
  if (!resp.ok) throw new Error(`缩略图拉取失败: HTTP ${resp.status}`)
  const blob = await resp.blob()
  const bmp = await createImageBitmap(blob)

  const rotated = bmp.width > bmp.height
  const canvas = document.createElement('canvas')
  canvas.width = rotated ? bmp.height : bmp.width
  canvas.height = rotated ? bmp.width : bmp.height
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) {
    bmp.close()
    throw new Error('无法创建 2D 上下文')
  }
  if (rotated) {
    // 顺时针 90°：原点平移到画布中心再旋转，图像恰好铺满
    ctx.translate(canvas.width / 2, canvas.height / 2)
    ctx.rotate(Math.PI / 2)
    ctx.drawImage(bmp, -bmp.width / 2, -bmp.height / 2)
  } else {
    ctx.drawImage(bmp, 0, 0)
  }
  bmp.close()
  const img = ctx.getImageData(0, 0, canvas.width, canvas.height)
  return { data: img.data, width: canvas.width, height: canvas.height }
}

/** 单张缩略图判定。解码失败不抛出——返回 suspect 档等人工兜底。 */
export async function classifyThumb(thumbUrl: string): Promise<FaceVerdict> {
  try {
    const { data, width, height } = await loadPixels(thumbUrl)
    return classifyFront(extractFeatures(data, width, height))
  } catch {
    return {
      face: 'unknown',
      tier: 'suspect',
      features: {
        whiteRatio: -1,
        midWhiteRatio: -1,
        midDarkRatio: -1,
        cornerWhiteRatio: -1,
      },
    }
  }
}
