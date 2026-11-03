<script setup lang="ts">
import { ref } from 'vue'
import { apiRequest } from '@/api/client'
import type { DriverRecommendation } from '@/types'
import { Navigation, Clock, Layers, Gauge, MapPin } from 'lucide-vue-next'

const lat = ref(56.3269)
const lon = ref(44.0059)
const isLoading = ref(false)
const recommendation = ref<DriverRecommendation | null>(null)
const mapUrl = ref<string>('/api/v1/recommendations/driver/map?lat=56.3269&lon=44.0059')
const errorMessage = ref('')

async function calculateRoute() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const data = await apiRequest<DriverRecommendation>(
      `/recommendations/driver?lat=${lat.value}&lon=${lon.value}`
    )
    recommendation.value = data
    mapUrl.value = `/api/v1/recommendations/driver/map?lat=${lat.value}&lon=${lon.value}&t=${Date.now()}`
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка расчета маршрута'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="border-b border-slate-200 pb-4">
      <h2 class="text-lg font-bold text-slate-900 tracking-tight">Маршрутизация и диспетчеризация курьера</h2>
      <p class="text-xs text-slate-500">
        Расчет оптимального филиала по графу дорог с учетом пробок и текущей очереди: min(время - очередь * 2)
      </p>
    </div>

    <!-- Error Alert -->
    <div v-if="errorMessage" class="p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs">
      {{ errorMessage }}
    </div>

    <!-- Control Panel -->
    <div class="bg-white border border-slate-200 p-5">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
            Широта курьера (Latitude)
          </label>
          <input
            v-model.number="lat"
            type="number"
            step="0.0001"
            class="w-full px-3 py-2 text-sm font-mono bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
          />
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
            Долгота курьера (Longitude)
          </label>
          <input
            v-model.number="lon"
            type="number"
            step="0.0001"
            class="w-full px-3 py-2 text-sm font-mono bg-slate-50 border border-slate-300 focus:bg-white focus:outline-none focus:border-slate-800"
          />
        </div>

        <button
          type="button"
          @click="calculateRoute"
          :disabled="isLoading"
          class="w-full py-2.5 px-4 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold uppercase tracking-wider flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
        >
          <Navigation class="w-4 h-4" />
          <span>{{ isLoading ? 'Расчет Дейкстры...' : 'Рассчитать лучший филиал' }}</span>
        </button>
      </div>
    </div>

    <!-- Recommendation Stats Grid (if calculated) -->
    <div v-if="recommendation" class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="bg-white border border-slate-200 p-4">
        <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center justify-between mb-1">
          <span>Рекомендован</span>
          <MapPin class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-base font-bold text-slate-900 truncate">
          {{ recommendation.recommended_branch.name }}
        </div>
        <div class="text-[11px] text-slate-500 font-mono mt-1">
          ID: #{{ recommendation.recommended_branch.id }}
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-4">
        <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center justify-between mb-1">
          <span>Время в пути</span>
          <Clock class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ recommendation.estimated_travel_time_minutes }} мин
        </div>
        <div class="text-[11px] text-slate-500 mt-1">
          По графу дорог с пробками
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-4">
        <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center justify-between mb-1">
          <span>Очередь заказов</span>
          <Layers class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ recommendation.recommended_branch.current_queue }}
        </div>
        <div class="text-[11px] text-slate-500 mt-1">
          Ожидают доставки
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-4">
        <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center justify-between mb-1">
          <span>Быстродействие</span>
          <Gauge class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ recommendation.elapsed_ms }} мс
        </div>
        <div class="text-[11px] text-slate-500 mt-1">
          FastRoutingService (Dijkstra)
        </div>
      </div>
    </div>

    <!-- Map Preview Iframe -->
    <div class="bg-white border border-slate-200">
      <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
        <span class="text-xs font-bold uppercase tracking-wider text-slate-800">
          Интерактивная карта маршрута (OpenStreetMap / Folium)
        </span>
        <span class="text-[11px] font-mono text-slate-500">Нижний Новгород</span>
      </div>
      <div class="h-[520px] w-full bg-slate-100">
        <iframe
          :src="mapUrl"
          class="w-full h-full border-0"
          title="Карта маршрута водителя"
        ></iframe>
      </div>
    </div>
  </div>
</template>
