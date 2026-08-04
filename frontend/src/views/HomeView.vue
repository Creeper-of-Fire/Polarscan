<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
onMounted(() => {
  router.replace('/list')
})
</script>

<template>
  <div style="padding: 24px; color: #666">跳转到浏览…</div>
</template>