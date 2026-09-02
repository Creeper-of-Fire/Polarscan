// useShotDateResolver: 共享不变量 — 跨日拍立得不允许保留 shot_date 默认值
//
// 背景:
// - Polaroid.shot_date 是单值字段 (schema 决策; 跨日建模暂缓).
// - assetsDateRange(...) 在拍立得跨多日时返回 ≥2 个候选.
// - NewView 多次拖入 / BenchView 编辑既有跨日 polaroid 时, 已存的 shot_date
//   (例如之前 NewView "1 候选自动填"留下的首日, 或 yaml 旧值) 会变成"无歧义的默认值"
//   —— 表单看着像可多选 (dateRange.length > 1 按钮列表), 但字段预填了一个旧值,
//   与"多候选时让用户主动选"的设计冲突.
//
// 不变量:
//   assetsDateRange(polaroid.assets) ≥ 2  →  polaroid.shot_date 强制清空 (null)
//
// 1 / 0 候选时不动: 1 候选的"自动填"是 caller 策略 (例如 NewView.handleDropReady),
// 0 候选时本就是空.
//
// 跨 NewView / BenchView 复用同一不变量, 避免两边各自写 watch 漂移.

import { watch } from 'vue'
import type { Ref } from 'vue'
import type { Polaroid } from '@/types'
import { assetsDateRange } from './usePathParse'

export function useShotDateResolver(polaroid: Ref<Polaroid>): void {
  watch(
    () => assetsDateRange(polaroid.value.assets),
    (dates) => {
      if (dates.length >= 2 && polaroid.value.shot_date !== null) {
        polaroid.value.shot_date = null
      }
    },
    { immediate: true },
  )
}
