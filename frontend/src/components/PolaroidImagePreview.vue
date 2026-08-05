<!--
  Polaroid album-style image preview

  职责:
  - 接收整个 polaroid,展示其全部 assets 为"专辑"式布局
  - 大封面 (current) + 底部缩略图条 (切换)
  - 空 polaroid 走空状态
  - 不管编辑,不管保存;只读展示

  Props:
    polaroid     当前拍立得 (id 为空 = 尚未保存)
    initialIdx   初始展示第几张 (默认 0)
    showCaptions 是否在缩略图条下显示 role / 文件名 (默认 false)
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { NEmpty } from 'naive-ui'
import type { Polaroid } from '@/types'
import { thumbUrl as buildThumbUrl } from '@/lib/thumb'
import SingleImagePreview from './SingleImagePreview.vue'

const props = withDefaults(
  defineProps<{
    polaroid: Polaroid
    initialIdx?: number
    showCaptions?: boolean
  }>(),
  {
    initialIdx: 0,
    showCaptions: false,
  },
)

const currentIdx = ref(props.initialIdx)

// 安全的 idx:clamp 到 assets 范围内,无需 watcher
// (currentIdx 可能在切换 polaroid 后 stale,但渲染时夹紧,避免 out-of-bounds)
const safeIdx = computed(() => {
  const max = props.polaroid.assets.length - 1
  if (max < 0) return 0
  return Math.min(Math.max(currentIdx.value, 0), max)
})

const hasAssets = computed(() => props.polaroid.assets.length > 0)
const canPreview = computed(() => hasAssets.value && props.polaroid.id !== '')

const currentAsset = computed(() =>
  hasAssets.value ? props.polaroid.assets[safeIdx.value] : null,
)

// 缩略图条用: 直接拿 lib/thumb 拼 (不走 SingleImagePreview, 因为缩略图条是选择按钮, 不要 lightbox 也不要 cursor:zoom-in).
function stripThumbUrl(idx: number): string {
  const a = props.polaroid.assets[idx]
  return buildThumbUrl(props.polaroid.id, idx, a?.hash)
}

function selectAsset(idx: number) {
  currentIdx.value = idx
}
</script>

<template>
  <div class="polaroid-image-preview">
    <!-- Empty: 没有任何资产 -->
    <div v-if="!hasAssets" class="pip-empty">
      <NEmpty description="这张拍立得还没有资产" />
    </div>

    <!-- Not yet saved: 有 assets 但 polaroid 未持久化,无法预览缩略图 -->
    <div v-else-if="!canPreview" class="pip-empty">
      <NEmpty description="保存拍立得后可查看图片" />
    </div>

    <!-- Album view: 上面大图 + 下面缩略图条 -->
    <div v-else class="pip-album">
      <div class="pip-cover">
        <SingleImagePreview
          :polaroid-id="polaroid.id"
          :asset="currentAsset"
          :asset-idx="safeIdx"
          :caption="`${polaroid.id} · ${currentAsset?.role || `asset #${safeIdx}`}`"
        />
      </div>

      <div v-if="polaroid.assets.length > 1" class="pip-thumbs">
        <button
          v-for="(asset, idx) in polaroid.assets"
          :key="idx"
          type="button"
          class="pip-thumb-btn"
          :class="{ 'pip-thumb-btn-active': idx === safeIdx }"
          @click="selectAsset(idx)"
        >
          <img
            :src="stripThumbUrl(idx)"
            :alt="`asset ${idx}`"
            loading="lazy"
            class="pip-thumb-img"
          />
          <div v-if="showCaptions" class="pip-thumb-caption">
            {{ asset.role }}
          </div>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.polaroid-image-preview {
  width: 100%;
}
.pip-empty {
  padding: 24px;
}
.pip-album {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.pip-cover {
  width: 100%;
  aspect-ratio: 4 / 3;
  background: #f5f5f5;
  border-radius: 4px;
  overflow: hidden;
}
.pip-thumbs {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 4px;
}
.pip-thumb-btn {
  flex: 0 0 auto;
  width: 64px;
  height: 64px;
  padding: 0;
  border: 2px solid transparent;
  border-radius: 4px;
  background: #f5f5f5;
  cursor: pointer;
  overflow: hidden;
  position: relative;
  transition: border-color 0.15s;
}
.pip-thumb-btn:hover {
  border-color: #aaa;
}
.pip-thumb-btn-active {
  border-color: #1890ff;
}
.pip-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.pip-thumb-caption {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 10px;
  padding: 1px 4px;
  text-align: center;
}
</style>