<!--
  ListView: 浏览全部拍立得

  过滤设计 (L2 + 纯客户端):
    - 全表一次加载到 store, 之后过滤都在 computed 里走 every()
    - 顶部 prefix chip 单选切换
    - 当前 prefix 下的 value chip 多选 toggle, 跨 prefix 累积
    - AND 逻辑: 选中的所有 tag 都需命中 polaroid.tags
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NSpin, NEmpty, NSpace, NCard, NButton, NTag } from 'naive-ui'
import { usePolarscanStore } from '@/stores/polarscan'
import { shotDateHint } from '@/composables/usePathParse'
import SingleImagePreview from '@/components/SingleImagePreview.vue'

const router = useRouter()
const store = usePolarscanStore()

// 前缀顺序：shot 放最前（审查主战场），其余按 schema 顺序
const PREFIX_ORDER = ['shot', 'char', 'event', 'theme', 'collection', 'composite', 'moment', 'sig']
const DEFAULT_PREFIX = 'shot'

const activePrefix = ref<string>(DEFAULT_PREFIX)
const selectedTags = ref<Set<string>>(new Set())
const tagGroups = ref<Record<string, string[]>>({})
const loading = ref(false)

const totalCount = ref(0)

onMounted(async () => {
  loading.value = true
  try {
    const [summaries, groups] = await Promise.all([
      store.listSummaries(),
      store.listAllTagGroups(),
    ])
    totalCount.value = summaries.length
    tagGroups.value = groups
  } finally {
    loading.value = false
  }
})

const sortedPrefixes = computed(() => {
  const known = PREFIX_ORDER.filter((p) => p in tagGroups.value)
  const extra = Object.keys(tagGroups.value).filter((p) => !PREFIX_ORDER.includes(p))
  return [...known, ...extra]
})

const currentValues = computed(() => tagGroups.value[activePrefix.value] ?? [])

const selectedTagList = computed(() => Array.from(selectedTags.value))

/** 纯客户端 AND 过滤. */
const filtered = computed(() => {
  const required = selectedTagList.value
  if (required.length === 0) return store.summaries
  return store.summaries.filter((s) => required.every((t) => s.tags?.includes(t)))
})

function isSelected(prefix: string, value: string): boolean {
  return selectedTags.value.has(`${prefix}:${value}`)
}

function toggleValue(value: string) {
  const full = `${activePrefix.value}:${value}`
  const next = new Set(selectedTags.value)
  if (next.has(full)) next.delete(full)
  else next.add(full)
  selectedTags.value = next
}

function removeTag(tag: string) {
  const next = new Set(selectedTags.value)
  next.delete(tag)
  selectedTags.value = next
}

function clearFilter() {
  selectedTags.value = new Set()
}

async function reload() {
  loading.value = true
  try {
    const summaries = await store.reloadSummaries()
    totalCount.value = summaries.length
    tagGroups.value = await store.listAllTagGroups()
  } finally {
    loading.value = false
  }
}

function open(id: string) {
  router.push(`/bench/${encodeURIComponent(id)}`)
}

/** 处理卡片点击: ctrl/cmd/middle click 让浏览器原生处理 (新标签页);其他走 SPA 路由。 */
function handleCardClick(e: MouseEvent, id: string) {
  if (e.ctrlKey || e.metaKey || e.button === 1) return
  e.preventDefault()
  router.push(`/bench/${encodeURIComponent(id)}`)
}
</script>

<template>
  <div>
    <h2 style="margin-top: 0">
      浏览 ({{ filtered.length }} / {{ totalCount }})
      <small v-if="selectedTagList.length > 0" style="font-weight: normal; color: #666">
        · 过滤 (AND):
        <NTag
          v-for="t in selectedTagList"
          :key="t"
          size="small"
          type="success"
          closable
          style="margin: 0 4px"
          @close="() => removeTag(t)"
        >
          {{ t }}
        </NTag>
      </small>
    </h2>

    <!-- prefix 切换 -->
    <div style="margin-bottom: 12px">
      <span style="color: #666; font-size: 12px; margin-right: 8px">前缀:</span>
      <NSpace :size="4" inline>
        <NButton
          v-for="p in sortedPrefixes"
          :key="p"
          size="small"
          :type="activePrefix === p ? 'primary' : 'default'"
          @click="activePrefix = p"
        >
          {{ p }}
        </NButton>
      </NSpace>
    </div>

    <!-- 当前 prefix 下的 values (多选 AND) -->
    <div style="margin-bottom: 16px">
      <span style="color: #666; font-size: 12px; margin-right: 8px">
        {{ activePrefix }}: 值 (多选 AND)
      </span>
      <NSpace :size="4" inline>
        <NButton
          v-for="v in currentValues"
          :key="v"
          size="small"
          :type="isSelected(activePrefix, v) ? 'success' : 'default'"
          ghost
          @click="toggleValue(v)"
        >
          {{ v }}
        </NButton>
        <span v-if="currentValues.length === 0" style="color: #999; font-size: 12px">
          (无值)
        </span>
      </NSpace>
    </div>

    <!-- 操作行 -->
    <NSpace style="margin-bottom: 16px">
      <NButton @click="clearFilter" :disabled="selectedTagList.length === 0">清空过滤</NButton>
      <NButton @click="reload" ghost>从磁盘重载</NButton>
    </NSpace>

    <NSpin :show="loading">
      <NEmpty v-if="!loading && filtered.length === 0" description="没有匹配的拍立得">
        <template #extra>
          <NButton @click="clearFilter">清空过滤</NButton>
        </template>
      </NEmpty>

      <div v-else style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px">
        <NCard v-for="s in filtered" :key="s.id" hoverable content-style="padding: 0">
          <a
            :href="`/bench/${encodeURIComponent(s.id)}`"
            target="_blank"
            rel="noopener"
            style="display: block; color: inherit; text-decoration: none; cursor: pointer"
            @click="(e: MouseEvent) => handleCardClick(e, s.id)"
          >
            <div style="aspect-ratio: 1; overflow: hidden; background: #eee">
              <SingleImagePreview
                :path="s.cover_asset?.path ?? null"
                :hash="s.cover_asset?.hash"
                :enable-lightbox="false"
              />
            </div>
            <div style="padding: 8px 12px">
              <code style="font-size: 12px">{{ s.id }}</code>
              <div style="margin-top: 4px; font-size: 12px; color: #666">
                {{ s.shot_date || (shotDateHint(s.id) || '—') }}
                <span v-if="!s.shot_date && shotDateHint(s.id)" style="color: #999">（由 id 推导）</span>
              </div>
            </div>
          </a>
        </NCard>
      </div>
    </NSpin>
  </div>
</template>