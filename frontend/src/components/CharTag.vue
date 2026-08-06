<!--
  CharTag: 角色专用 tag chip

  职责 (单一职责):
  - 接收完整 tag 字符串 (如 'char:hime')
  - 自己从 store 拿该角色的元数据 (应援色 / 未来 canonical_name 等)
  - 显示逻辑封装在此 (key 去掉 'char:' 前缀 / 应援色 swatch / hovertip 文案)

  设计要点 (2026-08 应援色):
  - caller 只传 tag 字符串, 不需要知道 charColors / store / 元数据加载.
  - store 的 charColors 由 CharTag 在 onMounted 懒加载触发 (store 内部 dedup).
  - click 事件 emit 出去的是 key (已去掉前缀), 方便 caller 直接用:
      @click="goChar"        // 已保存的 char chip → 跳转到该角色编辑页
      @click="addFromPool"   // charPool 快捷按钮 → 加到 polaroid
  - 文本逻辑封装在此 (后续切 canonical_name 等只改本组件).
-->
<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { NTag, NTooltip } from 'naive-ui'
import { usePolarscanStore } from '@/stores/polarscan'

const props = withDefaults(
  defineProps<{
    tag: string
    closable?: boolean
    interactive?: boolean
  }>(),
  { closable: false, interactive: false },
)

const emit = defineEmits<{
  close: []
  click: [key: string]
}>()

const store = usePolarscanStore()

// 触发 store 懒加载 (首次 CharTag 渲染时拉, 后续由 store 内部 dedup).
onMounted(() => {
  void store.loadCharColors()
})

// 角色 key: 去掉 'char:' 前缀. 文本逻辑封装在此.
const key = computed(() => props.tag.replace(/^char:/, ''))

// 应援色: 自己从 store 拿. 字段读取约定见 types.ts:charOshiColorFromMeta.
const color = computed(() => store.charColors[key.value])

const swatch = computed(() => color.value?.rgb || '#d9d9d9')
const hoverText = computed(() => color.value?.name
  ? `${props.tag}  (${color.value.name})`
  : props.tag,
)

function onClick() {
  emit('click', key.value)
}
</script>

<template>
  <NTooltip :delay="300">
    <template #trigger>
      <NTag
        :closable="closable"
        :class="{ 'char-tag-clickable': interactive }"
        @click="onClick"
        @close="emit('close')"
      >
        <span class="char-tag-swatch" :style="{ background: swatch }" />
        <span class="char-tag-text">{{ key }}</span>
      </NTag>
    </template>
    {{ hoverText }}
  </NTooltip>
</template>

<style scoped>
.char-tag-swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-right: 4px;
  border-radius: 2px;
  border: 1px solid rgba(0, 0, 0, 0.15);
  vertical-align: -2px;
}
.char-tag-text {
  font-weight: 500;
}
.char-tag-clickable {
  cursor: pointer;
}
.char-tag-clickable:hover :deep(.ntag__content) {
  filter: brightness(0.97);
}
</style>