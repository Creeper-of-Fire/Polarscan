<!--
  NewView: 新建拍立得

  数据流:
    usePolaroidEditor()    → 极简空 polaroid (id='', assets=[]) + create action
    useDropzone            → 拖入文件 → handleDropReady 追加到 polaroid.assets
    AssetListEditor        → v-model 绑 polaroid.assets, 提供 role/captured_at/device 编辑
    PolaroidImagePreview   → 预览 (assets 空 → empty state; id 空但 assets 有 → "资产已填入, 点创建后预览")
-->
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NForm, NFormItem, NInput, NButton, NSpace, NTag, useMessage,
} from 'naive-ui'
import { polaroidsApi } from '@/api'
import { usePolaroidEditor } from '@/composables/usePolaroidEditor'
import { useDropzone } from '@/composables/useDropzone'
import { parentDirName, parseFolderDateRange } from '@/composables/usePathParse'
import type { Asset, DroppedFile } from '@/types'
import AssetListEditor from '@/components/AssetListEditor.vue'
import PolaroidImagePreview from '@/components/PolaroidImagePreview.vue'

const router = useRouter()
const message = useMessage()

// 编辑 session (create 模式; pid 由 create() 推到 /bench/{newPid})
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
  removeFile, reset, fileStatusLabel } = dz

// dropzone 完成: 把 importable 文件追加到 polaroid.assets
// 每个 asset 都带 hash (dropzone 在浏览器侧用 blake2b 算) — 这是 PUT 入库必需的 invariant.
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

  // 从第一个新文件的路径推断 shot_date
  if (!polaroid.value.shot_date) {
    for (const p of newOnes.map((i) => i.path)) {
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

// 清空按钮: dropzone 状态 + 已填入 polaroid.assets 一并清
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

// ---------- 角色候选 (从已有 polaroids 拉) ----------
const charOptions = ref<string[]>([])
;(async () => {
  try {
    const list = await polaroidsApi.byTag('char')
    // 从 polaroid id 提取 char (id 形如 2026-XX-XX_charname_hash; charname 现在允许中文等 Unicode)
    const chars = new Set<string>()
    for (const p of list) {
      // \w + u flag 匹配 Unicode word 字符；过滤占位符 nochar/nostamp
      const m = p.id.match(/_(\w+)_[a-f0-9]{6}$/u)
      if (m && m[1] !== 'nochar' && m[1] !== 'nostamp') chars.add(m[1])
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
        <p v-else-if="status === 'candidates-checking'">candidates 检查中…</p>
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
          已添加 {{ importable.length }} 个文件到下方表单。
          <NButton size="small" @click="resetAll()">清空全部</NButton>
        </div>
      </div>
    </section>

    <!-- 资产表单 (AssetListEditor) -->
    <NCard title="资产 (assets)" style="margin-bottom: 16px" content-style="padding: 16px">
      <AssetListEditor
        v-model="polaroid.assets"
        :polaroid-id="polaroid.id"
      />
    </NCard>

    <!-- 预览 -->
    <div style="margin-bottom: 16px">
      <PolaroidImagePreview :polaroid="polaroid" :show-captions="true" />
    </div>

    <!-- 元数据表单 -->
    <NForm label-placement="top" style="max-width: 720px">
      <NFormItem label="标识（id）">
        <div style="display: flex; gap: 8px; align-items: center; width: 100%">
          <NInput
            v-model:value="polaroid.id"
            placeholder="留空点右侧“自动派生”或手动输入（允许中文）"
            style="flex: 1"
          />
          <NButton size="small" @click="suggestId">自动派生</NButton>
        </div>
        <small style="color: #666">默认根据拍摄日期与首个角色自动派生，可手动覆盖；id 写入 YAML 后即冻结</small>
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