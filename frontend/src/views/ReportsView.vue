<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { apiRequest } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type {
  ReportTemplate,
  ReportMetric,
  ReportGroupBy,
  OrderStatusName,
  CsvDelimiter,
  ReportPreview,
} from '@/types'
import {
  Download,
  FileSpreadsheet,
  Calendar,
  Plus,
  Trash2,
  Table,
  Sliders,
  Check,
  AlertCircle,
  CheckCircle,
} from 'lucide-vue-next'

const authStore = useAuthStore()

// Tabs
const activeTab = ref<'templates' | 'builder'>('templates')

// Common filters
const dateFrom = ref('')
const dateTo = ref('')
const delimiter = ref<CsvDelimiter>(';')

// Templates state
const templates = ref<ReportTemplate[]>([])
const selectedTemplateId = ref<number | null>(null)
const isLoadingTemplates = ref(false)
const isExporting = ref(false)

// Builder state
const customReportName = ref('Новый кастомный отчет')
const customReportDesc = ref('')
const isPreviewing = ref(false)
const isSavingTemplate = ref(false)
const previewResult = ref<ReportPreview | null>(null)

// Config selections
const selectedMetrics = ref<ReportMetric[]>([
  'orders',
  'delivered',
  'canceled',
  'cancel_rate',
  'avg_delivery_minutes',
])

const selectedGroupBy = ref<ReportGroupBy | ''>('branch')
const selectedStatuses = ref<OrderStatusName[]>([])

const availableMetrics: { id: ReportMetric; label: string }[] = [
  { id: 'orders', label: 'Всего заказов' },
  { id: 'delivered', label: 'Доставлено' },
  { id: 'canceled', label: 'Отменено' },
  { id: 'cancel_rate', label: 'Коэффициент отмен' },
  { id: 'avg_delivery_minutes', label: 'Среднее время доставки (мин)' },
  { id: 'median_delivery_minutes', label: 'Медианное время (мин)' },
  { id: 'p90_delivery_minutes', label: '90-й перцентиль P90 (мин)' },
]

const availableGroupings: { id: ReportGroupBy | ''; label: string }[] = [
  { id: '', label: '— Без группировки (Итоговая строка) —' },
  { id: 'branch', label: 'По филиалам сети' },
  { id: 'driver', label: 'По водителям-курьерам' },
  { id: 'status', label: 'По статусу заказа' },
  { id: 'day', label: 'По дням (Календарный ряд)' },
  { id: 'hour', label: 'По часам' },
  { id: 'week', label: 'По неделям (с понедельника)' },
  { id: 'hour_of_day', label: 'По часу суток (0..23)' },
  { id: 'weekday', label: 'По дням недели (Пн..Вс)' },
]

const availableStatuses: OrderStatusName[] = ['Delivered', 'InDelivery', 'Pending', 'Canceled']

const errorMessage = ref('')
const successMessage = ref('')
const dateValidationError = ref('')

watch([dateFrom, dateTo], () => {
  if (dateFrom.value && dateTo.value && dateFrom.value > dateTo.value) {
    dateValidationError.value = 'Начало периода не может быть позже окончания'
  } else {
    dateValidationError.value = ''
  }
})

async function loadTemplates() {
  isLoadingTemplates.value = true
  errorMessage.value = ''
  try {
    const data = await apiRequest<ReportTemplate[]>('/reports/templates')
    templates.value = data
    if (data.length > 0 && !selectedTemplateId.value) {
      selectedTemplateId.value = data[0].id
    }
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка загрузки шаблонов'
    // Fallback default templates
    templates.value = [
      {
        id: 1,
        name: 'Сводка по сети',
        system_name: 'summary',
        description: 'Итоговые показатели заказов, отмен и времени доставки по всей сети',
        is_system: true,
        config: { metrics: ['orders', 'delivered', 'canceled', 'cancel_rate', 'avg_delivery_minutes', 'p90_delivery_minutes'], group_by: null, default_period_days: 30 },
      },
      {
        id: 2,
        name: 'Нагрузка филиалов',
        system_name: 'branch_load',
        description: 'Распределение заказов, доставок и среднего времени по каждому филиалу',
        is_system: true,
        config: { metrics: ['orders', 'delivered', 'canceled', 'avg_delivery_minutes'], group_by: 'branch', default_period_days: 30 },
      },
      {
        id: 3,
        name: 'Динамика заказов по дням',
        system_name: 'daily_trend',
        description: 'Календарный ряд заказов со средним временем доставки',
        is_system: true,
        config: { metrics: ['orders', 'delivered', 'avg_delivery_minutes'], group_by: 'day', default_period_days: 14 },
      },
      {
        id: 4,
        name: 'Эффективность водителей',
        system_name: 'driver_performance',
        description: 'Число доставок и среднее время на рейс по каждому курьеру',
        is_system: true,
        config: { metrics: ['orders', 'delivered', 'avg_delivery_minutes', 'median_delivery_minutes'], group_by: 'driver', default_period_days: 30 },
      },
    ]
    selectedTemplateId.value = 1
  } finally {
    isLoadingTemplates.value = false
  }
}

async function exportTemplateCsv() {
  if (!selectedTemplateId.value || dateValidationError.value) return
  isExporting.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    const params = new URLSearchParams()
    if (dateFrom.value) params.append('date_from', dateFrom.value)
    if (dateTo.value) params.append('date_to', dateTo.value)
    params.append('delimiter', delimiter.value)

    const token = localStorage.getItem('access_token')
    const response = await fetch(`/api/v1/reports/templates/${selectedTemplateId.value}/export.csv?${params.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || 'Не удалось сформировать CSV файл')
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
    successMessage.value = 'Отчёт успешно экспортирован в CSV'
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка выгрузки отчёта'
  } finally {
    isExporting.value = false
  }
}

function buildCurrentConfig() {
  return {
    metrics: selectedMetrics.value.length > 0 ? selectedMetrics.value : (['orders'] as ReportMetric[]),
    group_by: selectedGroupBy.value ? selectedGroupBy.value : null,
    filters: {
      statuses: selectedStatuses.value.length > 0 ? selectedStatuses.value : null,
    },
    default_period_days: 30,
  }
}

async function runPreview() {
  if (dateValidationError.value) return
  isPreviewing.value = true
  errorMessage.value = ''
  try {
    const payload = {
      name: customReportName.value,
      config: buildCurrentConfig(),
      date_from: dateFrom.value ? `${dateFrom.value}T00:00:00Z` : null,
      date_to: dateTo.value ? `${dateTo.value}T23:59:59Z` : null,
    }

    const data = await apiRequest<ReportPreview>('/reports/preview', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    previewResult.value = data
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка генерации предпросмотра'
    // Fallback preview for offline demonstration
    previewResult.value = {
      period: { date_from: dateFrom.value || '2026-10-01', date_to: dateTo.value || '2026-11-01' },
      columns: ['Группировка', 'Всего заказов', 'Доставлено', 'Отменено', 'Ср. время (мин)'],
      rows: [
        { 'Группировка': 'Филиал «Центр»', 'Всего заказов': 310, 'Доставлено': 295, 'Отменено': 15, 'Ср. время (мин)': 23.4 },
        { 'Группировка': 'Филиал «Автозавод»', 'Всего заказов': 280, 'Доставлено': 265, 'Отменено': 15, 'Ср. время (мин)': 26.1 },
        { 'Группировка': 'Филиал «Сормово»', 'Всего заказов': 240, 'Доставлено': 224, 'Отменено': 16, 'Ср. время (мин)': 29.8 },
      ],
    }
  } finally {
    isPreviewing.value = false
  }
}

async function exportAdhocCsv() {
  if (dateValidationError.value) return
  isExporting.value = true
  errorMessage.value = ''
  try {
    const payload = {
      name: customReportName.value,
      config: buildCurrentConfig(),
      date_from: dateFrom.value ? `${dateFrom.value}T00:00:00Z` : null,
      date_to: dateTo.value ? `${dateTo.value}T23:59:59Z` : null,
    }

    const token = localStorage.getItem('access_token')
    const response = await fetch(`/api/v1/reports/export.csv?delimiter=${delimiter.value}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    })

    if (!response.ok) {
      throw new Error('Ошибка экспорта ad-hoc CSV')
    }

    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `custom_report_${Date.now()}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
    successMessage.value = 'Пользовательский отчёт скачан'
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка экспорта CSV'
  } finally {
    isExporting.value = false
  }
}

async function saveAsTemplate() {
  if (!customReportName.value.trim()) {
    alert('Укажите название шаблона')
    return
  }

  isSavingTemplate.value = true
  errorMessage.value = ''
  try {
    await apiRequest('/reports/templates', {
      method: 'POST',
      body: JSON.stringify({
        name: customReportName.value.trim(),
        description: customReportDesc.value.trim() || null,
        config: buildCurrentConfig(),
        is_system: false,
      }),
    })
    successMessage.value = `Шаблон «${customReportName.value}» успешно сохранен`
    await loadTemplates()
    activeTab.value = 'templates'
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка сохранения шаблона'
  } finally {
    isSavingTemplate.value = false
  }
}

async function deleteTemplate(t: ReportTemplate) {
  if (t.is_system) {
    alert('Системные шаблоны нельзя удалять')
    return
  }
  if (!confirm(`Удалить шаблон «${t.name}»?`)) return

  try {
    await apiRequest(`/reports/templates/${t.id}`, { method: 'DELETE' })
    successMessage.value = `Шаблон «${t.name}» удален`
    await loadTemplates()
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка удаления шаблона'
  }
}

function toggleMetric(m: ReportMetric) {
  const idx = selectedMetrics.value.indexOf(m)
  if (idx > -1) {
    if (selectedMetrics.value.length > 1) {
      selectedMetrics.value.splice(idx, 1)
    }
  } else {
    selectedMetrics.value.push(m)
  }
}

function toggleStatus(s: OrderStatusName) {
  const idx = selectedStatuses.value.indexOf(s)
  if (idx > -1) {
    selectedStatuses.value.splice(idx, 1)
  } else {
    selectedStatuses.value.push(s)
  }
}

onMounted(() => {
  loadTemplates()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="border-b border-slate-200 pb-4 flex items-center justify-between">
      <div>
        <h2 class="text-lg font-bold text-slate-900 tracking-tight">Генератор и конструктор аналитических отчетов</h2>
        <p class="text-xs text-slate-500">
          Формирование отчетов по шаблонам сети, гибкий конструктор метрик и выгрузка в формате CSV (Excel RU / RFC 4180)
        </p>
      </div>

      <!-- Mode Selector Tabs -->
      <div class="flex items-center gap-1 border border-slate-300 bg-white p-1">
        <button
          type="button"
          @click="activeTab = 'templates'"
          class="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 transition-colors"
          :class="activeTab === 'templates' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'"
        >
          <FileSpreadsheet class="w-3.5 h-3.5" />
          <span>Шаблоны отчетов</span>
        </button>
        <button
          type="button"
          @click="activeTab = 'builder'"
          class="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 transition-colors"
          :class="activeTab === 'builder' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'"
        >
          <Sliders class="w-3.5 h-3.5" />
          <span>Конструктор (Ad-hoc)</span>
        </button>
      </div>
    </div>

    <!-- Alerts -->
    <div v-if="dateValidationError" class="p-3 bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-center gap-2">
      <AlertCircle class="w-4 h-4 text-amber-600 shrink-0" />
      <div>
        <span class="font-bold">Ошибка периода: </span>
        <span>{{ dateValidationError }}</span>
      </div>
    </div>

    <div v-if="errorMessage" class="p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
      <AlertCircle class="w-4 h-4 text-rose-600 shrink-0" />
      <span>{{ errorMessage }}</span>
    </div>

    <div v-if="successMessage" class="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
      <CheckCircle class="w-4 h-4 text-emerald-600 shrink-0" />
      <span>{{ successMessage }}</span>
    </div>

    <!-- Global Parameters Bar (Period & Delimiter) -->
    <div class="bg-white border border-slate-200 p-4 grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1 flex items-center gap-1.5">
          <Calendar class="w-3.5 h-3.5 text-slate-400" />
          Дата начала (UTC)
        </label>
        <input
          v-model="dateFrom"
          type="date"
          class="w-full px-3 py-1.5 text-xs font-mono bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
        />
      </div>

      <div>
        <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1 flex items-center gap-1.5">
          <Calendar class="w-3.5 h-3.5 text-slate-400" />
          Дата окончания (UTC)
        </label>
        <input
          v-model="dateTo"
          type="date"
          class="w-full px-3 py-1.5 text-xs font-mono bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
        />
      </div>

      <div>
        <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
          Разделитель CSV
        </label>
        <select
          v-model="delimiter"
          class="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
        >
          <option value=";">Точка с запятой «;» (Excel RU, UTF-8 с BOM)</option>
          <option value=",">Запятая «,» (Международный стандарт)</option>
        </select>
      </div>

      <div class="text-[11px] text-slate-500 font-mono">
        Период: <span class="font-bold text-slate-800">{{ dateFrom || 'начало' }}</span> &rarr; <span class="font-bold text-slate-800">{{ dateTo || 'конец' }}</span>
      </div>
    </div>

    <!-- TAB 1: PRE-CONFIGURED TEMPLATES VIEW -->
    <div v-if="activeTab === 'templates'" class="space-y-6">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <!-- Template Selection List (1 col) -->
        <div class="bg-white border border-slate-200 p-5 space-y-3">
          <div class="flex items-center justify-between border-b border-slate-200 pb-2 mb-2">
            <span class="text-xs font-bold uppercase tracking-wider text-slate-800">
              Шаблоны в системе
            </span>
            <span class="text-xs font-mono text-slate-400">Всего: {{ templates.length }}</span>
          </div>

          <div class="space-y-2">
            <div
              v-for="t in templates"
              :key="t.id"
              @click="selectedTemplateId = t.id"
              class="p-3 border cursor-pointer transition-colors"
              :class="selectedTemplateId === t.id
                ? 'border-slate-900 bg-slate-100'
                : 'border-slate-200 bg-slate-50 hover:bg-slate-100/70'"
            >
              <div class="flex items-center justify-between">
                <span class="text-xs font-semibold text-slate-900">{{ t.name }}</span>
                <span
                  class="text-[9px] font-mono uppercase px-1 py-0.5 border"
                  :class="t.is_system ? 'border-slate-300 bg-white text-slate-600' : 'border-blue-300 bg-blue-50 text-blue-700'"
                >
                  {{ t.is_system ? 'System' : 'Custom' }}
                </span>
              </div>
              <p class="text-[11px] text-slate-500 mt-1 line-clamp-2">
                {{ t.description || 'Без описания' }}
              </p>
            </div>
          </div>
        </div>

        <!-- Selected Template Inspector & Export Card (2 cols) -->
        <div class="md:col-span-2 bg-white border border-slate-200 p-6 flex flex-col justify-between">
          <div v-if="templates.find(t => t.id === selectedTemplateId)" class="space-y-4">
            <div class="border-b border-slate-200 pb-3 flex items-center justify-between">
              <div>
                <h3 class="text-base font-bold text-slate-900">
                  {{ templates.find(t => t.id === selectedTemplateId)?.name }}
                </h3>
                <p class="text-xs text-slate-500 mt-0.5">
                  {{ templates.find(t => t.id === selectedTemplateId)?.description }}
                </p>
              </div>

              <!-- Delete button if custom template and user is owner/admin -->
              <button
                v-if="!templates.find(t => t.id === selectedTemplateId)?.is_system"
                type="button"
                @click="deleteTemplate(templates.find(t => t.id === selectedTemplateId)!)"
                title="Удалить пользовательский шаблон"
                class="p-1.5 text-rose-500 hover:text-rose-700 border border-slate-200 hover:border-rose-300 transition-colors"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>

            <!-- Parameters Grid -->
            <div class="grid grid-cols-2 gap-4 text-xs">
              <div class="p-3 bg-slate-50 border border-slate-200">
                <span class="text-[10px] font-mono uppercase tracking-wider text-slate-400 block mb-1">
                  Группировка данных
                </span>
                <span class="font-bold text-slate-800">
                  {{ templates.find(t => t.id === selectedTemplateId)?.config.group_by || 'Общий итог (без группировки)' }}
                </span>
              </div>

              <div class="p-3 bg-slate-50 border border-slate-200">
                <span class="text-[10px] font-mono uppercase tracking-wider text-slate-400 block mb-1">
                  Период по умолчанию
                </span>
                <span class="font-bold text-slate-800 font-mono">
                  {{ templates.find(t => t.id === selectedTemplateId)?.config.default_period_days || 30 }} дней
                </span>
              </div>
            </div>

            <!-- Metrics list -->
            <div>
              <span class="text-xs font-semibold uppercase tracking-wider text-slate-700 block mb-2">
                Включенные метрики отчета:
              </span>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="m in templates.find(t => t.id === selectedTemplateId)?.config.metrics"
                  :key="m"
                  class="text-[11px] font-mono px-2 py-0.5 border border-slate-300 bg-slate-100 text-slate-800"
                >
                  {{ availableMetrics.find(item => item.id === m)?.label || m }}
                </span>
              </div>
            </div>
          </div>

          <!-- Export CSV Action Button -->
          <div class="pt-6 border-t border-slate-200 flex items-center justify-between">
            <span class="text-xs text-slate-500 font-mono">
              Формат: CSV ({{ delimiter === ';' ? 'точка с запятой' : 'запятая' }}), UTF-8 с BOM
            </span>

            <button
              type="button"
              @click="exportTemplateCsv"
              :disabled="isExporting || !selectedTemplateId"
              class="px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold uppercase tracking-wider flex items-center gap-2 transition-colors disabled:opacity-50"
            >
              <Download class="w-4 h-4" />
              <span>{{ isExporting ? 'Формирование CSV...' : 'Скачать сформированный CSV' }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 2: AD-HOC REPORT BUILDER VIEW -->
    <div v-else class="space-y-6">
      <div class="bg-white border border-slate-200 p-6 space-y-6">
        <!-- Template Meta Inputs -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 border-b border-slate-200 pb-5">
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Название отчета *
            </label>
            <input
              v-model="customReportName"
              type="text"
              class="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
            />
          </div>

          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
              Описание / комментарий
            </label>
            <input
              v-model="customReportDesc"
              type="text"
              placeholder="Для оперативного анализа эффективности филиалов"
              class="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
            />
          </div>
        </div>

        <!-- 1. Metrics Checkbox Grid -->
        <div>
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-800 mb-2">
            1. Выберите метрики для включения в отчёт (колонки)
          </label>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
            <button
              v-for="m in availableMetrics"
              :key="m.id"
              type="button"
              @click="toggleMetric(m.id)"
              class="p-2 text-left border text-xs flex items-center justify-between transition-colors"
              :class="selectedMetrics.includes(m.id)
                ? 'border-slate-900 bg-slate-100 text-slate-900 font-semibold'
                : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100/70'"
            >
              <span>{{ m.label }}</span>
              <Check v-if="selectedMetrics.includes(m.id)" class="w-3.5 h-3.5 text-slate-900 shrink-0" />
            </button>
          </div>
        </div>

        <!-- 2. Group By Selector -->
        <div>
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-800 mb-2">
            2. Уровень группировки строк
          </label>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
            <button
              v-for="g in availableGroupings"
              :key="g.id"
              type="button"
              @click="selectedGroupBy = g.id"
              class="p-2 text-left border text-xs transition-colors"
              :class="selectedGroupBy === g.id
                ? 'border-slate-900 bg-slate-100 text-slate-900 font-semibold'
                : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100/70'"
            >
              {{ g.label }}
            </button>
          </div>
        </div>

        <!-- 3. Status Filters -->
        <div>
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-800 mb-2">
            3. Фильтр по статусам заказов (опционально)
          </label>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="s in availableStatuses"
              :key="s"
              type="button"
              @click="toggleStatus(s)"
              class="px-2.5 py-1 text-xs border font-mono transition-colors"
              :class="selectedStatuses.includes(s)
                ? 'border-slate-900 bg-slate-900 text-white'
                : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'"
            >
              {{ s }}
            </button>
          </div>
        </div>

        <!-- Action Bar: Preview / Export / Save -->
        <div class="pt-4 border-t border-slate-200 flex flex-wrap items-center justify-between gap-3">
          <div class="flex items-center gap-2">
            <button
              type="button"
              @click="runPreview"
              :disabled="isPreviewing"
              class="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              <Table class="w-3.5 h-3.5" />
              <span>{{ isPreviewing ? 'Расчет...' : 'Предпросмотр данных' }}</span>
            </button>

            <button
              type="button"
              @click="exportAdhocCsv"
              :disabled="isExporting"
              class="px-4 py-2 bg-white border border-slate-300 hover:border-slate-800 text-slate-800 text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              <Download class="w-3.5 h-3.5" />
              <span>Скачать CSV</span>
            </button>
          </div>

          <button
            type="button"
            @click="saveAsTemplate"
            :disabled="isSavingTemplate || authStore.isDriver"
            class="px-4 py-2 bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-700 text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <Plus class="w-3.5 h-3.5" />
            <span>Сохранить в шаблоны</span>
          </button>
        </div>
      </div>

      <!-- Live Data Preview Table (if generated) -->
      <div v-if="previewResult" class="bg-white border border-slate-200">
        <div class="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
            <Table class="w-4 h-4 text-slate-400" />
            Предпросмотр структуры данных
          </h3>
          <span class="text-[11px] font-mono text-slate-500">
            Строк: {{ previewResult.rows.length }} | Колонок: {{ previewResult.columns.length }}
          </span>
        </div>

        <div class="overflow-x-auto max-h-96">
          <table class="w-full text-left border-collapse table-flat">
            <thead>
              <tr>
                <th v-for="col in previewResult.columns" :key="col" class="whitespace-nowrap">
                  {{ col }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, idx) in previewResult.rows" :key="idx" class="hover:bg-slate-50/70 transition-colors">
                <td v-for="col in previewResult.columns" :key="col" class="font-mono text-xs whitespace-nowrap">
                  {{ row[col] !== null && row[col] !== undefined ? row[col] : '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
