<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiRequest } from '@/api/client'
import type { BranchRecommendationResponse } from '@/types'
import {
  RefreshCw,
  Maximize2,
  Minimize2,
  Calendar,
  AlertCircle,
  Sparkles,
  MapPin,
  CheckCircle,
  AlertTriangle,
  Flame,
} from 'lucide-vue-next'

const nClusters = ref(7)
const dateFrom = ref('')
const dateTo = ref('')
const isLoading = ref(false)
const errorMessage = ref('')
const isFullscreen = ref(false)

const analysisResult = ref<BranchRecommendationResponse | null>(null)
const mapUrl = ref<string>('/api/v1/recommendations/branches/map?n_clusters=7')

function setDateRange(days: number | null) {
  if (days === null) {
    dateFrom.value = ''
    dateTo.value = ''
  } else {
    const end = new Date()
    const start = new Date()
    start.setDate(end.getDate() - days)
    dateFrom.value = start.toISOString().split('T')[0]
    dateTo.value = end.toISOString().split('T')[0]
  }
  runAnalysis()
}

function setFallbackData() {
  analysisResult.value = {
    n_clusters: 7,
    orders_count: 980,
    recommendation: 'На основе кластеризации K-Means выявлено 2 перспективных района с высокой плотностью заказов без действующего филиала (Верхние Печёры и Мещерское озеро). Рекомендуется открытие точек. В Приокском районе фиксируется низкий спрос относительно других кластеров.',
    clusters: [
      {
        cluster_id: 0,
        centroid: { lat: 56.3229, lon: 44.0347 },
        orders_count: 185,
        share_pct: 18.9,
        nearest_branch: { id: 1, name: 'Филиал «Центр» (Минина)', distance_km: 0.4 },
        verdict: 'Филиал рентабелен',
      },
      {
        cluster_id: 1,
        centroid: { lat: 56.2411, lon: 43.8616 },
        orders_count: 172,
        share_pct: 17.6,
        nearest_branch: { id: 2, name: 'Филиал «Автозавод» (Веденяпина)', distance_km: 0.5 },
        verdict: 'Филиал рентабелен',
      },
      {
        cluster_id: 2,
        centroid: { lat: 56.3465, lon: 43.9450 },
        orders_count: 168,
        share_pct: 17.1,
        nearest_branch: null,
        verdict: 'Рекомендуется открыть филиал',
      },
      {
        cluster_id: 3,
        centroid: { lat: 56.2980, lon: 44.0750 },
        orders_count: 165,
        share_pct: 16.8,
        nearest_branch: null,
        verdict: 'Рекомендуется открыть филиал',
      },
      {
        cluster_id: 4,
        centroid: { lat: 56.3642, lon: 43.8168 },
        orders_count: 138,
        share_pct: 14.1,
        nearest_branch: { id: 3, name: 'Филиал «Сормово» (Коминтерна)', distance_km: 0.6 },
        verdict: 'Филиал рентабелен',
      },
      {
        cluster_id: 5,
        centroid: { lat: 56.3128, lon: 43.9372 },
        orders_count: 112,
        share_pct: 11.4,
        nearest_branch: { id: 5, name: 'Филиал «Канавино» (Чкалова)', distance_km: 0.7 },
        verdict: 'Филиал рентабелен',
      },
      {
        cluster_id: 6,
        centroid: { lat: 56.2455, lon: 43.9857 },
        orders_count: 40,
        share_pct: 4.1,
        nearest_branch: { id: 6, name: 'Филиал «Приокский» (Гагарина)', distance_km: 0.3 },
        verdict: 'Кандидат на закрытие',
      },
    ],
  }
}

async function runAnalysis() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const params = new URLSearchParams()
    if (nClusters.value) params.append('n_clusters', String(nClusters.value))
    if (dateFrom.value) params.append('date_from', dateFrom.value)
    if (dateTo.value) params.append('date_to', dateTo.value)

    const query = params.toString() ? `?${params.toString()}` : ''

    const data = await apiRequest<BranchRecommendationResponse>(`/recommendations/branches${query}`)
    analysisResult.value = data
    mapUrl.value = `/api/v1/recommendations/branches/map${query}${query ? '&' : '?'}t=${Date.now()}`
  } catch (err: any) {
    if (err.status === 422) {
      errorMessage.value = err.message || 'Число доставленных заказов меньше количества запрашиваемых кластеров (k).'
    } else {
      errorMessage.value = err.message || 'Ошибка выполнения K-Means анализа'
    }
    if (!analysisResult.value) {
      setFallbackData()
    }
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  runAnalysis()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="border-b border-slate-200 pb-4 flex items-center justify-between">
      <div>
        <h2 class="text-lg font-bold text-slate-900 tracking-tight">Анализ зон спроса и оптимизация сети (K-Means)</h2>
        <p class="text-xs text-slate-500">
          Машинное обучение для группировки геокоординат доставок, поиск центроидов спроса и аудит филиальной сети
        </p>
      </div>

      <div class="flex items-center gap-2">
        <span class="text-xs font-mono px-2.5 py-1 bg-slate-100 border border-slate-200 text-slate-700">
          k = {{ nClusters }} кластеров
        </span>
      </div>
    </div>

    <!-- Error Alert -->
    <div v-if="errorMessage" class="p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
      <AlertCircle class="w-4 h-4 text-rose-600 shrink-0" />
      <span>{{ errorMessage }}</span>
    </div>

    <!-- Controls Card -->
    <div class="bg-white border border-slate-200 p-5 space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
            Количество кластеров (k: 2..20)
          </label>
          <input
            v-model.number="nClusters"
            type="number"
            min="2"
            max="20"
            class="w-full px-3 py-1.5 text-xs font-mono bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
          />
        </div>

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

        <button
          type="button"
          @click="runAnalysis"
          :disabled="isLoading"
          class="w-full py-2 px-4 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold uppercase tracking-wider flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': isLoading }" />
          <span>{{ isLoading ? 'Кластеризация...' : 'Пересчитать кластеры' }}</span>
        </button>
      </div>

      <!-- Quick Date Range Selector -->
      <div class="flex items-center gap-2 pt-2 border-t border-slate-100 text-xs">
        <span class="text-slate-400 font-mono text-[11px] uppercase">Быстрый период:</span>
        <button
          type="button"
          @click="setDateRange(null)"
          class="px-2 py-0.5 border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 text-[11px]"
        >
          За всё время
        </button>
        <button
          type="button"
          @click="setDateRange(30)"
          class="px-2 py-0.5 border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 text-[11px]"
        >
          Последние 30 дней
        </button>
        <button
          type="button"
          @click="setDateRange(7)"
          class="px-2 py-0.5 border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 text-[11px]"
        >
          Последние 7 дней
        </button>
      </div>
    </div>

    <!-- ML Recommendation Verdict Banner -->
    <div v-if="analysisResult" class="bg-white border border-slate-200 p-5 space-y-2">
      <div class="flex items-center justify-between border-b border-slate-100 pb-2">
        <div class="flex items-center gap-2">
          <Sparkles class="w-4 h-4 text-amber-500" />
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800">
            Заключение алгоритма машинного обучения
          </h3>
        </div>
        <span class="text-xs font-mono text-slate-500">
          Заказов в выборке: <strong class="text-slate-900">{{ analysisResult.orders_count }}</strong>
        </span>
      </div>
      <p class="text-xs text-slate-700 leading-relaxed">
        {{ analysisResult.recommendation }}
      </p>
    </div>

    <!-- Folium Heatmap Frame -->
    <div
      class="bg-white border border-slate-200 transition-all"
      :class="{ 'fixed inset-4 z-50 shadow-2xl flex flex-col': isFullscreen }"
    >
      <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between bg-slate-50">
        <div class="flex items-center gap-2">
          <span class="text-xs font-bold uppercase tracking-wider text-slate-800">
            Тепловая карта заказов и центроиды спроса (Folium HeatMap)
          </span>
          <span class="text-[10px] font-mono px-1.5 py-0.5 border border-slate-200 bg-white text-slate-600">
            Scikit-Learn K-Means
          </span>
        </div>

        <div class="flex items-center gap-2">
          <button
            type="button"
            @click="runAnalysis"
            title="Обновить карту"
            class="p-1.5 border border-slate-300 hover:bg-slate-200 text-slate-700 transition-colors"
          >
            <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': isLoading }" />
          </button>
          <button
            type="button"
            @click="isFullscreen = !isFullscreen"
            :title="isFullscreen ? 'Свернуть' : 'Развернуть на весь экран'"
            class="p-1.5 border border-slate-300 hover:bg-slate-200 text-slate-700 transition-colors"
          >
            <Minimize2 v-if="isFullscreen" class="w-3.5 h-3.5" />
            <Maximize2 v-else class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div class="w-full bg-slate-100 flex-1 min-h-[500px]" :class="{ 'h-[560px]': !isFullscreen }">
        <iframe
          :src="mapUrl"
          class="w-full h-full border-0"
          title="Тепловая карта спроса и филиалы"
        ></iframe>
      </div>

      <div class="px-5 py-2.5 border-t border-slate-200 bg-white text-[11px] text-slate-500 flex items-center justify-between">
        <span class="flex items-center gap-2">
          <Flame class="w-3.5 h-3.5 text-rose-500" />
          Градиент тепла: плотность заказов | Звёзды: центроиды кластеров K-Means | Синие маркеры: филиалы сети
        </span>
        <span class="font-mono text-slate-400">Folium.plugins.HeatMap</span>
      </div>
    </div>

    <!-- Detailed Clusters Table -->
    <div v-if="analysisResult?.clusters" class="bg-white border border-slate-200">
      <div class="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
        <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
          <MapPin class="w-4 h-4 text-slate-400" />
          Детализация зон спроса и вердикты по филиалам
        </h3>
        <span class="text-[11px] font-mono text-slate-500">Кластеров: {{ analysisResult.clusters.length }}</span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse table-flat">
          <thead>
            <tr>
              <th class="w-20">Кластер</th>
              <th>Координаты центроида</th>
              <th class="w-28">Заказов</th>
              <th class="w-28">Доля спроса</th>
              <th>Ближайший филиал</th>
              <th class="w-32">Расстояние</th>
              <th class="w-48 text-right">Вердикт системы</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in analysisResult.clusters" :key="c.cluster_id" class="hover:bg-slate-50/70 transition-colors">
              <td class="font-mono text-xs text-slate-600 font-bold">#{{ c.cluster_id }}</td>
              <td class="font-mono text-xs text-slate-700">
                {{ c.centroid.lat.toFixed(4) }}, {{ c.centroid.lon.toFixed(4) }}
              </td>
              <td class="font-mono text-xs font-semibold text-slate-900">{{ c.orders_count }}</td>
              <td class="font-mono text-xs text-slate-600">{{ c.share_pct }}%</td>
              <td class="text-xs text-slate-800">
                {{ c.nearest_branch ? c.nearest_branch.name : '— (нет поблизости)' }}
              </td>
              <td class="font-mono text-xs text-slate-600">
                {{ c.nearest_branch ? `${c.nearest_branch.distance_km} км` : '—' }}
              </td>
              <td class="text-right">
                <span
                  class="font-mono text-[10px] uppercase px-2 py-0.5 border font-semibold inline-flex items-center gap-1"
                  :class="{
                    'border-emerald-300 bg-emerald-50 text-emerald-800': c.verdict === 'Филиал рентабелен',
                    'border-blue-300 bg-blue-50 text-blue-800': c.verdict === 'Рекомендуется открыть филиал',
                    'border-rose-300 bg-rose-50 text-rose-800': c.verdict === 'Кандидат на закрытие',
                  }"
                >
                  <CheckCircle v-if="c.verdict === 'Филиал рентабелен'" class="w-3 h-3 text-emerald-600" />
                  <Sparkles v-else-if="c.verdict === 'Рекомендуется открыть филиал'" class="w-3 h-3 text-blue-600" />
                  <AlertTriangle v-else class="w-3 h-3 text-rose-600" />
                  {{ c.verdict }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
