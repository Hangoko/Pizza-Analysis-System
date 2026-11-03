import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

import AppLayout from '@/layouts/AppLayout.vue'
import LoginView from '@/views/LoginView.vue'
import DashboardView from '@/views/DashboardView.vue'
import DriverMapView from '@/views/DriverMapView.vue'
import BranchesMapView from '@/views/BranchesMapView.vue'
import ReportsView from '@/views/ReportsView.vue'
import AdminUsersView from '@/views/AdminUsersView.vue'
import AdminGraphView from '@/views/AdminGraphView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { requiresGuest: true },
    },
    {
      path: '/',
      component: AppLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          redirect: () => {
            const authStore = useAuthStore()
            return authStore.role === 'driver' ? '/map/driver' : '/dashboard'
          },
        },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: DashboardView,
          meta: { roles: ['admin', 'manager', 'executive'] },
        },
        {
          path: 'map/driver',
          name: 'driver-map',
          component: DriverMapView,
          meta: { roles: ['admin', 'manager', 'driver'] },
        },
        {
          path: 'map/branches',
          name: 'branches-map',
          component: BranchesMapView,
          meta: { roles: ['admin', 'manager', 'executive'] },
        },
        {
          path: 'reports',
          name: 'reports',
          component: ReportsView,
          meta: { roles: ['admin', 'manager', 'executive'] },
        },
        {
          path: 'admin/users',
          name: 'admin-users',
          component: AdminUsersView,
          meta: { roles: ['admin'] },
        },
        {
          path: 'admin/graph',
          name: 'admin-graph',
          component: AdminGraphView,
          meta: { roles: ['admin'] },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/dashboard',
    },
  ],
})

router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()

  // For development demo purposes: if no token in localStorage, we allow guest preview or redirect to login
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({ name: 'login' })
    return
  }

  if (to.meta.requiresGuest && authStore.isAuthenticated) {
    next({ name: 'dashboard' })
    return
  }

  // Check roles if required
  if (to.meta.roles && Array.isArray(to.meta.roles)) {
    const userRole = authStore.role
    if (userRole && !to.meta.roles.includes(userRole)) {
      next(userRole === 'driver' ? '/map/driver' : '/dashboard')
      return
    }
  }

  next()
})

export default router
