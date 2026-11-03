import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, AuthResponse, Role } from '@/types'
import { apiRequest } from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const savedUser = localStorage.getItem('user')
  const user = ref<User | null>(savedUser ? JSON.parse(savedUser) : null)
  const isLoading = ref(false)

  const isAuthenticated = computed(() => !!token.value || !!user.value)
  const role = computed<Role>(() => user.value?.role || 'driver')
  const isAdmin = computed(() => role.value === 'admin')
  const isManager = computed(() => role.value === 'manager')
  const isExecutive = computed(() => role.value === 'executive')
  const isDriver = computed(() => role.value === 'driver')

  async function login(username: string, password: string): Promise<void> {
    isLoading.value = true
    try {
      const body = new URLSearchParams()
      body.append('username', username)
      body.append('password', password)

      const data = await apiRequest<AuthResponse>('/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: body.toString(),
      })

      token.value = data.access_token
      localStorage.setItem('access_token', data.access_token)

      // Retrieve full user profile
      await fetchMe()
    } finally {
      isLoading.value = false
    }
  }

  async function register(payload: {
    username: string
    password: string
    email?: string | null
    full_name?: string | null
  }): Promise<User> {
    isLoading.value = true
    try {
      const newUser = await apiRequest<User>('/auth/register', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      return newUser
    } finally {
      isLoading.value = false
    }
  }

  async function fetchMe(): Promise<User | null> {
    if (!token.value) return null
    try {
      const profile = await apiRequest<User>('/auth/me')
      user.value = profile
      localStorage.setItem('user', JSON.stringify(profile))
      return profile
    } catch {
      // If token expired, clear session
      logout()
      return null
    }
  }

  // Helper for quick demo/testing in frontend
  function setDemoUser(demoRole: Role): void {
    const demoProfiles: Record<Role, User> = {
      admin: {
        id: 1,
        username: 'admin',
        email: 'admin@pizza.local',
        full_name: 'Климов М.Д. (Администратор)',
        role: 'admin',
        is_active: true,
        driver_id: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      manager: {
        id: 2,
        username: 'manager_zyuzin',
        email: 'manager@pizza.local',
        full_name: 'Зюзин Н.М. (Менеджер)',
        role: 'manager',
        is_active: true,
        driver_id: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      executive: {
        id: 3,
        username: 'exec_akhmetov',
        email: 'exec@pizza.local',
        full_name: 'Ахметов Д.Д. (Руководитель)',
        role: 'executive',
        is_active: true,
        driver_id: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      driver: {
        id: 4,
        username: 'driver_01',
        email: null,
        full_name: 'Водитель №1 (Курьер)',
        role: 'driver',
        is_active: true,
        driver_id: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    }

    const profile = demoProfiles[demoRole]
    user.value = profile
    token.value = `demo_token_${demoRole}`
    localStorage.setItem('access_token', token.value)
    localStorage.setItem('user', JSON.stringify(profile))
  }

  function logout(): void {
    token.value = null
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
  }

  return {
    token,
    user,
    isLoading,
    isAuthenticated,
    role,
    isAdmin,
    isManager,
    isExecutive,
    isDriver,
    login,
    register,
    fetchMe,
    setDemoUser,
    logout,
  }
})
