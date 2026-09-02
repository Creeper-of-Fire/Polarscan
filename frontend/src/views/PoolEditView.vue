<!--
  PoolEditView: 编辑单条 pool 元数据 (canonical_name + aliases + notes + 应援色 + 其他任意字段)

  应援色字段 (顶层, 与 canonical_name 同级):
    color_name  str   文字描述 (例: "黄色")
    color_rgb   str   #RRGGBB hex 字符串

  core 不解析元数据内部结构, 这里走 backend 的"任意 JSON 透传"约定;
  后端 /pool/.../edit 端点把 form 字段写入 meta 顶层 dict.

  2026-09: "附加字段" 改用通用 MetadataEditor (逐 key-value 编辑器),
  替代旧的 "已有额外字段只读展示 + JSON 文本框" 双块结构.
  - 已知字段保留独立 UI (canonical_name / aliases / notes / color_name / color_rgb)
  - 其他任意 extras 字段统一交给 MetadataEditor, v-model 绑到 extrasDict
  - save() 时把 extrasDict 序列化成 JSON 字符串走 extra_json form 字段, 后端契约不变
-->
<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  NSpin, NForm, NFormItem, NInput, NButton, NSpace,
  NCard, NColorPicker, useMessage, useDialog,
} from 'naive-ui'
import { poolApi } from '@/api'
import { usePolarscanStore } from '@/stores/polarscan'
import MetadataEditor from '@/components/MetadataEditor.vue'
import type { PolaroidSummary } from '@/types'

/** 硬编码顶层字段: 由各表单单独编辑, 不进 MetadataEditor */
const KNOWN_FIELDS = new Set([
  'canonical_name', 'aliases', 'notes', 'color_name', 'color_rgb',
])

const props = defineProps<{ prefix: string; tagKey: string }>()
const router = useRouter()
const route = useRoute()
const message = useMessage()
const dialog = useDialog()
const store = usePolarscanStore()

const info = ref<Record<string, unknown>>({})
const usedBy = ref<PolaroidSummary[]>([])
const loading = ref(false)

const canonicalName = ref('')
const aliasesText = ref('')
const notes = ref('')
const colorName = ref('')
// color_rgb 默认空字符串: 与 "是否定义应援色" 语义对齐 — 空 = 未设置.
// 不 fallback 到中性灰, 否则用户进编辑页不主动改色直接保存, 会把中性灰写入后端.
const colorRgb = ref('')

// NColorPicker 在 value=空 时进入 "未设置" 特殊态, 重新选色可能输出 rgb()/rgba() 而非 #RRGGBB.
// 后端 _is_valid_hex_color 只接受 #RRGGBB, 这里把任何格式归一到 #RRGGBB (大写).
// 未知格式 → 保持原值不变, 避免破坏已有合法状态.
function normalizeColorRgb(v: string): string {
  if (v == null || v === '') return ''
  if (/^#[0-9a-fA-F]{6}$/.test(v)) return v.toUpperCase()
  const m3 = v.match(/^#([0-9a-fA-F])([0-9a-fA-F])([0-9a-fA-F])$/)
  if (m3) return ('#' + m3[1] + m3[1] + m3[2] + m3[2] + m3[3] + m3[3]).toUpperCase()
  const mr = v.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/)
  if (mr) {
    const h = (n: string) => Number(n).toString(16).padStart(2, '0')
    return ('#' + h(mr[1]) + h(mr[2]) + h(mr[3])).toUpperCase()
  }
  return colorRgb.value
}

const returnTo = computed(() => (route.query.return_to as string) || `/pool/${props.prefix}`)

onMounted(async () => {
  loading.value = true
  try {
    const r = await poolApi.edit(props.prefix, props.tagKey)
    info.value = r.info
    usedBy.value = r.used_by
    canonicalName.value = (r.info.canonical_name as string) || ''
    aliasesText.value = ((r.info.aliases as string[]) || []).join(', ')
    notes.value = (r.info.notes as string) || ''
    colorName.value = (r.info.color_name as string) || ''
    const rawRgb = (r.info.color_rgb as string) || ''
    // 后端无值 / 非 hex 都归为空字符串 → NColorPicker 进入"未设置"态.
    colorRgb.value = /^#[0-9a-fA-F]{6}$/.test(rawRgb) ? rawRgb : ''
  } finally {
    loading.value = false
  }
})

async function save() {
  const aliases = aliasesText.value.split(',').map((s) => s.trim()).filter(Boolean)
  const r = await poolApi.save(props.prefix, props.tagKey, {
    canonical_name: canonicalName.value,
    aliases,
    notes: notes.value,
    color_name: colorName.value.trim(),
    color_rgb: colorRgb.value,
    extra_json: JSON.stringify(extrasDict.value),
    return_to: returnTo.value,
  })
  if (r.ok) {
    message.success('已保存')
    // char 应援色变更后强制刷新缓存, 回到 BenchView 不会看到 stale 颜色
    if (props.prefix === 'char') {
      await store.refreshCharColorsForce()
    }
    router.push(returnTo.value)
  } else {
    message.error('保存失败')
  }
}

async function deleteMeta() {
  dialog.warning({
    title: '从池中删除元数据',
    content: `从池中删除 ${props.prefix}:${props.tagKey} 的元数据？此操作不会移除拍立得上的标签。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      await poolApi.delete(props.prefix, props.tagKey)
      // 同样刷新 char 颜色缓存 (万一删的是带颜色的 char)
      if (props.prefix === 'char') {
        await store.refreshCharColorsForce()
      }
      message.success('已删除')
      router.push(`/pool/${props.prefix}`)
    },
  })
}

const extrasDict = computed<Record<string, unknown>>({
  get: () => {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(info.value)) {
      if (!KNOWN_FIELDS.has(k)) out[k] = v
    }
    return out
  },
  set: (next) => {
    // 保留已知字段, 替换 extras — 防止 MetadataEditor 的 emit 覆盖硬编码字段
    const merged: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(info.value)) {
      if (KNOWN_FIELDS.has(k)) merged[k] = v
    }
    for (const [k, v] of Object.entries(next)) {
      merged[k] = v
    }
    info.value = merged
  },
})
</script>

<template>
  <div>
    <h2 style="margin-top: 0">
      编辑 <code>{{ prefix }}:{{ tagKey }}</code>
    </h2>

    <NSpin :show="loading">
      <div v-if="!loading">
        <p style="color: #666">
          被 {{ usedBy.length }} 张拍立得使用:
          <RouterLink v-for="p in usedBy.slice(0, 8)" :key="p.id" :to="`/bench/${encodeURIComponent(p.id)}`"
                      style="margin-right: 8px">
            <code>{{ p.id }}</code>
          </RouterLink>
          <span v-if="usedBy.length > 8">…</span>
        </p>

        <NForm label-placement="top" style="max-width: 720px">
          <NFormItem label="规范名称（canonical_name）">
            <NInput v-model:value="canonicalName" placeholder="供界面显示，可留空" />
          </NFormItem>

          <!-- 应援色 (硬编码字段, 文本 + RGB; 与 canonical_name 平级) -->
          <NCard title="应援色 (oshi color)" size="small" style="margin-bottom: 16px">
            <NSpace vertical>
              <NFormItem label="颜色文字（color_name）" :show-feedback="false" style="margin-bottom: 0">
                <NInput v-model:value="colorName" placeholder="例: 黄色 / 粉色" />
              </NFormItem>
              <NFormItem label="RGB (color_rgb)" :show-feedback="false" style="margin-bottom: 0">
                <!-- 裸 inline 排列: NColorPicker 在 NSpace 的 flex 容器里会被 min-width: 0 压扁,
                     三个元素不必用 NSpace 这种抽象, 直接 inline-block + margin 控间距最稳. -->
                <!-- modes=['hex'] 强制面板只显示 hex 输入; normalizeColorRgb 兜底把 rgb()/rgba()
                     函数式输出归一到 #RRGGBB (Naive UI 在 value=空 选色时可能退化为 rgb()). -->
                <NColorPicker
                  :value="colorRgb"
                  :show-alpha="false"
                  :modes="['hex']"
                  @update:value="(v: string) => colorRgb = normalizeColorRgb(v)"
                />
                <code style="margin-left: 8px; color: #666">{{ colorRgb || '(未设置)' }}</code>
                <NButton
                  size="small"
                  style="margin-left: 8px"
                  :disabled="!colorRgb"
                  @click="colorRgb = ''"
                >
                  清空
                </NButton>
              </NFormItem>
            </NSpace>
          </NCard>

          <NFormItem label="别名（aliases，逗号分隔）">
            <NInput v-model:value="aliasesText" placeholder="供搜索使用" />
          </NFormItem>
          <NFormItem label="备注（notes）">
            <NInput v-model:value="notes" type="textarea" :rows="4" />
          </NFormItem>
          <NFormItem label="附加字段 (任意 JSON 透传)">
            <MetadataEditor v-model="extrasDict" />
          </NFormItem>
          <NSpace>
            <NButton type="primary" @click="save">💾 保存</NButton>
            <NButton @click="router.push(returnTo)">取消</NButton>
            <NButton type="error" ghost @click="deleteMeta">从池删除元数据</NButton>
          </NSpace>
        </NForm>
      </div>
    </NSpin>
  </div>
</template>