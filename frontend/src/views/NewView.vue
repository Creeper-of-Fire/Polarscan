<!--
  NewView: 新建拍立得

  数据流:
    usePolaroidEditor()    → 极简空 polaroid (id='', assets=[]) + save action
    useDropzone            → 拖入文件 → handleDropReady 追加到 polaroid.assets
    AssetListEditor        → v-model 绑 polaroid.assets, 提供 role/captured_at/device 编辑
    PolaroidImagePreview   → 预览 (by-path, 不依赖 polaroid 是否索引)
    PolaroidTagsEditor     → 统一角色 + 其他标签 (与 BenchView 共享; 归并后 char 加得上去)
-->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  NCard, NForm, NFormItem, NInput, NButton, NSpace, useMessage,
} from 'naive-ui'
import { tagsApi } from '@/api'
import { usePolaroidEditor } from '@/composables/usePolaroidEditor'
import { useDropzone } from '@/composables/useDropzone'
import { assetsDateRange } from '@/composables/usePathParse'
import type { Asset, DroppedFile } from '@/types'
import AssetListEditor from '@/components/AssetListEditor.vue'
import PolaroidImagePreview from '@/components/PolaroidImagePreview.vue'
import PolaroidTagsEditor from '@/components/PolaroidTagsEditor.vue'

const router = useRouter()
const message = useMessage()

// 编辑 session (create 模式; pid 由 save() 推到 /bench/{newPid})
const editor = usePolaroidEditor()
const polaroid = editor.polaroid
const submitting = ref(false)

// ---------- 标签候选 (给 PolaroidTagsEditor) ----------
const allSuggestions = ref<string[]>([])
;(async () => {
  try {
    const grouped = await tagsApi.all()
    allSuggestions.value = ([] as string[]).concat(...Object.values(grouped))
  } catch {
    allSuggestions.value = []
  }
})()

// 派生 id 用: 取 polaroid.tags 里第一个 char tag 的 char 名
const primaryCharForId = computed<string | null>(() => {
  for (const t of polaroid.value.tags) {
    if (t.startsWith('char:')) return t.slice(5)
    if (!t.includes(':')) return t
  }
  return null
})

// 从已拖入资产路径推断的日期范围 (用于 shot_date 快捷按钮)
const assetDates = computed(() => assetsDateRange(polaroid.value.assets))

// ---------- dropzone ----------
const dz = useDropzone({
  withThumb: true,
  onReady: handleDropReady,
})
const { files, status, errorMsg, isDragging,
  importable, handleDrop,
  onDragEnter, onDragOver, onDragLeave,
  removeFile, reset, fileStatusLabel } = dz

// dropzone 完成: 把 importable 文件追加到 polaroid.assets
// 每个 asset 都带 hash (dropzone 在浏览器侧用 blake2b 算) — 这是 PUT 入库必需的 invariant,
// 同时也是后续 thumb URL cache-bust 的依据 (后端 /thumb?path=&hash=&v= 走 hash).
function handleDropReady(_identifiedFiles: DroppedFile[]) {
  const newOnes = importable.value
  if (newOnes.length === 0) return

  const existing = new Set(polaroid.value.assets.map((a) => a.path))
  // 用文件路径 → dropzone 文件对象 映射, 把 hash 注入到 asset
  const fileByPath = new Map<string, DroppedFile>()
  for (const f of files.value) {
    const c = (f.identify.candidates || [])[0]
    if (c?.path) fileByPath.set(c.path, f)
  }

  const newAssets: Asset[] = newOnes
    .filter((i) => !existing.has(i.path))
    .map((i, n) => {
      const f = fileByPath.get(i.path)
      return {
        role: defaultRoleFor(polaroid.value.assets.length + n),
        path: i.path,
        // hash 由 dropzone JS 算出; PUT 后端信任这个值 (见 server.py PUT /polaroid/{pid})
        hash: f?.hash || null,
      }
    })
  polaroid.value.assets = [...polaroid.value.assets, ...newAssets]

  // 从当前全部 assets 路径推断拍立得范围的"第一天"作为 shot_date hint (留空时不强行覆盖)
  if (!polaroid.value.shot_date) {
    const all = assetsDateRange(polaroid.value.assets)
    if (all.length > 0) polaroid.value.shot_date = all[0]
  }
  // 触发派生 id
  suggestId()
}

function defaultRoleFor(index: number): string {
  if (index === 0) return 'front'
  if (index === 1) return 'back'
  return 'additional'
}

async function suggestId() {
  try {
    const pid = await editor.suggestId(
      polaroid.value.shot_date ?? null,
      primaryCharForId.value,
    )
    polaroid.value.id = pid
  } catch {
    // 派生失败不影响主流程
  }
}

function onShotDateInput(v: string) {
  polaroid.value!.shot_date = v || null
  suggestId()
}

function applyDate(d: string) {
  polaroid.value.shot_date = d
  suggestId()
}

// PolaroidTagsEditor v-model 已写入 polaroid.tags; 这里只触发 id 派生
function onTagsChanged() {
  suggestId()
}

function onNotesInput(v: string) {
  polaroid.value!.notes = v
}

// 清空按钮: dropzone 状态 + 已填入 polaroid 全部字段一并清
function resetAll() {
  reset()                          // dropzone
  polaroid.value.assets = []        // editor 同步
  polaroid.value.id = ''
  polaroid.value.shot_date = null
  polaroid.value.tags = []
  polaroid.value.notes = ''
}

// ---------- 提交 ----------
async function submit() {
  if (polaroid.value.assets.length === 0) {
    message.error('至少填一个资产')
    return
  }
  if (!polaroid.value.id) await suggestId()

  submitting.value = true
  try {
    const r = await editor.save(polaroid.value)
    if (r.created) {
      message.success(`已创建 ${r.pid}`)
      router.push(`/bench/${encodeURIComponent(r.pid)}`)
    } else {
      // 已存在 (理论上 PID 不会撞, 但服务端校验说存在的话, 不跳转只提示)
      message.success(`已更新 ${r.pid}`)
    }
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div>
    <h2 style="margin-top: 0">新建拍立得</h2>

    <!-- 左右两列: 左 = dropzone + 资产 + 预览; 右 = 元数据表单 -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px">
      <!-- 左: 资产侧 -->
      <div>
        <!-- Dropzone (整个 section 是 drop target, 拖拽时整块变色) -->
        <section
          class="dropzone-section"
          :class="{ 'is-dragging': isDragging }"
          @dragenter="onDragEnter"
          @dragover="onDragOver"
          @dragleave="onDragLeave"
          @drop="handleDrop"
        >
          <p v-if="status === 'idle'">拖入文件到这里创建新拍立得</p>
          <p v-else-if="status === 'candidates-checking'">candidates 检查中…</p>
          <p v-else-if="status === 'hashing'">算 hash 中…</p>
          <p v-else-if="status === 'identifying'">identify 中…</p>
          <p v-else-if="status === 'submitting'">提交中…</p>
          <p v-else-if="status === 'error'" style="color: #c00">{{ errorMsg }}</p>

          <div v-if="status === 'ready' || status === 'error'" style="margin-top: 12px">
            <div v-for="(f, i) in files" :key="f.name + f.mtime"
                 style="display: flex; gap: 12px; align-items: center; padding: 8px; border-bottom: 1px solid #eee">
              <img v-if="f.thumb" :src="f.thumb" style="width: 48px; height: 48px; object-fit: cover; border-radius: 4px" />
              <div style="flex: 1; min-width: 0">
                <code style="font-size: 12px">{{ f.name }}</code>
                <div style="font-size: 12px; color: 666">
                  {{ fileStatusLabel(f) }}
                </div>
              </div>
              <NButton size="small" @click="removeFile(i)">×</NButton>
            </div>
            <div style="margin-top: 12px; color: #666; font-size: 12px">
              已添加 {{ importable.length }} 个文件到下方表单。
              <NButton size="small" @click="resetAll()">清空全部</NButton>
            </div>
          </div>
        </section>

        <!-- 预览 -->
        <NCard title="预览" style="margin-bottom: 16px">
          <PolaroidImagePreview :polaroid="polaroid" :show-captions="true" />
        </NCard>

        <!-- 资产编辑 -->
        <NCard title="资产 (assets)">
          <AssetListEditor v-model="polaroid.assets" />
        </NCard>
      </div>

      <!-- 右: 元数据 -->
      <NForm label-placement="top">
        <NFormItem label="标识（id）">
          <div style="display: flex; gap: 8px; align-items: center; width: 100%">
            <NInput
              v-model:value="polaroid.id"
              placeholder="留空点右侧“自动派生”或手动输入（允许中文）"
              style="flex: 1"
            />
            <NButton size="small" @click="suggestId">自动派生</NButton>
          </div>
          <small style="color: #666">
            默认根据拍摄日期与首个 char tag 自动派生，可手动覆盖；id 写入 YAML 后即冻结
          </small>
        </NFormItem>

        <NFormItem label="拍摄日期（shot_date）">
          <NInput :value="polaroid.shot_date || ''" placeholder="YYYY-MM-DD" @input="(v: string) => onShotDateInput(v)" />
          <div v-if="assetDates.length > 0" style="margin-top: 8px">
            <span style="color: #666; font-size: 12px">资产推断 → 点选填入：</span>
            <NButton v-for="d in assetDates" :key="d" size="small" type="primary" ghost @click="applyDate(d)">
              {{ d }}
            </NButton>
          </div>
        </NFormItem>

        <!-- 角色 + 其他标签 (统一组件, 与 BenchView 共享) -->
        <NFormItem label="标签 (tags)">
          <PolaroidTagsEditor
            v-model="polaroid.tags"
            :suggestions="allSuggestions"
            @update:model-value="onTagsChanged"
          />
          <small style="color: #666">
            改 char tag 也会重新派生 id；首个 char 作为派生用主角色
          </small>
        </NFormItem>

        <NFormItem label="备注（notes）">
          <NInput :value="polaroid.notes" type="textarea" :rows="4"
                  @input="(v: string) => onNotesInput(v)" />
        </NFormItem>

        <NSpace style="margin-top: 12px">
          <NButton type="primary" :loading="submitting" @click="submit">创建</NButton>
          <NButton @click="router.push('/list')">取消</NButton>
        </NSpace>
      </NForm>
    </div>
  </div>
</template>
