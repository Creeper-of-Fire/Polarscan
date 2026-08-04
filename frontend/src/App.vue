<script setup lang="ts">
import { NConfigProvider, NMessageProvider, NDialogProvider, NNotificationProvider, NLoadingBarProvider, zhCN, darkTheme as _darkTheme, lightTheme } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'
import AppShell from '@/components/AppShell.vue'

// 学术报告/论文风格：light theme + 黑字
const theme = lightTheme
// 这里我们暂时不自定义主题颜色，靠 Naive UI 默认；后续按需调整
const themeOverrides: GlobalThemeOverrides = {}
void _darkTheme // 暂不引用 dark，保持 light
</script>

<template>
  <NConfigProvider :theme="theme" :theme-overrides="themeOverrides" :locale="zhCN">
    <NLoadingBarProvider>
      <NMessageProvider>
        <NNotificationProvider>
          <NDialogProvider>
            <AppShell>
              <RouterView />
            </AppShell>
          </NDialogProvider>
        </NNotificationProvider>
      </NMessageProvider>
    </NLoadingBarProvider>
  </NConfigProvider>
</template>

<style>
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #fafafa;
  color: #222;
}
* {
  box-sizing: border-box;
}
</style>