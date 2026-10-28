// useIngestBoard — 连连看画布的 composable：响应式壳 + scan 流水线 + 提交循环。
//
// 分层（docs/spec/ingest-scan.md）：
//   lib/ingestBoard.ts —— 纯状态机（node 可测，本文件不含任何转换逻辑）
//   本文件 —— Vue 响应式包装 + IO 编排：
//     scan:   后端扫描（纯 IO）→ 前端逐张判定（useFaceClassify）→ initBoard
//     commit: 逐卡 suggest-id + PUT /polaroid（role 显式、shot_date 不自动填）
import { computed, ref } from 'vue'
import {
  addTag as libAddTag,
  addZone as libAddZone,
  cardPayload,
  committableCards,
  flipChip as libFlipChip,
  addItems,
  initBoard,
  moveCard as libMoveCard,
  pairBack as libPairBack,
  poolChips,
  removeCards as libRemoveCards,
  removeChips as libRemoveChips,
  removeTag as libRemoveTag,
  removeZone as libRemoveZone,
  unpairBack as libUnpairBack,
  unsortedByBatch,
  ZONE_UNSORTED,
  type BatchGroup,
  type Board,
  type Chip,
} from '@/lib/ingestBoard'
import { classifyThumb } from '@/composables/useFaceClassify'
import { parseFolderDays } from '@/lib/folderDateCompat'
import { parentDirName } from '@/composables/usePathParse'
import { ingestApi, newApi, polaroidsApi, type IngestScanItemDto } from '@/api'

export type ScanStatus = 'idle' | 'scanning' | 'classifying' | 'ready' | 'committing' | 'error'

/** useIngestBoard 返回值类型（供子组件 props 引用） */
export type IngestBoardApi = ReturnType<typeof useIngestBoard>

export interface CommitOutcome {
  ok: string[]        // 提交成功的 pid（与 okCardIds 一一对应）
  okCardIds: string[]
  failed: Array<{ cardId: string; reason: string }>
}

/** 忽略区记录（浏览器 localStorage，按内容 hash 过滤） */
export interface IgnoredItem {
  hash: string
  path: string
  thumbUrl: string
}

const IGNORE_STORAGE_KEY = 'polarscan-ingest-ignored'

function loadIgnored(): IgnoredItem[] {
  try {
    const raw = localStorage.getItem(IGNORE_STORAGE_KEY)
    return raw ? (JSON.parse(raw) as IgnoredItem[]) : []
  } catch {
    return []
  }
}

export function useIngestBoard() {
  const board = ref<Board | null>(null)
  const status = ref<ScanStatus>('idle')
  const errorMsg = ref('')
  const progress = ref({ done: 0, total: 0 })
  const scanMeta = ref({ skippedKnown: 0, errors: [] as Array<{ path: string; reason: string }> })

  // ---- 响应式派生 ----
  const pool = computed<Chip[]>(() => (board.value ? poolChips(board.value) : []))
  const cards = computed(() => (board.value ? Object.values(board.value.cards) : []))
  const zones = computed(() => (board.value ? [...board.value.zones].sort() : []))
  const unsortedCards = computed(() => cards.value.filter((c) => c.zone === ZONE_UNSORTED))
  /** 可提交 = 日期区里的卡（未分类/左栏 = 本次不提交） */
  const committable = computed(() => cards.value.filter((c) => c.zone !== ZONE_UNSORTED))
  /** 未分类大框：按批次分小框（卡 + 待配对背面同框相邻） */
  const batchGroups = computed<BatchGroup[]>(() =>
    board.value ? unsortedByBatch(board.value) : [],
  )

  // ---- 忽略区（localStorage，按 hash 过滤） ----
  const ignored = ref<IgnoredItem[]>(loadIgnored())
  const ignoredHashes = computed(() => new Set(ignored.value.map((it) => it.hash)))
  function persistIgnored(): void {
    localStorage.setItem(IGNORE_STORAGE_KEY, JSON.stringify(ignored.value))
  }
  /** 放入忽略区：hash 记录 + 画布侧删除（卡本体→解散；挂载背面→解除；自由→消失） */
  function ignoreChip(chipId: string): void {
    const b = board.value
    if (!b) return
    const chip = b.chips[chipId]
    if (!chip || ignoredHashes.value.has(chip.hash)) return
    ignored.value = [...ignored.value, { hash: chip.hash, path: chip.path, thumbUrl: chip.thumbUrl }]
    persistIgnored()
    libRemoveChips(b, [chipId])
  }
  /** 从忽略区移除（下次扫描会重新出现；如画布还开着可直接重扫） */
  function unignore(hash: string): void {
    ignored.value = ignored.value.filter((it) => it.hash !== hash)
    persistIgnored()
  }
  /** 本次扫描被忽略区过滤掉的文件数（scan 后有效） */
  const filteredByIgnore = ref(0)

  function chipOf(chipId: string | null | undefined): Chip | undefined {
    return chipId && board.value ? board.value.chips[chipId] : undefined
  }

  // ---- 流水线 ----

  /** 【扫描】explicit gesture：后端 rglob + hash + 缩略图 → 前端判定 → 建画布。
   * 画布已存在时增量合并（保留已配对 / 已分区 / 手动日期区）。 */
  async function scan(): Promise<void> {
    status.value = 'scanning'
    errorMsg.value = ''
    progress.value = { done: 0, total: 0 }
    try {
      const res = await ingestApi.scan()
      // 忽略区过滤：按内容 hash（文件挪动/重命名后仍然过滤）
      const freshItems = res.new.filter((it) => !ignoredHashes.value.has(it.hash))
      filteredByIgnore.value = res.new.length - freshItems.length
      scanMeta.value = { skippedKnown: res.skipped_known, errors: res.errors }
      status.value = 'classifying'
      progress.value = { done: 0, total: freshItems.length }

      // 候选日期区：批次文件夹名解析（合法来源 #1；addZone 手动新建是来源 #2）
      const zoneDates = new Set<string>()
      for (const it of res.new) {
        const days = parseFolderDays(parentDirName(it.path))
        if (days) for (const d of days) zoneDates.add(d)
      }

      // 判定串行：每张缩略图 fetch + 解码 + 特征，避免并发内存尖峰
      const items = []
      for (const it of freshItems) {
        const verdict = await classifyThumb(it.thumb_url)
        items.push({
          path: it.path,
          hash: it.hash,
          thumbUrl: it.thumb_url,
          batch: parentDirName(it.path) ?? '',
          face: verdict.face,
          tier: verdict.tier,
          dupPid: it.dup_pid,
        })
        progress.value.done++
      }
      // 画布已存在 → 增量合并（保留已配对 / 已分区）；否则新建
      const dates = [...zoneDates].sort()
      if (board.value) {
        addItems(board.value, items, dates)
      } else {
        board.value = initBoard(items, dates)
      }
      status.value = 'ready'
    } catch (e) {
      errorMsg.value = e instanceof Error ? e.message : String(e)
      status.value = 'error'
    }
  }

  /** 逐卡提交：suggest-id → PUT。成功卡本地清除（反面区剩余保留）。 */
  async function commitAll(): Promise<CommitOutcome> {
    const b = board.value
    if (!b) return { ok: [], okCardIds: [], failed: [] }
    status.value = 'committing'
    const ok: string[] = []
    const okCardIds: string[] = []
    const failed: CommitOutcome['failed'] = []
    for (const card of committableCards(b)) {
      const payload = cardPayload(b, card.id)
      if (!payload) continue
      try {
        const primary = payload.tags.find((t) => t.startsWith('char:'))?.slice('char:'.length)
        const { pid } = await newApi.suggestId(payload.shot_date ?? undefined, primary)
        await polaroidsApi.save({
          id: pid,
          shot_date: payload.shot_date,
          tags: payload.tags,
          notes: '',
          assets: payload.assets,
          metadata: {},
        } as Parameters<typeof polaroidsApi.save>[0])
        ok.push(pid)
        okCardIds.push(card.id)
      } catch (e) {
        failed.push({ cardId: card.id, reason: e instanceof Error ? e.message : String(e) })
      }
    }
    libRemoveCards(b, okCardIds)
    status.value = 'ready'
    return { ok, okCardIds, failed }
  }

  /** 从忽略区移回：直接增量加回画布（单张判定，不清空已配好的状态）。
   * 画布未开时仅移出记录——下次扫描自然出现。 */
  async function restore(hash: string): Promise<void> {
    const idx = ignored.value.findIndex((it) => it.hash === hash)
    if (idx < 0) return
    const [record] = ignored.value.splice(idx, 1)
    persistIgnored()
    const b = board.value
    if (!b) return
    const verdict = await classifyThumb(record.thumbUrl)
    const batch = parentDirName(record.path) ?? ''
    const days = parseFolderDays(batch)
    addItems(b, [
      {
        path: record.path,
        hash: record.hash,
        thumbUrl: record.thumbUrl,
        batch,
        face: verdict.face,
        tier: verdict.tier,
        dupPid: null,
      },
    ], days ?? [])
  }

  // ---- 动作包装（board 为空时 no-op / false） ----
  function act(fn: (b: Board) => void): void {
    if (board.value) fn(board.value)
  }

  return {
    // 状态
    board, status, errorMsg, progress, scanMeta, filteredByIgnore,
    pool, cards, zones, unsortedCards, committable, batchGroups,
    ignored,
    chipOf,
    // 流水线
    scan, commitAll,
    // 动作
    flipChip: (chipId: string) => act((b) => libFlipChip(b, chipId)),
    pairBack: (backChipId: string, cardId: string) =>
      board.value ? libPairBack(board.value, backChipId, cardId) : false,
    unpairBack: (cardId: string) => act((b) => libUnpairBack(b, cardId)),
    moveCard: (cardId: string, zone: string) =>
      board.value ? libMoveCard(board.value, cardId, zone) : false,
    addZone: (dateIso: string) => (board.value ? libAddZone(board.value, dateIso) : false),
    removeZone: (dateIso: string) => act((b) => libRemoveZone(b, dateIso)),
    addTag: (cardId: string, tag: string) =>
      board.value ? libAddTag(board.value, cardId, tag) : false,
    removeTag: (cardId: string, tag: string) => act((b) => libRemoveTag(b, cardId, tag)),
    ignoreChip,
    unignore,
    restore,
  }
}
