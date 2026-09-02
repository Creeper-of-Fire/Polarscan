<!--
  PoolIndexView: 池页面

  职责:
  - 展示指定 prefix 下所有 tag: 已注册 (registered, 在 yaml tags 字典里有 metadata)
    + 未定义 (undefined, 仅在 polaroid.tags 中被引用)
  - 数据聚合: 后端两个端点 → 客户端 union
      poolApi.index(prefix)        → [{key, meta, count}]   (registered only)
      tagsApi.prefixValues(prefix)  → [full_tag, ...]         (used, 含 undefined)
  - 视觉: 卡片化 list (PoolRow.vue); registered 实线 / undefined 虚线
  - 操作:
      registered 行 → 编辑
      undefined  行 → 注册 (upsert_tag(prefix, key, {}) → 跳 /pool/{prefix}/{key}/edit)
  - filter: 全部 / 仅已注册 / 仅未定义

  数据流动 (2026-09 响应式化):
    watch(props.prefix, immediate=true) → 双端点拉取 → items 派生 → render
-->
<!-- TODO - usedCount 数据源统一:
  当前已注册走后端 poolApi.index.count (走 polaroids_with_tag 全表扫),
  未定义走客户端 store.summaries 累计.
  两路实现层不一致, 若 summary API 有过滤会 drift.
  倾向: 统一走客户端, 后端 count 字段后续可省.
-->
<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NSpin, NEmpty, NSpace, NButton, NSelect } from 'naive-ui'
import { poolApi, tagsApi } from '@/api'
import { usePolarscanStore } from '@/stores/polarscan'
import type { PoolItem } from '@/types'
import PoolRow from '@/components/PoolRow.vue'

const props = defineProps<{ prefix: string }>()
const router = useRouter()
const store = usePolarscanStore()

// 原始拉取
const registered = ref<PoolItem[]>([])       // poolApi.index → [{key, meta, count}]
const usedTags = ref<string[]>([])           // tagsApi.prefixValues → used 集合 (去重)
const loading = ref(false)

// 聚合后的行 (registered ∪ undefined), 每项含 isUndefined 标志
interface PoolRowData {
  fullTag: string
  key: string
  meta: Record<string, unknown>
  usedCount: number
  isUndefined: boolean
}

const items = computed<PoolRowData[]>(() => {
  const regMap = new Map<string, PoolItem>()
  for (const r of registered.value) regMap.set(r.key, r)

  // used count 必须从 polaroid.tags 派生, 不能只看 tagsApi.prefixValues
  // (那个只返回去重集合, 不含次数). 走 store.summaries (已含 tags).
  const prefixColon = `${props.prefix}:`
  const usedCounts = new Map<string, number>()
  for (const s of store.summaries) {
    for (const t of s.tags || []) {
      if (t.startsWith(prefixColon)) {
        const key = t.slice(prefixColon.length)
        usedCounts.set(key, (usedCounts.get(key) || 0) + 1)
      }
    }
  }
  const usedKeys = new Set(usedCounts.keys())

  const allKeys = new Set<string>()
  for (const k of regMap.keys()) allKeys.add(k)
  for (const k of usedKeys) allKeys.add(k)

  return Array.from(allKeys).map((key) => {
    const reg = regMap.get(key)
    // 已注册用后端 count (后端走 polaroids_with_tag 精确计算),
    // 未注册用客户端 usedCounts (store.summaries tags 累计).
    return {
      fullTag: `${props.prefix}:${key}`,
      key,
      meta: reg?.meta ?? {},
      usedCount: reg?.count ?? usedCounts.get(key) ?? 0,
      isUndefined: !reg,
    }
  })
})

// filter: 全部 / 仅已注册 / 仅未定义
type FilterMode = 'all' | 'registered' | 'undefined'
const filterMode = ref<FilterMode>('all')

const visibleItems = computed(() => {
  if (filterMode.value === 'all') return items.value
  if (filterMode.value === 'registered') return items.value.filter((it) => !it.isUndefined)
  return items.value.filter((it) => it.isUndefined)
})

// 排序: 已注册优先 (实线视觉更显眼), 然后 count 降序, 最后 key 升序
const sortedItems = computed(() => {
  return [...visibleItems.value].sort((a, b) => {
    if (a.isUndefined !== b.isUndefined) return a.isUndefined ? 1 : -1
    if (a.usedCount !== b.usedCount) return b.usedCount - a.usedCount
    return a.key.localeCompare(b.key)
  })
})

// filter label 动态化 (count 后缀实时反映 items)
const filterOpts = computed(() => [
  { label: `全部 (${items.value.length})`, value: 'all' },
  { label: `仅已注册 (${items.value.filter((it) => !it.isUndefined).length})`, value: 'registered' },
  { label: `仅未定义 (${items.value.filter((it) => it.isUndefined).length})`, value: 'undefined' },
])

// 自然派生: prefix 变 → items 自动重拉. 避免跨 /pool/char → /pool/event 时
// 组件复用不刷新 (旧 onMounted 单次副作用).
// summaries 用于客户端算 undefined 的 usedCount; store 内部 dedup, 多次调用不重复.
watch(
  () => props.prefix,
  async (p) => {
    loading.value = true
    try {
      const [_, reg, used] = await Promise.all([
        store.listSummaries(),
        poolApi.index(p),
        tagsApi.prefixValues(p),
      ])
      registered.value = reg
      usedTags.value = used
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

// 注册未定义 tag: 走 poolApi.save 创建空 meta entry, 然后跳编辑页
async function registerUndefined(fullTag: string) {
  const [prefix, ...rest] = fullTag.split(':')
  const key = rest.join(':')  // 处理 key 里含冒号的边界 (理论存在)
  try {
    await poolApi.save(prefix, key, {
      canonical_name: '',
      aliases: [],
      notes: '',
      color_name: '',
      color_rgb: '',
      extra_json: '',
    })
    router.push(`/pool/${prefix}/${encodeURIComponent(key)}/edit`)
  } catch (e) {
    // PoolIndexView 当前不挂 useMessage; 简单 alert. TODO: 改 useMessage
    alert(`注册失败: ${e instanceof Error ? e.message : String(e)}`)
  }
}
</script>

<template>
  <div>
    <h2 style="margin-top: 0">
      <code>{{ prefix }}</code> 池 — 共 {{ items.length }} 条
      <small v-if="items.length > 0" style="font-weight: normal; color: #666">
        · 已注册 {{ items.filter((it) => !it.isUndefined).length }} /
          未定义 {{ items.filter((it) => it.isUndefined).length }}
      </small>
    </h2>

    <NSpace style="margin-bottom: 12px">
      <NSelect
        v-model:value="filterMode"
        :options="filterOpts"
        style="min-width: 220px"
      />
      <NButton @click="router.push('/list')">← 回到浏览</NButton>
    </NSpace>

    <NSpin :show="loading">
      <NEmpty
        v-if="!loading && items.length === 0"
        :description="`当前前缀下还没有任何 tag。可以先在工作台添加 ${prefix}:xxx, 系统会把已使用的键加入候选。`"
      />
      <PoolRow
        v-for="row in sortedItems"
        :key="row.fullTag"
        :prefix="row.fullTag.split(':')[0]"
        :tag-key="row.key"
        :full-tag="row.fullTag"
        :meta="row.meta"
        :used-count="row.usedCount"
        :is-undefined="row.isUndefined"
        @register="registerUndefined"
      />
    </NSpin>
  </div>
</template>
