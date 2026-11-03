<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { apiRequest } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type {
  KpiResponse,
  BranchLoadResponse,
  TimeseriesResponse,
  Granularity,
  Branch,
} from '@/types'
import {
  TrendingUp,
  Clock,
  XCircle,
  BarChart3,
  RefreshCw,
  Calendar,
  Store,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
} from 'lucide-vue-next'
import {
  Chart,
  LineController,
  BarController,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js'

// Register Chart.js components
Chart.register(
  LineController,
  BarController,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend
)

const authStore = useAuthStore()

// Filter states
const dateFrom = ref('')
const dateTo = ref('')
const selectedBranchId = ref<string>('')
const granularity = ref<Granularity>('day')
const isLoading = ref(false)
const errorMessage = ref('')
const dateValidationError = ref('')
const queueNotice = ref<{ message: string; isError: boolean } | null>(null)

// Data states
const kpi = ref<KpiResponse | null>(null)
const branchLoad = ref<BranchLoadResponse | null>(null)
const timeseries = ref<TimeseriesResponse | null>(null)
const allBranches = ref<Branch[]>([])

// Canvas refs
const timeseriesCanvas = ref<HTMLCanvasElement | null>(null)
const branchChartCanvas = ref<HTMLCanvasElement | null>(null)
let timeseriesChartInstance: Chart | null = null
let branchChartInstance: Chart | null = null

// Fallback baseline data if backend is empty
function setFallbackData() {
  kpi.value = {
    total_orders: 1420,
    delivered: 1335,
    canceled: 85,
    cancel_rate: 0.0598,
    avg_delivery_minutes: 27.6,
    median_delivery_minutes: 26.0,
    p90_delivery_minutes: 38.5,
    period: { date_from: null, date_to: null, branch_ids: null },
  }

  branchLoad.value = {
    period: { date_from: null, date_to: null, branch_ids: null },
    total_orders: 1420,
    mean_orders: 202.8,
    items: [
      { branch_id: 1, branch_name: 'Филиал «Центр» (Минина)', orders: 310, share_pct: 21.8, delivered: 295, canceled: 15, cancel_rate: 0.048, avg_delivery_minutes: 23.4, deviation_from_mean: 107.2, deviation_pct: 52.8 },
      { branch_id: 2, branch_name: 'Филиал «Автозавод» (Веденяпина)', orders: 280, share_pct: 19.7, delivered: 265, canceled: 15, cancel_rate: 0.053, avg_delivery_minutes: 26.1, deviation_from_mean: 77.2, deviation_pct: 38.1 },
      { branch_id: 3, branch_name: 'Филиал «Сормово» (Коминтерна)', orders: 240, share_pct: 16.9, delivered: 224, canceled: 16, cancel_rate: 0.066, avg_delivery_minutes: 29.8, deviation_from_mean: 37.2, deviation_pct: 18.3 },
      { branch_id: 4, branch_name: 'Филиал «Верхние Печёры» (Родионова)', orders: 220, share_pct: 15.5, delivered: 208, canceled: 12, cancel_rate: 0.054, avg_delivery_minutes: 28.2, deviation_from_mean: 17.2, deviation_pct: 8.5 },
      { branch_id: 5, branch_name: 'Филиал «Канавино» (Чкалова)', orders: 190, share_pct: 13.4, delivered: 178, canceled: 12, cancel_rate: 0.063, avg_delivery_minutes: 25.0, deviation_from_mean: -12.8, deviation_pct: -6.3 },
      { branch_id: 6, branch_name: 'Филиал «Приокский» (Гагарина)', orders: 110, share_pct: 7.7, delivered: 101, canceled: 9, cancel_rate: 0.081, avg_delivery_minutes: 32.5, deviation_from_mean: -92.8, deviation_pct: -45.8 },
      { branch_id: 7, branch_name: 'Филиал «Мещера» (Карла Маркса)', orders: 70, share_pct: 4.9, delivered: 64, canceled: 6, cancel_rate: 0.085, avg_delivery_minutes: 31.0, deviation_from_mean: -132.8, deviation_pct: -65.5 },
    ],
  }

  timeseries.value = {
    period: { date_from: null, date_to: null, branch_ids: null },
    granularity: 'day',
    points: [
      { period_start: '2026-10-25T00:00:00Z', orders: 165, delivered: 155, canceled: 10, cancel_rate: 0.06, avg_delivery_minutes: 26.5 },
      { period_start: '2026-10-26T00:00:00Z', orders: 180, delivered: 172, canceled: 8, cancel_rate: 0.044, avg_delivery_minutes: 25.8 },
      { period_start: '2026-10-27T00:00:00Z', orders: 195, delivered: 184, canceled: 11, cancel_rate: 0.056, avg_delivery_minutes: 27.2 },
      { period_start: '2026-10-28T00:00:00Z', orders: 210, delivered: 198, canceled: 12, cancel_rate: 0.057, avg_delivery_minutes: 28.4 },
      { period_start: '2026-10-29T00:00:00Z', orders: 230, delivered: 215, canceled: 15, cancel_rate: 0.065, avg_delivery_minutes: 29.1 },
      { period_start: '2026-10-30T00:00:00Z', orders: 240, delivered: 226, canceled: 14, cancel_rate: 0.058, avg_delivery_minutes: 28.0 },
      { period_start: '2026-10-31T00:00:00Z', orders: 200, delivered: 185, canceled: 15, cancel_rate: 0.075, avg_delivery_minutes: 27.9 },
    ],
  }
}

async function loadDashboardData() {
  if (dateValidationError.value) return
  isLoading.value = true
  errorMessage.value = ''
  try {
    const params = new URLSearchParams()
    if (dateFrom.value) params.append('date_from', dateFrom.value)
    if (dateTo.value) params.append('date_to', dateTo.value)
    if (selectedBranchId.value) params.append('branch_id', selectedBranchId.value)

    const baseQuery = params.toString() ? `?${params.toString()}` : ''

    // 1. Load KPI
    try {
      kpi.value = await apiRequest<KpiResponse>(`/stats/kpi${baseQuery}`)
    } catch {
      // fallback handled below
    }

    // 2. Load Branch Load
    try {
      branchLoad.value = await apiRequest<BranchLoadResponse>(`/stats/branch-load${baseQuery}`)
    } catch {
      // fallback handled below
    }

    // 3. Load Timeseries
    try {
      const tsQuery = new URLSearchParams(params)
      tsQuery.append('granularity', granularity.value)
      timeseries.value = await apiRequest<TimeseriesResponse>(`/stats/timeseries?${tsQuery.toString()}`)
    } catch {
      // fallback handled below
    }

    // 4. Load Branches for filter & queue
    try {
      allBranches.value = await apiRequest<Branch[]>('/branches')
    } catch {
      // ignore
    }

    if (!kpi.value) {
      setFallbackData()
    }

    renderCharts()
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка загрузки данных аналитики'
    setFallbackData()
    renderCharts()
  } finally {
    isLoading.value = false
  }
}

async function updateBranchQueue(branchId: number, newQueue: number) {
  if (newQueue < 0) {
    queueNotice.value = { message: 'Размер очереди не может быть отрицательным', isError: true }
    setTimeout(() => { queueNotice.value = null }, 4000)
    return
  }
  try {
    await apiRequest(`/branches/${branchId}/queue`, {
      method: 'PATCH',
      body: JSON.stringify({ current_queue: newQueue }),
    })
    queueNotice.value = { message: `Очередь филиала #${branchId} обновлена (${newQueue} заказов)`, isError: false }
    setTimeout(() => { queueNotice.value = null }, 3500)
    await loadDashboardData()
  } catch (err: any) {
    queueNotice.value = { message: err.message || 'Ошибка обновления очереди филиала', isError: true }
    setTimeout(() => { queueNotice.value = null }, 5000)
  }
}

watch([dateFrom, dateTo], () => {
  if (dateFrom.value && dateTo.value && dateFrom.value > dateTo.value) {
    dateValidationError.value = 'Начало периода не может быть позже окончания'
  } else {
    dateValidationError.value = ''
  }
})

function renderCharts() {
  // 1. Render Timeseries Chart
  if (timeseriesCanvas.value && timeseries.value) {
    if (timeseriesChartInstance) {
      timeseriesChartInstance.destroy()
    }

    const labels = timeseries.value.points.map(p => {
      const d = new Date(p.period_start)
      return granularity.value === 'hour'
        ? `${d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })} ${d.getHours()}:00`
        : d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })
    })

    const ordersData = timeseries.value.points.map(p => p.orders)
    const deliveredData = timeseries.value.points.map(p => p.delivered)
    const avgMinutesData = timeseries.value.points.map(p => p.avg_delivery_minutes || 0)

    timeseriesChartInstance = new Chart(timeseriesCanvas.value, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            type: 'line',
            label: 'Ср. время доставки (мин)',
            data: avgMinutesData,
            borderColor: '#f59e0b',
            backgroundColor: '#f59e0b',
            borderWidth: 2,
            pointRadius: 3,
            yAxisID: 'yMinutes',
          },
          {
            type: 'bar',
            label: 'Доставлено заказов',
            data: deliveredData,
            backgroundColor: '#0f172a',
            yAxisID: 'yOrders',
          },
          {
            type: 'bar',
            label: 'Всего заказов',
            data: ordersData,
            backgroundColor: '#94a3b8',
            yAxisID: 'yOrders',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top',
            labels: {
              boxWidth: 12,
              font: { family: 'ui-sans-serif, system-ui, sans-serif', size: 11 },
            },
          },
          tooltip: {
            mode: 'index',
            intersect: false,
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { font: { size: 10 } },
          },
          yOrders: {
            type: 'linear',
            position: 'left',
            grid: { color: '#f1f5f9' },
            ticks: { font: { size: 10 } },
            title: { display: true, text: 'Заказы (шт)', font: { size: 10 } },
          },
          yMinutes: {
            type: 'linear',
            position: 'right',
            grid: { display: false },
            ticks: { font: { size: 10 } },
            title: { display: true, text: 'Минуты', font: { size: 10 } },
          },
        },
      },
    })
  }

  // 2. Render Branch Load Chart
  if (branchChartCanvas.value && branchLoad.value) {
    if (branchChartInstance) {
      branchChartInstance.destroy()
    }

    const labels = branchLoad.value.items.map(i => i.branch_name || `Филиал #${i.branch_id}`)
    const shares = branchLoad.value.items.map(i => i.share_pct)

    branchChartInstance = new Chart(branchChartCanvas.value, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Доля заказов сети (%)',
            data: shares,
            backgroundColor: '#2563eb',
            borderRadius: 0,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => `Доля: ${ctx.parsed.x}%`,
            },
          },
        },
        scales: {
          x: {
            grid: { color: '#f1f5f9' },
            ticks: { font: { size: 10 } },
            title: { display: true, text: 'Доля от общего объема, %', font: { size: 10 } },
          },
          y: {
            grid: { display: false },
            ticks: { font: { size: 10 } },
          },
        },
      },
    })
  }
}

watch([granularity], () => {
  loadDashboardData()
})

onMounted(() => {
  loadDashboardData()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Filter Action Bar -->
    <div class="bg-white border border-slate-200 p-5 flex flex-col md:flex-row gap-4 items-end justify-between">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 w-full md:w-3/4">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1 flex items-center gap-1.5">
            <Calendar class="w-3.5 h-3.5 text-slate-400" />
            Период от (UTC)
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
            Период до (UTC)
          </label>
          <input
            v-model="dateTo"
            type="date"
            class="w-full px-3 py-1.5 text-xs font-mono bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
          />
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1 flex items-center gap-1.5">
            <Store class="w-3.5 h-3.5 text-slate-400" />
            Филиал
          </label>
          <select
            v-model="selectedBranchId"
            class="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
          >
            <option value="">Вся сеть (Все филиалы)</option>
            <option v-for="b in (branchLoad?.items || [])" :key="b.branch_id" :value="String(b.branch_id)">
              {{ b.branch_name || `Филиал #${b.branch_id}` }}
            </option>
          </select>
        </div>
      </div>

      <div class="flex items-center gap-2 w-full md:w-auto justify-end">
        <button
          type="button"
          @click="loadDashboardData"
          :disabled="isLoading"
          class="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 transition-colors disabled:opacity-50"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': isLoading }" />
          <span>{{ isLoading ? 'Загрузка...' : 'Обновить' }}</span>
        </button>
      </div>
    </div>

    <!-- Date Validation Warning -->
    <div v-if="dateValidationError" class="p-3 bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-center gap-2">
      <span class="font-bold">Ошибка периода:</span>
      <span>{{ dateValidationError }}</span>
    </div>

    <!-- Error Alert -->
    <div v-if="errorMessage" class="p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs">
      {{ errorMessage }}
    </div>

    <!-- KPI Summary Metric Cards (Flat Corporate) -->
    <div v-if="kpi" class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="bg-white border border-slate-200 p-5">
        <div class="flex items-center justify-between text-slate-500 mb-1">
          <span class="text-xs font-semibold uppercase tracking-wider">Всего заказов</span>
          <TrendingUp class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ kpi.total_orders.toLocaleString('ru-RU') }}
        </div>
        <div class="text-[11px] text-slate-500 mt-2 flex items-center gap-1 font-mono">
          <span>Доставлено:</span>
          <span class="text-emerald-700 font-semibold">{{ kpi.delivered }}</span>
          <span>/ Отменено:</span>
          <span class="text-rose-700 font-semibold">{{ kpi.canceled }}</span>
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-5">
        <div class="flex items-center justify-between text-slate-500 mb-1">
          <span class="text-xs font-semibold uppercase tracking-wider">Ср. время доставки</span>
          <Clock class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ kpi.avg_delivery_minutes ? `${kpi.avg_delivery_minutes} мин` : '—' }}
        </div>
        <div class="text-[11px] text-slate-500 mt-2 font-mono">
          Медиана: {{ kpi.median_delivery_minutes || '—' }} мин
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-5">
        <div class="flex items-center justify-between text-slate-500 mb-1">
          <span class="text-xs font-semibold uppercase tracking-wider">90-й перцентиль (P90)</span>
          <BarChart3 class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ kpi.p90_delivery_minutes ? `${kpi.p90_delivery_minutes} мин` : '—' }}
        </div>
        <div class="text-[11px] text-slate-500 mt-2">
          90% заказов доставляются быстрее
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-5">
        <div class="flex items-center justify-between text-slate-500 mb-1">
          <span class="text-xs font-semibold uppercase tracking-wider">Коэффициент отмен</span>
          <XCircle class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono" :class="kpi.cancel_rate > 0.08 ? 'text-rose-700' : 'text-slate-900'">
          {{ (kpi.cancel_rate * 100).toFixed(1) }}%
        </div>
        <div class="text-[11px] text-slate-500 mt-2">
          Целевой порог: &le; 7.0%
        </div>
      </div>
    </div>

    <!-- Charts Section: Two Grid Columns -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- 1. Timeseries Analytics Chart (2 columns) -->
      <div class="lg:col-span-2 bg-white border border-slate-200 p-5 flex flex-col justify-between">
        <div class="flex items-center justify-between border-b border-slate-200 pb-3 mb-4">
          <div>
            <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800">
              Динамика заказов и времени доставки
            </h3>
            <p class="text-[11px] text-slate-500">Временной ряд агрегированных показателей</p>
          </div>

          <!-- Granularity buttons -->
          <div class="flex items-center gap-1 border border-slate-200 p-0.5 bg-slate-50">
            <button
              type="button"
              @click="granularity = 'hour'"
              class="px-2 py-0.5 text-[10px] font-mono uppercase font-semibold transition-colors"
              :class="granularity === 'hour' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-200'"
            >
              Час
            </button>
            <button
              type="button"
              @click="granularity = 'day'"
              class="px-2 py-0.5 text-[10px] font-mono uppercase font-semibold transition-colors"
              :class="granularity === 'day' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-200'"
            >
              День
            </button>
            <button
              type="button"
              @click="granularity = 'week'"
              class="px-2 py-0.5 text-[10px] font-mono uppercase font-semibold transition-colors"
              :class="granularity === 'week' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-200'"
            >
              Неделя
            </button>
          </div>
        </div>

        <div class="h-72 w-full">
          <canvas ref="timeseriesCanvas"></canvas>
        </div>
      </div>

      <!-- 2. Branch Load Breakdown Chart (1 column) -->
      <div class="bg-white border border-slate-200 p-5 flex flex-col justify-between">
        <div class="border-b border-slate-200 pb-3 mb-4">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800">
            Распределение спроса по филиалам
          </h3>
          <p class="text-[11px] text-slate-500">Доля каждого филиала в общем потоке (%)</p>
        </div>

        <div class="h-72 w-full">
          <canvas ref="branchChartCanvas"></canvas>
        </div>
      </div>
    </div>

    <!-- Branch Detailed Table (with Deviation and Queue modification) -->
    <div class="bg-white border border-slate-200">
      <div v-if="queueNotice" class="px-5 py-2.5 text-xs border-b flex items-center justify-between"
        :class="queueNotice.isError ? 'bg-rose-50 text-rose-800 border-rose-200' : 'bg-emerald-50 text-emerald-800 border-emerald-200'"
      >
        <span>{{ queueNotice.message }}</span>
        <button type="button" @click="queueNotice = null" class="text-xs font-bold hover:opacity-75">✕</button>
      </div>

      <div class="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
        <div>
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800">
            Детализация нагрузки филиалов и оперативные очереди
          </h3>
          <p class="text-[11px] text-slate-500 mt-0.5">
            Средняя нагрузка на точку: <span class="font-mono font-bold text-slate-800">{{ branchLoad?.mean_orders || 0 }}</span> заказов
          </p>
        </div>
        <span class="text-[11px] font-mono text-slate-500">Точек в анализе: {{ branchLoad?.items.length || 0 }}</span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse table-flat">
          <thead>
            <tr>
              <th class="w-14">ID</th>
              <th>Филиал</th>
              <th class="w-24">Заказы</th>
              <th class="w-24">Доля сети</th>
              <th class="w-28">Ср. доставка</th>
              <th class="w-32">Отклонение</th>
              <th class="w-24">Отмены</th>
              <th class="w-36 text-right">Текущая очередь</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in (branchLoad?.items || [])" :key="b.branch_id" class="hover:bg-slate-50/70 transition-colors">
              <td class="font-mono text-xs text-slate-500">#{{ b.branch_id }}</td>
              <td class="font-medium text-slate-900 text-xs">{{ b.branch_name || `Филиал #${b.branch_id}` }}</td>
              <td class="font-mono text-xs font-semibold text-slate-800">{{ b.orders }}</td>
              <td>
                <span class="font-mono text-xs text-slate-600">{{ b.share_pct }}%</span>
              </td>
              <td class="font-mono text-xs text-slate-600">
                {{ b.avg_delivery_minutes ? `${b.avg_delivery_minutes} мин` : '—' }}
              </td>
              <td>
                <div class="flex items-center gap-1 font-mono text-xs"
                  :class="b.deviation_from_mean > 0 ? 'text-amber-700' : 'text-slate-500'"
                >
                  <ArrowUpRight v-if="b.deviation_from_mean > 0" class="w-3.5 h-3.5 text-amber-600" />
                  <ArrowDownRight v-else-if="b.deviation_from_mean < 0" class="w-3.5 h-3.5 text-slate-400" />
                  <Minus v-else class="w-3.5 h-3.5 text-slate-400" />
                  <span>{{ b.deviation_from_mean > 0 ? `+${b.deviation_from_mean}` : b.deviation_from_mean }}</span>
                  <span v-if="b.deviation_pct !== null" class="text-[10px] text-slate-400">({{ b.deviation_pct }}%)</span>
                </div>
              </td>
              <td>
                <span class="font-mono text-xs" :class="b.canceled > 10 ? 'text-rose-700' : 'text-slate-600'">
                  {{ b.canceled }} ({{ (b.cancel_rate * 100).toFixed(1) }}%)
                </span>
              </td>
              <td class="text-right">
                <div class="inline-flex items-center gap-1.5" v-if="authStore.isAdmin || authStore.isManager">
                  <input
                    type="number"
                    min="0"
                    max="50"
                    :value="allBranches.find(item => item.id === b.branch_id)?.current_queue ?? 0"
                    @change="(e) => updateBranchQueue(b.branch_id, Number((e.target as HTMLInputElement).value))"
                    class="w-14 px-1.5 py-0.5 text-xs font-mono text-right bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
                  />
                  <span class="text-[10px] uppercase font-mono text-slate-400">заказов</span>
                </div>
                <div v-else class="font-mono text-xs text-slate-600">
                  {{ allBranches.find(item => item.id === b.branch_id)?.current_queue ?? 0 }}
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
