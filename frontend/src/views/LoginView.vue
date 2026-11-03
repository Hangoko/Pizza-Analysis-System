<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { Role } from '@/types'
import { ShieldCheck, ArrowRight, UserPlus, LogIn } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()

const mode = ref<'login' | 'register'>('login')

// Form inputs
const username = ref('')
const password = ref('')
const fullName = ref('')
const email = ref('')

const errorMessage = ref('')
const successMessage = ref('')
const isSubmitting = ref(false)

async function onSubmit() {
  if (!username.value || !password.value) {
    errorMessage.value = 'Заполните обязательные поля: логин и пароль'
    return
  }

  isSubmitting.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    if (mode.value === 'login') {
      await authStore.login(username.value, password.value)
      router.push('/dashboard')
    } else {
      await authStore.register({
        username: username.value,
        password: password.value,
        full_name: fullName.value || null,
        email: email.value || null,
      })
      successMessage.value = 'Регистрация успешна! Теперь вы можете войти в систему.'
      mode.value = 'login'
      password.value = ''
    }
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка запроса. Проверьте правильность введённых данных.'
  } finally {
    isSubmitting.value = false
  }
}

function handleDemoLogin(role: Role) {
  authStore.setDemoUser(role)
  if (role === 'driver') {
    router.push('/map/driver')
  } else {
    router.push('/dashboard')
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-100 p-4 antialiased">
    <div class="w-full max-w-md bg-white border border-slate-300 p-8">
      <!-- Brand & Security Header -->
      <div class="mb-6 border-b border-slate-200 pb-5">
        <div class="flex items-center justify-between mb-2">
          <span class="text-[11px] font-mono font-semibold uppercase tracking-widest text-slate-500">
            NEWFASTPIZZA LOGISTICS
          </span>
          <span class="text-[10px] font-mono px-1.5 py-0.5 border border-slate-200 bg-slate-50 text-slate-600">
            RBAC GATEWAY
          </span>
        </div>
        <h2 class="text-xl font-bold text-slate-900 tracking-tight">
          {{ mode === 'login' ? 'Авторизация в системе' : 'Регистрация учетной записи' }}
        </h2>
        <p class="text-xs text-slate-500 mt-1">
          {{ mode === 'login' ? 'Доступ к дашборду аналитики, маршрутам и управлению' : 'Саморегистрация профиля водителя (роль driver)' }}
        </p>
      </div>

      <!-- Mode Switcher Tabs -->
      <div class="grid grid-cols-2 gap-2 mb-6 border-b border-slate-200 pb-4">
        <button
          type="button"
          @click="mode = 'login'; errorMessage = ''; successMessage = ''"
          class="py-2 text-xs font-semibold uppercase tracking-wider border transition-colors flex items-center justify-center gap-1.5"
          :class="mode === 'login' ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100'"
        >
          <LogIn class="w-3.5 h-3.5" />
          <span>Вход</span>
        </button>

        <button
          type="button"
          @click="mode = 'register'; errorMessage = ''; successMessage = ''"
          class="py-2 text-xs font-semibold uppercase tracking-wider border transition-colors flex items-center justify-center gap-1.5"
          :class="mode === 'register' ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100'"
        >
          <UserPlus class="w-3.5 h-3.5" />
          <span>Регистрация</span>
        </button>
      </div>

      <!-- Alerts -->
      <div
        v-if="errorMessage"
        class="mb-5 p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2"
      >
        <span class="font-bold">Ошибка:</span> {{ errorMessage }}
      </div>

      <div
        v-if="successMessage"
        class="mb-5 p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2"
      >
        <span class="font-bold">Успешно:</span> {{ successMessage }}
      </div>

      <!-- Auth Form -->
      <form @submit.prevent="onSubmit" class="space-y-4">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
            Логин (username) *
          </label>
          <input
            v-model="username"
            type="text"
            required
            placeholder="admin / driver"
            class="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800 transition-colors"
          />
        </div>

        <div v-if="mode === 'register'">
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
            ФИО сотрудника
          </label>
          <input
            v-model="fullName"
            type="text"
            placeholder="Иванов Иван Иванович"
            class="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800 transition-colors"
          />
        </div>

        <div v-if="mode === 'register'">
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
            Электронная почта (Email)
          </label>
          <input
            v-model="email"
            type="email"
            placeholder="driver@example.com"
            class="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800 transition-colors"
          />
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
            Пароль (min 8 символов) *
          </label>
          <input
            v-model="password"
            type="password"
            required
            minlength="8"
            placeholder="••••••••"
            class="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800 transition-colors"
          />
        </div>

        <button
          type="submit"
          :disabled="isSubmitting"
          class="w-full mt-2 py-2.5 px-4 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold uppercase tracking-wider flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
        >
          <span>{{ isSubmitting ? 'Обработка...' : (mode === 'login' ? 'Войти в панель' : 'Зарегистрироваться') }}</span>
          <ArrowRight v-if="!isSubmitting" class="w-4 h-4" />
        </button>
      </form>

      <!-- Quick Role Fill / Demo Testing -->
      <div class="mt-8 pt-5 border-t border-slate-200">
        <div class="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2 flex items-center justify-between">
          <span>Тестовый вход по ролям:</span>
          <span>DEV MODE</span>
        </div>
        <div class="grid grid-cols-4 gap-1.5">
          <button
            type="button"
            @click="handleDemoLogin('admin')"
            class="py-1 text-[11px] font-mono border border-slate-200 bg-slate-50 hover:bg-slate-200 text-slate-800 uppercase transition-colors"
          >
            admin
          </button>
          <button
            type="button"
            @click="handleDemoLogin('manager')"
            class="py-1 text-[11px] font-mono border border-slate-200 bg-slate-50 hover:bg-slate-200 text-slate-800 uppercase transition-colors"
          >
            manager
          </button>
          <button
            type="button"
            @click="handleDemoLogin('executive')"
            class="py-1 text-[11px] font-mono border border-slate-200 bg-slate-50 hover:bg-slate-200 text-slate-800 uppercase transition-colors"
          >
            exec
          </button>
          <button
            type="button"
            @click="handleDemoLogin('driver')"
            class="py-1 text-[11px] font-mono border border-slate-200 bg-slate-50 hover:bg-slate-200 text-slate-800 uppercase transition-colors"
          >
            driver
          </button>
        </div>
      </div>

      <!-- Corporate Footer Note -->
      <div class="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
        <span class="flex items-center gap-1.5">
          <ShieldCheck class="w-3.5 h-3.5 text-slate-400" />
          OAuth2 JWT Bearer
        </span>
        <span class="font-mono">NNGU 2026</span>
      </div>
    </div>
  </div>
</template>
