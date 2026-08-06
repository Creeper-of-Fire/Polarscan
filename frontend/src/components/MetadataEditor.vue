<!--
  MetadataEditor: 任意 JSON 透传字段的编辑器

  职责:
  - v-model 双向绑定 metadata 字典
  - 用户直接编辑 JSON 文本; 解析成功则 emit dict, 失败显示错误但不丢文本

  设计要点 (2026-08):
  - 与现有 PolaroidTagsEditor 风格保持一致 (NCard 包裹)
  - 用 NInput textarea 输入, 即"JSON 编辑器"
  - 解析失败时保留文本让用户修复, 不强行重置
  - core 不解析 metadata 内部结构, 这里也不做 schema 校验
-->
<script setup lang="ts">
import { ref, watch } from 'vue'
import { NCard, NInput, NSpace, NText } from 'naive-ui'

const props = defineProps<{
  /** 受控的 metadata 字典 (v-model). undefined / null 时视为空 dict. */
  modelValue?: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:modelValue': [metadata: Record<string, unknown>]
}>()

// 用户输入的 JSON 文本. 解析成功时与 modelValue 同步.
const text = ref<string>('')
const parseError = ref<string | null>(null)

function tryParseJson(s: string):
  | { ok: true; value: Record<string, unknown> }
  | { ok: false; error: string } {
  const trimmed = s.trim()
  if (trimmed === '') return { ok: true, value: {} }
  try {
    const parsed = JSON.parse(trimmed)
    if (
      typeof parsed !== 'object' ||
      parsed === null ||
      Array.isArray(parsed)
    ) {
      return {
        ok: false,
        error: 'metadata 必须是 JSON object, 例: {"rating": 5}',
      }
    }
    return { ok: true, value: parsed as Record<string, unknown> }
  } catch (e) {
    return {
      ok: false,
      error: `JSON 解析失败: ${(e as Error).message}`,
    }
  }
}

function syncTextFromProps(next: Record<string, unknown> | undefined) {
  text.value = JSON.stringify(next ?? {}, null, 2)
  parseError.value = null
}

function onTextInput(v: string) {
  text.value = v
  const result = tryParseJson(v)
  if (result.ok) {
    parseError.value = null
    emit('update:modelValue', result.value)
  } else {
    parseError.value = result.error
    // 不 emit — 等用户修复
  }
}

// 父组件切换 polaroid / 外部修改 metadata → 同步内部 text.
// 这是组件唯一允许的 watcher — props 是外部输入, 不能假设父组件会显式调 reset.
watch(
  () => props.modelValue,
  (next) => syncTextFromProps(next),
  { immediate: true, deep: true },
)
</script>

<template>
  <NCard title="元数据 (metadata)" size="small">
    <NSpace vertical>
      <NInput
        type="textarea"
        :value="text"
        :autosize="{ minRows: 4, maxRows: 16 }"
        placeholder='任意 JSON object, 例: {"rating": 5, "source": "scanner_x"}'
        @update:value="onTextInput"
      />
      <NText v-if="parseError" type="error" style="font-size: 12px">
        {{ parseError }}
      </NText>
      <NText v-else style="font-size: 12px; color: #888">
        core 不解析 metadata 内部结构 — 任意 JSON object 都会被原样保存。
      </NText>
    </NSpace>
  </NCard>
</template>