// useCharDisplay: char tag 的展示字段派生 (display_name / aliases / color_*).
//
// 职责 (单一职责):
// - 接收一个完整 tag 字符串 (如 'char:小薰') 或其 ref/getter, 返回响应式
//   TagDisplay 对象 (prefix / key / display_name / canonical_name / aliases / color_*)。
// - 懒加载触发: 首次渲染时调 store.loadTagMeta(); store 内部 dedup,
//   多次调用不重复请求。
// - 类型保护: meta 内部字段缺失/类型异常时降级为 null, 不抛错。
//
// 展示规则 (canonical_name || key) 本身在 store.getTagDisplay 里, 与 prefix 无关;
// 本 composable 只是 CharTag 单实例场景的薄封装 —— caller 只传完整 tag, 不需要
// 知道 tagMeta / store / 元数据加载。
//
// 与 NAutoComplete 选项渲染的关系:
// - NAutoComplete 的 options 不能逐元素调 composable (computed 内调 composable
//   不响应 props), caller 在 setup 顶层触发 store.loadTagMeta(), 然后在
//   computed 里直接用 store.getTagDisplay(tag). 两个调用方共用同一数据真值。

import { computed, onMounted, toValue } from 'vue'
import type { ComputedRef, MaybeRefOrGetter } from 'vue'
import { usePolarscanStore, type TagDisplay } from '@/stores/polarscan'

export type { TagDisplay }

export function useCharDisplay(tag: MaybeRefOrGetter<string>): ComputedRef<TagDisplay> {
  const store = usePolarscanStore()

  // 触发懒加载 (store 内部 dedup by tagMetaLoaded)
  onMounted(() => {
    void store.loadTagMeta()
  })

  return computed<TagDisplay>(() => store.getTagDisplay(toValue(tag)))
}