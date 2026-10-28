<script setup lang="ts">
// IngestCard — 卡片（= 正面 chip 本体 + 可选挂载背面 + tags）。
// 侧栏（sm）与日期区（md）复用同一组件，尺寸由 size 控制。
//
// 交互：
//   拖正面图     = 拖整张卡（T_CARD；容器接 drop 决定去哪）
//   双击正面/背面 = 放大预览（lightbox，inject 自 IngestView）
//   卡作为 drop 目标：背面 chip → 配对；tag → 打标
//   ⤾           = 翻转为背面（卡解散）
//   🚫           = 放入忽略区（忽略正面文件=卡解散，挂载背面弹回池）
//   背面 ✕        = 解除配对
import { computed, inject } from 'vue'
import { useMessage } from 'naive-ui'
import CharTag from '@/components/CharTag.vue'
import type { Card, Chip } from '@/lib/ingestBoard'
import type { IngestBoardApi } from '@/composables/useIngestBoard'

const props = withDefaults(defineProps<{ card: Card; ib: IngestBoardApi; size?: 'sm' | 'md' }>(), {
  size: 'md',
})
const message = useMessage()

const T_CHIP = 'application/x-polar-chip'
const T_CARD = 'application/x-polar-card'
const T_TAG = 'application/x-polar-tag'

/** 放大预览（由 IngestView provide） */
const openLightbox = inject<(chip: Chip) => void>('ingestLightbox', () => {})

const front = computed(() => props.ib.chipOf(props.card.frontChipId))
const back = computed(() => props.ib.chipOf(props.card.backChipId))

function cardDragStart(e: DragEvent) {
  e.dataTransfer?.setData(T_CARD, props.card.id)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}
function dragOver(e: DragEvent) {
  const types = e.dataTransfer?.types
  if (types?.includes(T_CHIP) || types?.includes(T_TAG)) e.preventDefault()
}
function drop(e: DragEvent) {
  e.preventDefault()
  const chipId = e.dataTransfer?.getData(T_CHIP)
  if (chipId) {
    if (!props.ib.pairBack(chipId, props.card.id)) {
      message.warning('配对失败：卡已有背面，或该 chip 不是背面')
    }
    return
  }
  const tag = e.dataTransfer?.getData(T_TAG)
  if (tag) props.ib.addTag(props.card.id, tag)
}
</script>

<template>
  <div
    class="card"
    :class="[`size-${size}`]"
    :title="front?.path"
    @dragover="dragOver($event)"
    @drop="drop($event)"
  >
    <img
      class="front"
      :src="front!.thumbUrl"
      alt=""
      loading="lazy"
      draggable="true"
      title="双击放大 · 拖动移卡"
      @dragstart="cardDragStart($event)"
      @dblclick="front && openLightbox(front)"
    />
    <div v-if="back" class="back-wrap">
      <img
        class="back"
        :src="back.thumbUrl"
        alt=""
        loading="lazy"
        :title="back.path + '（双击放大）'"
        @dblclick="openLightbox(back)"
      />
      <button class="unpair" title="解除配对（背面回左栏）" @click.stop="ib.unpairBack(card.id)">✕</button>
    </div>
    <div class="tags">
      <CharTag v-for="t in card.tags" :key="t" :tag="t" closable @close="ib.removeTag(card.id, t)" />
    </div>
    <div class="ops">
      <button class="op" title="翻转为背面（卡解散）" @click.stop="ib.flipChip(card.id)">⤾</button>
      <button class="op ignore" title="放入忽略区（忽略此文件；挂载背面弹回左栏）" @click.stop="ib.ignoreChip(card.frontChipId)">🚫</button>
    </div>
  </div>
</template>

<style scoped>
.card { position: relative; border: 1px solid #ddd; border-radius: 8px; background: #fff; padding: 4px; }
.card.size-md { width: 128px; }
.card.size-sm { width: 104px; }
.front { width: 100%; border-radius: 4px; display: block; cursor: grab; object-fit: cover; }
.size-md .front { height: 150px; }
.size-sm .front { height: 122px; }
.back-wrap { position: relative; }
.back { width: 100%; height: 56px; object-fit: cover; border-radius: 4px; display: block; margin-top: 4px; opacity: .9; }
.unpair { position: absolute; right: 2px; top: 6px; border: none; border-radius: 4px; background: rgba(255,255,255,.85); cursor: pointer; font-size: 10px; padding: 0 4px; color: #d03050; }
.tags { display: flex; flex-wrap: wrap; gap: 2px; margin-top: 4px; min-height: 16px; }
.ops { position: absolute; right: 3px; top: 3px; display: flex; gap: 2px; }
.op { border: none; border-radius: 4px; background: rgba(255,255,255,.85); cursor: pointer; font-size: 11px; padding: 1px 5px; }
.op:hover { background: #fff; }
.op.ignore { font-size: 10px; }
</style>
