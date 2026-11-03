<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ShieldCheck, ArrowRight } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const errorMessage = ref('')
const isSubmitting = ref(false)

async function onSubmit() {
  if (!username.value || !password.value) {
    errorMessage.value = 'Введите логин и пароль'
    return
  }

  isSubmitting.value = true
  errorMessage.value = ''

  try {
    await authStore.login(username.value, password.value)
    router.push('/dashboard')
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка аутентификации. Проверьте данные.'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-100 p-4 antialiased">
    <div class="w-full max-w-md bg-white border border-slate-300 p-8">
      <!-- Header -->
      <div class="mb-8 border-b border-slate-200 pb-5">
        <div class="flex items-center justify-between mb-2">
          <span class="text-[11px] font-mono font-semibold uppercase tracking-widest text-slate-500">
            NEWFASTPIZZA LOGISTICS
          </span>
          <span class="text-[10px] font-mono px-1.5 py-0.5 border border-slate-200 bg-slate-50 text-slate-600">
            INTERNAL
          </span>
        </div>
        <h2 class="text-xl font-bold text-slate-900 tracking-tight">
          Авторизация в системе
        </h2>
        <p class="text-xs text-slate-500 mt-1">
          Введите учетные данные для доступа к аналитическому ядру
        </p>
      </div>

      <!-- Error Alert -->
      <div
        v-if="errorMessage"
        class="mb-6 p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2"
      >
        <span class="font-bold">Ошибка:</span> {{ errorMessage }}
      </div>

      <!-- Form -->
      <form @submit.prevent="onSubmit" class="space-y-5">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
            Имя пользователя / Логин
          </label>
          <input
            v-model="username"
            type="text"
            required
            placeholder="admin / driver"
            class="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800 transition-colors"
          />
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
            Пароль
          </label>
          <input
            v-model="password"
            type="password"
            required
            placeholder="••••••••"
            class="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800 transition-colors"
          />
        </div>

        <button
          type="submit"
          :disabled="isSubmitting"
          class="w-full py-2.5 px-4 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold uppercase tracking-wider flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
        >
          <span>{{ isSubmitting ? 'Вход в систему...' : 'Войти в панель' }}</span>
          <ArrowRight v-if="!isSubmitting" class="w-4 h-4" />
        </button>
      </form>

      <!-- Corporate Footer Note -->
      <div class="mt-8 pt-5 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
        <span class="flex items-center gap-1.5">
          <ShieldCheck class="w-3.5 h-3.5 text-slate-400" />
          Защищенный шлюз RBAC
        </span>
        <span class="font-mono">NNGU 2026</span>
      </div>
    </div>
  </div>
</template>
