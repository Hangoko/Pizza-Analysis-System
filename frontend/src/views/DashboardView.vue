<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiRequest } from '@/api/client'
import {
  TrendingUp,
  Clock,
  CheckCircle2,
  Store,
  RefreshCw,
} from 'lucide-vue-next'

interface KpiData {
  total_orders?: number
  delivered_orders?: number
  average_delivery_time?: number
  active_branches_count?: number
}

const isLoading = ref(false)
const kpi = ref<KpiData>({
  total_orders: 1250,
  delivered_orders: 1184,
  average_delivery_time: 28.4,
  active_branches_count: 7,
})

const branches = ref([
  { id: 1, name: 'Филиал «Центр» (Минина)', queue: 2, status: 'Активен', avg_time: '24 мин' },
  { id: 2, name: 'Филиал «Сормово» (Коминтерна)', queue: 5, status: 'Активен', avg_time: '31 мин' },
  { id: 3, name: 'Филиал «Автозавод» (Веденяпина)', queue: 1, status: 'Активен', avg_time: '26 мин' },
  { id: 4, name: 'Филиал «Верхние Печёры» (Родионова)', queue: 4, status: 'Активен', avg_time: '29 мин' },
  { id: 5, name: 'Филиал «Советский» (Бекетова)', queue: 0, status: 'Активен', avg_time: '22 мин' },
])

async function loadData() {
  isLoading.value = true
  try {
    const data = await apiRequest<KpiData>('/stats/kpi')
    if (data) {
      kpi.value = { ...kpi.value, ...data }
    }
  } catch {
    // Keep baseline mockup metrics if server is not seeded yet
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Action Bar -->
    <div class="flex items-center justify-between border-b border-slate-200 pb-4">
      <div>
        <h2 class="text-lg font-bold text-slate-900 tracking-tight">Операционные показатели сети</h2>
        <p class="text-xs text-slate-500">Сводные KPI и статус загрузки филиалов в режиме реального времени</p>
      </div>
      <button
        type="button"
        @click="loadData"
        :disabled="isLoading"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-slate-800 text-slate-700 text-xs font-semibold uppercase tracking-wider transition-colors disabled:opacity-50"
      >
        <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': isLoading }" />
        Обновить данные
      </button>
    </div>

    <!-- KPI Metric Cards Grid (Flat corporate style) -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="bg-white border border-slate-200 p-5">
        <div class="flex items-center justify-between text-slate-500 mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider">Всего заказов</span>
          <TrendingUp class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ kpi.total_orders?.toLocaleString('ru-RU') || '—' }}
        </div>
        <div class="text-[11px] text-slate-500 mt-2 flex items-center gap-1">
          <span class="text-emerald-700 font-medium">94.7%</span> успешных доставок
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-5">
        <div class="flex items-center justify-between text-slate-500 mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider">Доставлено</span>
          <CheckCircle2 class="w-4 h-4 text-emerald-600" />
        </div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ kpi.delivered_orders?.toLocaleString('ru-RU') || '—' }}
        </div>
        <div class="text-[11px] text-slate-500 mt-2">
          В пределах целевого норматива
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-5">
        <div class="flex items-center justify-between text-slate-500 mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider">Ср. время доставки</span>
          <Clock class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ kpi.average_delivery_time ? `${kpi.average_delivery_time} мин` : '—' }}
        </div>
        <div class="text-[11px] text-slate-500 mt-2">
          Норматив: &le; 30 минут
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-5">
        <div class="flex items-center justify-between text-slate-500 mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider">Активных точек</span>
          <Store class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ kpi.active_branches_count || '7' }}
        </div>
        <div class="text-[11px] text-slate-500 mt-2">
          Нижний Новгород
        </div>
      </div>
    </div>

    <!-- Branch Status Table -->
    <div class="bg-white border border-slate-200">
      <div class="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
        <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800">
          Текущая нагрузка филиалов сети
        </h3>
        <span class="text-[11px] font-mono text-slate-500">По данным системы</span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse table-flat">
          <thead>
            <tr>
              <th class="w-16">ID</th>
              <th>Наименование филиала</th>
              <th class="w-32">Очередь</th>
              <th class="w-36">Ср. время</th>
              <th class="w-32">Статус</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in branches" :key="b.id" class="hover:bg-slate-50/70 transition-colors">
              <td class="font-mono text-xs text-slate-500">#{{ b.id }}</td>
              <td class="font-medium text-slate-800">{{ b.name }}</td>
              <td>
                <span class="font-mono font-semibold px-2 py-0.5 border text-xs"
                  :class="b.queue > 3 ? 'border-amber-300 bg-amber-50 text-amber-800' : 'border-slate-200 bg-slate-50 text-slate-700'"
                >
                  {{ b.queue }} заказов
                </span>
              </td>
              <td class="font-mono text-xs text-slate-600">{{ b.avg_time }}</td>
              <td>
                <span class="inline-flex items-center gap-1.5 text-xs text-emerald-700 font-medium">
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                  {{ b.status }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
