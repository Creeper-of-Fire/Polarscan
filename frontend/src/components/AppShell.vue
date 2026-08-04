<script setup lang="ts">
import { computed, h } from 'vue'
import { useRouter, useRoute, RouterLink } from 'vue-router'
import { NLayout, NLayoutHeader, NLayoutContent, NMenu, NButton, NSpace, NIcon, useMessage } from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import { systemApi } from '@/api'

const router = useRouter()
const route = useRoute()
const message = useMessage()

const activeKey = computed(() => {
  const p = route.path
  if (p === '/list' || p === '/') return 'list'
  if (p.startsWith('/new')) return 'new'
  if (p.startsWith('/bench')) return 'bench'
  if (p.startsWith('/pool/char')) return 'pool-char'
  if (p.startsWith('/pool/event')) return 'pool-event'
  if (p.startsWith('/pool/theme')) return 'pool-theme'
  if (p.startsWith('/pool/collection')) return 'pool-collection'
  if (p.startsWith('/pool/composite')) return 'pool-composite'
  return ''
})

const menuOptions: MenuOption[] = [
  { label: () => h(RouterLink, { to: '/list' }, () => '浏览'), key: 'list' },
  { label: () => h(RouterLink, { to: '/new' }, () => '新建'), key: 'new' },
  { type: 'divider', key: 'd1' },
  { label: () => h(RouterLink, { to: '/pool/char' }, () => '角色池'), key: 'pool-char' },
  { label: () => h(RouterLink, { to: '/pool/event' }, () => '事件池'), key: 'pool-event' },
  { label: () => h(RouterLink, { to: '/pool/theme' }, () => '主题池'), key: 'pool-theme' },
  { label: () => h(RouterLink, { to: '/pool/collection' }, () => '系列池'), key: 'pool-collection' },
  { label: () => h(RouterLink, { to: '/pool/composite' }, () => '复合池'), key: 'pool-composite' },
]

async function reload() {
  try {
    await systemApi.reload()
    message.success('已从磁盘重载')
    router.go(0)
  } catch (e) {
    message.error(`重载失败: ${e instanceof Error ? e.message : String(e)}`)
  }
}

void h // 类型占位避免 unused
</script>

<template>
  <NLayout style="height: 100vh">
    <NLayoutHeader bordered style="padding: 12px 24px; display: flex; align-items: center; gap: 24px">
      <RouterLink to="/list" style="font-weight: 700; font-size: 18px; color: #222; text-decoration: none">
        Polarscan
      </RouterLink>
      <NMenu mode="horizontal" :options="menuOptions" :value="activeKey" responsive />
      <div style="flex: 1" />
      <NSpace>
        <NButton @click="reload" type="primary" ghost>从磁盘重载</NButton>
      </NSpace>
    </NLayoutHeader>
    <NLayoutContent style="padding: 24px; overflow: auto">
      <slot />
    </NLayoutContent>
  </NLayout>
</template>