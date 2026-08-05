<!--
  PolaroidTagsEditor: 角色 (char) + 其他标签 (tag) 的统一编辑 UI

  职责:
  - v-model 双向绑定 tag 列表 (modelValue / update:modelValue)
  - 自动拆分/合并 char 与 other (e.g. `char:my_push` vs `event:xxx`)
  - 提供 chip 输入 + 候选补全 + 角色池快捷按钮

  设计要点 (2026-08 重构):
  - 归并自 BenchView 的两段 chip UI, NewView 也走同一份 (不再用 primaryChar 独立 ref).
  - 内部用两个 useChipStream 实例 (autoPrefix='char' / freeform).
  - 唯一的 watcher 用于 props.modelValue 变化时同步内部 streams (切换 polaroid 时必须).
  - 用户操作 chip 走 emit merged, 不依赖 watcher 链.
-->
<script setup lang="ts">
import { computed, watch } from 'vue'
import { NCard, NAutoComplete, NButton, NTag, NSpace } from 'naive-ui'
import { useChipStream } from '@/composables/useChipStream'

const props = defineProps<{
  /** 受控的完整 tags 列表 (v-model) */
  modelValue: string[]
  /** 候选集 (带前缀的 tag 全集, 如 ['char:strawberry', 'shot:pair', ...]) */
  suggestions: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [tags: string[]]
}>()

// char 流: autoPrefix='char', 用户输入 'my_push' 自动补为 'char:my_push'
const charStream = useChipStream({
  autoPrefix: 'char',
  allowFreeform: false,
  suggestions: () => props.suggestions,
})
const {
  modelValue: charTags,
  query: charQuery,
  suggestItems: charItems,
  addChip: charAddChip,
  removeChip: charRemoveChip,
  onInput: charOnInput,
  setTags: charSetTags,
} = charStream

// other 流: 自由格式, 用户输入完整 tag (e.g. 'event:shenshan_3rd_om_cd')
const otherStream = useChipStream({
  autoPrefix: '',
  allowFreeform: true,
  suggestions: () => props.suggestions,
})
const {
  modelValue: otherTags,
  query: otherQuery,
  suggestItems: otherItems,
  addChip: otherAddChip,
  removeChip: otherRemoveChip,
  onInput: otherOnInput,
  setTags: otherSetTags,
} = otherStream

/** 把完整 tags 列表拆分成 char / other (按前缀).
 *  规则:
 *  - char:xxx → char
 *  - 无冒号的纯文本 → char (历史遗留, 视为无名角色)
 *  - 其他带冒号 (event:..., shot:..., sig:...) → other */
function splitTags(tags: string[]): { char: string[]; other: string[] } {
  const cs: string[] = []
  const os: string[] = []
  for (const t of tags) {
    if (t.startsWith('char:') || !t.includes(':')) cs.push(t)
    else os.push(t)
  }
  return { char: cs, other: os }
}

function syncFromProps(next: string[]) {
  const { char, other } = splitTags(next)
  charSetTags(char)
  otherSetTags(other)
}

/** 同步外部 modelValue 到内部 streams. 触发时机:
 *  - immediate: 初次挂载 (父组件 v-model 已传入值, 可能是空 polaroid)
 *  - watch: 父组件切换 polaroid / 外部修改 (e.g. load 完后)
 *  这是组件唯一允许的 watcher — props 是外部输入, 不能假设父组件会显式调用 setTags. */
watch(
  () => props.modelValue,
  (next) => syncFromProps(next),
  { immediate: true },
)

/** char/other chip 改动 → emit 合并后的 tags 给父组件 */
function emitMerged() {
  const merged = [...charTags.value, ...otherTags.value]
  emit('update:modelValue', merged)
}

// 包装 useChipStream 的 add/remove, 让每次操作都触发 emit
function charAdd(raw: string) {
  if (charAddChip(raw)) emitMerged()
}
function charRemove(tag: string) {
  charRemoveChip(tag)
  emitMerged()
}
function otherAdd(raw: string) {
  if (otherAddChip(raw)) emitMerged()
}
function otherRemove(tag: string) {
  otherRemoveChip(tag)
  emitMerged()
}

// 角色池快捷按钮: 从 suggestions 提取已知 char 名的集合
const charPool = computed(() =>
  props.suggestions
    .filter((s) => s.startsWith('char:'))
    .map((s) => s.slice(5)),
)
const shotPool = computed(() =>
  props.suggestions
    .filter((s) => s.startsWith('shot:'))
    .map((s) => s.slice(5)),
)
const sigPool = computed(() =>
  props.suggestions
    .filter((s) => s.startsWith('sig:'))
    .map((s) => s.slice(4)),
)

// NAutoComplete options: 由 suggestItems 直接派生 (filterable=false, 过滤逻辑保留在 useChipStream)
const charOptions = computed(() =>
  charItems.value.map((s) => ({ label: s, value: s })),
)
const otherOptions = computed(() =>
  otherItems.value.map((s) => ({ label: s, value: s })),
)

// NAutoComplete 输入时: 更新 query ref + 重算候选
function onCharQueryInput(v: string) {
  charQuery.value = v
  charOnInput()
}
function onOtherQueryInput(v: string) {
  otherQuery.value = v
  otherOnInput()
}
</script>

<template>
  <div class="polaroid-tags-editor">
    <!-- 角色 (char) -->
    <NCard title="角色 (char)" size="small" style="margin-bottom: 12px">
      <div>
        <NTag
          v-for="tag in charTags"
          :key="tag"
          closable
          style="margin: 2px"
          @close="charRemove(tag)"
        >
          {{ tag }}
        </NTag>
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
        <NButton
          v-for="c in charPool.slice(0, 18)"
          :key="c"
          size="small"
          text
          @click="charAdd(`char:${c}`)"
        >
          + {{ c }}
        </NButton>
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
