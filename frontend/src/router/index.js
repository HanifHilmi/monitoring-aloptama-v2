import { createRouter, createWebHistory } from 'vue-router'

// Future systems (AWOS CAT. I, AWS Digitalisasi) are hidden from the nav
// by default but remain routable.
export const SHOW_FUTURE = import.meta.env.VITE_SHOW_FUTURE === 'true'

const routes = [
  // NEW summary-of-all dashboard
  { path: '/', name: 'home', component: () => import('@/views/HomeView.vue') },

  // AWOS CAT. III (old SLA/OLA dashboard — kept as-is)
  {
    path: '/cat3',
    name: 'cat3',
    component: () => import('@/views/DashboardView.vue'),
  },
  { path: '/cat3/system', name: 'cat3-system', component: () => import('@/views/SystemView.vue') },
  { path: '/cat3/runway/04', name: 'cat3-runway-04', component: () => import('@/views/RunwayView.vue'), props: { siteSlug: '04' } },
  { path: '/cat3/runway/middle', name: 'cat3-runway-middle', component: () => import('@/views/RunwayView.vue'), props: { siteSlug: 'middle' } },
  { path: '/cat3/runway/22', name: 'cat3-runway-22', component: () => import('@/views/RunwayView.vue'), props: { siteSlug: '22' } },
  { path: '/cat3/metar', name: 'cat3-metar', component: () => import('@/views/MetarView.vue') },

  // AWOS CAT. I (future — hidden unless SHOW_FUTURE)
  ...(SHOW_FUTURE
    ? [
        { path: '/cat1/system', name: 'cat1-system', component: () => import('@/views/SystemView.vue') },
        { path: '/cat1/runway/21', name: 'cat1-runway-21', component: () => import('@/views/RunwayView.vue'), props: { siteSlug: '21' } },
        { path: '/cat1/metar', name: 'cat1-metar', component: () => import('@/views/MetarView.vue') },
      ]
    : []),

  // AWS Digitalisasi (future — hidden unless SHOW_FUTURE)
  ...(SHOW_FUTURE
    ? [{ path: '/aws/garden', name: 'aws-garden', component: () => import('@/views/GardenView.vue') }]
    : []),

  // Backward-compat redirects
  { path: '/runway/:slug', redirect: (to) => `/cat3/runway/${to.params.slug}` },
  { path: '/dashboard', redirect: '/cat3' },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})