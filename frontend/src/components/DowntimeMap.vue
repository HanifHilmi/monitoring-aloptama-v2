<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '@/api/client'
import EChart from '@/components/EChart.vue'

const cdps = ref([])          // [{cdp_id,name,days:[{day,downtime_minutes}]}]
const year = ref(new Date().getUTCFullYear())
const loading = ref(false)
const Y_MIN = 2026
const Y_MAX = new Date().getUTCFullYear()

async function load() {
  loading.value = true
  try {
    const d = await api.getDowntimeMap(year.value)
    cdps.value = d.cdps || []
  } catch {
    cdps.value = []
  } finally {
    loading.value = false
  }
}

// Build an ECharts calendar-heatmap option for one CDP node.
function buildHeatmap(cdp) {
  const startDate = `${year.value}-01-01`
  const endDate = `${year.value}-12-31`
  const data = (cdp.days || []).map((r) => [r.day, r.downtime_minutes])
  const maxDown = Math.max(1, ...data.map(([, v]) => v))

  return {
    animation: true,
    tooltip: {
      backgroundColor: '#0b1220',
      borderColor: '#1e2a45',
      textStyle: { color: '#e2e8f0', fontSize: 11 },
      formatter(params) {
        const val = params.value ? `${params.value[1]} min` : '0 min'
        return `${params.value[0]}: <b>${val}</b> down`
      },
    },
    visualMap: {
      min: 0,
      max: maxDown,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      text: ['More', 'Less'],
      textStyle: { color: '#94a3b8', fontSize: 10 },
      inRange: { color: ['#0f172a', '#f43f5e'] },
    },
    calendar: {
      top: 20,
      left: 10,
      right: 10,
      bottom: 60,
      cellSize: ['auto', 16],
      range: [startDate, endDate],
      splitLine: { show: true, lineStyle: { color: '#1e293b' } },
      itemStyle: { color: '#0b1220', borderWidth: 0 },
      yearLabel: { show: false },
      dayLabel: { color: '#64748b', fontSize: 10 },
      monthLabel: { color: '#64748b', fontSize: 10 },
    },
    series: [
      {
        type: 'heatmap',
        coordinateSystem: 'calendar',
        data,
      },
    ],
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-semibold uppercase tracking-wide text-slate-400">Downtime Map</h3>
      <select v-model="year" @change="load" class="rounded border border-runway-border bg-runway-panel px-2 py-1 text-xs text-slate-200">
        <option v-for="n in Y_MAX - Y_MIN + 1" :key="n" :value="Y_MAX - (n - 1)">{{ Y_MAX - (n - 1) }}</option>
      </select>
    </div>

    <div v-if="loading" class="py-12 text-center text-xs text-slate-500">Loading…</div>
    <div v-else-if="!cdps.length" class="py-12 text-center text-xs text-slate-500">
      No downtime data yet — run Backfill CDP uptime
    </div>

    <div v-else class="grid gap-6 xl:grid-cols-2">
      <div v-for="c in cdps" :key="c.cdp_id" class="panel">
        <div class="mb-1 font-mono text-xs font-semibold text-slate-200">{{ c.name }}</div>
        <EChart :option="buildHeatmap(c)" height="190px" />
      </div>
    </div>
  </div>
</template>