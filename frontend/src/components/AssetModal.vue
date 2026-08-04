<script setup lang="ts">
import { ref, watch } from 'vue'
import { NModal, NButton, NSpace, NInput, useMessage } from 'naive-ui'
import type { Asset } from '@/types'

const props = defineProps<{
  show: boolean
  pid: string
  initial: Asset[]
}>()
const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'saved'): void
}>()

const message = useMessage()
const assets = ref<Asset[]>([])
const saving = ref(false)
const errorMsg = ref('')

watch(
  () => [props.show, props.initial],
  ([show]) => {
    if (show) {
      assets.value = JSON.parse(JSON.stringify(props.initial))
      errorMsg.value = ''
    }
  },
  { immediate: true },
)

function close() {
  emit('update:show', false)
}

function moveUp(i: number) {
  if (i <= 0) return
  const tmp = assets.value[i - 1]
  assets.value[i - 1] = assets.value[i]
  assets.value[i] = tmp
}
function moveDown(i: number) {
  if (i >= assets.value.length - 1) return
  const tmp = assets.value[i + 1]
  assets.value[i + 1] = assets.value[i]
  assets.value[i] = tmp
}

async function save() {
  for (const a of assets.value) {
    if (!a.path || !String(a.path).trim()) {
      errorMsg.value = '每行必须有 path'
      return
    }
  }
  saving.value = true
  errorMsg.value = ''
  try {
    const r = await fetch(`/bench/${encodeURIComponent(props.pid)}/save-assets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        assets: assets.value.map((a) => ({
          role: a.role || 'front',
          path: String(a.path).trim(),
          captured_at: a.captured_at || null,
          device: a.device || null,
        })),
      }),
    })
    if (!r.ok) {
      const t = await r.text()
      throw new Error(`HTTP ${r.status} - ${t}`)
    }
    message.success('已保存')
    emit('saved')
    close()
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <NModal :show="show" preset="card" style="width: 720px" :title="`编辑资产 - ${pid}`"
          :mask-closable="!saving" :on-close="close">
    <p style="color: #666">修改 role / captured_at / device。不能增删 path — 增删走 dropzone / 追加。</p>

    <div v-for="(a, i) in assets" :key="i"
         style="display: grid; grid-template-columns: 1fr 2fr 1fr 1fr auto auto; gap: 8px; align-items: center; margin-bottom: 8px">
      <NInput v-model:value="a.role" placeholder="role" size="small" />
      <NInput v-model:value="a.path" placeholder="path" size="small" readonly />
      <NInput v-model:value="a.captured_at" placeholder="captured_at (ISO)" size="small" />
      <NInput v-model:value="a.device" placeholder="device" size="small" />
      <NButton size="small" :disabled="i === 0" @click="moveUp(i)">↑</NButton>
      <NButton size="small" :disabled="i === assets.length - 1" @click="moveDown(i)">↓</NButton>
    </div>

    <p v-if="errorMsg" style="color: #c00">{{ errorMsg }}</p>

    <template #footer>
      <NSpace>
        <NButton @click="close">取消</NButton>
        <NButton type="primary" :loading="saving" @click="save">保存</NButton>
      </NSpace>
    </template>
  </NModal>
</template>