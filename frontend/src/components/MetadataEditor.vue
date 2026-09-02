<!--
  MetadataEditor: 任意 JSON 透传字段的编辑器 (逐 key-value 列表)

  职责:
  - v-model 双向绑定 metadata 字典 (Record<string, any>)
  - 每行一个 key + 类型选择 + 类型化 value 输入 + 删除按钮
  - 支持 string/number/boolean/null/object/array 六种类型
  - object/array 走内嵌 JSON 文本框 (避免无限递归 UI)
  - 解析失败时不 emit, 保留用户输入让修复

  设计要点 (2026-09 升级):
  - 与 PolaroidTagsEditor 风格保持一致 (NCard 包裹)
  - 替代旧版 "textarea + JSON.parse": 字段被固化/以奇怪形式显示的体验差
  - 类型切换不自动转换 raw; 由用户自己重新输入
  - 嵌套结构 (object/array) 不递归 UI, 走 JSON 文本框 — 这是用户能接受的"通用"
  - core 不解析 metadata 内部结构, 这里也不做 schema 校验
  - 不在 setup 内 watch props (immediate: true): 父组件 v-if 包裹 + 后台异步取数
    会让 MetadataEditor 在 onMounted 之后才挂载, 此时 props.modelValue 已是真实数据,
    immediate 触发会和 "父组件真实数据" 撞车误判为 self-emit 跳过, 导致 rows 永远空.
    改为 onMounted 主动 syncFromProps 一次 + watch 走 deepEqual 内容对比.
-->
<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { NCard, NInput, NInputNumber, NSwitch, NSelect, NSpace, NButton, NText } from 'naive-ui'

type JsonValueType = 'string' | 'number' | 'boolean' | 'null' | 'object' | 'array'

interface FieldRow {
  /** 内部稳定 id — 不依赖用户 key, 用于 v-for key / 增删定位 */
  rowId: string
  key: string
  type: JsonValueType
  /** string / number 的字符串形式; object / array 的 JSON 字符串 */
  raw: string
  /** boolean 的状态 */
  boolValue: boolean
  /** object / array 解析错误信息; null = 解析成功或尚未校验 */
  parseError: string | null
}

const props = defineProps<{
  /** 受控的 metadata 字典 (v-model). undefined / null 时视为空 dict. */
  modelValue?: Record<string, any>
}>()

const emit = defineEmits<{
  'update:modelValue': [metadata: Record<string, any>]
}>()

const rows = ref<FieldRow[]>([])
/** 顶层错误摘要 (空 key / 重复 key 之类跨字段问题); 单行错误走 row.parseError */
const errorBanner = ref<string | null>(null)

let rowCounter = 0
function newRowId(): string {
  rowCounter += 1
  return `r${rowCounter}`
}

function inferType(v: unknown): JsonValueType {
  if (v === null) return 'null'
  if (Array.isArray(v)) return 'array'
  const t = typeof v
  if (t === 'string') return 'string'
  if (t === 'number') return 'number'
  if (t === 'boolean') return 'boolean'
  return 'object'
}

function serializeForRaw(type: JsonValueType, v: unknown): string {
  if (v === undefined) return ''
  if (type === 'string' || type === 'number') return String(v)
  if (type === 'null') return ''
  // object / array
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return ''
  }
}

function makeRow(key: string, value: unknown): FieldRow {
  const type = inferType(value)
  return {
    rowId: newRowId(),
    key,
    type,
    raw: type === 'boolean' ? '' : serializeForRaw(type, value),
    boolValue: type === 'boolean' ? Boolean(value) : false,
    parseError: null,
  }
}

function syncFromProps(dict: Record<string, any> | undefined) {
  const d = dict ?? {}
  rows.value = Object.entries(d).map(([k, v]) => makeRow(k, v))
  errorBanner.value = null
}

function parseRawValue(
  row: FieldRow,
): { ok: true; value: unknown } | { ok: false; error: string } {
  if (row.type === 'string') return { ok: true, value: row.raw }
  if (row.type === 'number') {
    if (row.raw.trim() === '') return { ok: false, error: '数字不能为空' }
    const n = Number(row.raw)
    if (Number.isNaN(n)) return { ok: false, error: '数字格式错误' }
    return { ok: true, value: n }
  }
  if (row.type === 'boolean') return { ok: true, value: row.boolValue }
  if (row.type === 'null') return { ok: true, value: null }
  // object / array
  const trimmed = row.raw.trim()
  if (trimmed === '') {
    if (row.type === 'object') return { ok: true, value: {} }
    return { ok: true, value: [] }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch (e) {
    return { ok: false, error: `JSON 解析失败: ${(e as Error).message}` }
  }
  if (row.type === 'object') {
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { ok: false, error: 'object 字段必须是 JSON object' }
    }
  } else {
    if (!Array.isArray(parsed)) {
      return { ok: false, error: 'array 字段必须是 JSON array' }
    }
  }
  return { ok: true, value: parsed }
}

function updateRow(rowId: string, patch: Partial<FieldRow>) {
  const row = rows.value.find((r) => r.rowId === rowId)
  if (!row) return
  Object.assign(row, patch)
  // 类型切换 / raw 改变时清掉 stale parseError
  if ('type' in patch || 'raw' in patch || 'boolValue' in patch) {
    row.parseError = null
  }
  emitOutput()
}

function addRow() {
  rows.value = [
    ...rows.value,
    {
      rowId: newRowId(),
      key: '',
      type: 'string',
      raw: '',
      boolValue: false,
      parseError: null,
    },
  ]
}

function removeRow(rowId: string) {
  rows.value = rows.value.filter((r) => r.rowId !== rowId)
  emitOutput()
}

/** 收集错误并 emit (无错时). 解析失败 / 空 key 都阻断 emit — 避免脏数据回到父组件. */
function emitOutput() {
  const out: Record<string, any> = {}
  const errors: string[] = []
  for (const row of rows.value) {
    const parsed = parseRawValue(row)
    if (!parsed.ok) {
      row.parseError = parsed.error
      errors.push(`字段 "${row.key || '(未命名)'}": ${parsed.error}`)
      continue
    }
    if (!row.key) {
      errors.push('存在空 key 字段, 请填写后再保存')
      continue
    }
    out[row.key] = parsed.value
  }
  // 跨字段问题: 重复 key (后写覆盖前写, JSON 规范允许但用户大概率写错)
  const dupKeys = new Set<string>()
  const seen = new Set<string>()
  for (const r of rows.value) {
    if (!r.key) continue
    if (seen.has(r.key)) dupKeys.add(r.key)
    seen.add(r.key)
  }
  if (dupKeys.size > 0) {
    errors.push(`重复 key: ${[...dupKeys].join(', ')} (后写覆盖前写)`)
  }
  errorBanner.value = errors.length > 0 ? errors[0] : null
  if (errors.length === 0) {
    emit('update:modelValue', out)
  }
}

const typeOptions = [
  { label: 'string', value: 'string' },
  { label: 'number', value: 'number' },
  { label: 'boolean', value: 'boolean' },
  { label: 'null', value: 'null' },
  { label: 'object', value: 'object' },
  { label: 'array', value: 'array' },
]

/** 仅用于高亮 key 输入框, 不阻断 emit (重复 key 在 banner 里集中提示) */
const duplicateKeys = computed<Set<string>>(() => {
  const seen = new Set<string>()
  const dups = new Set<string>()
  for (const r of rows.value) {
    if (!r.key) continue
    if (seen.has(r.key)) dups.add(r.key)
    seen.add(r.key)
  }
  return dups
})

/** props 变化 → deepEqual 比对: 内容等价跳过 (父 v-model round-trip), 不等则重建 rows.
 *  挂载时主动 syncFromProps 一次 — 不走 watch + immediate, 避免父 v-if 异步挂载场景下
 *  把 "父组件真实数据" 误判为 self-emit (参见文件顶部设计说明). */
onMounted(() => {
  syncFromProps(props.modelValue)
})

watch(() => props.modelValue, (next) => {
  if (deepEqual(next ?? {}, dictFromRows())) return
  syncFromProps(next)
})

/** 当前 rows 重建出的 dict (含解析失败的行会被跳过, 与 emit 输出一致) */
function dictFromRows(): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const row of rows.value) {
    if (!row.key) continue
    const parsed = parseRawValue(row)
    if (parsed.ok) out[row.key] = parsed.value
  }
  return out
}

/** 浅层 deep equal — metadata 字段值可能是 string/number/bool/null/object/array,
 *  递归到叶子即可. 不处理 Date/RegExp/Map/Set 等 core 不会存的类型. */
function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (a === null || b === null) return false
  if (typeof a !== typeof b) return false
  if (typeof a !== 'object') return false
  const aArr = Array.isArray(a)
  const bArr = Array.isArray(b)
  if (aArr !== bArr) return false
  if (aArr) {
    const aa = a as unknown[]
    const bb = b as unknown[]
    if (aa.length !== bb.length) return false
    for (let i = 0; i < aa.length; i++) {
      if (!deepEqual(aa[i], bb[i])) return false
    }
    return true
  }
  const ao = a as Record<string, unknown>
  const bo = b as Record<string, unknown>
  const ak = Object.keys(ao)
  const bk = Object.keys(bo)
  if (ak.length !== bk.length) return false
  for (const k of ak) {
    if (!deepEqual(ao[k], bo[k])) return false
  }
  return true
}
</script>

<template>
  <NCard title="元数据 (metadata)" size="small">
    <NSpace vertical>
      <div v-if="rows.length === 0" style="color: #999; font-size: 12px">
        暂无字段, 点下方按钮添加
      </div>

      <div
        v-for="row in rows"
        :key="row.rowId"
        style="display: flex; gap: 8px; align-items: flex-start"
      >
        <!-- key -->
        <NInput
          :value="row.key"
          placeholder="key"
          :status="!row.key || duplicateKeys.has(row.key) ? 'error' : undefined"
          style="flex: 0 0 160px"
          @update:value="(v: string) => updateRow(row.rowId, { key: v })"
        />

        <!-- type -->
        <NSelect
          :value="row.type"
          :options="typeOptions"
          style="flex: 0 0 110px"
          @update:value="(v: JsonValueType) => updateRow(row.rowId, { type: v })"
        />

        <!-- value (按类型) -->
        <div style="flex: 1; min-width: 0">
          <NInput
            v-if="row.type === 'string'"
            :value="row.raw"
            placeholder="value"
            @update:value="(v: string) => updateRow(row.rowId, { raw: v })"
          />
          <NInputNumber
            v-else-if="row.type === 'number'"
            :value="row.raw === '' ? null : Number(row.raw)"
            style="width: 100%"
            @update:value="(v: number | null) => updateRow(row.rowId, { raw: v === null ? '' : String(v) })"
          />
          <NSwitch
            v-else-if="row.type === 'boolean'"
            :value="row.boolValue"
            @update:value="(v: boolean) => updateRow(row.rowId, { boolValue: v })"
          />
          <NInput v-else-if="row.type === 'null'" value="null" readonly disabled />
          <NInput
            v-else
            type="textarea"
            :value="row.raw"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :status="row.parseError ? 'error' : undefined"
            :placeholder="row.type === 'object' ? '{ key: value }' : '[1, 2, 3]'"
            @update:value="(v: string) => updateRow(row.rowId, { raw: v })"
          />
          <NText
            v-if="row.parseError"
            type="error"
            style="font-size: 12px; display: block; margin-top: 2px"
          >
            {{ row.parseError }}
          </NText>
        </div>

        <!-- 删除 -->
        <NButton size="small" type="error" ghost @click="removeRow(row.rowId)">
          ×
        </NButton>
      </div>

      <NText v-if="errorBanner" type="error" style="font-size: 12px">
        {{ errorBanner }}
      </NText>

      <NButton size="small" dashed @click="addRow">
        + 添加字段
      </NButton>

      <NText style="font-size: 12px; color: #888">
        core 不解析 metadata 内部结构 — 任意 JSON 原样保存
      </NText>
    </NSpace>
  </NCard>
</template>
