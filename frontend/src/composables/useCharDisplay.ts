// useCharDisplay: char tag 的展示字段派生 (canonical_name / aliases / color_*).
//
// 职责 (单一职责):
// - 接收一个完整 char tag (如 'char:小薰') 或其 ref/getter, 返回响应式
//   CharDisplay 对象 (key / canonical_name / aliases / color_rgb / color_name).
// - 懒加载触发: 首次渲染时调 store.loadCharMeta(); store 内部 dedup,
//   多次调用不重复请求.
// - 类型保护: meta 内部字段缺失/类型异常时降级为 null, 不抛错.
//
// 与 CharTag / NAutoComplete 选项渲染的关系:
// - CharTag 调用本 composable 反查 (组件实例内部一次注册).
// - NAutoComplete 的 options 不能逐元素调 composable (computed 内调 composable
//   不响应 props), caller 在 setup 顶层触发 store.loadCharMeta(), 然后在
//   computed 里直接用 store.getCharDisplay(key). 两个调用方共用同一数据真值,
//   本 composable 是 CharTag 单实例场景的薄封装.

import { computed, onMounted, toValue } from 'vue'
import type { ComputedRef, MaybeRefOrGetter } from 'vue'
import { usePolarscanStore, type CharDisplay } from '@/stores/polarscan'

export type { CharDisplay }

export function useCharDisplay(tag: MaybeRefOrGetter<string>): ComputedRef<CharDisplay> {
  const store = usePolarscanStore()

  // 触发懒加载 (store 内部 dedup by charMetaLoaded)
  onMounted(() => {
    void store.loadCharMeta()
  })

  return computed<CharDisplay>(() => {
    const t = toValue(tag)
    const key = t.replace(/^char:/, '')
    return store.getCharDisplay(key)
  })
}
