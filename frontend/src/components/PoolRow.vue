<!--
  PoolRow: 池页面单个 tag 行 (单格 NCard)

  职责:
  - 展示一个 tag 的所有可见信息 (key / canonical_name / aliases / notes / count)
  - 视觉按 isUndefined 区分: 已注册 (实线) vs 未定义 (虚线 + 浅背景)
  - 暴露操作: 已注册 → 编辑; 未定义 → 注册

  设计要点 (2026-09 引入):
  - 卡片化 vs NDataTable: 离开 NDataTable 的列约束, 给将来更复杂的自定义内容/行为
    (e.g. char 应援色 / 别名 chips / 元数据 inline 编辑) 留扩展空间.
  - **单格 NCard**: 用 Naive UI NCard 提供统一的卡片视觉 (border / radius / size),
    通过 content-style 抹掉默认 padding + 注入 flex 单行布局, 整张卡片只有"一格"高.
  - PoolIndexView 负责数据聚合 (registered ∪ undefined) + 排序 + filter,
    PoolRow 只关心单行渲染 + emit register / 跳编辑.
  - 已知字段名 (KNOWN_FIELDS) 与 tag-pool spec §2 字段约定一致.
-->

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { NCard, NTag, NButton } from 'naive-ui'

// 与 docs/spec/tag-pool.md §2 字段约定一致的硬编码字段名; 其它走 extras.
const KNOWN_FIELDS = ['canonical_name', 'aliases', 'notes', 'color_name', 'color_rgb']

const props = defineProps<{
  /** 前缀, 用于编辑 / 注册跳转 URL */
  prefix: string
  /** tag key (已去前缀). 用 tagKey 避免与 Vue 内置 key attribute 冲突. */
  tagKey: string
  /** 完整 tag (`prefix:key`), 用于显示 */
  fullTag: string
  /** metadata 字典; undefined tag 时为 {} */
  meta: Record<string, unknown>
  /** 拍立得使用数量 */
  usedCount: number
  /** 是否未定义 (未在池里注册) */
  isUndefined: boolean
}>()

const emit = defineEmits<{
  /** 未定义 tag 注册按钮: 由 caller 走 upsert_tag(prefix, key, {}) 后跳编辑页 */
  register: [fullTag: string]
}>()

const router = useRouter()

// 已知字段派生
const canonicalName = computed(() => (props.meta.canonical_name as string) || '')
const aliases = computed(() => (props.meta.aliases as string[]) || [])
const notes = computed(() => (props.meta.notes as string) || '')

// 额外字段 (除已知外的任意 key-value) → 单行紧凑展示
const extras = computed(() =>
  Object.entries(props.meta).filter(([k]) => !KNOWN_FIELDS.includes(k)),
)

// 应援色圆点: 判定 = meta.color_rgb 是否定义, 与 tag 类型 (char/非char) 解耦.
// 无 color_rgb → null → 不渲染 swatch 元素本身 (无占位 / 无 placeholder, 用户接受轻微视觉错位).
const swatchColor = computed(() => {
  const rgb = props.meta.color_rgb as string | undefined
  if (!rgb || !/^#[0-9a-fA-F]{6}$/.test(rgb)) return null
  return rgb
})

function gotoEdit() {
  router.push(`/pool/${props.prefix}/${encodeURIComponent(props.tagKey)}/edit`)
}

function onRegister() {
  emit('register', props.fullTag)
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}
</script>

<template>
  <!-- 单格 NCard: size=small 收高度, content-style 抹默认 padding + 注入 flex 单行布局. -->
  <!-- 已注册 (实线) / 未定义 (虚线) 通过 class 控制 NCard 内部 .n-card__border / .n-card__content. -->
  <!-- 行布局 (review 友好, 单行紧凑):
       canonical_name (眼第一落点) → fullTag (小字染色) → aliases NTag → notes → extras → (spacer) → usedCount → 状态 NTag → 操作按钮 -->
  <NCard
    size="small"
    :bordered="true"
    :hoverable="false"
    :class="['pool-row', { 'is-undefined': isUndefined }]"
    content-style="padding: 6px 12px; display: flex; align-items: center; gap: 10px; flex-wrap: nowrap; overflow-x: auto"
  >
    <span
      v-if="swatchColor"
      class="pool-row-swatch"
      :style="{ background: swatchColor }"
    />

    <span v-if="!isUndefined && canonicalName" class="pool-row-canonical">
      {{ canonicalName }}
    </span>

    <code class="pool-row-key">{{ fullTag }}</code>

    <span v-if="!isUndefined && aliases.length > 0" class="pool-row-aliases">
      <NTag
        v-for="a in aliases"
        :key="a"
        size="small"
        style="margin: 0 2px"
      >
        {{ a }}
      </NTag>
    </span>

    <span v-if="!isUndefined && notes" class="pool-row-notes">
      {{ truncate(notes, 80) }}
    </span>

    <span v-if="!isUndefined && extras.length > 0" class="pool-row-extras">
      <span
        v-for="[k, v] in extras"
        :key="k"
        class="pool-row-extra-item"
      >
        <span style="color: #999">{{ k }}=</span>
        <code>{{ truncate(String(v), 30) }}</code>
      </span>
    </span>

    <span v-if="isUndefined" class="pool-row-hint">
      已被 {{ usedCount }} 张拍立得引用, 未注册 metadata
    </span>

    <span style="flex: 1" />

    <span class="pool-row-count">{{ usedCount }} 张使用</span>

    <NTag v-if="isUndefined" size="small" type="info" :dashed="true">未定义</NTag>
    <NTag v-else size="small" type="success">已注册</NTag>

    <NButton
      v-if="isUndefined"
      size="small"
      type="primary"
      @click="onRegister"
    >
      注册
    </NButton>
    <NButton v-else size="small" @click="gotoEdit">编辑</NButton>
  </NCard>
</template>

<style scoped>
/* NCard 提供 border / radius / size 视觉, 此处只管卡片之间的间距 + 未定义态特殊样式. */
.pool-row {
  margin-bottom: 4px;
}
/* 未定义态: 边框变虚线 + 内部内容区背景变浅灰 (NCard 内部需要 :deep 穿透). */
.pool-row.is-undefined :deep(.n-card__border) {
  border-style: dashed;
  border-color: #999;
}
.pool-row.is-undefined :deep(.n-card__content) {
  background: #fafafa;
}
.pool-row-canonical {
  font-weight: 500;
  white-space: nowrap;
  flex-shrink: 0;
  border-radius: 3px;
}
.pool-row-key {
  /* 缩小字号 + 轻量化字重: canonical_name 是眼第一落点,
     fullTag 作为标识符/染色作用点放后面, 不抢戏. */
  font-weight: 500;
  font-size: 11px;
  white-space: nowrap;
  flex-shrink: 0;
}
/* 应援色圆点: 15px 直径 + 细黑边描边, 与 CharTag 的 swatch 视觉对齐.
   无 color_rgb → 元素整体不渲染 (用户接受"有 vs 没有"的轻微视觉错位). */
.pool-row-swatch {
  display: inline-block;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  border: 2px solid rgba(0, 0, 0, 0.15);
  flex-shrink: 0;
}
.pool-row-aliases {
  display: inline-flex;
  flex-shrink: 0;
}
.pool-row-notes {
  color: #666;
  font-size: 12px;
  white-space: nowrap;
  flex-shrink: 0;
}
.pool-row-extras {
  display: inline-flex;
  gap: 10px;
  font-size: 12px;
  flex-shrink: 0;
}
.pool-row-extra-item {
  white-space: nowrap;
}
.pool-row-hint {
  color: #999;
  font-size: 12px;
  font-style: italic;
  white-space: nowrap;
  flex-shrink: 0;
}
.pool-row-count {
  color: #666;
  font-size: 12px;
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
