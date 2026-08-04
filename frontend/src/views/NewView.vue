<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NForm, NFormItem, NInput, NButton, NSpace, NAlert, NTag, useMessage,
} from 'naive-ui'
import { newApi, polaroidsApi } from '@/api'
import { useDropzone } from '@/composables/useDropzone'
import { parentDirName, parseFolderDateRange } from '@/composables/usePathParse'

const router = useRouter()
const message = useMessage()

const shotDate = ref('')
const primaryChar = ref('')
const assetPathsText = ref('')
const tagsText = ref('')
const notes = ref('')
const pid = ref('')
const error = ref('')
const charOptions = ref<string[]>([])
const submitting = ref(false)

// 解构 dropzone 的 ref/computed 到顶层, 让 template 类型推断正确
const dz = useDropzone({ withThumb: true })
const files = dz.files
const status = dz.status
const errorMsg = dz.errorMsg
const importable = dz.importable
const hashHits = dz.hashHits
const handleDrop = dz.handleDrop
const removeFile = dz.removeFile
const reset = dz.reset
const fileStatus = dz.fileStatus
const fileStatusLabel = dz.fileStatusLabel
const firstCandidatePath = dz.firstCandidatePath

// 日期段建议（来自 dropzone 候选路径）
const dateSuggestion = computed(() => {
  const tryFromFiles = (candidates: Array<{ path: string }>) => {
    for (const cand of candidates) {
      const dn = parentDirName(cand.path)
      if (!dn) continue
      const r = parseFolderDateRange(dn)
      if (r) return r
    }
    return null
  }
  const importablePaths = importable.value.map((i) => ({ path: i.path }))
  return tryFromFiles(importablePaths) || tryFromFiles(files.value.flatMap((f) => (f.identify.candidates || []).slice(0, 1)))
})

function applyDate(d: string) {
  shotDate.value = d
  suggestId()
}

function randomHex6(): string {
  return Array.from({ length: 3 }, () => Math.floor(Math.random() * 256).toString(16).padStart(2, '0')).join('')
}

function suggestId() {
  const s = (shotDate.value.trim() || 'nostamp') + '_' + (primaryChar.value.trim() || 'nochar') + '_' + randomHex6()
  pid.value = s
}

// 自动填表单（dropzone 处理完调）
watch(status, (s) => {
  if (s !== 'ready') return
  const paths = importable.value.map((i) => i.path)
  if (paths.length === 0) return
  const existing = assetPathsText.value.split('\n').map((s) => s.trim()).filter(Boolean)
  const merged = [...new Set([...existing, ...paths])]
  assetPathsText.value = merged.join('\n')
  if (!shotDate.value.trim()) {
    for (const p of paths) {
      const dn = parentDirName(p)
      if (!dn) continue
      const r = parseFolderDateRange(dn)
      if (r) {
        shotDate.value = r.start
        suggestId()
        break
      }
    }
  } else {
    suggestId()
  }
})

onMounted(async () => {
  try {
    charOptions.value = (await polaroidsApi.byTag('char')).map((p) => p.id)
  } catch {
    charOptions.value = []
  }
})

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    const paths = assetPathsText.value.split('\n').map((s) => s.trim()).filter(Boolean)
    if (paths.length === 0) {
      error.value = '至少填一个资产路径'
      return
    }
    if (!pid.value) suggestId()
    const tags = tagsText.value.split(',').map((s) => s.trim()).filter(Boolean)
    const r = await newApi.create({
      pid: pid.value,
      shot_date: shotDate.value,
      primary_char: primaryChar.value,
      asset_paths: paths,
      tags,
      notes: notes.value,
    })
    if (r.ok && r.pid) {
      message.success(`已创建 ${r.pid}`)
      router.push(`/bench/${encodeURIComponent(r.pid)}`)
    } else {
      error.value = r.error || '创建失败'
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div>
    <h2 style="margin-top: 0">新建拍立得</h2>

    <!-- Dropzone -->
    <section style="border: 2px dashed #ccc; border-radius: 8px; padding: 16px; margin-bottom: 16px; background: #fafafa">
      <div @dragover.prevent @drop.prevent="handleDrop">
        <p v-if="status === 'idle'">拖入文件到这里创建新拍立得（也可使用下方手动表单）</p>
        <p v-else-if="status === 'hashing'">算 hash 中…</p>
        <p v-else-if="status === 'identifying'">identify 中…</p>
        <p v-else-if="status === 'submitting'">提交中…</p>
        <p v-else-if="status === 'error'" style="color: #c00">{{ errorMsg }}</p>
      </div>

      <div v-if="status === 'ready' || status === 'error'" style="margin-top: 12px">
        <div v-for="(f, i) in files" :key="f.name + f.mtime"
             style="display: flex; gap: 12px; align-items: center; padding: 8px; border-bottom: 1px solid #eee">
          <img v-if="f.thumb" :src="f.thumb" style="width: 48px; height: 48px; object-fit: cover; border-radius: 4px" />
          <div style="flex: 1; min-width: 0">
            <code style="font-size: 12px">{{ f.name }}</code>
            <div style="font-size: 12px; color: #666">
              {{ fileStatusLabel(f) }}
              <template v-if="fileStatus(f) === 'hash-hit'">
                · 已在 polaroid <code>{{ f.identify.by_hash[0].pid }}</code>
                第 {{ f.identify.by_hash[0].asset_idx + 1 }} 张
              </template>
              <template v-else-if="fileStatus(f) === 'candidate-in-yaml'">
                · F:盘路径 <code>{{ firstCandidatePath(f) }}</code>
                已导入到 <code>{{ f.identify.candidates[0]?.in_yaml_pid }}</code>
              </template>
              <template v-else-if="fileStatus(f) === 'new'">
                · 将新建，路径 <code>{{ firstCandidatePath(f) }}</code>
              </template>
            </div>
          </div>
          <NButton size="small" @click="removeFile(i)">×</NButton>
        </div>

        <div v-if="dateSuggestion" style="margin-top: 12px; padding: 8px; background: #fff8dc; border-radius: 4px">
          <span style="color: #666">从路径推断的日期：</span>
          <NButton size="small" type="primary" ghost @click="applyDate(dateSuggestion.start)">
            {{ dateSuggestion.start }}
          </NButton>
          <template v-if="dateSuggestion.start !== dateSuggestion.end">
            <span>~</span>
            <NButton size="small" type="primary" ghost @click="applyDate(dateSuggestion.end)">
              {{ dateSuggestion.end }}
            </NButton>
          </template>
        </div>

        <div style="margin-top: 12px; color: #666; font-size: 12px">
          已自动填入下方表单（{{ importable.length }} 个）。
          hash 命中 {{ hashHits.length }} 个已跳过。
          <NButton size="small" @click="reset()">清空</NButton>
        </div>
      </div>
    </section>

    <!-- 表单 -->
    <NForm label-placement="top" style="max-width: 720px">
      <NFormItem label="标识（id：shot_date + 首个 char + 6 位十六进制后缀）">
        <NInput v-model:value="pid" placeholder="自动派生" />
        <small style="color: #666">根据下面的拍摄日期与首个角色自动派生</small>
      </NFormItem>

      <NFormItem label="拍摄日期（shot_date）">
        <NInput v-model:value="shotDate" placeholder="YYYY-MM-DD" @change="suggestId" />
      </NFormItem>

      <NFormItem label="首个角色（用于派生 id）">
        <NInput v-model:value="primaryChar" placeholder="strawberry / my_push / ..." @input="suggestId" />
        <div style="margin-top: 4px; display: flex; gap: 4px; flex-wrap: wrap">
          <NTag v-for="c in charOptions" :key="c" size="small" checkable
                :checked="primaryChar === c"
                @update:checked="(v: boolean) => v && (primaryChar = c)">
            {{ c }}
          </NTag>
        </div>
      </NFormItem>

      <NFormItem label="资产路径（每行一个绝对路径）">
        <NInput v-model:value="assetPathsText" type="textarea" :rows="4"
                placeholder="例:&#10;F:\相册\...\img1.png&#10;F:\相册\...\img2.png" />
      </NFormItem>

      <NFormItem label="其他标签（tags，逗号分隔）">
        <NInput v-model:value="tagsText" placeholder="例: shot:pair, event:shenshan_3rd_om_cd" />
      </NFormItem>

      <NFormItem label="备注（notes）">
        <NInput v-model:value="notes" type="textarea" :rows="4" />
      </NFormItem>

      <NAlert v-if="error" type="error" style="margin-bottom: 12px">{{ error }}</NAlert>

      <NSpace>
        <NButton type="primary" :loading="submitting" @click="submit">创建</NButton>
        <NButton @click="router.push('/list')">取消</NButton>
      </NSpace>
    </NForm>
  </div>
</template>