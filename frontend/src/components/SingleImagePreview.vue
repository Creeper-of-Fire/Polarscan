<!--
  单图预览 widget

  职责:
  - 接收 polaroidId + asset + assetIdx,渲染该资产
  - 内部拼缩略图 / 原图 URL (含 ?v={hash[:6]} cache-bust)
  - 点击 → lightbox 弹原图 (enableLightbox=false 时不响应)
  - 处理 loading / error / empty 状态

  设计要点:
  - 调用方不接触 URL 模板. /thumb/{pid}/{idx}?v={hash[:6]} 的拼装完全封进组件.
  - asset === null → 空状态 ("无可显示的图片"); asset 非空 → 渲染缩略图.
  - assetIdx 为 backend /img/{pid}/{idx} 路径参数, 需要外部传入 (Asset 自身不含 idx).
  - 旧 contract (thumbUrl/originUrl) 拆掉后, ListView 不再自己拼 URL, 直接传业务对象.

  Props:
    polaroidId      所属拍立得的 id (用于拼 /thumb|img URL)
    asset           单个 asset;null 时显示空状态 (legacy 无 hash 资产也可走这里)
    assetIdx        该资产在 polaroid.assets 中的 idx
    caption         lightbox / 缩略图 alt/title;可选
    enableLightbox  是否启用"点击查看原图" (ListView 想关掉时光能跳到工作台)
-->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { NSpin, NModal } from 'naive-ui'
import type { Asset } from '@/types'
import { thumbUrl as buildThumbUrl, originUrl as buildOriginUrl } from '@/lib/thumb'

const props = withDefaults(defineProps<{
  polaroidId: string
  asset: Asset | null
  assetIdx: number
  caption?: string
  enableLightbox?: boolean
}>(), {
  enableLightbox: true,
  caption: '',
})

const thumbUrl = computed<string | null>(() => {
  if (!props.polaroidId || !props.asset) return null
  return buildThumbUrl(props.polaroidId, props.assetIdx, props.asset.hash)
})

const originUrl = computed<string | null>(() => {
  if (!props.polaroidId || props.assetIdx < 0) return null
  return buildOriginUrl(props.polaroidId, props.assetIdx, props.asset?.hash)
})

const showLightbox = ref(false)
const thumbLoading = ref(false)
const thumbError = ref(false)
const originLoading = ref(false)
const originError = ref(false)

function onThumbLoad() {
  thumbLoading.value = false
  thumbError.value = false
}
function onThumbError() {
  thumbLoading.value = false
  thumbError.value = true
}
function onThumbLoadStart() {
  thumbLoading.value = true
  thumbError.value = false
}
function onOriginLoad() {
  originLoading.value = false
  originError.value = false
}
function onOriginError() {
  originLoading.value = false
  originError.value = true
}

function openLightbox() {
  if (!props.enableLightbox) return
  if (!originUrl.value) return
  showLightbox.value = true
}
</script>

<template>
  <div class="single-image-preview">
    <!-- Empty: 没有 asset (legacy 无 hash 资产或极空拍立得) -->
    <div v-if="thumbUrl === null" class="sip-empty">
      <span>{{ caption || '无可显示的图片' }}</span>
    </div>

    <!-- 有 asset: 渲染缩略图 + 错误/加载状态 -->
    <div v-else class="sip-thumb-wrap" @click="openLightbox">
      <img
        :src="thumbUrl"
        :alt="caption || ''"
        loading="lazy"
        class="sip-thumb"
        :class="{ 'sip-thumb-error': thumbError }"
        @load="onThumbLoad"
        @error="onThumbError"
        @loadstart="onThumbLoadStart"
      />
      <div v-if="thumbLoading" class="sip-overlay sip-overlay-loading">
        <NSpin size="small" />
      </div>
      <div v-else-if="thumbError" class="sip-overlay sip-overlay-error">
        缩略图加载失败
      </div>
      <div v-else-if="enableLightbox && originUrl !== null" class="sip-overlay sip-overlay-hint">
        点击查看原图
      </div>
    </div>

    <!-- Lightbox: 显示原图 -->
    <NModal
      v-model:show="showLightbox"
      preset="card"
      :style="{ width: '90vw', maxWidth: '1200px' }"
      :title="caption || '原图'"
      :mask-closable="!originLoading"
    >
      <div v-if="originUrl !== null" class="sip-lightbox">
        <NSpin v-if="originLoading" size="large" />
        <img
          v-show="!originError"
          :src="originUrl"
          :alt="caption || ''"
          class="sip-origin"
          @load="onOriginLoad"
          @error="onOriginError"
        />
        <div v-if="originError" class="sip-origin-error">
          原图加载失败 (F 盘可能离线)
        </div>
      </div>
    </NModal>
  </div>
</template>

<style scoped>
.single-image-preview {
  width: 100%;
  height: 100%;
}
.sip-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: #f5f5f5;
  color: #999;
  font-size: 13px;
  min-height: 80px;
}
.sip-thumb-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  cursor: zoom-in;
  overflow: hidden;
  background: #f5f5f5;
}
.sip-thumb {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.sip-thumb-error {
  opacity: 0.3;
}
.sip-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  font-size: 12px;
  color: #666;
  background: rgba(255, 255, 255, 0.7);
}
.sip-overlay-error {
  color: #c00;
  background: rgba(255, 245, 245, 0.85);
}
.sip-overlay-hint {
  opacity: 0;
  transition: opacity 0.15s;
  background: rgba(0, 0, 0, 0.4);
  color: #fff;
}
.sip-thumb-wrap:hover .sip-overlay-hint {
  opacity: 1;
}
.sip-lightbox {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 200px;
  justify-content: center;
}
.sip-origin {
  width: 100%;
  max-height: 80vh;
  object-fit: contain;
  display: block;
}
.sip-origin-error {
  color: #c00;
  font-size: 14px;
  padding: 24px;
}
</style>
