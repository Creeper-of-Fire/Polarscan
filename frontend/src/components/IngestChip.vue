<script setup lang="ts">
// IngestChip — 待配对背面（左栏批次框里的自由 chip）。
// 拖到卡上 = 配对；⤾ = 翻转为正面（升级成新卡）；✕ = 放入忽略区；双击 = 放大。
import { inject } from 'vue'
import type { Chip } from '@/lib/ingestBoard'
import type { IngestBoardApi } from '@/composables/useIngestBoard'

const props = defineProps<{ chip: Chip; ib: IngestBoardApi }>()

const T_CHIP = 'application/x-polar-chip'

/** 放大预览（由 IngestView provide） */
const openLightbox = inject<(chip: Chip) => void>('ingestLightbox', () => {})

function chipDragStart(e: DragEvent) {
  e.dataTransfer?.setData(T_CHIP, props.chip.id)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copyMove'
}
</script>

<template>
  <div
    class="chip"
    :class="[chip.tier]"
    :title="chip.path + '（双击放大）'"
    draggable="true"
    @dragstart="chipDragStart($event)"
    @dblclick="openLightbox(chip)"
  >
    <img :src="chip.thumbUrl" alt="" loading="lazy" />
    <button class="flip" title="翻转为正面（成卡）" @click.stop="ib.flipChip(chip.id)">⤾</button>
    <button class="ignore" title="放入忽略区" @click.stop="ib.ignoreChip(chip.id)">🚫</button>
    <span v-if="chip.dupPid" class="dup" title="库中已有相同内容">dup</span>
  </div>
</template>

<style scoped>
.chip { position: relative; width: 104px; border: 2px solid transparent; border-radius: 6px; overflow: hidden; background: #fff; }
.chip img { display: block; width: 100%; height: 122px; object-fit: cover; }
.chip.auto { border-color: #63e2b7; }
.chip.review { border-color: #f0a020; }
.chip.suspect { border-color: #d03050; }
.flip { position: absolute; right: 2px; bottom: 2px; font-size: 11px; border: none; border-radius: 4px; background: rgba(255,255,255,.85); cursor: pointer; padding: 1px 5px; }
.ignore { position: absolute; left: 2px; bottom: 2px; font-size: 9px; border: none; border-radius: 4px; background: rgba(255,255,255,.85); cursor: pointer; padding: 1px 4px; }
.dup { position: absolute; left: 2px; top: 2px; font-size: 10px; background: #d03050; color: #fff; border-radius: 3px; padding: 0 4px; }
</style>
