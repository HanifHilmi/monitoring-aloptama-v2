<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '@/api/client'
import EChart from '@/components/EChart.vue'

const cdps = ref([])          // [{cdp_id,name,days:[{day,downtime_minutes}]}]
const year = ref(new Date().getUTCFullYear())
const loading = ref(false)
const Y_MIN = 2026
const Y_MAX = new Date().getUTCFullYear()
let timer = null

async function load() {
  loading.value = true
  try {
    const d = await api.getDowntimeMap(year.value)
    let list = d.cdps || []
    // Zero-fill fallback so the chart always renders even before backfill.
    if (!list.length) {
      const ov = await api.getStatusOverview().catch(() => null)
      const nodes = ov?.cdp_nodes || [
        { cdp_id: 1, name: 'CDP1' },
        { cdp_id: 2, name: 'CDP2' },
      ]
      const zeroDays = zeroDaysFor(year.value)
      list = nodes.map((n) => ({
        cdp_id: n.cdp_id ?? n.id,
        name: n.name,
        days: zeroDays.map((day) => ({ day, downtime_minutes: 0 })),
      }))
    }
    cdps.value = list
  } catch {
    if (!cdps.value.length) {
      cdps.value = [
        { cdp_id: 1, name: 'CDP1', days: zeroDaysFor(year.value).map((day) => ({ day, downtime_minutes: 0 })) },
        { cdp_id: 2, name: 'CDP2', days: zeroDaysFor(year.value).map((day) => ({ day, downtime_minutes: 0 })) },
      ]
    }
  } finally {
    loading.value = false
  }
}

// All days of the year up to today (or the full year for past years).
function zeroDaysFor(y) {
  const out = []
  const now = new Date()
  const lastDay = y < now.getUTCFullYear()
    ? new Date(Date.UTC(y, 11, 31))
    : now
  const d = new Date(Date.UTC(y, 0, 1))
  while (d <= lastDay) {
    out.push(`${y}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`)
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return out
}

// One combined option: CDP1 + CDP2 calendars + one shared PIECEWISE visualMap.
function buildOption() {
  const startDate = `${year.value}-01-01`
  const endDate = `${year.value}-12-31`
  const byIndex = (i) => (cdps.value[i]?.days || []).map((r) => [r.day, r.downtime_minutes])

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
    // Piecewise visualMap (no slider): fixed downtime buckets.
    visualMap: {
      type: 'piecewise',
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      textStyle: { color: '#94a3b8', fontSize: 10 },
      pieces: [
        { value: 0, label: '0', color: '#0f172a' },
        { lte: 59, min: 1, label: '1–59', color: '#fca5a5' },      // light red
        { lte: 359, min: 60, label: '60–359', color: '#ef4444' },  // medium red
        { min: 360, label: '360+', color: '#7f1d1d' },             // dark red
      ],
    },
    calendar: [
      {
        top: 16,
        left: 34,
        right: 16,
        bottom: '52%',
        cellSize: ['auto', 14],
        range: [startDate, endDate],
        splitLine: { lineStyle: { color: '#1e293b' } },
        itemStyle: { color: '#0b1220', borderWidth: 0 },
        yearLabel: { show: false },
        dayLabel: { color: '#94a3b8', fontSize: 9 },
        monthLabel: { color: '#64748b', fontSize: 10 },
      },
      {
        top: '54%',
        left: 34,
        right: 16,
        bottom: 32,
        cellSize: ['auto', 14],
        range: [startDate, endDate],
        splitLine: { lineStyle: { color: '#1e293b' } },
        itemStyle: { color: '#0b1220', borderWidth: 0 },
        yearLabel: { show: false },
        dayLabel: { color: '#94a3b8', fontSize: 9 },
        monthLabel: { color: '#64748b', fontSize: 10 },
      },
    ],
    series: [
      {
        name: cdps.value[0]?.name || 'CDP1',
        type: 'heatmap',
        coordinateSystem: 'calendar',
        calendarIndex: 0,
        data: byIndex(0),
      },
      {
        name: cdps.value[1]?.name || 'CDP2',
        type: 'heatmap',
        coordinateSystem: 'calendar',
        calendarIndex: 1,
        data: byIndex(1),
      },
    ],
  }
}

// ---- Year picker (matches other sections) ----
const yearOpen = ref(false)
const yearPageStart = ref(Y_MIN)
const years = new Array(Y_MAX - Y_MIN + 1).fill(0).map((_, i) => Y_MIN + i)
function yearPage() {
  return years.slice(yearPageStart.value - Y_MIN, yearPageStart.value - Y_MIN + 8)
}
function navYearPage(delta) {
  const idx = yearPageStart.value - Y_MIN + delta * 8
  yearPageStart.value = Math.max(Y_MIN, Math.min(Y_MAX - 7, Y_MIN + idx))
}
function pickYear(y) {
  year.value = y
  yearOpen.value = false
  load()
}

onMounted(() => {
  load()
  // Auto-refresh so newly persisted connectivity updates the heatmaps.
  timer = setInterval(load, 30_000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-semibold uppercase tracking-wide text-slate-400">Downtime Map</h3>
      <div class="relative">
        <button class="rounded bg-runway-dark px-2 py-1 text-slate-200" @click="yearOpen = !yearOpen">
          {{ year }} ▾
        </button>
        <div v-if="yearOpen" class="absolute right-0 top-full z-30 mt-1 w-32 rounded-md border border-runway-border bg-runway-panel p-2 shadow-xl">
          <div class="mb-1 flex items-center justify-between">
            <button class="px-1 text-slate-400 hover:text-white" @click="navYearPage(-1)">‹</button>
            <span class="text-xs font-semibold text-slate-200">{{ yearPageStart }}–{{ Math.min(yearPageStart + 7, Y_MAX) }}</span>
            <button class="px-1 text-slate-400 hover:text-white" :disabled="yearPageStart + 8 > Y_MAX" @click="navYearPage(1)">›</button>
          </div>
          <div class="grid grid-cols-2 gap-0.5">
            <button
              v-for="y in yearPage()"
              :key="y"
              class="rounded px-1 py-1 text-[11px] transition-colors"
              :class="year === y ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-runway-dark'"
              @click="pickYear(y)"
            >
              {{ y }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="py-12 text-center text-xs text-slate-500">Loading…</div>
    <div v-else class="panel">
      <!-- One combined chart: CDP1 (top) + CDP2 (bottom), shared piecewise legend -->
      <EChart :option="buildOption()" height="460px" />
    </div>
  </div>
</template>