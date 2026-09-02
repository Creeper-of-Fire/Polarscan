<!--
  PolaroidTagsEditor: 角色 (char) + 其他标签 (tag) 的统一编辑 UI

  职责:
  - v-model 双向绑定 tag 列表 (modelValue / update:modelValue)
  - **单源头**: charTags / otherTags 都从 props.modelValue 派生, 显示时按前缀过滤;
    添加走 emit update:modelValue, 不维护内部副本, 因此不存在跨区重复 / 跨区跳位.
  - chip 输入 + 候选补全 + 角色池快捷按钮
  - 角色 chip 走 CharTag (RGB 色块 + 隐藏前缀 + hovertip + 点击跳转)

  设计要点 (2026-08 重构, B1+B2+应援色; 2026-09 候选加权+应援色命中+应援色 hover):
  - 归并自 BenchView 的两段 chip UI, NewView 也走同一份
  - 内部用两个 useChipStream 实例, 但仅用于 query + 候选, 不持有 modelValue
  - 不再有 watcher / splitTags 双向同步; 数据归属 = props.modelValue
  - char 候选自派生: 候选集 = charMeta ∪ suggestions ∩ char:; 走 lib/charSearch 的
    scoreCharMatch 加权 (key 完全 100 / canonical 完全 90 / alias 完全 85 /
    prefix 80-60 / contains 50-30 + 多字段命中 +20/字段), 多命中候选自然排前.
  - 应援色在 dropdown 表达: 命中段背景 (~20% alpha 应援色) + 左竖条 (100% 应援色,
    border-radius 圆角). hover 加应援色背景 (~15% alpha) 走 inline JS
    (onMouseenter/onMouseleave), 不用 CSS (teleport + :deep 不可靠).

  TODO (char dropdown 视觉):
  - 评估是否要把 hover 检测点从 char-option 改成 NAutoComplete 外部 option div,
    让 hit area 等于整个 option 矩形 (含 option padding). 当前 char-option 自绑
    mouseenter 仅覆盖 chip 矩形, 视觉差几乎不可见.
    候选方案:
      A. char-option padding 撑到等于 option padding (视觉等效, 实现简单)
      B. renderOption 完全替代 NAutoComplete 默认 option 渲染 (丢内置 click /
         keyboard / pending class, 工作量大)
      C. NAutoComplete :node-props 监听外层 div mouseenter, 跨 ref 反向给
         char-option 设 backgroundColor (跨 component 引用, fragile)
      D. 其他可能方案 (待探索, 保持开放):
         - 用 floating-vue / popper 之类的 popover 库替代 NAutoComplete, 拿到完整
           渲染控制权
         - 改用 NSelect 自定义 filter + render (比 NAutoComplete 更灵活)
         - 把 char dropdown 拆成独立组件, 不用 NAutoComplete
         - 用 dropdown 包装层监听 mouseover/mouseout, 维护一个 "current hover option"
           ref, 在 chip 内读取并响应
         - 直接禁用 NAutoComplete hover 高亮, 用 :hover CSS + :global 注入 dropdown
         - 其他 (想到再加)
    现状: chip 自绑 mouseenter 已 work, 视觉差几乎不可见, 不必强求 B/C. D 留作未来
    若出现具体痛点再讨论.
-->

<script setup lang="ts">
import { computed, h, onMounted } from 'vue'
import type { VNode } from 'vue'
import { useRouter } from 'vue-router'
import { NCard, NAutoComplete, NButton, NTag, NSpace } from 'naive-ui'
import { useChipStream } from '@/composables/useChipStream'
import { usePolarscanStore } from '@/stores/polarscan'
import type { CharDisplay } from '@/stores/polarscan'
import { scoreCharMatch } from '@/lib/charSearch'
import CharTag from './CharTag.vue'

const props = defineProps<{
  /** 受控的完整 tags 列表 (v-model) */
  modelValue: string[]
  /** 候选集 (带前缀的 tag 全集, 如 ['char:strawberry', 'shot:pair', ...]) */
  suggestions: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [tags: string[]]
}>()

const router = useRouter()
const store = usePolarscanStore()

// char 池 meta 懒加载: 用 await 确保 NAutoComplete 第一次弹出选项时
// store.charMeta 已就绪, 选项能拿到应援色 / canonical / aliases;
// 否则 dropdown 会全是中性灰 (色块未着色).
// store 内部 dedup by charMetaLoaded, 多次调用不重复请求.
onMounted(async () => {
  await store.loadCharMeta()
})

// ---------- 单源头派生 ----------
/** 严格判定: 'char:' 前缀才视为 char tag. 无冒号 legacy 落入 other (数据正确, 仅显示层). */
function isCharTag(t: string): boolean {
  return t.startsWith('char:')
}
const charTags = computed(() => props.modelValue.filter(isCharTag))
const otherTags = computed(() => props.modelValue.filter((t) => !isCharTag(t)))

// ---------- 候选流 (仅 query + 候选, 不持有 modelValue) ----------
// char 流: 仅借用 computeTag / clearQuery (输入语义 + dedup); suggestItems
// 不用 useChipStream.onInput (那只能匹配 tag 字符串本身), 由下方 charOptions
// 自己派生 (含 aliases / canonical_name 搜索 + 加权排序 + highlight).
const charStream = useChipStream({
  autoPrefix: 'char',
  allowFreeform: false,
  suggestions: () => props.suggestions,
  getSelected: () => props.modelValue,
})
const {
  query: charQuery,
  computeTag: charComputeTag,
  clearQuery: charClearQuery,
} = charStream

const otherStream = useChipStream({
  allowFreeform: true,
  suggestions: () => props.suggestions,
  getSelected: () => props.modelValue,
})
const {
  query: otherQuery,
  suggestItems: otherItems,
  onInput: otherOnInput,
  clearQuery: otherClearQuery,
} = otherStream

// ---------- add / remove → emit 新 union ----------
function charAdd(raw: string) {
  const tag = charComputeTag(raw)
  if (!tag) return
  emit('update:modelValue', [...props.modelValue, tag])
  charClearQuery()
}
function charRemove(tag: string) {
  emit('update:modelValue', props.modelValue.filter((t) => t !== tag))
}
function otherAdd(raw: string) {
  const tag = otherStream.computeTag(raw)
  if (!tag) return
  emit('update:modelValue', [...props.modelValue, tag])
  otherClearQuery()
}
function otherRemove(tag: string) {
  emit('update:modelValue', props.modelValue.filter((t) => t !== tag))
}

// ---------- 池子快捷按钮 ----------
const charPool = computed(() =>
  props.suggestions.filter((s) => s.startsWith('char:')).map((s) => s.slice(5)),
)
const shotPool = computed(() =>
  props.suggestions.filter((s) => s.startsWith('shot:')).map((s) => s.slice(5)),
)
const sigPool = computed(() =>
  props.suggestions.filter((s) => s.startsWith('sig:')).map((s) => s.slice(4)),
)

// ---------- char NAutoComplete 选项 ----------
// 候选源 = charMeta (registered) ∪ suggestions ∩ char: (used including unregistered).
// 评分 / 排序 / highlight 走 scoreCharMatch (lib/charSearch.ts).
// 同分按 key 升序, 输出稳定.
//
// meta 未就绪时 dropdown 暂不显示, 避免"灰色 swatch 闪烁"的视觉错位 (用户
// 看到灰 swatch 以为系统坏了, 但其实是 charMeta 还在飞). store.charMetaLoaded
// 在 loadCharMeta 完成后变 true, computed 自动重算 → 出现带色 swatch 的候选.
type CharOption = {
  label: string
  value: string
  display: CharDisplay
  /** 当前查询串 (用于 highlight 渲染, 空 → 无命中段) */
  q: string
}
const CHAR_OPTION_LIMIT = 12
const charOptions = computed<CharOption[]>(() => {
  if (!store.charMetaLoaded) return []  // 等 meta, 避免灰 swatch
  const q = charQuery.value.trim()
  if (!q) return []

  const prefix = 'char:'
  const selected = new Set(props.modelValue)

  // 候选源: union of charMeta keys + suggestions (used-but-unregistered)
  const all = new Set<string>()
  for (const k of Object.keys(store.charMeta)) all.add(`${prefix}${k}`)
  for (const s of props.suggestions) {
    if (s.startsWith(prefix)) all.add(s)
  }

  type Scored = { tag: string; display: CharDisplay; score: number }
  const scored: Scored[] = []
  for (const tag of all) {
    if (selected.has(tag)) continue
    const key = tag.slice(prefix.length)
    const display = store.getCharDisplay(key)
    const m = scoreCharMatch(q, display)
    if (m.score > 0) scored.push({ tag, display, score: m.score })
  }
  scored.sort((a, b) => b.score - a.score || a.display.key.localeCompare(b.display.key))
  return scored.slice(0, CHAR_OPTION_LIMIT).map(s => ({
    label: s.tag,
    value: s.tag,
    display: s.display,
    q,
  }))
})
const otherOptions = computed(() => otherItems.value.map((s) => ({ label: s, value: s })))

// 把字符串里 q 命中的子串包成 <mark>; 无命中返回原字符串 (VNode|string union).
// 调用方须把返回值作为 h() 的 child (不能放进字符串模板 — VNode toString 会变
// "[object Object]", 用户截图里的 bug).
//
// hitColor: 该 char 的应援色 (hex like '#F9A7D6'). 命中段用这个色的 ~20% alpha
// 做背景 — 每个候选用自己的应援色高亮. 不加 padding (会和前后字符"分隔开",
// 让命中段看起来像独立 chip), 仅靠 background + border-radius 区分. 命中不
// 加粗, 保持和原文一致.
function highlightText(text: string, q: string, hitColor: string | null): VNode | string {
  if (!q) return text
  const idx = text.toLowerCase().indexOf(q.toLowerCase())
  if (idx < 0) return text
  // hex + '33' ≈ 51/255 ≈ 20% alpha; fallback 中性灰 (无 color_rgb 时)
  const bg = hitColor ? `${hitColor}33` : 'rgba(150, 150, 150, 0.25)'
  return h('span', null, [
    text.slice(0, idx),
    h('mark', {
      class: 'char-option-hit',
      style: `background: ${bg}; border-radius: 2px`,
    }, text.slice(idx, idx + q.length)),
    text.slice(idx + q.length),
  ])
}

// char 选项渲染: 应援色放两处 — ① 命中段背景 (highlight 用每个候选自己的色)
// ② 左侧竖条 (3px border-left + 圆角, 让色带两端圆弧).
// hover 时整个 chip 用应援色做背景 — 用 inline onMouseenter/onMouseleave 直接
// 改 element.style.backgroundColor, 不依赖 scoped CSS 穿透到 NAutoComplete
// 的 teleport dropdown (之前的 :deep() + .pending class 方案不可靠, dropdown
// 是 teleport 到 body 下, scoped style 不一定能匹配).
//
// 主显示文本 = canonical_name 优先, fallback 到 key (无前缀); 走 fallback 时
// 把 key 作为搜索提示括起来. aliases 全部列出, 命中的 alias 在 highlightText
// 内部包 <mark>.
function renderCharLabel(option: CharOption): VNode {
  const d = option.display
  const q = option.q
  const hasCanonical = !!d.canonical_name
  const mainText = d.canonical_name ?? d.key
  // 应援色: 有 color_rgb 用之, 没有就 transparent (避免画无意义的灰色边框/色带).
  const color = d.color_rgb ?? 'transparent'
  // hover 背景色: 应援色 ~15% alpha (比命中段 ~20% 浅一档, 区分静态命中和 hover).
  // 未定义 char (无 color_rgb) 走中性灰 fallback, 视觉上仍有 hover 反馈.
  const hoverBg = d.color_rgb ? `${d.color_rgb}26` : 'rgba(150, 150, 150, 0.15)'

  // 直接在 element 上设/清 backgroundColor. 用 currentTarget 而不是 target —
  // target 是触发元素 (可能是子 span), currentTarget 是绑事件的元素 (char-option).
  function onEnter(e: MouseEvent) {
    (e.currentTarget as HTMLElement).style.backgroundColor = hoverBg
  }
  function onLeave(e: MouseEvent) {
    (e.currentTarget as HTMLElement).style.backgroundColor = ''
  }

  return h('span', {
    class: 'char-option',
    style: `
      display: inline-flex; align-items: center; gap: 6px;
      padding: 2px 6px;
      border-radius: 3px;
      border-left: 3px solid ${color};
      max-width: 100%;
    `,
    onMouseenter: onEnter,
    onMouseleave: onLeave,
  }, [
    h('span', {
      class: 'char-tag-text',
    }, highlightText(mainText, q, d.color_rgb)),
    // 主显示是 canonical 时, 把 key 作为搜索提示 (便于识别) — 命中时也 highlight.
    // 关键: highlightText 必须作为 h() 的 child, 不能嵌进字符串模板 (→ [object Object]).
    hasCanonical
      ? h('span', {
        class: 'char-option-key-hint',
        style: 'color: #999; font-size: 11px; margin-left: 4px',
      }, ['(', highlightText(d.key, q, d.color_rgb), ')'])
      : null,
    // aliases 全列; 命中的 alias 自动 highlight
    d.aliases.length > 0
      ? h('span', {
        class: 'char-option-aliases',
        style: 'color: #999; font-size: 11px; margin-left: 4px',
      }, d.aliases.flatMap((alias, i) => {
        const sep = i > 0 ? ', ' : ''
        return [sep, highlightText(alias, q, d.color_rgb)]
      }))
      : null,
  ])
}

function onCharQueryInput(v: string) {
  charQuery.value = v
  // 不再调 useChipStream.onInput; charOptions 自己基于 query + meta 派生
}
function onOtherQueryInput(v: string) {
  otherQuery.value = v
  otherOnInput()
}

// char chip 点击 → 跳转到该角色 pool 编辑页 (CharTag emit 的是 key, 已去前缀)
function goChar(key: string) {
  router.push(`/pool/char/${encodeURIComponent(key)}/edit`)
}
</script>

<template>
  <div class="polaroid-tags-editor">
    <!-- 角色 (char) -->
    <NCard title="角色 (char)" size="small" style="margin-bottom: 12px">
      <div>
        <CharTag
          v-for="tag in charTags"
          :key="tag"
          :tag="tag"
          closable
          @close="charRemove(tag)"
          @click="goChar"
        />
      </div>
      <NSpace style="margin-top: 8px">
        <NAutoComplete
          :value="charQuery"
          :options="charOptions"
          :render-label="renderCharLabel"
          :filterable="false"
          :default-active-first-option="false"
          clearable
          placeholder="角色标识 (例: my_push)"
          style="min-width: 320px"
          @update:value="onCharQueryInput"
          @select="(v: string) => charAdd(v)"
          @keyup.enter="charAdd(charQuery)"
        />
        <NButton @click="charAdd(charQuery)">+ 角色</NButton>
      </NSpace>
      <div v-if="charPool.length > 0" style="margin-top: 8px">
        <span style="color: #666; font-size: 12px">角色池:</span>
        <CharTag
          v-for="c in charPool.slice(0, 18)"
          :key="c"
          :tag="`char:${c}`"
          interactive
          @click="(k) => charAdd(`char:${k}`)"
        />
      </div>
    </NCard>

    <!-- 其他标签 -->
    <NCard title="其他标签 (tag)" size="small">
      <div>
        <NTag
          v-for="tag in otherTags"
          :key="tag"
          closable
          :type="tag.startsWith('shot:') ? 'success' : tag.startsWith('sig:') ? 'warning' : 'default'"
          style="margin: 2px"
          @close="otherRemove(tag)"
        >
          {{ tag }}
        </NTag>
      </div>
      <NSpace style="margin-top: 8px">
        <NAutoComplete
          :value="otherQuery"
          :options="otherOptions"
          :filterable="false"
          :default-active-first-option="false"
          clearable
          placeholder="其他标签 (例: event:shenshan_3rd_om_cd, shot:pair)"
          style="min-width: 360px"
          @update:value="onOtherQueryInput"
          @select="(v: string) => otherAdd(v)"
          @keyup.enter="otherAdd(otherQuery)"
        />
        <NButton @click="otherAdd(otherQuery)">+ 标签</NButton>
      </NSpace>
      <!-- 池快捷按钮: 与已选 chip 统一 NTag 形态 (dashed + 加号 = "可加");
           视觉上与已选 (实色 type=success|warning) 区分, 点击是 + -->
      <div v-if="shotPool.length > 0 || sigPool.length > 0" style="margin-top: 8px">
        <span style="color: #666; font-size: 12px">shot / sig 池:</span>
        <NTag
          v-for="s in shotPool.slice(0, 8)"
          :key="'shot-' + s"
          type="success"
          size="small"
          :dashed="true"
          style="cursor: pointer; margin: 2px"
          @click="otherAdd(`shot:${s}`)"
        >
          + shot:{{ s }}
        </NTag>
        <NTag
          v-for="s in sigPool.slice(0, 8)"
          :key="'sig-' + s"
          type="warning"
          size="small"
          :dashed="true"
          style="cursor: pointer; margin: 2px"
          @click="otherAdd(`sig:${s}`)"
        >
          + sig:{{ s }}
        </NTag>
      </div>
    </NCard>
  </div>
</template>

<style scoped>
.polaroid-tags-editor {
  display: flex;
  flex-direction: column;
}
</style>