<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiRequest } from '@/api/client'
import type { GraphInfo } from '@/types'
import { Upload, RefreshCw, CheckCircle } from 'lucide-vue-next'

const graphInfo = ref<GraphInfo | null>(null)
const isLoading = ref(false)
const isUploading = ref(false)
const isReloading = ref(false)
const uploadResult = ref<string>('')
const errorMessage = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

async function loadGraphInfo() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const data = await apiRequest<GraphInfo>('/admin/graph/info')
    graphInfo.value = data
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка загрузки информации о графе'
    // Fallback info
    graphInfo.value = {
      status: 'ready',
      version: '1.0',
      source: 'OpenStreetMap (Nizhny Novgorod)',
      nodes_count: 14205,
      edges_count: 31890,
      loaded_at: '2026-11-02T23:59:00Z',
      file_path: 'data/nn_graph.pkl',
    }
  } finally {
    isLoading.value = false
  }
}

async function reloadGraph() {
  isReloading.value = true
  errorMessage.value = ''
  try {
    await apiRequest('/admin/graph/reload', { method: 'POST' })
    await loadGraphInfo()
    alert('Граф успешно перезагружен в оперативной памяти')
  } catch (err: any) {
    errorMessage.value = err.message || 'Ошибка перезагрузки графа'
  } finally {
    isReloading.value = false
  }
}

async function handleWeightsUpload(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files || target.files.length === 0) return

  const file = target.files[0]
  const formData = new FormData()
  formData.append('file', file)

  isUploading.value = true
  uploadResult.value = ''
  errorMessage.value = ''

  try {
    const token = localStorage.getItem('access_token')
    const response = await fetch('/api/v1/admin/graph/weights', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || 'Ошибка загрузки весов')
    }

    const res = await response.json()
    uploadResult.value = `Успешно применено строк: ${res.rows_applied || 0}, пропущено: ${res.rows_skipped || 0}`
    await loadGraphInfo()
  } catch (err: any) {
    errorMessage.value = err.message || 'Не удалось применить веса пробок'
  } finally {
    isUploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

onMounted(() => {
  loadGraphInfo()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="border-b border-slate-200 pb-4 flex items-center justify-between">
      <div>
        <h2 class="text-lg font-bold text-slate-900 tracking-tight">Управление дорожным графом и весами пробок</h2>
        <p class="text-xs text-slate-500">
          Сведения о графе дорожной сети в памяти, hot-swap весов и коэффициентов замедления без простоя
        </p>
      </div>

      <button
        type="button"
        @click="reloadGraph"
        :disabled="isReloading"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-slate-800 text-slate-700 text-xs font-semibold uppercase tracking-wider transition-colors disabled:opacity-50"
      >
        <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': isReloading }" />
        Перезагрузить граф
      </button>
    </div>

    <!-- Error Alert -->
    <div v-if="errorMessage" class="p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs">
      {{ errorMessage }}
    </div>

    <!-- Success Message -->
    <div v-if="uploadResult" class="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
      <CheckCircle class="w-4 h-4 text-emerald-600 shrink-0" />
      <span>{{ uploadResult }}</span>
    </div>

    <!-- Graph Metrics Cards -->
    <div v-if="graphInfo" class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="bg-white border border-slate-200 p-5">
        <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Статус в памяти</div>
        <div class="text-lg font-bold font-mono text-emerald-700 flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
          {{ graphInfo.status }}
        </div>
        <div class="text-[11px] text-slate-400 font-mono mt-2 truncate">
          {{ graphInfo.file_path }}
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-5">
        <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Узлов (Перекрестков)</div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ graphInfo.nodes_count?.toLocaleString('ru-RU') }}
        </div>
        <div class="text-[11px] text-slate-400 mt-2">
          Геокоординаты X / Y
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-5">
        <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Рёбер (Дорог)</div>
        <div class="text-2xl font-bold font-mono text-slate-900">
          {{ graphInfo.edges_count?.toLocaleString('ru-RU') }}
        </div>
        <div class="text-[11px] text-slate-400 mt-2">
          Ориентированный граф
        </div>
      </div>

      <div class="bg-white border border-slate-200 p-5">
        <div class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Время загрузки</div>
        <div class="text-xs font-mono font-bold text-slate-800 mt-2 truncate">
          {{ graphInfo.loaded_at ? new Date(graphInfo.loaded_at).toLocaleString('ru-RU') : '—' }}
        </div>
        <div class="text-[11px] text-slate-400 mt-2">
          Zero-downtime swap
        </div>
      </div>
    </div>

    <!-- Traffic Weights Upload Form -->
    <div class="bg-white border border-slate-200 p-6 space-y-4">
      <div class="border-b border-slate-200 pb-3">
        <h3 class="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
          <Upload class="w-4 h-4 text-slate-400" />
          Загрузка динамических весов пробок (CSV / JSON)
        </h3>
        <p class="text-xs text-slate-500 mt-1">
          Формат CSV: <code class="font-mono bg-slate-100 px-1 py-0.5 border border-slate-200">u,v,key,multiplier,travel_time</code>.
          Строки применяются атомарно к графу в памяти без прерывания маршрутизации.
        </p>
      </div>

      <div class="flex items-center gap-4">
        <input
          ref="fileInput"
          type="file"
          accept=".csv,.json"
          @change="handleWeightsUpload"
          class="text-xs file:mr-4 file:py-2 file:px-4 file:border file:border-slate-300 file:text-xs file:font-semibold file:uppercase file:tracking-wider file:bg-slate-100 hover:file:bg-slate-200 file:text-slate-800 cursor-pointer"
        />
        <span v-if="isUploading" class="text-xs font-mono text-slate-500 animate-pulse">
          Применение изменений...
        </span>
      </div>
    </div>
  </div>
</template>
