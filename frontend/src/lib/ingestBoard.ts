// ingestBoard — 连连看画布状态机（纯函数，无 Vue 依赖，node 可测）。
//
// ── 心智模型（与用户对齐的设计，见 docs/spec/ingest-scan.md § 2.4）───────
//   卡 = 正面 chip。背面 chip 本质上是一种高级 tag：
//     face = front 的 chip ≡ 一张卡的本体（卡 = 本体 + 0..1 挂载背面 + tags）
//     face = back / unknown 且未挂载 ≡ 反面区自由 chip
//
// ── 翻转语义（角标点击）──────────────────────────────────────────────────
//   front → back        卡解散：挂载背面（若有）弹回反面区，本体回反面区
//   back / unknown → front  摘除挂载（若有），升级成一张新卡（进未分类区）
//
// ── 硬规则 ──────────────────────────────────────────────────────────────
//   - 背面挂载互斥：一卡最多一个背面
//   - 日期区只有两个来源：initBoard 的解析候选 + addZone 手动新建；
//     moveCard 不接受不存在的区（卡永远不能自动长出日期区）
//   - 跳过的卡不参与提交（payload 由视图层逐卡组装）
//
import type { Face, FaceTier } from './faceRules'

/** 固定区：未分类 */
export const ZONE_UNSORTED = 'unsorted'

export interface Chip {
  /** 扫描件唯一标识（用 path） */
  id: string
  path: string
  hash: string
  thumbUrl: string
  /** 来源批次 = 父文件夹名（合法分组依据：文件夹名来自人类手工分类） */
  batch: string
  /** 当前面别（机器判定 + 人工翻转后的生效值） */
  face: Face
  /** 机器判定原值（翻转后保留，供 UI 显示"机器原判"） */
  autoFace: Face
  tier: FaceTier
  dupPid: string | null
}

export interface Card {
  /** = 正面 chip id */
  id: string
  frontChipId: string
  backChipId: string | null
  tags: string[]
  /** ZONE_UNSORTED 或 ISO 日期（YYYY-MM-DD）。未分类 = 不参与提交 */
  zone: string
}

export interface Board {
  chips: Record<string, Chip>
  cards: Record<string, Card>
  /** 日期区列表（ISO 日期，升序展示由视图层排） */
  zones: string[]
}

/** scan 端点返回的单项（前端拿到后先过 useFaceClassify 填 face/tier） */
export interface ScanItem {
  path: string
  hash: string
  thumbUrl: string
  /** 来源批次（父文件夹名），由 composable 派生 */
  batch: string
  face: Face
  tier: FaceTier
  dupPid: string | null
}

// ───────────────────────── 初始化 ─────────────────────────

/**
 * scan 结果 + 候选日期区 → 初始画布。
 * face = front 的 chip 自动成卡进未分类区；back / unknown 留作自由 chip
 * （显示时按 batch 分组待在所属批次框里）。
 */
export function initBoard(items: ScanItem[], zoneDates: string[]): Board {
  const board: Board = { chips: {}, cards: {}, zones: [...new Set(zoneDates)] }
  for (const it of items) {
    board.chips[it.path] = {
      id: it.path,
      path: it.path,
      hash: it.hash,
      thumbUrl: it.thumbUrl,
      batch: it.batch,
      face: it.face,
      autoFace: it.face,
      tier: it.tier,
      dupPid: it.dupPid,
    }
    if (it.face === 'front') {
      board.cards[it.path] = {
        id: it.path,
        frontChipId: it.path,
        backChipId: null,
        tags: [],
        zone: ZONE_UNSORTED,
      }
    }
  }
  return board
}

/**
 * 向现有画布增量添加扫描项（忽略区恢复 / 重扫合并用）。
 * **保留现有卡 / 配对 / 日期区**：front 成新卡进未分类，back / unknown 入自由池；
 * 新批次的候选日合并进 zones（去重）；已在画布的 path 跳过。
 */
export function addItems(board: Board, items: ScanItem[], zoneDates: string[]): void {
  for (const d of zoneDates) {
    if (d !== ZONE_UNSORTED && !board.zones.includes(d)) board.zones.push(d)
  }
  for (const it of items) {
    if (board.chips[it.path]) continue
    board.chips[it.path] = {
      id: it.path,
      path: it.path,
      hash: it.hash,
      thumbUrl: it.thumbUrl,
      batch: it.batch,
      face: it.face,
      autoFace: it.face,
      tier: it.tier,
      dupPid: it.dupPid,
    }
    if (it.face === 'front') {
      board.cards[it.path] = {
        id: it.path,
        frontChipId: it.path,
        backChipId: null,
        tags: [],
        zone: ZONE_UNSORTED,
      }
    }
  }
}

// ───────────────────────── 翻转 ─────────────────────────

/**
 * 角标点击翻转（二态：front↔back；unknown 视作背面侧）。
 * back/unknown → front：摘除现有挂载（若有），升级成新卡（未分类区）。
 * front → back：卡解散，挂载背面弹回反面区，本体回反面区。
 */
export function flipChip(board: Board, chipId: string): void {
  const chip = board.chips[chipId]
  if (!chip) return

  if (chip.face === 'front') {
    // 卡解散：先弹出挂载的背面
    const card = board.cards[chipId]
    if (card) {
      card.backChipId = null // 挂载关系即消失（chip 本身留在 chips 表 = 反面区）
      delete board.cards[chipId]
    }
    chip.face = 'back'
    return
  }

  // back / unknown → front：若挂在某卡上，先解除
  for (const card of Object.values(board.cards)) {
    if (card.backChipId === chipId) card.backChipId = null
  }
  chip.face = 'front'
  board.cards[chipId] = {
    id: chipId,
    frontChipId: chipId,
    backChipId: null,
    tags: [],
    zone: ZONE_UNSORTED,
  }
}

// ───────────────────────── 配对（挂载） ─────────────────────────

/** 拖背面 chip 到卡 → 配对。成功 false 的情形：卡不存在 / 已有背面 / chip 非背面侧。 */
export function pairBack(board: Board, backChipId: string, cardId: string): boolean {
  const chip = board.chips[backChipId]
  const card = board.cards[cardId]
  if (!chip || !card) return false
  if (chip.face === 'front') return false
  if (card.backChipId) return false
  // 若该 chip 已挂在别的卡上，先解除
  for (const c of Object.values(board.cards)) {
    if (c.backChipId === backChipId) c.backChipId = null
  }
  card.backChipId = backChipId
  return true
}

/** 解除卡的背面挂载（拖回反面区）。 */
export function unpairBack(board: Board, cardId: string): void {
  const card = board.cards[cardId]
  if (card) card.backChipId = null
}

// ───────────────────────── 日期区 ─────────────────────────

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/** 手动新建日期区（唯一合法的运行时新建途径）。非法格式 / 已存在 → false。 */
export function addZone(board: Board, dateIso: string): boolean {
  if (!ISO_DATE.test(dateIso)) return false
  if (board.zones.includes(dateIso) || dateIso === ZONE_UNSORTED) return false
  board.zones.push(dateIso)
  return true
}

/** 删除日期区：区里的卡全部弹回未分类区。 */
export function removeZone(board: Board, dateIso: string): void {
  if (dateIso === ZONE_UNSORTED) return
  board.zones = board.zones.filter((z) => z !== dateIso)
  for (const card of Object.values(board.cards)) {
    if (card.zone === dateIso) card.zone = ZONE_UNSORTED
  }
}

/** 卡入区（拖拽柄）。区不存在（且不是未分类）→ false，绝不隐式建区。 */
export function moveCard(board: Board, cardId: string, zone: string): boolean {
  const card = board.cards[cardId]
  if (!card) return false
  if (zone !== ZONE_UNSORTED && !board.zones.includes(zone)) return false
  card.zone = zone
  return true
}

// ───────────────────────── tag ─────────────────────────

export function addTag(board: Board, cardId: string, tag: string): boolean {
  const card = board.cards[cardId]
  if (!card || !tag || card.tags.includes(tag)) return false
  card.tags.push(tag)
  return true
}

export function removeTag(board: Board, cardId: string, tag: string): void {
  const card = board.cards[cardId]
  if (card) card.tags = card.tags.filter((t) => t !== tag)
}

// ───────────────────────── 忽略（chip 级删除） ─────────────────────────

/**
 * 从画布删除指定 chip（"放入忽略区"的画布侧动作；localStorage 记录由 composable 负责）。
 * - 自由背面 chip：直接消失
 * - 挂载中的背面：解除挂载后消失（宿主卡保留）
 * - 卡本体（正面）：卡解散，其挂载背面（若有）自动弹回自由池
 */
export function removeChips(board: Board, chipIds: string[]): void {
  for (const chipId of chipIds) {
    const chip = board.chips[chipId]
    if (!chip) continue
    if (chip.face === 'front') {
      // 卡解散：backChipId 引用随卡对象一起消失，背面自动回到自由池
      delete board.cards[chipId]
    } else {
      for (const c of Object.values(board.cards)) {
        if (c.backChipId === chipId) c.backChipId = null
      }
    }
    delete board.chips[chipId]
  }
}

// ───────────────────────── 查询 ─────────────────────────

/** 反面区自由 chip：face 为 back/unknown 且未挂载任何卡。 */
export function poolChips(board: Board): Chip[] {
  const mounted = new Set(
    Object.values(board.cards).map((c) => c.backChipId).filter(Boolean as unknown as (v: string | null) => v is string),
  )
  return Object.values(board.chips).filter(
    (ch) => ch.face !== 'front' && !mounted.has(ch.id),
  )
}

export interface BatchGroup {
  /** 批次名（父文件夹名） */
  batch: string
  /** 该批次未分类的卡 */
  cards: Card[]
  /** 该批次未挂载的背面 chip（待配对，就在卡的旁边） */
  chips: Chip[]
}

/** 未分类大框的分组视图：按批次分小框——卡按正面 chip 的批次归组，
 * 自由背面 chip 按自身批次归组。批次顺序按名称排序。
 *
 * 注意：这是**摆放**分组，不是配对依据——按文件夹名摆放合法（人类手工分类），
 * 配对仍只能由人的拖拽决定（AGENTS.md 否决扫描时间/文件序配对）。 */
export function unsortedByBatch(board: Board): BatchGroup[] {
  const groups = new Map<string, BatchGroup>()
  const get = (batch: string): BatchGroup => {
    let g = groups.get(batch)
    if (!g) {
      g = { batch, cards: [], chips: [] }
      groups.set(batch, g)
    }
    return g
  }
  for (const card of Object.values(board.cards)) {
    if (card.zone !== ZONE_UNSORTED) continue
    const chip = board.chips[card.frontChipId]
    if (chip) get(chip.batch).cards.push(card)
  }
  for (const chip of poolChips(board)) {
    get(chip.batch).chips.push(chip)
  }
  return [...groups.values()].sort((a, b) => a.batch.localeCompare(b.batch))
}

/** 可提交的卡 = 日期区里的卡（未分类/左栏 = 本次不提交）。 */
export function committableCards(board: Board): Card[] {
  return Object.values(board.cards).filter((c) => c.zone !== ZONE_UNSORTED)
}

/** 提交成功后的本地清理：删卡 + 删卡上全部 chip（含挂载背面）。
 * 反面区剩余 chip 不受影响。 */
export function removeCards(board: Board, cardIds: string[]): void {
  for (const cardId of cardIds) {
    const card = board.cards[cardId]
    if (!card) continue
    delete board.chips[card.frontChipId]
    if (card.backChipId) delete board.chips[card.backChipId]
    delete board.cards[cardId]
  }
}

// ───────────────────────── 提交载荷 ─────────────────────────

export interface CardPayload {
  /** PUT /polaroid 的 assets 字段（role 显式；id 由视图层经 suggest-id 生成） */
  assets: Array<{ role: string; path: string; hash: string; device: null; metadata: Record<string, unknown> }>
  /** 区日期或 null——绝不自动填（shot-date-semantics） */
  shot_date: string | null
  tags: string[]
}

/** 组装单卡提交载荷。未分类（左栏）的卡不参与提交；判定元数据随资产透传。 */
export function cardPayload(board: Board, cardId: string): CardPayload | null {
  const card = board.cards[cardId]
  if (!card || card.zone === ZONE_UNSORTED) return null
  const front = board.chips[card.frontChipId]
  if (!front) return null

  const faceMeta = (ch: Chip): Record<string, unknown> => ({
    ingest: {
      auto_face: ch.autoFace,
      tier: ch.tier,
      manual_flip: ch.face !== ch.autoFace,
    },
  })

  const assets: CardPayload['assets'] = [
    { role: 'front', path: front.path, hash: front.hash, device: null, metadata: faceMeta(front) },
  ]
  if (card.backChipId) {
    const back = board.chips[card.backChipId]
    if (back) {
      assets.push({ role: 'back', path: back.path, hash: back.hash, device: null, metadata: faceMeta(back) })
    }
  }
  return {
    assets,
    shot_date: card.zone === ZONE_UNSORTED ? null : card.zone,
    tags: [...card.tags],
  }
}
