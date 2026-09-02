<!--
  CharTag: 角色专用 tag chip

  职责 (单一职责):
  - 接收完整 tag 字符串 (如 'char:小薰')
  - 用 useCharDisplay 反查该角色的元数据 (应援色 / canonical_name / aliases)
  - 显示逻辑封装在此 (key 去掉 'char:' 前缀 / 应援色 swatch / hovertip 文案)

  设计要点 (2026-08 应援色; 2026-09 元数据搬到 composable):
  - caller 只传 tag 字符串, 不需要知道 charMeta / store / 元数据加载.
  - 元数据反查通过 useCharDisplay, store 内部 dedup.
  - click 事件 emit 出去的是 key (已去掉前缀), 方便 caller 直接用:
      @click="goChar"        // 已保存的 char chip → 跳转到该角色编辑页
      @click="addFromPool"   // charPool 快捷按钮 → 加到 polaroid
  - 文本逻辑封装在此 (后续切 canonical_name 等只改本组件).
-->
<script setup lang="ts">
import { computed } from 'vue'
import { NTag, NTooltip } from 'naive-ui'
import { useCharDisplay } from '@/composables/useCharDisplay'

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

// 反查 + 懒加载都封装在 composable; CharTag 只用 display 渲染.
const display = useCharDisplay(() => props.tag)

// 视觉字段: 应援色由 color_rgb 字段定义; 空字符串/null → 不渲染 swatch, 不 fallback 到中性灰.
// 判定一律 "是否有定义应援色", 与 tag 类型 (char/非char) 解耦.
const swatch = computed(() => display.value.color_rgb || null)
// hovertip: 有 color_name 时附在 tag 后, 没有就只显示原 tag.
const hoverText = computed(() => display.value.color_name
  ? `${display.value.tag}  (${display.value.color_name})`
  : display.value.tag,
)

function onClick() {
  emit('click', display.value.key)
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
        <span v-if="swatch" class="char-tag-swatch" :style="{ background: swatch }" />
        <span class="char-tag-text">{{ display.key }}</span>
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