<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  LayoutDashboard,
  Navigation,
  MapPin,
  FileSpreadsheet,
  Users,
  Network,
  LogOut,
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const navigationItems = [
  {
    name: 'Аналитика и KPI',
    path: '/dashboard',
    icon: LayoutDashboard,
    roles: ['admin', 'manager', 'executive'],
  },
  {
    name: 'Рекомендации курьеру',
    path: '/map/driver',
    icon: Navigation,
    roles: ['admin', 'manager', 'driver'],
  },
  {
    name: 'Зоны спроса (K-Means)',
    path: '/map/branches',
    icon: MapPin,
    roles: ['admin', 'manager', 'executive'],
  },
  {
    name: 'Отчеты и экспорт',
    path: '/reports',
    icon: FileSpreadsheet,
    roles: ['admin', 'manager', 'executive'],
  },
  {
    name: 'Управление доступом',
    path: '/admin/users',
    icon: Users,
    roles: ['admin'],
  },
  {
    name: 'Граф дорог и пробки',
    path: '/admin/graph',
    icon: Network,
    roles: ['admin'],
  },
]

const filteredNav = computed(() => {
  const currentRole = authStore.role || 'driver'
  return navigationItems.filter(item => item.roles.includes(currentRole))
})

const currentTitle = computed(() => {
  const current = navigationItems.find(i => i.path === route.path)
  return current ? current.name : 'Панель управления'
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <div class="flex h-screen bg-slate-50 antialiased font-sans overflow-hidden">
    <!-- Sidebar -->
    <aside class="w-64 bg-white border-r border-slate-200 flex flex-col justify-between shrink-0">
      <div>
        <!-- Logo / Brand Header -->
        <div class="h-16 px-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <div class="text-xs font-bold tracking-widest uppercase text-slate-400">СИСТЕМА АНАЛИЗА</div>
            <div class="text-base font-semibold tracking-tight text-slate-900">NewFastPizza</div>
          </div>
          <span class="text-[10px] font-mono uppercase bg-slate-100 text-slate-600 px-1.5 py-0.5 border border-slate-200">
            v0.1
          </span>
        </div>

        <!-- Navigation Links -->
        <nav class="py-4 px-2 space-y-1">
          <RouterLink
            v-for="item in filteredNav"
            :key="item.path"
            :to="item.path"
            class="flex items-center gap-3 px-3 py-2 text-xs font-medium transition-colors border-l-2"
            :class="[
              route.path === item.path
                ? 'border-slate-900 bg-slate-100 text-slate-900 font-semibold'
                : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50'
            ]"
          >
            <component :is="item.icon" class="w-4 h-4 text-slate-500 shrink-0" />
            <span>{{ item.name }}</span>
          </RouterLink>
        </nav>
      </div>

      <!-- Bottom User info in sidebar -->
      <div class="p-4 border-t border-slate-200 bg-slate-50/50">
        <div class="flex items-center justify-between">
          <div class="truncate mr-2">
            <div class="text-xs font-medium text-slate-800 truncate">
              {{ authStore.user?.full_name || authStore.user?.username || 'Оператор' }}
            </div>
            <div class="text-[10px] uppercase font-mono tracking-wider text-slate-500">
              {{ authStore.role || 'Пользователь' }}
            </div>
          </div>
          <button
            type="button"
            @click="handleLogout"
            title="Выйти из системы"
            class="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-white border border-transparent hover:border-slate-200 transition-colors"
          >
            <LogOut class="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>

    <!-- Main Workspace -->
    <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
      <!-- Topbar Header -->
      <header class="h-16 bg-white border-b border-slate-200 px-6 flex items-center justify-between shrink-0">
        <div class="flex items-center gap-3">
          <h1 class="text-sm font-semibold uppercase tracking-wider text-slate-800">
            {{ currentTitle }}
          </h1>
        </div>

        <div class="flex items-center gap-4 text-xs">
          <!-- Status pill -->
          <div class="flex items-center gap-2 px-2.5 py-1 bg-slate-100 border border-slate-200 text-slate-600">
            <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span class="font-mono text-[11px]">API: Online</span>
          </div>

          <!-- Role switcher selector -->
          <div class="flex items-center gap-1.5 border border-slate-300 bg-white px-2 py-0.5">
            <span class="text-[10px] uppercase font-mono text-slate-400">Роль:</span>
            <select
              :value="authStore.role"
              @change="(e) => authStore.setDemoUser((e.target as HTMLSelectElement).value as any)"
              class="font-mono text-[11px] uppercase tracking-wider text-slate-800 bg-transparent focus:outline-none cursor-pointer"
            >
              <option value="admin">admin</option>
              <option value="manager">manager</option>
              <option value="executive">executive</option>
              <option value="driver">driver</option>
            </select>
          </div>
        </div>
      </header>

      <!-- Page Content View -->
      <main class="flex-1 overflow-y-auto p-6 bg-slate-50">
        <div class="max-w-7xl mx-auto">
          <RouterView />
        </div>
      </main>
    </div>
  </div>
</template>
