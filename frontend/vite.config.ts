import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      // 只代理**真后端端点**。判定标准: apps/web/server.py 里有没有对应的
      // @app.get/post/put/delete 路由。
      //
      // ⚠ 不要把 SPA 路由 (/, /list, /bench/:pid, /new, /pool/*) 加进来。
      // Vite 的 proxy 中间件跑在 SPA fallback **之前**: 一旦命中, 请求就被转发
      // 到 8765, 拿到的是上一次 `pnpm build` 的旧 dist/index.html, 而它引用的
      // /assets/index-<hash>.js 在 dev 下不存在 —— 结果是浏览器拿 HTML 当 JS 执行,
      // 白屏。开发时这些路径必须由 Vite 自己返回 index.html (appType: 'spa')。

      // JSON API
      '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      // 拍立得读写: PUT /polaroid/{pid} (幂等保存) + DELETE /polaroid/{pid}。
      // 注意这两个是**非 /api 前缀**的裸端点, 漏掉它保存/删除在 dev 下到不了后端。
      '/polaroid': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      // 缩略图 / 原图
      '/thumb': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/img': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      // 重载索引: POST /reload
      '/reload': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      // 标签池表单: POST /pool/{prefix}/{key}/edit 与 /pool/{prefix}/{key}/delete。
      // 但 GET /pool/* 同时是 SPA 路由 (/pool/:prefix 与 /pool/:prefix/:tagKey/edit),
      // 两者路径形状完全一样, 只差 HTTP method —— 所以必须按 method 分流。
      '/pool': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
        bypass(req) {
          // GET/HEAD 是 SPA 导航: 改写成 /index.html 交回 Vite, 拿带 HMR client
          // 的 dev HTML。其余 method 是真表单端点, 继续代理。
          return req.method === 'GET' || req.method === 'HEAD' ? '/index.html' : undefined
        },
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})