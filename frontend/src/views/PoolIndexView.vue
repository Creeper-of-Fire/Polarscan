<script setup lang="ts">
import { onMounted, ref, computed, h } from 'vue'
import { useRouter } from 'vue-router'
import { NSpin, NEmpty, NDataTable, NTag, NButton, NSpace } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { poolApi } from '@/api'
import type { PoolItem } from '@/types'

const props = defineProps<{ prefix: string }>()
const router = useRouter()

const items = ref<PoolItem[]>([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    items.value = await poolApi.index(props.prefix)
  } finally {
    loading.value = false
  }
})

const columns = computed<DataTableColumns<PoolItem>>(() => [
  { title: '键', key: 'key', width: 180, render: (row) => row.key },
  {
    title: '规范名称',
    key: 'canonical_name',
    render: (row) => (row.meta.canonical_name as string) || '—',
  },
  {
    title: '别名',
    key: 'aliases',
    render: (row) => {
      const aliases = (row.meta.aliases as string[]) || []
      if (aliases.length === 0) return '—'
      return h_NSpace_aliases(aliases)
    },
  },
  {
    title: '备注',
    key: 'notes',
    ellipsis: { tooltip: true },
    render: (row) => truncate(((row.meta.notes as string) || ''), 80),
  },
  {
    title: '其他字段',
    key: 'extras',
    render: (row) => h_extras(row.meta),
  },
  { title: '使用数量', key: 'count', width: 100 },
  {
    title: '',
    key: 'actions',
    width: 100,
    render: (row) =>
      h(
        NButton as never,
        { size: 'small', onClick: () => router.push(`/pool/${props.prefix}/${encodeURIComponent(row.key)}/edit`) },
        { default: () => '编辑' },
      ),
  },
])

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '…' : s
}

function h_NSpace_aliases(aliases: string[]) {
  // 简化：直接返回字符串，Naive 表格里用 NSpace 会有渲染问题，先用逗号分隔
  return aliases.join(', ')
}

function h_extras(meta: Record<string, unknown>) {
  const entries = Object.entries(meta).filter(
    ([k]) => !['canonical_name', 'aliases', 'notes'].includes(k),
  )
  if (entries.length === 0) return '—'
  return entries.map(([k, v]) => `${k}=${v}`).join(', ')
}
</script>

<template>
  <div>
    <h2 style="margin-top: 0">
      <code>{{ prefix }}</code> 池 — 已注册 {{ items.length }} 条
    </h2>

    <NSpin :show="loading">
      <NEmpty v-if="!loading && items.length === 0"
              :description="`当前前缀下还没有注册标签。可以先在工作台添加 ${prefix}:xxx，系统会把已使用的键加入候选。`" />
      <NDataTable v-else :columns="columns" :data="items" :bordered="false" />
    </NSpin>

    <div style="margin-top: 16px">
      <NButton @click="router.push('/list')">← 回到浏览</NButton>
    </div>
  </div>
</template>