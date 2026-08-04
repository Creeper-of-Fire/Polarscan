<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NSpin, NTag, NInput, NButton, NSpace, NCard, NEmpty, useMessage, useDialog,
} from 'naive-ui'
import { usePolarscanStore } from '@/stores/polarscan'
import { polaroidsApi, tagsApi } from '@/api'
import { useAutosave } from '@/composables/useAutosave'
import { useDropzone } from '@/composables/useDropzone'
import { useChipStream } from '@/composables/useChipStream'
import { idDateRange } from '@/composables/usePathParse'
import AssetModal from '@/components/AssetModal.vue'

const props = defineProps<{ pid: string }>()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const store = usePolarscanStore()

const loading = ref(false)
const shotDateInput = ref('')
const notesInput = ref('')
const showAssetModal = ref(false)

// ---------- dropzone (追加) ----------
const dz = useDropzone({ withThumb: false })
const { files: dzFiles, status: dzStatus, errorMsg: dzErrorMsg, importable: dzImportable,
  handleDrop: dzHandleDrop, removeFile: dzRemoveFile, reset: dzReset,
  fileStatus: dzFileStatus, fileStatusLabel: dzFileStatusLabel } = dz

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

// ---------- char / other tag streams ----------
const charStream = useChipStream({
  autoPrefix: 'char',
  allowFreeform: false,
  suggestions: () => allSuggestions.value,
})
const otherStream = useChipStream({
  autoPrefix: '',
  allowFreeform: true,
  suggestions: () => allSuggestions.value,
})
const { modelValue: charTags, query: charQuery, showSuggest: charShow, suggestItems: charItems,
  addChip: charAdd, removeChip: charRemove, onInput: charOnInput, pickSuggest: charPick } = charStream
const { modelValue: otherTags, query: otherQuery, showSuggest: otherShow, suggestItems: otherItems,
  addChip: otherAdd, removeChip: otherRemove, onInput: otherOnInput, pickSuggest: otherPick } = otherStream

// ---------- 数据加载 ----------
onMounted(async () => {
  loading.value = true
  try {
    await store.ensureSummaries()
    await store.loadPolaroid(props.pid)
    syncFromStore()
    await loadSuggestions()
  } finally {
    loading.value = false
  }
})

watch(
  () => props.pid,
  async () => {
    loading.value = true
    try {
      await store.loadPolaroid(props.pid)
      syncFromStore()
    } finally {
      loading.value = false
    }
  },
)

function syncFromStore() {
  if (!store.current) return
  shotDateInput.value = store.current.shot_date || ''
  notesInput.value = store.current.notes || ''
}

// 把 store.current.tags 拆成 char 和 other
function splitTags() {
  if (!store.current) return
  const cs: string[] = []
  const os: string[] = []
  for (const t of store.current.tags) {
    if (t.startsWith('char:') || !t.includes(':')) cs.push(t)
    else os.push(t)
  }
  charStream.setTags(cs)
  otherStream.setTags(os)
}

watch(() => store.current?.id, splitTags, { immediate: true })

// ---------- 顶部导航 ----------
const prevId = computed(() => store.prevId)
const nextId = computed(() => store.nextId)
const nextUntaggedId = computed(() => store.nextUntaggedId)
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

// 日期段
const dateRange = computed(() => idDateRange(props.pid))

// ---------- Autosave ----------
const { state: saveState, flush, save } = useAutosave(
  async (payload: { tags?: string[]; shot_date?: string; notes?: string }) => {
    return polaroidsApi.autosave(props.pid, payload)
  },
  { debounceMs: 600 },
)

// tags 增减 → 立即保存
function onTagsChanged() {
  const all: string[] = [...charTags.value, ...otherTags.value]
  if (store.current) store.current.tags = all
  save({ tags: all })
}

// shot_date 防抖保存
let shotTimer: ReturnType<typeof setTimeout> | null = null
function onShotInput() {
  if (shotTimer) clearTimeout(shotTimer)
  shotTimer = setTimeout(() => {
    flush({ shot_date: shotDateInput.value })
    if (store.current) store.current.shot_date = shotDateInput.value || null
  }, 600)
}

// notes 防抖保存
let notesTimer: ReturnType<typeof setTimeout> | null = null
function onNotesInput() {
  if (notesTimer) clearTimeout(notesTimer)
  notesTimer = setTimeout(() => {
    flush({ notes: notesInput.value })
    if (store.current) store.current.notes = notesInput.value
  }, 600)
}

function applyDate(d: string) {
  shotDateInput.value = d
  onShotInput()
}

// 删除 polaroid
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

// ---------- dropzone 追加 ----------
async function confirmAppend() {
  const paths = dzImportable.value.map((i) => i.path)
  if (paths.length === 0) {
    dzErrorMsg.value = '没有可追加的文件'
    dzStatus.value = 'error'
    return
  }
  try {
    await polaroidsApi.appendFiles(props.pid, paths)
    message.success('已追加')
    await store.loadPolaroid(props.pid)
    dzReset()
  } catch (e) {
    dzErrorMsg.value = e instanceof Error ? e.message : String(e)
    dzStatus.value = 'error'
  }
}

async function onAssetsSaved() {
  await store.loadPolaroid(props.pid)
}

// ---------- 候选 + quick ----------
const charValues = computed(() =>
  allSuggestions.value.filter((s) => s.startsWith('char:')).map((s) => s.slice(5)),
)
const shotValues = computed(() =>
  allSuggestions.value.filter((s) => s.startsWith('shot:')).map((s) => s.slice(5)),
)
const sigValues = computed(() =>
  allSuggestions.value.filter((s) => s.startsWith('sig:')).map((s) => s.slice(4)),
)

const saveStateLabel = computed(() => {
  switch (saveState.value) {
    case 'idle': return '● 已保存'
    case 'saving': return '○ 保存中…'
    case 'dirty': return '● 待保存'
    case 'error': return '⚠ 保存失败'
  }
})
const saveStateColor = computed(() => {
  switch (saveState.value) {
    case 'idle': return '#52c41a'
    case 'saving': return '#1890ff'
    case 'dirty': return '#faad14'
    case 'error': return '#f5222d'
  }
})
</script>

<template>
  <NSpin :show="loading">
    <div v-if="store.current">
      <!-- 顶部导航 -->
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px">
        <NButton :disabled="!prevId" @click="prevId && router.push(`/bench/${encodeURIComponent(prevId)}`)">‹ 上一张</NButton>
        <span style="color: #666"># {{ idx + 1 }} / {{ total }}</span>
        <NButton :disabled="!nextId" @click="nextId && router.push(`/bench/${encodeURIComponent(nextId)}`)">下一张 ›</NButton>
        <NButton v-if="nextUntaggedId" @click="goto('untagged')">跳到下一张未打标</NButton>
        <span style="flex: 1" />
        <span :style="{ color: saveStateColor, fontWeight: 600 }">{{ saveStateLabel }}</span>
      </div>

      <!-- 日期段 -->
      <div v-if="dateRange.length > 0" style="margin-bottom: 12px">
        <span style="color: #666; margin-right: 8px">id 日期段：</span>
        <NButton v-for="d in dateRange" :key="d" size="small" type="primary" ghost @click="applyDate(d)">
          {{ d }}
        </NButton>
      </div>

      <!-- Dropzone（追加） -->
      <section style="border: 2px dashed #ccc; border-radius: 8px; padding: 12px; margin-bottom: 16px; background: #fafafa">
        <div @dragover.prevent @drop.prevent="dzHandleDrop">
          <p v-if="dzStatus === 'idle'">拖入文件追加到这张拍立得</p>
          <p v-else-if="dzStatus === 'hashing'">算 hash 中…</p>
          <p v-else-if="dzStatus === 'identifying'">identify 中…</p>
          <p v-else-if="dzStatus === 'submitting'">提交中…</p>
          <p v-else-if="dzStatus === 'error'" style="color: #c00">{{ dzErrorMsg }}</p>
        </div>

        <div v-if="dzStatus === 'ready' || dzStatus === 'error'" style="margin-top: 8px">
          <div v-for="(f, i) in dzFiles" :key="f.name + f.mtime"
               style="display: flex; gap: 8px; padding: 4px; border-bottom: 1px solid #eee; align-items: center">
            <code style="flex: 1; font-size: 12px">{{ f.name }}</code>
            <span style="font-size: 12px; color: #666">{{ dzFileStatusLabel(f) }}</span>
            <NButton size="small" @click="dzRemoveFile(i)">×</NButton>
          </div>
          <NSpace style="margin-top: 8px" v-if="dzImportable.length > 0">
            <NButton type="primary" @click="confirmAppend">确认追加</NButton>
            <NButton @click="dzReset()">清空</NButton>
          </NSpace>
        </div>
      </section>

      <!-- 主布局：左图 + 右元数据 -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px">
        <!-- 左：大图 + 资产列表 -->
        <div>
          <NCard title="预览">
            <template v-if="store.current.assets.length > 0">
              <img :src="`/thumb/${encodeURIComponent(props.pid)}`" :alt="props.pid"
                   style="max-width: 100%; display: block; margin: 0 auto" />
              <div style="margin-top: 8px; text-align: right">
                <a :href="`/img/${encodeURIComponent(props.pid)}`" target="_blank" rel="noopener">
                  查看原图 (F 盘) ↗
                </a>
              </div>
            </template>
            <NEmpty v-else description="无资产" />
          </NCard>

          <NCard :title="`资产 (${store.current.assets.length})`" style="margin-top: 12px">
            <div v-for="(a, i) in store.current.assets" :key="i"
                 style="padding: 6px 0; border-bottom: 1px solid #eee">
              <code style="font-size: 12px; color: #1890ff">{{ a.role }}</code>
              <code style="font-size: 11px; margin-left: 8px; word-break: break-all">{{ a.path }}</code>
              <div v-if="a.captured_at || a.device" style="font-size: 11px; color: #888; margin-top: 2px">
                {{ a.captured_at || '?' }} · {{ a.device || '?' }}
              </div>
            </div>
          </NCard>
        </div>

        <!-- 右：元数据 -->
        <div>
          <h2 style="margin-top: 0"><code>{{ props.pid }}</code></h2>
          <small style="color: #666">id 是稳定标识；修改 shot_date 或 char 不会改变它。</small>

          <!-- 角色面板 -->
          <NCard title="角色（char）" style="margin-top: 16px">
            <div>
              <NTag v-for="tag in charTags" :key="tag"
                    closable @close="charRemove(tag); onTagsChanged()"
                    style="margin: 2px">
                {{ tag }}
              </NTag>
            </div>
            <NSpace style="margin-top: 8px">
              <NInput :value="charQuery" placeholder="角色标识（例：my_push）"
                      @input="(v: string) => { charQuery = v; charOnInput() }"
                      @keyup.enter="charAdd(charQuery); onTagsChanged()" />
              <NButton @click="charAdd(charQuery); onTagsChanged()">+ 角色</NButton>
            </NSpace>
            <div v-if="charShow" style="margin-top: 4px; border: 1px solid #eee; padding: 4px; border-radius: 4px">
              <NButton v-for="s in charItems" :key="s" size="small" text
                       @click="charPick(s); onTagsChanged()">
                {{ s }}
              </NButton>
            </div>
            <div v-if="charValues.length > 0" style="margin-top: 8px">
              <span style="color: #666; font-size: 12px">角色池：</span>
              <NButton v-for="c in charValues.slice(0, 18)" :key="c" size="small" text
                       @click="charAdd(`char:${c}`); onTagsChanged()">
                + {{ c }}
              </NButton>
            </div>
            <div style="margin-top: 8px">
              <RouterLink :to="`/pool/char`">→ 查看角色池并编辑规范名称与别名</RouterLink>
            </div>
          </NCard>

          <!-- 其他标签面板 -->
          <NCard title="其他标签（tag）" style="margin-top: 12px">
            <div>
              <NTag v-for="tag in otherTags" :key="tag"
                    closable @close="otherRemove(tag); onTagsChanged()"
                    :type="tag.startsWith('shot:') ? 'success' : tag.startsWith('sig:') ? 'warning' : 'default'"
                    style="margin: 2px">
                {{ tag }}
              </NTag>
            </div>
            <NSpace style="margin-top: 8px">
              <NInput :value="otherQuery" placeholder="其他标签（例：event:shenshan_3rd_om_cd、shot:pair）"
                      @input="(v: string) => { otherQuery = v; otherOnInput() }"
                      @keyup.enter="otherAdd(otherQuery); onTagsChanged()" />
              <NButton @click="otherAdd(otherQuery); onTagsChanged()">+ 标签</NButton>
            </NSpace>
            <div v-if="otherShow" style="margin-top: 4px; border: 1px solid #eee; padding: 4px; border-radius: 4px">
              <NButton v-for="s in otherItems" :key="s" size="small" text
                       @click="otherPick(s); onTagsChanged()">
                {{ s }}
              </NButton>
            </div>
            <div v-if="shotValues.length > 0 || sigValues.length > 0" style="margin-top: 8px">
              <span v-if="shotValues.length > 0" style="color: #666; font-size: 12px">shot:</span>
              <NButton v-for="c in shotValues.slice(0, 5)" :key="c" size="small" text
                       @click="otherAdd(`shot:${c}`); onTagsChanged()">
                + {{ c }}
              </NButton>
              <span v-if="sigValues.length > 0" style="color: #666; font-size: 12px; margin-left: 8px">sig:</span>
              <NButton v-for="c in sigValues.slice(0, 5)" :key="c" size="small" text
                       @click="otherAdd(`sig:${c}`); onTagsChanged()">
                + {{ c }}
              </NButton>
            </div>
          </NCard>

          <!-- 拍摄日期 -->
          <NCard title="拍摄日期（shot_date）" style="margin-top: 12px">
            <NInput v-model:value="shotDateInput" placeholder="YYYY-MM-DD" @input="onShotInput" />
            <div v-if="dateRange.length > 0" style="margin-top: 8px">
              <span style="color: #666; font-size: 12px">id 日期范围 → 点选填入：</span>
              <NButton v-for="d in dateRange" :key="d" size="small" type="primary" ghost @click="applyDate(d)">
                {{ d }}
              </NButton>
            </div>
            <small style="color: #666">自动保存：停止输入约 0.6 秒后写入</small>
          </NCard>

          <!-- 备注 -->
          <NCard title="备注（notes）" style="margin-top: 12px">
            <NInput v-model:value="notesInput" type="textarea" :rows="6" @input="onNotesInput" />
          </NCard>

          <NSpace style="margin-top: 12px">
            <NButton @click="showAssetModal = true">编辑资产</NButton>
            <NButton type="error" ghost @click="confirmDelete">删除这张</NButton>
          </NSpace>
        </div>
      </div>

      <AssetModal :show="showAssetModal" :pid="props.pid" :initial="store.current.assets"
                  @update:show="(v) => (showAssetModal = v)" @saved="onAssetsSaved" />
    </div>
    <NEmpty v-else description="加载中…" />
  </NSpin>
</template>