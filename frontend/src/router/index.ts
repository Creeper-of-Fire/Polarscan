import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('@/views/HomeView.vue') },
    { path: '/list', component: () => import('@/views/ListView.vue') },
    { path: '/new', component: () => import('@/views/NewView.vue') },
    { path: '/bench/:pid', component: () => import('@/views/BenchView.vue'), props: true },
    { path: '/pool/:prefix', component: () => import('@/views/PoolIndexView.vue'), props: true },
    { path: '/pool/:prefix/:key/edit', component: () => import('@/views/PoolEditView.vue'), props: true },
    // 兼容：所有 SPA 内的 hash-based / 旧 form action URL
    { path: '/:pathMatch(.*)*', redirect: '/list' },
  ],
})

export { router }