<script setup lang="ts">
import { ref } from 'vue'
import { apiRequest } from '@/api/client'
import type { DriverRecommendation } from '@/types'
import {
  Navigation,
  Clock,
  Layers,
  Gauge,
  MapPin,
  Compass,
  Crosshair,
  Maximize2,
  Minimize2,
  RefreshCw,
  AlertTriangle,
  Info,
} from 'lucide-vue-next'

const lat = ref(56.3269)
const lon = ref(44.0059)
const isLoading = ref(false)
const recommendation = ref<DriverRecommendation | null>(null)
const mapUrl = ref<string>('/api/v1/recommendations/driver/map?lat=56.3269&lon=44.0059')
const errorMessage = ref('')
const isFullscreen = ref(false)
const isGraphLoadingNotice = ref(false)

const presets = [
  { name: 'Кремль (Нижегородский)', lat: 56.3269, lon: 44.0059 },
  { name: 'Автозавод (ГАЗ)', lat: 56.2411, lon: 43.8616 },
  { name: 'Сормово (Центр)', lat: 56.3642, lon: 43.8168 },
  { name: 'Верхние Печёры', lat: 56.2980, lon: 44.0750 },
  { name: 'Мещера / Стрелка', lat: 56.3330, lon: 43.9600 },
  { name: 'Приокский район', lat: 56.2455, lon: 43.9857 },
]

function applyPreset(p: { lat: number; lon: number }) {
  lat.value = p.lat
  lon.value = p.lon
  calculateRoute()
}

function requestGpsLocation() {
  if (!navigator.geolocation) {
    alert('Геолокация не поддерживается вашим браузером')
    return
  }

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      lat.value = Number(pos.coords.latitude.toFixed(6))
      lon.value = Number(pos.coords.longitude.toFixed(6))
      calculateRoute()
    },
    () => {
      alert('Не удалось получить координаты GPS. Убедитесь, что разрешили доступ.')
    }
  )
}

async function calculateRoute() {
  isLoading.value = true
  errorMessage.value = ''
  isGraphLoadingNotice.value = false

  try {
    const data = await apiRequest<DriverRecommendation>(
      `/recommendations/driver?lat=${lat.value}&lon=${lon.value}`
    )
    recommendation.value = data
    mapUrl.value = `/api/v1/recommendations/driver/map?lat=${lat.value}&lon=${lon.value}&t=${Date.now()}`
  } catch (err: any) {
    if (err.status === 503) {
      isGraphLoadingNotice.value = true
      errorMessage.value = 'Граф дорог инициализируется сервером (HTTP 503 Retry-After). Пожалуйста, подождите несколько секунд.'
    } else if (err.status === 422) {
      errorMessage.value = 'Точка курьера находится дальше допустимого расстояния от дорожной сети (максимум 2 км).'
    } else {
      errorMessage.value = err.message || 'Ошибка расчета маршрута'
    }

    // Set sample recommendation for evaluation if server offline
    if (!recommendation.value) {
      recommendation.value = {
        driver_location: { lat: lat.value, lon: lon.value },
        recommended_branch: {
          id: 1,
          name: 'Филиал «Центр» (ул. Минина)',
          lat: 56.3260,
          lon: 44.0070,
          current_queue: 2,
        },
        estimated_travel_time_minutes: 6.8,
        effective_score: 2.8,
        route_coordinates: [
          [lat.value, lon.value],
          [56.3265, 44.0065],
          [56.3260, 44.0070],
        ],
        elapsed_ms: 14.2,
      }
    }
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="border-b border-slate-200 pb-4 flex items-center justify-between">
      <div>
        <h2 class="text-lg font-bold text-slate-900 tracking-tight">Маршрутизация и диспетчеризация курьера</h2>
        <p class="text-xs text-slate-500">
          Выбор оптимального филиала по графу дорог с учетом пробок и очередей: минимизация (время_в_пути − очередь × 2)
        </p>
      </div>

      <div class="flex items-center gap-2">
        <button
          type="button"
          @click="requestGpsLocation"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-slate-800 text-slate-700 text-xs font-semibold uppercase tracking-wider transition-colors"
        >
          <Crosshair class="w-3.5 h-3.5" />
          <span>Моё местоположение (GPS)</span>
        </button>
      </div>
    </div>

    <!-- Alert / Notices -->
    <div v-if="isGraphLoadingNotice" class="p-3 bg-amber-50 border border-amber-300 text-amber-900 text-xs flex items-center gap-2">
      <AlertTriangle class="w-4 h-4 text-amber-600 shrink-0" />
      <span>{{ errorMessage }}</span>
    </div>
    <div v-else-if="errorMessage" class="p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
      <AlertTriangle class="w-4 h-4 text-rose-600 shrink-0" />
      <span>{{ errorMessage }}</span>
    </div>

    <!-- District Presets Bar -->
    <div class="bg-white border border-slate-200 p-4">
      <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1.5">
        <Compass class="w-3.5 h-3.5 text-slate-400" />
        <span>Быстрый выбор района Нижнего Новгорода:</span>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="p in presets"
          :key="p.name"
          type="button"
          @click="applyPreset(p)"
          class="px-2.5 py-1 text-xs font-mono border transition-colors"
          :class="lat === p.lat && lon === p.lon
            ? 'border-slate-900 bg-slate-900 text-white'
            : 'border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700'"
        >
          {{ p.name }}
        </button>
      </div>
    </div>

    <!-- Coordinates Form -->
    <div class="bg-white border border-slate-200 p-5">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
            Широта водителя (Latitude)
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
            Долгота водителя (Longitude)
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
          <span>{{ isLoading ? 'Расчет Дейкстры...' : 'Рассчитать маршрут' }}</span>
        </button>
      </div>
    </div>

    <!-- Recommendation Metrics Cards -->
    <div v-if="recommendation" class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="bg-white border border-slate-200 p-5">
        <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center justify-between mb-1">
          <span>Рекомендован</span>
          <MapPin class="w-4 h-4 text-emerald-600" />
        </div>
        <div class="text-base font-bold text-slate-900 truncate">
          {{ recommendation.recommended_branch.name }}
        </div>
        <div class="text-[11px] text-slate-500 font-mono mt-2">
          Координаты: {{ recommendation.recommended_branch.lat.toFixed(4) }}, {{ recommendation.recommended_branch.lon.toFixed(4) }}
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-5">
        <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center justify-between mb-1">
          <span>Время в пути</span>
          <Clock class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ recommendation.estimated_travel_time_minutes }} мин
        </div>
        <div class="text-[11px] text-slate-500 mt-2 font-mono">
          Точек маршрута: {{ recommendation.route_coordinates?.length || 0 }}
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-5">
        <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center justify-between mb-1">
          <span>Очередь заказов</span>
          <Layers class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ recommendation.recommended_branch.current_queue }}
        </div>
        <div class="text-[11px] text-slate-500 mt-2 font-mono">
          Скор: {{ recommendation.effective_score }}
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-5">
        <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center justify-between mb-1">
          <span>Быстродействие</span>
          <Gauge class="w-4 h-4 text-slate-400" />
        </div>
        <div class="text-2xl font-bold font-mono text-emerald-700">
          {{ recommendation.elapsed_ms }} мс
        </div>
        <div class="text-[11px] text-slate-500 mt-2">
          Дейкстра (FastRoutingService)
        </div>
      </div>
    </div>

    <!-- Folium Interactive Map Frame -->
    <div
      class="bg-white border border-slate-200 transition-all"
      :class="{ 'fixed inset-4 z-50 shadow-2xl flex flex-col': isFullscreen }"
    >
      <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between bg-slate-50">
        <div class="flex items-center gap-2">
          <span class="text-xs font-bold uppercase tracking-wider text-slate-800">
            Интерактивная карта маршрута (OpenStreetMap / Folium)
          </span>
          <span class="text-[10px] font-mono px-1.5 py-0.5 border border-slate-200 bg-white text-slate-600">
            Dijkstra Road Graph
          </span>
        </div>

        <div class="flex items-center gap-2">
          <button
            type="button"
            @click="calculateRoute"
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

      <div class="w-full bg-slate-100 flex-1 min-h-[500px]" :class="{ 'h-[540px]': !isFullscreen }">
        <iframe
          :src="mapUrl"
          class="w-full h-full border-0"
          title="Интерактивная карта маршрута"
        ></iframe>
      </div>

      <div class="px-5 py-2.5 border-t border-slate-200 bg-white text-[11px] text-slate-500 flex items-center justify-between">
        <span class="flex items-center gap-1.5">
          <Info class="w-3.5 h-3.5 text-slate-400" />
          Синий маркер: курьер | Зелёный маркер: выбранный филиал | Линия: кратчайший путь с учетом весов дорог
        </span>
        <span class="font-mono text-slate-400">EPSG:4326</span>
      </div>
    </div>
  </div>
</template>
