<!--
  AssetListEditor: 拍立得资产列表的展示 + 字段编辑

  职责:
  - v-model 双向绑定资产列表 (modelValue / update:modelValue)
  - 每行: thumb + role + captured_at + device + remove
  - 完全不知道 caller 是 "新建" 还是 "编辑", 也不知道何时落库
  - 添加走 caller (dropzone 决定是 append_files 还是直接 mutate)

  设计要点:
  - 不接受 path 编辑 (path 是 F: 盘绝对路径, 改它需要走 append_files; 这是 caller 的职责)
  - 每次字段编辑/移除 → 整个数组 emit 一次 → parent 拿到 consistent state
  - role 用 NAutoComplete: 标准值下拉 + 自由输入 (业务上偶尔有 front_v2 / back_signature 之类)
  - 每行 thumb 走统一的 (path, hash) by-path 契约;不需要 polaroidId
-->
<script setup lang="ts">
import { computed, h } from 'vue'
import {
  NInput, NButton, NSpace, NAutoComplete,
  NForm, NFormItem, NEmpty,
} from 'naive-ui'
import SingleImagePreview from '@/components/SingleImagePreview.vue'
import type { Asset } from '@/types'

const ROLE_STANDARD = ['front', 'back', 'additional']
const ROLE_OPTIONS = computed(() =>
  ROLE_STANDARD.map((r) => ({ label: r, value: r })),
)

const props = defineProps<{
  /** 受控的资产列表 (v-model) */
  modelValue: Asset[]
}>()

const emit = defineEmits<{
  'update:modelValue': [assets: Asset[]]
}>()

function updateAsset(idx: number, patch: Partial<Asset>) {
  const next = [...props.modelValue]
  next[idx] = { ...next[idx], ...patch }
  emit('update:modelValue', next)
}

function removeAsset(idx: number) {
  emit(
    'update:modelValue',
    props.modelValue.filter((_, i) => i !== idx),
  )
}

// 空态: NEmpty 渲染 (naive-ui 元件, 无手撸 HTML)
function renderEmpty() {
  return h(NEmpty, { description: '还没有资产', size: 'small' })
}
</script>

<template>
  <div class="asset-list-editor">
    <component :is="renderEmpty()" v-if="modelValue.length === 0" />

    <div
      v-for="(asset, idx) in modelValue"
      v-else
      :key="`${asset.path}-${idx}`"
      class="ale-row"
    >
      <div class="ale-thumb">
        <SingleImagePreview
          :path="asset.path"
          :hash="asset.hash"
          :enable-lightbox="false"
        />
      </div>

      <NForm label-placement="top" size="small" class="ale-fields" :show-feedback="false">
        <NSpace :wrap="true" :size="12">
          <NFormItem label="角色 (role)">
            <NAutoComplete
              :value="asset.role"
              :options="ROLE_OPTIONS"
              clearable
              placeholder="front / back / additional / ..."
              style="min-width: 220px"
              @update:value="(v: string) => updateAsset(idx, { role: v })"
            />
          </NFormItem>
          <NFormItem label="拍摄时间 (captured_at)">
            <NInput
              :value="asset.captured_at ?? ''"
              placeholder="ISO 8601 (例: 2026-08-04T10:00:00)"
              style="min-width: 240px"
              @update:value="(v: string) => updateAsset(idx, { captured_at: v || null })"
            />
          </NFormItem>
          <NFormItem label="设备 (device)">
            <NInput
              :value="asset.device ?? ''"
              placeholder="例: iPhone 15"
              style="min-width: 200px"
              @update:value="(v: string) => updateAsset(idx, { device: v || null })"
            />
          </NFormItem>
        </NSpace>
        <code class="ale-path" :title="asset.path">{{ asset.path }}</code>
      </NForm>

      <NButton quaternary type="error" circle @click="removeAsset(idx)">×</NButton>
    </div>
  </div>
</template>

<style scoped>
.asset-list-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ale-row {
  display: grid;
  grid-template-columns: 96px 1fr auto;
  gap: 12px;
  align-items: flex-start;
  padding: 8px;
  border: 1px solid #eee;
  border-radius: 4px;
  background: #fafafa;
}
.ale-thumb {
  width: 96px;
  height: 96px;
  background: #eee;
  border-radius: 4px;
  overflow: hidden;
}
.ale-fields {
  min-width: 0;
}
.ale-path {
  display: block;
  margin-top: 6px;
  font-size: 11px;
  color: #999;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
