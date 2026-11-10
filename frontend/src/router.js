import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './store/auth'

const routes = [
  { path: '/login', component: () => import('./views/Login.vue') },
  {
    path: '/dashboard/:brand',
    component: () => import('./views/Dashboard.vue'),
    props: true,
    meta: { requiresAuth: true },
  },
  {
    path: '/dashboard/:brand/stores',
    component: () => import('./views/BrandStores.vue'),
    props: true,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/users',
    component: () => import('./views/AdminUsers.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/login-logs',
    component: () => import('./views/AdminLoginLogs.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  { path: '/home', component: () => import('./views/Home.vue'), meta: { requiresAuth: true } },
  { path: '/', redirect: '/home' },
  { path: '/:pathMatch(.*)*', redirect: '/home' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isLoggedIn) return '/login'
  if (to.meta.requiresAdmin && !auth.isAdmin) return '/home'
})

export default router
