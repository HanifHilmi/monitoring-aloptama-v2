import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
  { path: '/runway/04', name: 'runway-04', component: () => import('@/views/RunwayView.vue'), props: { siteSlug: '04' } },
  { path: '/runway/22', name: 'runway-22', component: () => import('@/views/RunwayView.vue'), props: { siteSlug: '22' } },
  { path: '/runway/middle', name: 'runway-middle', component: () => import('@/views/RunwayView.vue'), props: { siteSlug: 'middle' } },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})