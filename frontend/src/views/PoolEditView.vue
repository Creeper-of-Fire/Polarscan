<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  NSpin, NForm, NFormItem, NInput, NButton, NSpace, NDescriptions, NDescriptionsItem,
  useMessage, useDialog,
} from 'naive-ui'
import { poolApi } from '@/api'
import type { PolaroidSummary } from '@/types'

const props = defineProps<{ prefix: string; key: string }>()
const router = useRouter()
const route = useRoute()
const message = useMessage()
const dialog = useDialog()

const info = ref<Record<string, unknown>>({})
const usedBy = ref<PolaroidSummary[]>([])
const loading = ref(false)

const canonicalName = ref('')
const aliasesText = ref('')
const notes = ref('')
const extraJson = ref('')

const returnTo = computed(() => (route.query.return_to as string) || `/pool/${props.prefix}`)

onMounted(async () => {
  loading.value = true
  try {
    const r = await poolApi.edit(props.prefix, props.key)
    info.value = r.info
    usedBy.value = r.used_by
    canonicalName.value = (r.info.canonical_name as string) || ''
    aliasesText.value = ((r.info.aliases as string[]) || []).join(', ')
    notes.value = (r.info.notes as string) || ''
  } finally {
    loading.value = false
  }
})

async function save() {
  const aliases = aliasesText.value.split(',').map((s) => s.trim()).filter(Boolean)
  const r = await poolApi.save(props.prefix, props.key, {
    canonical_name: canonicalName.value,
    aliases,
    notes: notes.value,
    extra_json: extraJson.value,
    return_to: returnTo.value,
  })
  if (r.ok) {
    message.success('已保存')
    router.push(returnTo.value)
  } else {
    message.error('保存失败')
  }
}

async function deleteMeta() {
  dialog.warning({
    title: '从池中删除元数据',
    content: `从池中删除 ${props.prefix}:${props.key} 的元数据？此操作不会移除拍立得上的标签。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      await poolApi.delete(props.prefix, props.key)
      message.success('已删除')
      router.push(`/pool/${props.prefix}`)
    },
  })
}

const extras = computed(() =>
  Object.entries(info.value).filter(([k]) => !['canonical_name', 'aliases', 'notes'].includes(k)),
)
</script>

<template>
  <div>
    <h2 style="margin-top: 0">
      编辑 <code>{{ prefix }}:{{ key }}</code>
    </h2>

    <NSpin :show="loading">
      <div v-if="!loading">
        <p style="color: #666">
          被 {{ usedBy.length }} 张拍立得使用:
          <RouterLink v-for="p in usedBy.slice(0, 8)" :key="p.id" :to="`/bench/${encodeURIComponent(p.id)}`"
                      style="margin-right: 8px">
            <code>{{ p.id }}</code>
          </RouterLink>
          <span v-if="usedBy.length > 8">…</span>
        </p>

        <NForm label-placement="top" style="max-width: 720px">
          <NFormItem label="规范名称（canonical_name）">
            <NInput v-model:value="canonicalName" placeholder="供界面显示，可留空" />
          </NFormItem>
          <NFormItem label="别名（aliases，逗号分隔）">
            <NInput v-model:value="aliasesText" placeholder="供搜索使用" />
          </NFormItem>
          <NFormItem label="备注（notes）">
            <NInput v-model:value="notes" type="textarea" :rows="4" />
          </NFormItem>
          <NFormItem v-if="extras.length > 0" label="已有额外字段">
            <NDescriptions :column="1" bordered size="small">
              <NDescriptionsItem v-for="[k, v] in extras" :key="k" :label="k">
                <code>{{ v }}</code>
              </NDescriptionsItem>
            </NDescriptions>
          </NFormItem>
          <NFormItem label='附加字段 JSON（例: {"date": "2025-10-12", "venue": "成都"}）'>
            <NInput v-model:value="extraJson" type="textarea" :rows="3" />
          </NFormItem>
          <NSpace>
            <NButton type="primary" @click="save">💾 保存</NButton>
            <NButton @click="router.push(returnTo)">取消</NButton>
            <NButton type="error" ghost @click="deleteMeta">从池删除元数据</NButton>
          </NSpace>
        </NForm>
      </div>
    </NSpin>
  </div>
</template>