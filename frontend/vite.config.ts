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
    port: 5173,
    strictPort: true,
    proxy: {
      // 所有后端路径代理到 FastAPI:8765
      '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/bench': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/pool': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/list': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/new': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/thumb': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/img': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/reload': { target: 'http://127.0.0.1:8765', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})