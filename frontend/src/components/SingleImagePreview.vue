<!--
  单图预览 widget

  职责:
  - 接收 path + hash, 渲染该资产的缩略图 (点击可弹原图)
  - 内部拼 URL (by-path, 不依赖 polaroid 索引)
  - 处理 loading / error / empty 状态

  设计要点 (2026-08 重构):
  - 单一契约: 只关心 path + hash. 不接收 polaroid id / asset idx.
  - 这样 NewView 拖入后 (asset.path + asset.hash 已有) 即可立即预览,
    无需等服务端 polaroid 索引写入.
  - 旧的 (polaroidId, assetIdx, asset) 三元组契约已废弃 — 后端统一 by-path 后不再需要.

  Props:
    path            资产绝对路径; null/undefined 时显示空状态
    hash            blake2b 十六进制串 (>= 6 字符); 用于派生 thumb 文件名 + cache-bust
    caption         lightbox / 缩略图 alt/title; 可选
    enableLightbox  是否启用"点击查看原图" (ListView 想关掉时光能跳到工作台)
-->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { NSpin, NModal } from 'naive-ui'
import { thumbUrl as buildThumbUrl, originUrl as buildOriginUrl } from '@/lib/thumb'

const props = withDefaults(defineProps<{
  path: string | null
  hash?: string | null
  caption?: string
  enableLightbox?: boolean
}>(), {
  enableLightbox: true,
  caption: '',
  hash: null,
})

const thumbUrl = computed<string | null>(() => {
  if (!props.path) return null
  return buildThumbUrl(props.path, props.hash)
})

const originUrl = computed<string | null>(() => {
  if (!props.path) return null
  return buildOriginUrl(props.path)
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
    <!-- Empty: 没有 path (legacy 无 hash 资产或极空拍立得) -->
    <div v-if="thumbUrl === null" class="sip-empty">
      <span>{{ caption || '无可显示的图片' }}</span>
    </div>

    <!-- 有 path: 渲染缩略图 + 错误/加载状态 -->
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
