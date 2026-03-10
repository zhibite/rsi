import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  { path: '/',      component: () => import('../views/DashboardView.vue') },
  { path: '/scan',  component: () => import('../views/ScannerView.vue') },
  { path: '/trades',component: () => import('../views/TradesView.vue') },
  { path: '/stats', component: () => import('../views/StatsView.vue') },
  { path: '/settings', component: () => import('../views/SettingsView.vue') },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (!to.meta.public && !token) return '/login'
})

export default router
