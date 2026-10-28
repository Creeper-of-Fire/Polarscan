<script setup lang="ts">
// IngestView — 批量导入连连看画布（docs/spec/ingest-scan.md）。
//
// 三栏 = 工作流三段（从左到右推进）：
//   左栏（窄·滚动） 素材源：按批次折叠分组，正面卡与待配对背面同框相邻——
//                   配对全部发生在栏内（摆放分组合法，配对永远由人决定）
//   中间            日期区：唯一的卡投放目标集合，占最大空间
//   右栏（窄）      tag 池：工作流最后一步，贴着中间拖
// 「未分类」不再是独立框——侧边栏本身就是未分类（侧边=未处理，中间=已归日期）。
import { onBeforeUnmount, onMounted, provide, ref } from 'vue'
import { NButton, NInput, NModal, useMessage } from 'naive-ui'
import { useIngestBoard } from '@/composables/useIngestBoard'
import IngestCard from '@/components/IngestCard.vue'
import IngestChip from '@/components/IngestChip.vue'
import CharTag from '@/components/CharTag.vue'
import { tagsApi } from '@/api'
import type { Chip } from '@/lib/ingestBoard'

const message = useMessage()
const ib = useIngestBoard()

// ---- 双击放大（lightbox）----
const lightboxChip = ref<Chip | null>(null)
function openLightbox(chip: Chip): void {
  lightboxChip.value = chip
}
provide('ingestLightbox', openLightbox)
function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') lightboxChip.value = null
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

// ---- 忽略区面板 ----
const showIgnored = ref(false)
async function restoreFromIgnored(hash: string): Promise<void> {
  await ib.restore(hash)
  message.success('已移回画布（左栏对应批次）')
}

// ---- DnD ----
const T_CARD = 'application/x-polar-card'
const T_CHIP = 'application/x-polar-chip'
const T_TAG = 'application/x-polar-tag'

function tagDragStart(e: DragEvent, tag: string) {
  e.dataTransfer?.setData(T_TAG, tag)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy'
}

/** 日期区：接卡（T_CARD → moveCard） */
function zoneDragOver(e: DragEvent) {
  if (e.dataTransfer?.types.includes(T_CARD)) e.preventDefault()
}
function zoneDrop(e: DragEvent, zone: string) {
  e.preventDefault()
  const cardId = e.dataTransfer?.getData(T_CARD)
  if (cardId) ib.moveCard(cardId, zone)
}

/** 侧栏批次框：接卡（回未分类）+ 接背面（解除配对） */
function batchDragOver(e: DragEvent) {
  const types = e.dataTransfer?.types
  if (types?.includes(T_CARD) || types?.includes(T_CHIP)) e.preventDefault()
}
function batchDrop(e: DragEvent) {
  e.preventDefault()
  const cardId = e.dataTransfer?.getData(T_CARD)
  if (cardId) {
    ib.moveCard(cardId, 'unsorted')
    return
  }
  const chipId = e.dataTransfer?.getData(T_CHIP)
  if (chipId && ib.board.value) {
    const host = Object.values(ib.board.value.cards).find((c) => c.backChipId === chipId)
    if (host) ib.unpairBack(host.id)
  }
}

// ---- 批次折叠 ----
const collapsed = ref(new Set<string>())
function toggleBatch(batch: string) {
  const next = new Set(collapsed.value)
  if (next.has(batch)) next.delete(batch)
  else next.add(batch)
  collapsed.value = next
}

// ---- 日期区新建 ----
const newZone = ref('')
function submitNewZone() {
  const v = newZone.value.trim()
  if (!v) return
  if (!ib.addZone(v)) {
    message.error(`无法新建日期区 "${v}"：需要 YYYY-MM-DD 格式且不重复`)
    return
  }
  newZone.value = ''
}

// ---- tag 池 ----
const charTags = ref<string[]>([])
onMounted(async () => {
  try {
    charTags.value = await tagsApi.prefixValues('char')
  } catch {
    /* tag 池拉不到不阻塞画布 */
  }
})

// ---- 提交 ----
async function commit() {
  const outcome = await ib.commitAll()
  if (outcome.ok.length) message.success(`已提交 ${outcome.ok.length} 张`)
  if (outcome.failed.length) {
    message.error(`${outcome.failed.length} 张提交失败：${outcome.failed[0].reason}`)
  }
}

const scanning = () => ib.status.value === 'scanning' || ib.status.value === 'classifying'
const committing = () => ib.status.value === 'committing'
</script>

<template>
  <div class="ingest">
    <!-- 顶部工具条 -->
    <div class="toolbar">
      <NButton type="primary" :loading="scanning()" :disabled="committing()" @click="ib.scan()">
        扫描存储区新增
      </NButton>
      <template v-if="ib.status.value === 'ready'">
        <div class="zone-add">
          <NInput
            v-model:value="newZone"
            placeholder="YYYY-MM-DD"
            size="small"
            style="width: 130px"
            @keyup.enter="submitNewZone"
          />
          <NButton size="small" @click="submitNewZone">新建日期区</NButton>
        </div>
        <NButton
          type="success"
          :loading="committing()"
          :disabled="ib.committable.value.length === 0"
          @click="commit"
        >
          提交全部（{{ ib.committable.value.length }}）
        </NButton>
        <NButton size="small" quaternary @click="showIgnored = true">
          忽略区（{{ ib.ignored.value.length }}）
        </NButton>
        <span class="stat">
          待配对 {{ ib.pool.value.length }}
          <template v-if="ib.filteredByIgnore.value > 0"> · 本次过滤 {{ ib.filteredByIgnore.value }}</template>
        </span>
      </template>
      <span v-if="scanning()" class="stat">
        {{ ib.status.value === 'scanning' ? '冷盘扫描中…' : `判定中 ${ib.progress.value.done}/${ib.progress.value.total}` }}
      </span>
      <span v-if="ib.status.value === 'error'" class="error">{{ ib.errorMsg.value }}</span>
    </div>

    <!-- 空态 -->
    <div v-if="ib.status.value === 'idle'" class="empty">
      <p>把待入库的扫描件放入存储区（library_root）的批次文件夹，然后点「扫描存储区新增」。</p>
      <p class="hint">流程：配对（左栏内拖背面到卡）→ 拖卡进日期区（中间）→ 拖 tag（右栏）→ 提交</p>
    </div>

    <!-- 三栏画布 -->
    <div v-if="ib.board.value" class="layout">
      <!-- 左：素材源（按批次折叠分组） -->
      <aside class="sidebar" @dragover="batchDragOver($event)" @drop="batchDrop($event)">
        <div class="side-title">素材（未分类）</div>
        <div v-for="g in ib.batchGroups.value" :key="g.batch" class="batch">
          <button class="batch-head" @click="toggleBatch(g.batch)">
            <span class="arrow" :class="{ open: !collapsed.has(g.batch) }">▸</span>
            {{ g.batch }}
            <span class="count">卡 {{ g.cards.length }} · 背 {{ g.chips.length }}</span>
          </button>
          <div v-if="!collapsed.has(g.batch)" class="batch-body">
            <IngestCard v-for="card in g.cards" :key="card.id" :card="card" :ib="ib" size="sm" />
            <IngestChip v-for="chip in g.chips" :key="chip.id" :chip="chip" :ib="ib" />
          </div>
        </div>
        <div v-if="ib.batchGroups.value.length === 0" class="side-empty">
          左栏已清空——素材都在日期区或已提交
        </div>
      </aside>

      <!-- 中：日期区 -->
      <main class="zones">
        <div
          v-for="z in ib.zones.value"
          :key="z"
          class="zone"
          @dragover="zoneDragOver($event)"
          @drop="zoneDrop($event, z)"
        >
          <div class="zone-head">
            📅 {{ z }}
            <span class="count">{{ ib.cards.value.filter((c) => c.zone === z).length }}</span>
            <button class="del" title="删除该区（区内卡回左栏）" @click="ib.removeZone(z)">✕</button>
          </div>
          <div class="zone-body">
            <IngestCard
              v-for="card in ib.cards.value.filter((c) => c.zone === z)"
              :key="card.id"
              :card="card"
              :ib="ib"
            />
            <div v-if="ib.cards.value.filter((c) => c.zone === z).length === 0" class="zone-hint">
              拖卡到这里
            </div>
          </div>
        </div>
        <div v-if="ib.zones.value.length === 0" class="zones-empty">
          还没有日期区——用上方输入框新建，或扫描批次文件夹自动解析
        </div>
      </main>

      <!-- 右：tag 池（CharTag：展示名 + 应援色） -->
      <aside class="tagpool">
        <div class="side-title">tag 池（拖到卡上）</div>
        <div class="tag-list">
          <!-- draggable 放 wrapper 上：CharTag 根是 NTooltip，attrs fallthrough 落不到 NTag -->
          <div
            v-for="t in charTags"
            :key="t"
            class="tag-drag"
            draggable="true"
            @dragstart="tagDragStart($event, t)"
          >
            <CharTag :tag="t" />
          </div>
        </div>
      </aside>
    </div>

    <!-- 双击放大：完整缩略图预览（点遮罩 / Esc 关闭） -->
    <Teleport to="body">
      <div v-if="lightboxChip" class="lightbox" @click="lightboxChip = null">
        <img class="lightbox-img" :src="lightboxChip.thumbUrl" :alt="lightboxChip.path" @click.stop />
        <div class="lightbox-caption">{{ lightboxChip.path }}</div>
      </div>
    </Teleport>

    <!-- 忽略区面板 -->
    <NModal v-model:show="showIgnored" preset="card" title="忽略区（浏览器本地存储）" style="width: 640px">
      <p class="ignored-hint">
        被忽略的文件按内容 hash 记录，扫描时自动过滤（挪动/重命名后仍生效）。
        移出后需重新扫描才会回到画布。
      </p>
      <div v-if="ib.ignored.value.length === 0" class="ignored-empty">空</div>
      <div v-else class="ignored-grid">
        <div v-for="it in ib.ignored.value" :key="it.hash" class="ignored-item">
          <img :src="it.thumbUrl" :title="it.path" alt="" loading="lazy" />
          <button class="restore" title="移回画布（不清空当前进度）" @click="restoreFromIgnored(it.hash)">↺ 移回</button>
        </div>
      </div>
    </NModal>
  </div>
</template>

<style scoped>
.ingest { display: flex; flex-direction: column; gap: 12px; height: 100%; }
.toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; flex-shrink: 0; }
.stat { color: #666; font-size: 13px; }
.error { color: #d03050; }
.zone-add { display: flex; gap: 6px; align-items: center; }
.empty { color: #888; padding: 40px; text-align: center; }
.hint { font-size: 12px; }

/* 三栏骨架 */
.layout { display: flex; gap: 12px; align-items: stretch; min-height: 0; flex: 1; }

/* 左栏：素材源 */
.sidebar {
  width: 262px; flex-shrink: 0; overflow-y: auto;
  border: 1px solid #e0e0e6; border-radius: 8px; background: #fafafa;
  padding: 8px; max-height: calc(100vh - 160px);
}
.side-title { font-size: 12px; font-weight: 600; color: #888; margin: 2px 0 8px; }
.side-empty { font-size: 12px; color: #aaa; padding: 12px 4px; }
.batch { margin-bottom: 6px; }
.batch-head {
  display: flex; align-items: center; gap: 4px; width: 100%;
  border: none; background: none; cursor: pointer; text-align: left;
  font-size: 12px; font-weight: 600; color: #444; padding: 4px 2px; border-radius: 4px;
}
.batch-head:hover { background: #f0f0f4; }
.arrow { display: inline-block; transition: transform .12s; color: #999; }
.arrow.open { transform: rotate(90deg); }
.count { font-weight: 400; color: #999; font-size: 11px; }
.batch-body { display: flex; flex-wrap: wrap; gap: 6px; padding: 4px 0 8px; }

/* 中间：日期区 */
.zones {
  flex: 1; min-width: 0; overflow-y: auto; max-height: calc(100vh - 160px);
  display: flex; flex-wrap: wrap; gap: 12px; align-content: flex-start;
}
.zone {
  border: 1px solid #dcdce6; border-radius: 10px; background: #fff;
  padding: 10px; min-width: 300px; flex: 1 1 300px; max-width: 640px;
}
.zone-head { font-size: 13px; font-weight: 600; color: #333; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
.zone-head .count { color: #999; font-weight: 400; font-size: 11px; }
.del { border: none; background: none; color: #bbb; cursor: pointer; font-size: 11px; margin-left: auto; }
.del:hover { color: #d03050; }
.zone-body { display: flex; flex-wrap: wrap; gap: 10px; min-height: 60px; }
.zone-hint { color: #ccc; font-size: 12px; align-self: center; padding: 8px; }
.zones-empty { color: #aaa; font-size: 13px; padding: 24px; }

/* 右栏：tag 池 */
.tagpool {
  width: 170px; flex-shrink: 0; overflow-y: auto;
  border: 1px solid #e0e0e6; border-radius: 8px; background: #fafafa;
  padding: 8px; max-height: calc(100vh - 160px);
}
.tag-list { display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
.tag-drag { cursor: grab; display: inline-flex; user-select: none; }
.tag-drag:active { cursor: grabbing; }

/* 双击放大 */
.lightbox {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0, 0, 0, .82);
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px;
  cursor: zoom-out;
}
.lightbox-img { max-width: 92vw; max-height: 86vh; object-fit: contain; border-radius: 4px; cursor: default; }
.lightbox-caption { color: #ddd; font-size: 12px; max-width: 90vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 忽略区面板 */
.ignored-hint { font-size: 12px; color: #888; margin: 0 0 10px; }
.ignored-empty { color: #aaa; padding: 20px; text-align: center; }
.ignored-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.ignored-item { width: 120px; text-align: center; }
.ignored-item img { width: 120px; height: 140px; object-fit: cover; border-radius: 6px; display: block; opacity: .75; }
.restore { margin-top: 4px; border: 1px solid #ccc; background: #fff; border-radius: 4px; font-size: 12px; cursor: pointer; padding: 2px 8px; }
.restore:hover { border-color: #18a058; color: #18a058; }
</style>
