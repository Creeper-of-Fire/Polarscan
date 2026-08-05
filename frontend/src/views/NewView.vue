<!--
  NewView: 新建拍立得

  数据流:
    usePolaroidEditor(null)  → 空 polaroid + create action
    useDropzone              → 拖入文件 → 自动填充 polaroid.assets
    PolaroidImagePreview     → 预览 (空 polaroid 显示 empty state)
-->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  NForm, NFormItem, NInput, NButton, NSpace, NAlert, NTag, useMessage,
} from 'naive-ui'
import { polaroidsApi } from '@/api'
import { usePolaroidEditor } from '@/composables/usePolaroidEditor'
import { useDropzone } from '@/composables/useDropzone'
import { parentDirName, parseFolderDateRange } from '@/composables/usePathParse'
import type { Asset, DroppedFile } from '@/types'
import PolaroidImagePreview from '@/components/PolaroidImagePreview.vue'

const router = useRouter()
const message = useMessage()

// 编辑 session (create mode;pid 始终为 null,由 create() 推到 /bench/{newPid})
const editor = usePolaroidEditor()
const polaroid = editor.polaroid
const submitting = ref(false)

// 派生字段 (不在 polaroid 上的本地 form state)
const primaryChar = ref('')

// ---------- dropzone ----------
const dz = useDropzone({
  withThumb: true,
  onReady: handleDropReady,
})
const { files, status, errorMsg, importable, handleDrop,
  removeFile, reset, fileStatusLabel, firstCandidatePath } = dz

// ---------- 自动填表单 ----------
function handleDropReady(_identifiedFiles: DroppedFile[]) {
  const paths = importable.value.map((i) => i.path)
  if (paths.length === 0) return

  // 追加到 polaroid.assets (尚未保存,所以还没 hash)
  const existing = new Set(polaroid.value.assets.map((a) => a.path))
  const newAssets: Asset[] = paths
    .filter((p) => !existing.has(p))
    .map((p, i) => ({
      role: defaultRoleFor(polaroid.value.assets.length + i),
      path: p,
    }))
  polaroid.value.assets = [...polaroid.value.assets, ...newAssets]

  // 从第一个新文件的路径推断 shot_date
  if (!polaroid.value.shot_date) {
    for (const p of paths) {
      const dn = parentDirName(p)
      if (!dn) continue
      const r = parseFolderDateRange(dn)
      if (r) {
        polaroid.value.shot_date = r.start
        break
      }
    }
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
      primaryChar.value.trim() || null,
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

function onTagsInput(v: string) {
  polaroid.value!.tags = v.split(',').map((s) => s.trim()).filter(Boolean)
}

function onNotesInput(v: string) {
  polaroid.value!.notes = v
}

// ---------- 提交 ----------
async function submit() {
  if (polaroid.value.assets.length === 0) {
    message.error('至少填一个资产路径')
    return
  }
  if (!polaroid.value.id) await suggestId()

  submitting.value = true
  try {
    const newPid = await editor.create({
      pid: polaroid.value.id,
      shot_date: polaroid.value.shot_date ?? undefined,
      primary_char: primaryChar.value.trim() || undefined,
      asset_paths: polaroid.value.assets.map((a) => a.path),
      tags: polaroid.value.tags,
      notes: polaroid.value.notes,
    })
    message.success(`已创建 ${newPid}`)
    router.push(`/bench/${encodeURIComponent(newPid)}`)
  } catch (e) {
    message.error(e instanceof Error ? e.message : String(e))
  } finally {
    submitting.value = false
  }
}

// ---------- 角色候选 (从已有 polaroids 拉) ----------
const charOptions = ref<string[]>([])
;(async () => {
  try {
    const list = await polaroidsApi.byTag('char')
    // 从 polaroid id 提取 char (id 形如 2026-XX-XX_charname_hash)
    const chars = new Set<string>()
    for (const p of list) {
      const m = p.id.match(/_([a-z0-9_\-]+)_[a-f0-9]{6}$/)
      if (m) chars.add(m[1])
    }
    charOptions.value = [...chars]
  } catch {
    charOptions.value = []
  }
})()
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
            <div style="font-size: 12px; color: 666">
              {{ fileStatusLabel(f) }}
            </div>
          </div>
          <NButton size="small" @click="removeFile(i)">×</NButton>
        </div>
        <div style="margin-top: 12px; color: #666; font-size: 12px">
          已自动填入下方表单（{{ importable.length }} 个）。
          <NButton size="small" @click="reset()">清空</NButton>
        </div>
      </div>
    </section>

    <!-- 预览 -->
    <div style="margin-bottom: 16px">
      <PolaroidImagePreview :polaroid="polaroid" :show-captions="true" />
    </div>

    <!-- 表单 -->
    <NForm label-placement="top" style="max-width: 720px">
      <NFormItem label="标识（id：shot_date + 首个 char + 6 位十六进制后缀）">
        <NInput :value="polaroid.id" placeholder="自动派生" readonly />
        <small style="color: #666">根据下面的拍摄日期与首个角色自动派生</small>
      </NFormItem>

      <NFormItem label="拍摄日期（shot_date）">
        <NInput :value="polaroid.shot_date || ''" placeholder="YYYY-MM-DD" @input="(v: string) => onShotDateInput(v)" />
      </NFormItem>

      <NFormItem label="首个角色（用于派生 id）">
        <NInput v-model:value="primaryChar" placeholder="strawberry / my_push / ..." @input="suggestId" />
        <div v-if="charOptions.length > 0" style="margin-top: 4px; display: flex; gap: 4px; flex-wrap: wrap">
          <NTag v-for="c in charOptions" :key="c" size="small" checkable
                :checked="primaryChar === c"
                @update:checked="(v: boolean) => v && (primaryChar = c)">
            {{ c }}
          </NTag>
        </div>
      </NFormItem>

      <NFormItem label="其他标签（tags，逗号分隔）">
        <NInput :value="polaroid.tags.join(', ')" placeholder="例: shot:pair, event:shenshan_3rd_om_cd"
                @input="(v: string) => onTagsInput(v)" />
      </NFormItem>

      <NFormItem label="备注（notes）">
        <NInput :value="polaroid.notes" type="textarea" :rows="4"
                @input="(v: string) => onNotesInput(v)" />
      </NFormItem>

      <NSpace>
        <NButton type="primary" :loading="submitting" @click="submit">创建</NButton>
        <NButton @click="router.push('/list')">取消</NButton>
      </NSpace>
    </NForm>
  </div>
</template>