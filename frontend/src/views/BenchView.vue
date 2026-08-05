<!--
  BenchView: 单张拍立得编辑工作台

  数据流:
    usePolarscanStore (Pinia 全局) → summaries / 跳转 ID
    usePolaroidEditor (page-local composable) → polaroid + save actions
    useDropzone (page-local) → 追加文件 → editor.appendFiles
    PolaroidTagsEditor → 统一 char + other 标签编辑 (与 NewView 共享)
    PolaroidImagePreview → 纯展示
-->
<script setup lang="ts">
import { ref, computed, h, onMounted } from 'vue'
import { useRouter, onBeforeRouteUpdate } from 'vue-router'
import {
  NSpin, NTag, NInput, NButton, NSpace, NCard, useMessage, useDialog,
} from 'naive-ui'
import { usePolarscanStore } from '@/stores/polarscan'
import { polaroidsApi, tagsApi } from '@/api'
import { usePolaroidEditor } from '@/composables/usePolaroidEditor'
import { useDropzone } from '@/composables/useDropzone'
import { assetsDateRange } from '@/composables/usePathParse'
import PolaroidImagePreview from '@/components/PolaroidImagePreview.vue'
import AssetListEditor from '@/components/AssetListEditor.vue'
import PolaroidTagsEditor from '@/components/PolaroidTagsEditor.vue'
import type { DroppedFile } from '@/types'

const props = defineProps<{ pid: string }>()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const store = usePolarscanStore()

// ---------- 编辑 session (无 watcher;显式 setter + lifecycle) ----------
const editor = usePolaroidEditor()
const polaroid = editor.polaroid

// mount: 加载 summaries + polaroid,设置 currentId(prev/next 立刻可用)
onMounted(async () => {
  await Promise.all([
    store.ensureSummaries(),
    editor.load(props.pid),
  ])
  store.currentId = props.pid
  await loadSuggestions()
})

// 同组件路由切换(/bench/A → /bench/B):用 lifecycle hook 替代 watcher
onBeforeRouteUpdate(async (to) => {
  const newPid = to.params.pid as string
  store.currentId = newPid
  await editor.load(newPid)
  await loadSuggestions()
})

// ---------- 标签候选 ----------
const allSuggestions = ref<string[]>([])
async function loadSuggestions() {
  try {
    const grouped = await tagsApi.all()
    allSuggestions.value = ([] as string[]).concat(...Object.values(grouped))
  } catch {
    allSuggestions.value = []
  }
}

// ---------- dropzone (追加) ----------
const dz = useDropzone({ withThumb: false })
const { files: dzFiles, status: dzStatus, errorMsg: dzErrorMsg,
  isDragging: dzIsDragging,
  appendEligible: dzAppendEligible, hitFiles: dzHitFiles, noFPathFiles: dzNoFPathFiles,
  getHits: dzGetHits,
  handleDrop: dzHandleDrop,
  onDragEnter: dzOnDragEnter, onDragOver: dzOnDragOver, onDragLeave: dzOnDragLeave,
  removeFile: dzRemoveFile, reset: dzReset,
  fileStatusLabel: dzFileStatusLabel } = dz

// ---------- 顶部导航 ----------
const prevId = computed(() => store.prevId)
const nextId = computed(() => store.nextId)
const idx = computed(() => store.currentIdx)
const total = computed(() => store.summaries.length)

async function goto(direction: 'prev' | 'next' | 'untagged') {
  try {
    const r = await polaroidsApi.goto(props.pid, direction)
    if (r.target) router.push(`/bench/${encodeURIComponent(r.target)}`)
    else message.warning('已无更多可跳转项')
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e))
  }
}

// 日期段:从已绑资产路径推断,范围由父目录的日期范围语法决定 (支持跨月 2026.02.28-03.01).
const dateRange = computed(() => assetsDateRange(polaroid.value.assets))

// ---------- 编辑动作 (统一 debouncedSave) ----------
//
// 所有 form 修改 (tags / shot_date / notes / assets) 都走单一 PUT.
// 任意字段修改 → debouncedSave() → debounce 0.6s 后 send 一个完整的 polaroid.
// PUT 端点幂等, 重发同一份状态不会出错也不产生 side effect.

let saveTimer: ReturnType<typeof setTimeout> | null = null

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    void doSave()
  }, 600)
}

async function doSave() {
  try {
    await editor.save(polaroid.value)
  } catch (e) {
    message.error(`保存失败: ${e instanceof Error ? e.message : String(e)}`)
  }
}

function onTagsChanged() {
  // PolaroidTagsEditor v-model 已写入 polaroid.tags; 这里只触发 debounced save
  scheduleSave()
}

function onShotDateInput(v: string) {
  polaroid.value!.shot_date = v || null
  scheduleSave()
}

function onNotesInput(v: string) {
  polaroid.value!.notes = v
  scheduleSave()
}

function applyDate(d: string) {
  polaroid.value.shot_date = d
  scheduleSave()
}

// delete polaroid
async function deletePolaroid() {
  try {
    await polaroidsApi.delete(props.pid)
    message.success('已删除')
    router.push('/list')
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e))
  }
}
function confirmDelete() {
  dialog.warning({
    title: `删除 ${props.pid}?`,
    content: '此操作不可撤销。',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: deletePolaroid,
  })
}

// dropzone 追加 (这个跟 save 不同语义: 加新 path 到 server 端, server 算 hash)
async function doAppend(paths: string[]) {
  try {
    await editor.appendFiles(paths)
    message.success(`已追加 ${paths.length} 个文件`)
    dzReset()
  } catch (e) {
    dzErrorMsg.value = e instanceof Error ? e.message : String(e)
    dzStatus.value = 'error'
  }
}

function buildForceAddBody(currentPid: string, hits: DroppedFile[]) {
  // dialog content body: 列出 hash/路径命中位置, 同一张拍立得加 ⚠ 强警告
  return h('div', { style: 'max-width: 640px' }, [
    h('p', { style: 'margin: 0 0 8px 0' }, [
      `以下 `,
      h('strong', String(hits.length)),
      ` 个文件已在库中(命中 hash 或已在 yaml 的路径). 仍要追加到 `,
      h('strong', currentPid),
      ` 吗?`,
    ]),
    h('ul', {
      style: 'margin: 0; padding-left: 20px; max-height: 360px; overflow-y: auto',
    },
      hits.flatMap((f) => {
        const fileHits = dzGetHits(f)
        const samePid = fileHits.filter((x) => x.pid === currentPid)
        return [
          h('li', { style: 'margin-bottom: 10px; list-style: disc' }, [
            h('code', { style: 'font-size: 13px' }, f.name),
            h('span', { style: 'color: #999; font-size: 12px; margin-left: 8px' },
              f.hash ? `hash: ${f.hash.slice(0, 8)}…` : '(skip hash, path-hit only)'),
            h('ul', { style: 'margin-top: 4px; padding-left: 18px' },
              fileHits.map((hit) => {
                const isSame = hit.pid === currentPid
                return h('li', {
                  style: isSame
                    ? 'color: #c00; font-weight: 600; margin-bottom: 2px'
                    : 'color: #555; margin-bottom: 2px',
                }, [
                  `via ${hit.via}: `,
                  h('code', `${hit.pid} #${hit.asset_idx}`),
                  isSame ? ' ⚠ 同一张拍立得' : '',
                ])
              })
            ),
            samePid.length > 0
              ? h('div', {
                  style: 'margin-top: 4px; font-size: 12px; color: #c00',
                }, [
                  h('strong', '⚠ '),
                  `将向「${currentPid}」重复添加 `,
                  `${samePid.length} `,
                  `个 hash 相同的资产.`,
                ])
              : h('span'),
          ]),
        ]
      })
    ),
    h('p', { style: 'margin-top: 12px; color: #666; font-size: 12px' },
      `只有路径匹配的 F: 盘文件会被追加;无 F: 盘候选的文件已跳过。`),
  ])
}

async function confirmAppend() {
  const eligible = dzAppendEligible.value
  if (eligible.length === 0) {
    dzErrorMsg.value = '没有可追加的文件（缺少 F: 盘路径）'
    dzStatus.value = 'error'
    return
  }
  const paths = eligible.map((e) => e.path)
  const hits = dzHitFiles.value
  if (hits.length === 0) {
    await doAppend(paths)
    return
  }
  // 二次确认
  dialog.warning({
    title: '以下文件已在库中',
    content: () => buildForceAddBody(props.pid, hits),
    positiveText: '确认追加',
    negativeText: '取消',
    onPositiveClick: () => doAppend(paths),
  })
}

// ---------- 候选 + quick ----------
// (角色池 / shot 池 / sig 池 全部由 PolaroidTagsEditor 内部处理, 这里不再派生)

// 保存状态指示
const saveState = computed(() => {
  if (editor.isSaving.value) return 'saving'
  if (editor.error.value) return 'error'
  return 'idle'
})
const saveStateLabel = computed(() => {
  switch (saveState.value) {
    case 'idle': return '● 已保存'
    case 'saving': return '○ 保存中…'
    case 'error': return '⚠ 保存失败'
  }
})
const saveStateColor = computed(() => {
  switch (saveState.value) {
    case 'idle': return '#52c41a'
    case 'saving': return '#1890ff'
    case 'error': return '#f5222d'
  }
})
</script>

<template>
  <NSpin :show="editor.isLoading && !polaroid.id">
    <div v-if="polaroid.id">
      <!-- 顶部导航 -->
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px">
        <NButton :disabled="!prevId" @click="prevId && router.push(`/bench/${encodeURIComponent(prevId)}`)">‹ 上一张</NButton>
        <span style="color: #666"># {{ idx + 1 }} / {{ total }}</span>
        <NButton :disabled="!nextId" @click="nextId && router.push(`/bench/${encodeURIComponent(nextId)}`)">下一张 ›</NButton>
        <NButton @click="goto('untagged')">跳到下一张未打标</NButton>
        <span style="flex: 1" />
        <span :style="{ color: saveStateColor, fontWeight: 600 }">{{ saveStateLabel }}</span>
      </div>

      <!-- 日期段 -->
      <div v-if="dateRange.length > 0" style="margin-bottom: 12px">
        <span style="color: #666; margin-right: 8px">资产推断日期段：</span>
        <NButton v-for="d in dateRange" :key="d" size="small" type="primary" ghost @click="applyDate(d)">
          {{ d }}
        </NButton>
      </div>

      <!-- Dropzone（追加） -->
      <section
        class="dropzone-section"
        :class="{ 'is-dragging': dzIsDragging }"
        @dragenter="dzOnDragEnter"
        @dragover="dzOnDragOver"
        @dragleave="dzOnDragLeave"
        @drop="dzHandleDrop"
      >
        <p v-if="dzStatus === 'idle'">拖入文件追加到这张拍立得</p>
        <p v-else-if="dzStatus === 'candidates-checking'">candidates 检查中…</p>
        <p v-else-if="dzStatus === 'hashing'">算 hash 中…</p>
        <p v-else-if="dzStatus === 'identifying'">identify 中…</p>
        <p v-else-if="dzStatus === 'submitting'">提交中…</p>
        <p v-else-if="dzStatus === 'error'" style="color: #c00">{{ dzErrorMsg }}</p>

        <div v-if="dzStatus === 'ready' || dzStatus === 'error'" style="margin-top: 8px">
          <div v-for="(f, i) in dzFiles" :key="f.name + f.mtime"
               style="display: flex; gap: 8px; padding: 4px; border-bottom: 1px solid #eee; align-items: center">
            <code style="flex: 1; font-size: 12px">{{ f.name }}</code>
            <span :style="{
              fontSize: '12px',
              color: dzHitFiles.includes(f) ? '#fa8c16' : (dzNoFPathFiles.includes(f) ? '#bbb' : '#666'),
              fontWeight: dzHitFiles.includes(f) ? 600 : 400,
            }">{{ dzFileStatusLabel(f) }}</span>
            <NButton size="small" @click="dzRemoveFile(i)">×</NButton>
          </div>
          <NSpace style="margin-top: 8px" v-if="dzAppendEligible.length > 0">
            <NButton type="primary" @click="confirmAppend">
              确认追加 ({{ dzAppendEligible.length }})<span
                v-if="dzHitFiles.length > 0"
                style="margin-left: 4px; font-size: 12px; color: #fa8c16"
              >含 {{ dzHitFiles.length }} 个已存在</span>
            </NButton>
            <NButton @click="dzReset()">清空</NButton>
          </NSpace>
          <div v-if="dzNoFPathFiles.length > 0" style="margin-top: 8px; font-size: 12px; color: #999">
            {{ dzNoFPathFiles.length }} 个文件未在 F: 盘找到匹配,已跳过 (append 需要 F: 盘绝对路径)。
          </div>
        </div>
      </section>

      <!-- 主布局: 左侧 album preview + 资产编辑 + 右侧元数据 -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px">
        <!-- 左: 图片 album (PolaroidImagePreview) + 资产编辑 (AssetListEditor) -->
        <div>
          <NCard title="预览">
            <PolaroidImagePreview :polaroid="polaroid" :show-captions="true" />
          </NCard>

          <NCard title="资产 (assets)" style="margin-top: 12px">
            <AssetListEditor
              v-model="polaroid.assets"
              @update:model-value="scheduleSave"
            />
            <small style="display: block; margin-top: 8px; color: #999">
              改 role / captured_at / device / 删 asset 都会自动保存 (debounce 0.6s);
              加 path 用上方拖入区。
            </small>
          </NCard>
        </div>

        <!-- 右: 元数据 -->
        <div>
          <h2 style="margin-top: 0"><code>{{ polaroid.id }}</code></h2>
          <small style="color: #666">id 是稳定标识；修改 shot_date 或 char 不会改变它。</small>

          <!-- 角色 + 其他标签 (统一组件, 与 NewView 共享) -->
          <div style="margin-top: 16px">
            <PolaroidTagsEditor
              v-model="polaroid.tags"
              :suggestions="allSuggestions"
              @update:model-value="onTagsChanged"
            />
          </div>
          <div style="margin-top: 8px">
            <RouterLink :to="`/pool/char`">→ 查看角色池并编辑规范名称与别名</RouterLink>
          </div>

          <!-- 拍摄日期 -->
          <NCard title="拍摄日期（shot_date）" style="margin-top: 12px">
            <NInput :value="polaroid.shot_date || ''" placeholder="YYYY-MM-DD" @input="(v: string) => onShotDateInput(v)" />
            <div v-if="dateRange.length > 0" style="margin-top: 8px">
              <span style="color: #666; font-size: 12px">资产推断 → 点选填入：</span>
              <NButton v-for="d in dateRange" :key="d" size="small" type="primary" ghost @click="applyDate(d)">
                {{ d }}
              </NButton>
            </div>
            <small style="color: #666">自动保存：停止输入约 0.6 秒后写入</small>
          </NCard>

          <!-- 备注 -->
          <NCard title="备注（notes）" style="margin-top: 12px">
            <NInput :value="polaroid.notes" type="textarea" :rows="6" @input="(v: string) => onNotesInput(v)" />
          </NCard>

          <NSpace style="margin-top: 12px">
            <NButton type="error" ghost @click="confirmDelete">删除这张</NButton>
          </NSpace>
          <small style="display: block; margin-top: 8px; color: #999">
            编辑资产 metadata(role / captured_at / device)等功能将由通用表单编辑器承担(后续迭代)。
          </small>
        </div>
      </div>
    </div>
  </NSpin>
</template>