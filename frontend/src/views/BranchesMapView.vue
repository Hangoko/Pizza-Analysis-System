<script setup lang="ts">
import { ref } from 'vue'
import { apiRequest } from '@/api/client'
import { RefreshCw } from 'lucide-vue-next'

const nClusters = ref(7)
const dateFrom = ref('')
const dateTo = ref('')
const isLoading = ref(false)
const errorMessage = ref('')
const mapUrl = ref<string>('/api/v1/recommendations/branches/map')
const analysisResult = ref<any>(null)

async function runAnalysis() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const params = new URLSearchParams()
    if (nClusters.value) params.append('n_clusters', String(nClusters.value))
    if (dateFrom.value) params.append('date_from', dateFrom.value)
    if (dateTo.value) params.append('date_to', dateTo.value)

    const query = params.toString() ? `?${params.toString()}` : ''
    const data = await apiRequest(`/recommendations/branches${query}`)
    analysisResult.value = data
    mapUrl.value = `/api/v1/recommendations/branches/map${query}${query ? '&' : '?'}t=${Date.now()}`
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка выполнения K-Means анализа'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="border-b border-slate-200 pb-4">
      <h2 class="text-lg font-bold text-slate-900 tracking-tight">Анализ зон спроса и оптимизация филиалов (K-Means)</h2>
      <p class="text-xs text-slate-500">
        Машинное обучение для выявления плотности заказов, центроидов спроса и рекомендаций по открытию/закрытию филиалов
      </p>
    </div>

    <!-- Error Alert -->
    <div v-if="errorMessage" class="p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs">
      {{ errorMessage }}
    </div>

    <!-- Filters -->
    <div class="bg-white border border-slate-200 p-5">
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
            Число кластеров (k)
          </label>
          <input
            v-model.number="nClusters"
            type="number"
            min="2"
            max="20"
            class="w-full px-3 py-2 text-sm font-mono bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
          />
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
            Дата начала периода
          </label>
          <input
            v-model="dateFrom"
            type="date"
            class="w-full px-3 py-2 text-sm font-mono bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
          />
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
            Дата окончания периода
          </label>
          <input
            v-model="dateTo"
            type="date"
            class="w-full px-3 py-2 text-sm font-mono bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
          />
        </div>

        <button
          type="button"
          @click="runAnalysis"
          :disabled="isLoading"
          class="w-full py-2.5 px-4 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold uppercase tracking-wider flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoading }" />
          <span>{{ isLoading ? 'Анализ K-Means...' : 'Построить тепловую карту' }}</span>
        </button>
      </div>
    </div>

    <!-- Analysis Summary Card if returned -->
    <div v-if="analysisResult" class="bg-white border border-slate-200 p-5 space-y-3">
      <div class="flex items-center justify-between border-b border-slate-100 pb-2">
        <span class="text-xs font-bold uppercase tracking-wider text-slate-800">
          Результаты кластерного анализа
        </span>
        <span class="text-xs font-mono text-slate-500">
          Заказов в выборке: {{ analysisResult.orders_count || 0 }}
        </span>
      </div>
      <div class="text-xs text-slate-700 leading-relaxed" v-if="analysisResult.recommendation">
        {{ analysisResult.recommendation }}
      </div>
    </div>

    <!-- Folium Heatmap Frame -->
    <div class="bg-white border border-slate-200">
      <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
        <span class="text-xs font-bold uppercase tracking-wider text-slate-800">
          Тепловая карта заказов и центроиды спроса (Folium HeatMap)
        </span>
        <span class="text-[11px] font-mono text-slate-500">K-Means Engine</span>
      </div>
      <div class="h-[560px] w-full bg-slate-100">
        <iframe
          :src="mapUrl"
          class="w-full h-full border-0"
          title="Тепловая карта спроса"
        ></iframe>
      </div>
    </div>
  </div>
</template>
