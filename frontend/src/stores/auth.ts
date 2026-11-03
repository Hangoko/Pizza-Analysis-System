import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, AuthResponse } from '@/types'
import { apiRequest } from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const savedUser = localStorage.getItem('user')
  const user = ref<User | null>(savedUser ? JSON.parse(savedUser) : null)
  const isLoading = ref(false)

  const isAuthenticated = computed(() => !!token.value)
  const role = computed(() => user.value?.role || null)
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

      // Fetch user profile immediately
      await fetchMe()
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
      logout()
      return null
    }
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
    fetchMe,
    logout,
  }
})
