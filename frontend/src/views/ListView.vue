<!--
  ListView: 浏览全部拍立得

  过滤 + 分组 + 组序 (纯客户端, L2):
    - 全表一次加载到 store, 之后过滤 / 分组 / 组序都在 computed 里走
    - "分组" 那一行 chip 是维度选择器: 它同时决定
        1) 下面 "值" 那行显示谁 (只有 prefix 维度才有值; 日期维度整行不渲染)
        2) 结果按它切成若干 section
    - 值 chip 多选 toggle; AND 逻辑: 选中的 tag 都需命中 polaroid.tags
    - "组顺序" 只决定 section 之间的先后, 不影响组内顺序
    - 组内顺序固定按 shot_date 早→晚, 空值沉底, 同日按 id 兜底 (不给控件)
    - 缺值组恒沉底

  分组 / 组序的纯逻辑在 lib/grouping.ts, 排序不变量在那里单独校验。
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NSpin, NEmpty, NSpace, NCard, NButton, NTag } from 'naive-ui'
import { usePolarscanStore } from '@/stores/polarscan'
import { shotDateHint } from '@/composables/usePathParse'
import SingleImagePreview from '@/components/SingleImagePreview.vue'
import {
  DATE_DIM,
  buildGroups,
  dirText,
  isDateDimOf,
  keyBasisLabel,
  naturalDir,
  type SortBasis,
  type SortDir,
} from '@/lib/grouping'

const router = useRouter()
const store = usePolarscanStore()

// prefix 顺序: char 放最前（审查主战场）, 其余按 schema 顺序
const PREFIX_ORDER = ['char', 'shot', 'event', 'theme', 'collection', 'composite', 'moment', 'sig']
const DEFAULT_DIM = 'char'
// 默认依据是数量而不是名称。2026-10-06 对真实索引 (_index.yaml, 483 条) 盘过:
// 角色维度分布高度倾斜 —— 一档 23%、次三档各约 10%、其余 40 多个名字各 1~2 张。
// 按名称进落地是一串 1 张卡的组, 找不到实际在用的角色。
const DEFAULT_BASIS: SortBasis = 'count'

const activeDim = ref<string>(DEFAULT_DIM)
const selectedTags = ref<Set<string>>(new Set())
const tagGroups = ref<Record<string, string[]>>({})
const sortBasis = ref<SortBasis>(DEFAULT_BASIS)
const sortDir = ref<SortDir>('desc')
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
    // 初始方向取该 (维度, 依据) 组合的自然默认, 而不是写死的降序
    sortDir.value = naturalDir(activeDim.value, sortBasis.value)
  } finally {
    loading.value = false
  }
})

/** "日期" 不是 prefix, 所以它排在所有 prefix 前面, 不参与值筛选。 */
const sortedDims = computed(() => {
  const known = PREFIX_ORDER.filter((p) => p in tagGroups.value)
  const extra = Object.keys(tagGroups.value).filter((p) => !PREFIX_ORDER.includes(p))
  return [DATE_DIM, ...known, ...extra]
})

const isDateDim = computed(() => isDateDimOf(activeDim.value))

const currentValues = computed(() => tagGroups.value[activeDim.value] ?? [])

const selectedTagList = computed(() => Array.from(selectedTags.value))

/** 纯客户端 AND 过滤. */
const filtered = computed(() => {
  const required = selectedTagList.value
  if (required.length === 0) return store.summaries
  return store.summaries.filter((s) => required.every((t) => s.tags?.includes(t)))
})

const groups = computed(() => buildGroups(filtered.value, activeDim.value, sortBasis.value, sortDir.value))

const dirTextLabel = computed(() => dirText(activeDim.value, sortBasis.value, sortDir.value))
const dirArrow = computed(() => (sortDir.value === 'desc' ? '↓' : '↑'))

function isSelected(value: string): boolean {
  // value 现在是带 prefix 的完整 tag (后端契约: 见 polarscan/api.py:all_tags_with_prefix).
  return selectedTags.value.has(value)
}

function toggleValue(value: string) {
  const next = new Set(selectedTags.value)
  if (next.has(value)) next.delete(value)
  else next.add(value)
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

function setDim(key: string) {
  if (key === activeDim.value) return
  activeDim.value = key
  // 只保留属于当前维度的筛选: 看到的筛选 = 看到的维度
  selectedTags.value = new Set([...selectedTags.value].filter((t) => t.split(':')[0] === key))
  sortDir.value = naturalDir(key, sortBasis.value)
}

function setBasis(basis: SortBasis) {
  if (basis === sortBasis.value) return
  sortBasis.value = basis
  sortDir.value = naturalDir(activeDim.value, basis)
}

function toggleDir() {
  sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
}

/** 渲染时去掉 prefix (后端契约返回的是完整 tag, 但 UI 在 prefix chip 已选定的情况下,
 *  显示 value 部分即可). 无冒号的项按 legacy 处理, 原样返回. */
function valueDisplay(v: string): string {
  const c = v.indexOf(':')
  return c > 0 ? v.slice(c + 1) : v
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

function handleCardClick(e: MouseEvent, id: string) {
  // ctrl/cmd/middle click 让浏览器原生处理 (新标签页);其他走 SPA 路由。
  if (e.ctrlKey || e.metaKey || e.button === 1) return
  e.preventDefault()
  router.push(`/bench/${encodeURIComponent(id)}`)
}
</script>

<template>
  <div>
    <h2 style="margin-top: 0">
      浏览 ({{ filtered.length }} / {{ totalCount }})
      <small style="font-weight: normal; color: #666">
        · {{ groups.length }} 组
        <template v-if="selectedTagList.length > 0">
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
        </template>
      </small>
    </h2>

    <!-- 分组维度: 同时决定"值"那行显示谁 + 结果按它切 section -->
    <div style="margin-bottom: 12px">
      <span style="color: #666; font-size: 12px; margin-right: 8px">分组:</span>
      <NSpace :size="4" inline>
        <NButton
          v-for="d in sortedDims"
          :key="d"
          size="small"
          :type="activeDim === d ? 'primary' : 'default'"
          @click="setDim(d)"
        >
          {{ d === DATE_DIM ? '日期' : d }}
        </NButton>
      </NSpace>
    </div>

    <!-- 当前维度下的 values (多选 AND)。日期维度没有值可筛, 整行不渲染。 -->
    <div v-if="!isDateDim" style="margin-bottom: 16px">
      <span style="color: #666; font-size: 12px; margin-right: 8px">
        {{ activeDim }}: 值 (多选 AND)
      </span>
      <NSpace :size="4" inline>
        <NButton
          v-for="v in currentValues"
          :key="v"
          size="small"
          :type="isSelected(v) ? 'success' : 'default'"
          ghost
          @click="toggleValue(v)"
        >
          {{ valueDisplay(v) }}
        </NButton>
        <span v-if="currentValues.length === 0" style="color: #999; font-size: 12px">
          (无值)
        </span>
      </NSpace>
    </div>

    <!-- 组顺序: 只决定 section 之间的先后 -->
    <div style="margin-bottom: 16px">
      <span style="color: #666; font-size: 12px; margin-right: 8px">组顺序:</span>
      <NSpace :size="4" inline>
        <NButton
          size="small"
          :type="sortBasis === 'key' ? 'primary' : 'default'"
          @click="setBasis('key')"
        >
          {{ keyBasisLabel(activeDim) }}
        </NButton>
        <NButton
          size="small"
          :type="sortBasis === 'count' ? 'primary' : 'default'"
          @click="setBasis('count')"
        >
          按数量
        </NButton>
        <NButton size="small" ghost @click="toggleDir">
          {{ dirArrow }} {{ dirTextLabel }}
        </NButton>
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

      <div v-else>
        <section v-for="g in groups" :key="g.key" class="group">
          <div class="group-head">
            <span class="group-key">
              <span v-if="!isDateDim" class="group-prefix">{{ activeDim }}:</span>{{ g.key }}
            </span>
            <span class="group-rule" />
            <span class="group-count">{{ g.items.length }} 张</span>
          </div>
          <div class="group-grid">
            <NCard v-for="s in g.items" :key="s.id" hoverable content-style="padding: 0">
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
        </section>
      </div>
    </NSpin>
  </div>
</template>

<style scoped>
.group {
  border: 1px solid #e5e5e7;
  border-radius: 8px;
  margin-bottom: 20px;
  background: #fff;
  overflow: hidden;
}
.group-head {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 12px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid #f0f0f2;
}
.group-key {
  font-size: 13px;
  font-weight: 600;
}
.group-prefix {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  font-weight: 400;
  color: #999;
}
.group-rule {
  flex: 1;
  height: 1px;
  background: #f0f0f2;
}
.group-count {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: #888;
}
.group-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  padding: 16px;
}
</style>
