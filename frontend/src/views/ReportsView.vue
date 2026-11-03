<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiRequest } from '@/api/client'
import type { ReportTemplate } from '@/types'
import { Download, FileText, Calendar } from 'lucide-vue-next'

const templates = ref<ReportTemplate[]>([])
const selectedTemplateId = ref<number | null>(null)
const dateFrom = ref('')
const dateTo = ref('')
const isLoading = ref(false)
const isExporting = ref(false)
const errorMessage = ref('')

async function loadTemplates() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const data = await apiRequest<ReportTemplate[]>('/reports/templates')
    templates.value = data
    if (data.length > 0) {
      selectedTemplateId.value = data[0].id
    }
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка загрузки шаблонов отчетов'
    // Fallback default templates
    templates.value = [
      { id: 1, name: 'Сводный отчет по доставкам', system_name: 'summary_deliveries', description: 'Полный реестр заказов со статусами, филиалами и водителями', is_system: true },
      { id: 2, name: 'Эффективность работы водителей', system_name: 'driver_performance', description: 'Количество доставок и среднее время на рейс по каждому водителю', is_system: true },
      { id: 3, name: 'Нагрузка и очереди филиалов', system_name: 'branch_load', description: 'Анализ задержек и очередей по точкам продаж', is_system: true },
    ]
    selectedTemplateId.value = 1
  } finally {
    isLoading.value = false
  }
}

async function exportCsv() {
  if (!selectedTemplateId.value) return
  isExporting.value = true
  errorMessage.value = ''
  try {
    const params = new URLSearchParams()
    params.append('template_id', String(selectedTemplateId.value))
    if (dateFrom.value) params.append('date_from', dateFrom.value)
    if (dateTo.value) params.append('date_to', dateTo.value)

    const token = localStorage.getItem('access_token')
    const response = await fetch(`/api/v1/reports/export?${params.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })

    if (!response.ok) {
      throw new Error('Ошибка выгрузки CSV файла')
    }

    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `report_${selectedTemplateId.value}_${Date.now()}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка скачивания отчета'
  } finally {
    isExporting.value = false
  }
}

onMounted(() => {
  loadTemplates()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="border-b border-slate-200 pb-4">
      <h2 class="text-lg font-bold text-slate-900 tracking-tight">Конструктор и экспорт аналитических отчетов</h2>
      <p class="text-xs text-slate-500">
        Формирование регламентированных и кастомных реестров с выгрузкой в формате CSV
      </p>
    </div>

    <!-- Error Alert -->
    <div v-if="errorMessage" class="p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs">
      {{ errorMessage }}
    </div>

    <!-- Export Controls Card -->
    <div class="bg-white border border-slate-200 p-5">
      <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800 mb-4 flex items-center gap-2">
        <Calendar class="w-4 h-4 text-slate-400" />
        Параметры выгрузки данных
      </h3>

      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
            Шаблон отчета
          </label>
          <select
            v-model="selectedTemplateId"
            class="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
          >
            <option v-for="t in templates" :key="t.id" :value="t.id">
              {{ t.name }}
            </option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
            Дата начала
          </label>
          <input
            v-model="dateFrom"
            type="date"
            class="w-full px-3 py-2 text-sm font-mono bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
          />
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
            Дата окончания
          </label>
          <input
            v-model="dateTo"
            type="date"
            class="w-full px-3 py-2 text-sm font-mono bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
          />
        </div>

        <button
          type="button"
          @click="exportCsv"
          :disabled="isExporting || !selectedTemplateId"
          class="w-full py-2.5 px-4 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold uppercase tracking-wider flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
        >
          <Download class="w-4 h-4" />
          <span>{{ isExporting ? 'Экспорт...' : 'Скачать CSV файл' }}</span>
        </button>
      </div>
    </div>

    <!-- Available Templates Table -->
    <div class="bg-white border border-slate-200">
      <div class="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
        <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
          <FileText class="w-4 h-4 text-slate-400" />
          Доступные шаблоны в системе
        </h3>
        <span class="text-[11px] font-mono text-slate-500">Всего: {{ templates.length }}</span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse table-flat">
          <thead>
            <tr>
              <th class="w-16">ID</th>
              <th>Название шаблона</th>
              <th>Системный код</th>
              <th>Описание содержания</th>
              <th class="w-28">Тип</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="t in templates"
              :key="t.id"
              class="cursor-pointer hover:bg-slate-50/70 transition-colors"
              :class="{ 'bg-slate-50 font-medium': selectedTemplateId === t.id }"
              @click="selectedTemplateId = t.id"
            >
              <td class="font-mono text-xs text-slate-500">#{{ t.id }}</td>
              <td class="text-slate-900">{{ t.name }}</td>
              <td class="font-mono text-xs text-slate-500">{{ t.system_name || 'custom' }}</td>
              <td class="text-xs text-slate-600">{{ t.description || '—' }}</td>
              <td>
                <span
                  class="font-mono text-[10px] uppercase px-1.5 py-0.5 border"
                  :class="t.is_system ? 'border-slate-300 bg-slate-100 text-slate-700' : 'border-blue-200 bg-blue-50 text-blue-700'"
                >
                  {{ t.is_system ? 'System' : 'Custom' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
