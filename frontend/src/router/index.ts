import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'
import { usePolarscanStore } from '@/stores/polarscan'
import {
  canonicalizeBrowseQuery,
  isCanonicalBrowseQuery,
  validDimsFrom,
  type RawQuery,
} from '@/lib/browseQuery'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('@/views/HomeView.vue') },
    { path: '/list', component: () => import('@/views/ListView.vue') },
    { path: '/new', component: () => import('@/views/NewView.vue') },
    { path: '/bench/:pid', component: () => import('@/views/BenchView.vue'), props: true },
    { path: '/pool/:prefix', component: () => import('@/views/PoolIndexView.vue'), props: true },
    { path: '/pool/:prefix/:tagKey/edit', component: () => import('@/views/PoolEditView.vue'), props: true },
    // 兼容：所有 SPA 内的 hash-based / 旧 form action URL
    { path: '/:pathMatch(.*)*', redirect: '/list' },
  ],
})

/** 浏览页的 URL 规范化 —— 横切关注点, 不归视图管。
 *
 *  裸 /list、手改的非法值、历史链接、以及等价但不同写的 tag 形态（单字符串 vs
 *  单元素数组、顺序不同），全部在这里收敛成唯一一条规范 URL，再把地址栏重写成它。
 *  视图拿到的 route.query 已经是规范形态，可以直接渲染。
 *
 *  `beforeEach` 返回 location 会**替换**本次导航，所以不会在历史里留下
 *  「/list → /list?dim=char...」这一跳。
 *
 *  tag 池加载失败时退化成只做结构规范化 —— 数据不可用不该让页面打不开。 */
router.beforeEach(async (to: RouteLocationNormalized) => {
  if (to.path !== '/list') return true
  const query = to.query as RawQuery
  try {
    const store = usePolarscanStore()
    const validDims = validDimsFrom(await store.listAllTagGroups())
    const canonical = canonicalizeBrowseQuery(query, validDims)
    if (isCanonicalBrowseQuery(query, canonical)) return true
    return { path: to.path, query: canonical }
  } catch {
    const canonical = canonicalizeBrowseQuery(query, [])
    if (isCanonicalBrowseQuery(query, canonical)) return true
    return { path: to.path, query: canonical }
  }
})

export { router }