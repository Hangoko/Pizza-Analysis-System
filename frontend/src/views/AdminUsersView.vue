<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiRequest } from '@/api/client'
import type { User, Role } from '@/types'
import { Users, UserPlus, X, Search } from 'lucide-vue-next'

const users = ref<User[]>([])
const isLoading = ref(false)
const searchQuery = ref('')
const selectedRole = ref<string>('')
const errorMessage = ref('')

// Form state for creating new user
const showCreateModal = ref(false)
const newUsername = ref('')
const newPassword = ref('')
const newFullName = ref('')
const newEmail = ref('')
const newRole = ref<Role>('driver')
const isCreating = ref(false)

async function loadUsers() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const params = new URLSearchParams()
    if (searchQuery.value) params.append('search', searchQuery.value)
    if (selectedRole.value) params.append('role', selectedRole.value)
    params.append('limit', '50')

    const data = await apiRequest<{ items: User[]; total: number }>(`/admin/users?${params.toString()}`)
    users.value = data.items || []
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка загрузки пользователей'
    // Fallback mockup
    users.value = [
      { id: 1, username: 'admin', email: 'admin@pizza.local', full_name: 'Главный Администратор', role: 'admin', is_active: true, driver_id: null, created_at: '2026-11-01', updated_at: '2026-11-01' },
      { id: 2, username: 'manager1', email: 'manager@pizza.local', full_name: 'Иван Менеджер', role: 'manager', is_active: true, driver_id: null, created_at: '2026-11-01', updated_at: '2026-11-01' },
      { id: 3, username: 'driver_ivan', email: null, full_name: 'Иванов Иван (Курьер)', role: 'driver', is_active: true, driver_id: 1, created_at: '2026-11-01', updated_at: '2026-11-01' },
    ]
  } finally {
    isLoading.value = false
  }
}

async function createUser() {
  if (!newUsername.value || !newPassword.value) return
  isCreating.value = true
  try {
    await apiRequest('/admin/users', {
      method: 'POST',
      body: JSON.stringify({
        username: newUsername.value,
        password: newPassword.value,
        full_name: newFullName.value || null,
        email: newEmail.value || null,
        role: newRole.value,
      }),
    })
    showCreateModal.value = false
    newUsername.value = ''
    newPassword.value = ''
    newFullName.value = ''
    newEmail.value = ''
    await loadUsers()
  } catch (err: any) {
    alert(err.message || 'Ошибка создания пользователя')
  } finally {
    isCreating.value = false
  }
}

async function toggleActive(u: User) {
  try {
    if (u.is_active) {
      await apiRequest(`/admin/users/${u.id}`, { method: 'DELETE' })
    } else {
      await apiRequest(`/admin/users/${u.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: true }),
      })
    }
    await loadUsers()
  } catch (err: any) {
    alert(err.message || 'Ошибка обновления статуса пользователя')
  }
}

onMounted(() => {
  loadUsers()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between border-b border-slate-200 pb-4">
      <div>
        <h2 class="text-lg font-bold text-slate-900 tracking-tight">Управление учетными записями и ролями (RBAC)</h2>
        <p class="text-xs text-slate-500">
          Администрирование пользователей системы, назначение ролей и привязка профилей водителей
        </p>
      </div>
      <button
        type="button"
        @click="showCreateModal = true"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold uppercase tracking-wider transition-colors"
      >
        <UserPlus class="w-3.5 h-3.5" />
        Создать пользователя
      </button>
    </div>

    <!-- Error Alert -->
    <div v-if="errorMessage" class="p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs">
      {{ errorMessage }}
    </div>

    <!-- Search & Filter Bar -->
    <div class="bg-white border border-slate-200 p-4 flex flex-col md:flex-row gap-3 items-center justify-between">
      <div class="flex items-center gap-2 w-full md:w-80">
        <div class="relative w-full">
          <input
            v-model="searchQuery"
            @keyup.enter="loadUsers"
            type="text"
            placeholder="Поиск по логину или ФИО..."
            class="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
          />
          <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
        </div>
        <button
          type="button"
          @click="loadUsers"
          class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-700 text-xs font-semibold uppercase tracking-wider"
        >
          Найти
        </button>
      </div>

      <div class="flex items-center gap-3 w-full md:w-auto">
        <label class="text-xs font-semibold uppercase tracking-wider text-slate-600">Роль:</label>
        <select
          v-model="selectedRole"
          @change="loadUsers"
          class="px-3 py-1.5 text-xs bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
        >
          <option value="">Все роли</option>
          <option value="admin">admin</option>
          <option value="manager">manager</option>
          <option value="executive">executive</option>
          <option value="driver">driver</option>
        </select>
      </div>
    </div>

    <!-- Users Table -->
    <div class="bg-white border border-slate-200">
      <div class="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
        <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
          <Users class="w-4 h-4 text-slate-400" />
          Реестр сотрудников
        </h3>
        <span class="text-[11px] font-mono text-slate-500">Записей: {{ users.length }}</span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse table-flat">
          <thead>
            <tr>
              <th class="w-16">ID</th>
              <th>Логин</th>
              <th>ФИО</th>
              <th>Email</th>
              <th class="w-28">Роль</th>
              <th class="w-28">Статус</th>
              <th class="w-28 text-right">Действие</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id" class="hover:bg-slate-50/70 transition-colors">
              <td class="font-mono text-xs text-slate-500">#{{ u.id }}</td>
              <td class="font-medium text-slate-900 font-mono text-xs">{{ u.username }}</td>
              <td class="text-xs text-slate-700">{{ u.full_name || '—' }}</td>
              <td class="text-xs text-slate-500 font-mono">{{ u.email || '—' }}</td>
              <td>
                <span class="font-mono text-[10px] uppercase px-1.5 py-0.5 border border-slate-300 bg-slate-100 text-slate-800">
                  {{ u.role }}
                </span>
              </td>
              <td>
                <span
                  class="inline-flex items-center gap-1.5 text-xs font-medium"
                  :class="u.is_active ? 'text-emerald-700' : 'text-slate-400'"
                >
                  <span class="w-1.5 h-1.5 rounded-full" :class="u.is_active ? 'bg-emerald-500' : 'bg-slate-300'"></span>
                  {{ u.is_active ? 'Активен' : 'Отключен' }}
                </span>
              </td>
              <td class="text-right">
                <button
                  type="button"
                  @click="toggleActive(u)"
                  class="text-[11px] font-mono uppercase px-2 py-0.5 border transition-colors"
                  :class="u.is_active ? 'border-rose-200 text-rose-700 hover:bg-rose-50' : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'"
                >
                  {{ u.is_active ? 'Блокировать' : 'Включить' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Create User Modal (Flat Corporate) -->
    <div
      v-if="showCreateModal"
      class="fixed inset-0 bg-slate-900/40 backdrop-blur-none flex items-center justify-center p-4 z-50"
    >
      <div class="bg-white border border-slate-400 w-full max-w-md p-6 space-y-4">
        <div class="flex items-center justify-between border-b border-slate-200 pb-3">
          <h3 class="text-sm font-bold uppercase tracking-wider text-slate-900">
            Создание учетной записи
          </h3>
          <button @click="showCreateModal = false" class="text-slate-400 hover:text-slate-700">
            <X class="w-4 h-4" />
          </button>
        </div>

        <form @submit.prevent="createUser" class="space-y-4">
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Логин (username) *
            </label>
            <input
              v-model="newUsername"
              type="text"
              required
              class="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
            />
          </div>

          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Пароль (min 8 симв.) *
            </label>
            <input
              v-model="newPassword"
              type="password"
              required
              minlength="8"
              class="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
            />
          </div>

          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              ФИО сотрудника
            </label>
            <input
              v-model="newFullName"
              type="text"
              class="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
            />
          </div>

          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Email
            </label>
            <input
              v-model="newEmail"
              type="email"
              class="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
            />
          </div>

          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Роль доступа *
            </label>
            <select
              v-model="newRole"
              class="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
            >
              <option value="driver">driver (Водитель-курьер)</option>
              <option value="manager">manager (Менеджер смены)</option>
              <option value="executive">executive (Руководство)</option>
              <option value="admin">admin (Администратор)</option>
            </select>
          </div>

          <div class="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
            <button
              type="button"
              @click="showCreateModal = false"
              class="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-600 hover:text-slate-900 border border-slate-200"
            >
              Отмена
            </button>
            <button
              type="submit"
              :disabled="isCreating"
              class="px-4 py-1.5 text-xs font-semibold uppercase tracking-wider bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50"
            >
              Сохранить
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
