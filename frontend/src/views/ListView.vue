<!--
  ListView: 浏览全部拍立得

  每张卡片用 SingleImagePreview 显示 cover, 点击进入 BenchView。
  URL 拼装由 SingleImagePreview 内部处理, ListView 只传业务对象。
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NSpin, NEmpty, NSpace, NCard, NInput, NButton } from 'naive-ui'
import { usePolarscanStore } from '@/stores/polarscan'
import { shotDateHint } from '@/composables/usePathParse'
import SingleImagePreview from '@/components/SingleImagePreview.vue'

const router = useRouter()
const store = usePolarscanStore()
const tagFilter = ref('')
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    await store.listSummaries()
  } finally {
    loading.value = false
  }
})

const filtered = computed(() => {
  if (!tagFilter.value.trim()) return store.summaries
  return store.summaries.filter((s) => s.id.includes(tagFilter.value.trim()))
})

const totalCount = computed(() => store.summaries.length)

async function loadWithTag() {
  const tag = tagFilter.value.trim()
  loading.value = true
  try {
    if (!tag) {
      await store.reloadSummaries()
    } else {
      await store.listSummariesByTag(tag)
    }
  } finally {
    loading.value = false
  }
}

function open(id: string) {
  router.push(`/bench/${encodeURIComponent(id)}`)
}
</script>

<template>
  <div>
    <h2 style="margin-top: 0">
      浏览 ({{ filtered.length }} / {{ totalCount }})
      <small v-if="tagFilter" style="font-weight: normal; color: #666">
        · 标签: <code>{{ tagFilter }}</code>
      </small>
    </h2>

    <NSpace style="margin-bottom: 16px">
      <NInput v-model:value="tagFilter" placeholder="按 tag 过滤 (例: char:my_push)" clearable
              style="width: 320px" @keyup.enter="loadWithTag" />
      <NButton @click="loadWithTag">应用</NButton>
      <NButton @click="() => { tagFilter = ''; loadWithTag() }">清空</NButton>
    </NSpace>

    <NSpin :show="loading">
      <NEmpty v-if="!loading && filtered.length === 0" description="还没有录入任何拍立得">
        <template #extra>
          <NButton @click="router.push('/new')">新建一份</NButton>
        </template>
      </NEmpty>

      <div v-else style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px">
        <NCard v-for="s in filtered" :key="s.id" hoverable content-style="padding: 0"
               style="cursor: pointer" @click="open(s.id)">
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
        </NCard>
      </div>
    </NSpin>
  </div>
</template>