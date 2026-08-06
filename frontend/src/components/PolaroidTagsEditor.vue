<!--
  PolaroidTagsEditor: 角色 (char) + 其他标签 (tag) 的统一编辑 UI

  职责:
  - v-model 双向绑定 tag 列表 (modelValue / update:modelValue)
  - **单源头**: charTags / otherTags 都从 props.modelValue 派生, 显示时按前缀过滤;
    添加走 emit update:modelValue, 不维护内部副本, 因此不存在跨区重复 / 跨区跳位.
  - chip 输入 + 候选补全 + 角色池快捷按钮
  - 角色 chip 走 CharTag (RGB 色块 + 隐藏前缀 + hovertip + 点击跳转)

  设计要点 (2026-08 重构, B1+B2+应援色):
  - 归并自 BenchView 的两段 chip UI, NewView 也走同一份
  - 内部用两个 useChipStream 实例, 但仅用于 query + 候选, 不持有 modelValue
  - 不再有 watcher / splitTags 双向同步; 数据归属 = props.modelValue
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { NCard, NAutoComplete, NButton, NTag, NSpace } from 'naive-ui'
import { useChipStream } from '@/composables/useChipStream'
import CharTag from './CharTag.vue'

const props = defineProps<{
  /** 受控的完整 tags 列表 (v-model) */
  modelValue: string[]
  /** 候选集 (带前缀的 tag 全集, 如 ['char:strawberry', 'shot:pair', ...]) */
  suggestions: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [tags: string[]]
}>()

const router = useRouter()

// ---------- 单源头派生 ----------
/** 严格判定: 'char:' 前缀才视为 char tag. 无冒号 legacy 落入 other (数据正确, 仅显示层). */
function isCharTag(t: string): boolean {
  return t.startsWith('char:')
}
const charTags = computed(() => props.modelValue.filter(isCharTag))
const otherTags = computed(() => props.modelValue.filter((t) => !isCharTag(t)))

// ---------- 候选流 (仅 query + 候选, 不持有 modelValue) ----------
const charStream = useChipStream({
  autoPrefix: 'char',
  allowFreeform: false,
  suggestions: () => props.suggestions,
  getSelected: () => props.modelValue,
})
const {
  query: charQuery,
  suggestItems: charItems,
  onInput: charOnInput,
  clearQuery: charClearQuery,
} = charStream

const otherStream = useChipStream({
  allowFreeform: true,
  suggestions: () => props.suggestions,
  getSelected: () => props.modelValue,
})
const {
  query: otherQuery,
  suggestItems: otherItems,
  onInput: otherOnInput,
  clearQuery: otherClearQuery,
} = otherStream

// ---------- add / remove → emit 新 union ----------
function charAdd(raw: string) {
  const tag = charStream.computeTag(raw)
  if (!tag) return
  emit('update:modelValue', [...props.modelValue, tag])
  charClearQuery()
}
function charRemove(tag: string) {
  emit('update:modelValue', props.modelValue.filter((t) => t !== tag))
}
function otherAdd(raw: string) {
  const tag = otherStream.computeTag(raw)
  if (!tag) return
  emit('update:modelValue', [...props.modelValue, tag])
  otherClearQuery()
}
function otherRemove(tag: string) {
  emit('update:modelValue', props.modelValue.filter((t) => t !== tag))
}

// ---------- 池子快捷按钮 ----------
const charPool = computed(() =>
  props.suggestions.filter((s) => s.startsWith('char:')).map((s) => s.slice(5)),
)
const shotPool = computed(() =>
  props.suggestions.filter((s) => s.startsWith('shot:')).map((s) => s.slice(5)),
)
const sigPool = computed(() =>
  props.suggestions.filter((s) => s.startsWith('sig:')).map((s) => s.slice(4)),
)

const charOptions = computed(() => charItems.value.map((s) => ({ label: s, value: s })))
const otherOptions = computed(() => otherItems.value.map((s) => ({ label: s, value: s })))

function onCharQueryInput(v: string) {
  charQuery.value = v
  charOnInput()
}
function onOtherQueryInput(v: string) {
  otherQuery.value = v
  otherOnInput()
}

// char chip 点击 → 跳转到该角色 pool 编辑页 (CharTag emit 的是 key, 已去前缀)
function goChar(key: string) {
  router.push(`/pool/char/${encodeURIComponent(key)}/edit`)
}
</script>

<template>
  <div class="polaroid-tags-editor">
    <!-- 角色 (char) -->
    <NCard title="角色 (char)" size="small" style="margin-bottom: 12px">
      <div>
        <CharTag
          v-for="tag in charTags"
          :key="tag"
          :tag="tag"
          closable
          @close="charRemove(tag)"
          @click="goChar"
        />
      </div>
      <NSpace style="margin-top: 8px">
        <NAutoComplete
          :value="charQuery"
          :options="charOptions"
          :filterable="false"
          :default-active-first-option="false"
          clearable
          placeholder="角色标识 (例: my_push)"
          style="min-width: 320px"
          @update:value="onCharQueryInput"
          @select="(v: string) => charAdd(v)"
          @keyup.enter="charAdd(charQuery)"
        />
        <NButton @click="charAdd(charQuery)">+ 角色</NButton>
      </NSpace>
      <div v-if="charPool.length > 0" style="margin-top: 8px">
        <span style="color: #666; font-size: 12px">角色池:</span>
        <CharTag
          v-for="c in charPool.slice(0, 18)"
          :key="c"
          :tag="`char:${c}`"
          interactive
          @click="(k) => charAdd(`char:${k}`)"
        />
      </div>
    </NCard>

    <!-- 其他标签 -->
    <NCard title="其他标签 (tag)" size="small">
      <div>
        <NTag
          v-for="tag in otherTags"
          :key="tag"
          closable
          :type="tag.startsWith('shot:') ? 'success' : tag.startsWith('sig:') ? 'warning' : 'default'"
          style="margin: 2px"
          @close="otherRemove(tag)"
        >
          {{ tag }}
        </NTag>
      </div>
      <NSpace style="margin-top: 8px">
        <NAutoComplete
          :value="otherQuery"
          :options="otherOptions"
          :filterable="false"
          :default-active-first-option="false"
          clearable
          placeholder="其他标签 (例: event:shenshan_3rd_om_cd, shot:pair)"
          style="min-width: 360px"
          @update:value="onOtherQueryInput"
          @select="(v: string) => otherAdd(v)"
          @keyup.enter="otherAdd(otherQuery)"
        />
        <NButton @click="otherAdd(otherQuery)">+ 标签</NButton>
      </NSpace>
      <div v-if="shotPool.length > 0 || sigPool.length > 0" style="margin-top: 8px">
        <span style="color: #666; font-size: 12px">shot / sig 池:</span>
        <NButton
          v-for="s in shotPool.slice(0, 8)"
          :key="'shot-' + s"
          size="small"
          text
          type="success"
          @click="otherAdd(`shot:${s}`)"
        >
          + shot:{{ s }}
        </NButton>
        <NButton
          v-for="s in sigPool.slice(0, 8)"
          :key="'sig-' + s"
          size="small"
          text
          type="warning"
          @click="otherAdd(`sig:${s}`)"
        >
          + sig:{{ s }}
        </NButton>
      </div>
    </NCard>
  </div>
</template>

<style scoped>
.polaroid-tags-editor {
  display: flex;
  flex-direction: column;
}
</style>