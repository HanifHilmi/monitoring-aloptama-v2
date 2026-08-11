<script setup>
import { api } from '@/api/client'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import EChart from '@/components/EChart.vue'
import { buildDualAxisOption } from '@/utils/chart'

const props = defineProps({
  sensor: { type: Object, required: true },
  siteSlug: { type: String, required: true },
  range: { type: String, default: '24h' },
  win: { type: Object, default: null },
})

const metrics = ref({})   // metric -> points[]
const loading = ref(false)
const error = ref(null)
const refreshTick = ref(0)
let pollTimer = null

// Rolling window: keep the picker's start, but roll END to 'now' each poll
// so new /oneminute rows (past the originally-pinned end) appear live.
const liveWin = ref(props.win ? { ...props.win } : null)

const chartMetrics = computed(() => {
  const list = (props.sensor.chart_metrics || '').split(',').map((m) => m.trim()).filter(Boolean)
  // Defaults per sensor code when chart_metrics not populated yet.
  if (!list.length) {
    const byCode = {
      ATRH: ['TEMP', 'DEWP', 'RH'], BARO: ['QNH', 'DA'], ANEM: ['WS', 'WD'],
      PWX: ['PW', 'RA'], CEL: ['LR1', 'SKY'], RVR: ['RVR', 'VIS'],
      RAIN: ['RA'], SOLR: ['SOL'], LIGH: ['LTX'],
    }
    return byCode[props.sensor.code] || []
  }
  return list
})

async function load() {
  // Keep the current chart on screen while refreshing: only show the
  // spinner on the VERY FIRST load, and NEVER clear existing metrics so
  // the graph stays mounted across refreshes.
  const first = !hasData()
  if (first) loading.value = true
  error.value = null
  try {
    const all = await Promise.all(
      chartMetrics.value.map(async (m) => {
        try {
          const d = await api.getTelemetry(props.siteSlug, props.sensor.code, props.range, 1500, m, liveWin.value)
          return [m, d.series || d.points || d.samples || []]  // v2: series[]
        } catch {
          return [m, metrics.value[m] || []]  // keep last-known on error
        }
      }),
    )
    const merged = {}
    for (const [m, pts] of all) merged[m] = pts.length ? pts : (metrics.value[m] || [])
    metrics.value = merged
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function hasData() {
  return chartMetrics.value.some((m) => (metrics.value[m] || []).length > 0)
}

const isState = computed(() => props.sensor.is_state === true || props.sensor.code === 'DCP')

// DCP: status comes from the backend /status/overview (online when at
// least one other component on the site has fresh data). The overview may
// be missing the flag pre-migration; fall back to 'any chart metric data'.
const dcpOnline = computed(() => {
  if (!isState.value) return null
  if (props.sensor.status) return props.sensor.status === 'ok'
  return chartMetrics.value.length === 0
    ? false
    : chartMetrics.value.some((m) => (metrics.value[m] || []).length > 0)
})

// Per-metric display metadata: axis side + unit.
const METRIC_META = {
  TEMP: { ax: 0, unit: '°C' }, DEWP: { ax: 0, unit: '°C' }, RH: { ax: 1, unit: '%' },
  QNH: { ax: 0, unit: 'hPa' }, DA: { ax: 1, unit: 'ft' },
  WS: { ax: 0, unit: 'kt' }, WD: { ax: 1, unit: 'deg' }, WGS: { ax: 1, unit: 'kt' },
  RVR: { ax: 0, unit: 'm' }, VIS: { ax: 1, unit: 'm' }, ALS: { ax: 1, unit: 'cd' },
  RA: { ax: 0, unit: 'mm' }, PW: { ax: 0, unit: '' }, LR1: { ax: 0, unit: '100ft' },
  SKY: { ax: 1, unit: '' }, SOL: { ax: 0, unit: 'W/m2' }, LTX: { ax: 0, unit: '' },
}
const COLORS = ['#38bdf8', '#a78bfa', '#34d399', '#fbbf24', '#f472b6', '#fb7185']

const chartOption = computed(() => {
  const win = liveWin.value || props.win || {}
  const xMin = win.start || undefined
  const xMax = win.end || undefined

  const axisNames = ['', '']
  for (const m of chartMetrics.value) {
    const meta = METRIC_META[m] || { ax: 0, unit: '' }
    if (meta.ax >= 0 && !axisNames[meta.ax]) {
      axisNames[meta.ax] = m === 'TEMP' ? '°C' : (m === 'DEWP' ? '°C' : (meta.unit || m))
    }
  }

  const yAxis = [
    { type: 'value', scale: true, name: axisNames[0] || 'value', axisLabel: { color: '#64748b', fontSize: 11 }, splitLine: { lineStyle: { color: 'rgba(148,163,184,0.12)' } } },
    { type: 'value', scale: true, name: axisNames[1] || undefined, axisLabel: { color: '#64748b', fontSize: 11 }, splitLine: { show: false } },
  ]

  const series = chartMetrics.value.map((m, i) => {
    const meta = METRIC_META[m] || { ax: 0, unit: '' }
    const color = COLORS[i % COLORS.length]
    // samples: [{time, value, is_valid}]
    const data = (metrics.value[m] || [])
      .filter((p) => p && typeof p.value === 'number')
      .map((p) => [p.time, p.value])
    return {
      name: meta.unit ? `${m} (${meta.unit})` : m,
      type: 'line',
      yAxisIndex: meta.ax,
      showSymbol: false,
      data,
      lineStyle: { width: 1.5, color },
      itemStyle: { color },
      connectNulls: false,
    }
  })

  return {
    animation: true,
    grid: { left: 12, right: 16, top: 24, bottom: 0, containLabel: true },
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#94a3b8' }, top: 0, type: 'scroll' },
    xAxis: { type: 'time', min: xMin, max: xMax, axisLabel: { color: '#64748b', fontSize: 11 } },
    yAxis,
    series,
  }
})

// Wind gust stats for ANEM (WGS max + its direction in range).
const gustStats = computed(() => {
  if (props.sensor.code !== 'ANEM') return null
  const wgs = metrics.value['WGS'] || []
  const wgd = metrics.value['WGD'] || []
  if (!wgs.length) return null
  let max = -Infinity, at = null
  for (const p of wgs) if (p.value != null && p.value > max) { max = p.value; at = p }
  const d = at ? (wgd.find((q) => q.time === at.time) || {}).value : null
  return { max, direction: d, count: wgs.filter((p) => p.value != null && p.value > 0).length }
})

watch(() => [props.range, props.sensor.id, props.win?.start, props.win?.end], () => {
  if (props.win) liveWin.value = { ...props.win }
  load()
}, { deep: true })
load()  // ALWAYS load — never skip data fetching for any component

// Auto-refresh every 15s so the graph advances with the 1-minute /oneminute
// cadence. load() no longer clears metrics, and refreshTick++ forces EChart
// to re-render even if the option identity is unchanged.
async function poll() {
  // Roll the window END to the current time so the query returns rows up
  // to NOW (previously it was pinned to the picker-time end -> froze).
  if (liveWin.value) {
    liveWin.value = { ...liveWin.value, end: new Date().toISOString() }
  }
  await load()
  refreshTick.value++
}
pollTimer = setInterval(poll, 15_000)
onBeforeUnmount(() => clearInterval(pollTimer))
</script>

<template>
  <div class="panel">
    <!-- Header -->
    <div class="mb-2 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span class="font-semibold text-slate-200">{{ sensor.name }}</span>
        <span class="rounded bg-runway-dark px-1.5 py-0.5 text-[10px] text-slate-400">{{ chartMetrics.join(' + ') }}</span>
      </div>
      <span
        class="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px]"
        :class="sensor.status === 'ok' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'"
      >
        <span class="inline-block h-1.5 w-1.5 rounded-full" :class="sensor.status === 'ok' ? 'bg-emerald-400' : 'bg-amber-400'" />
        {{ sensor.status || 'ok' }}
      </span>
    </div>

    <!-- State chip (DCP) — shown alongside, NEVER replaces the graph -->
    <div v-if="isState" class="mb-2 flex items-center gap-2 text-xs">
      <span v-if="dcpOnline" class="font-bold text-emerald-400">● ONLINE</span>
      <span v-else class="font-bold text-red-400">● OFFLINE</span>
      <span class="text-slate-500">Online when ≥1 component has data (not ////)</span>
    </div>

    <!-- Wind gust stats above ANEM graph -->
    <div v-else-if="gustStats" class="mb-2 grid grid-cols-3 gap-2 text-xs">
      <div class="rounded bg-runway-dark px-2 py-1">
        <div class="text-slate-500">Gust Count</div>
        <div class="font-semibold text-slate-200">{{ gustStats.count }}</div>
      </div>
      <div class="rounded bg-runway-dark px-2 py-1">
        <div class="text-slate-500">Max Speed</div>
        <div class="font-semibold text-slate-200">{{ gustStats.max }} kt</div>
      </div>
      <div class="rounded bg-runway-dark px-2 py-1">
        <div class="text-slate-500">Gust Direction</div>
        <div class="font-semibold text-slate-200">{{ gustStats.direction ?? '—' }}°</div>
      </div>
    </div>

    <!-- Combined chart — ALWAYS rendered, no condition may hide it -->
    <div>
      <!-- Loading only while there is NO data yet; once a chart exists it
           stays on screen during refreshes (data merges in place). -->
      <div v-if="loading && !hasData()" class="py-10 text-center text-xs text-slate-500">Loading…</div>
      <div v-else-if="error && !hasData()" class="py-10 text-center text-xs text-red-400">{{ error }}</div>
      <EChart v-else-if="chartMetrics.length" :option="chartOption" :refresh-tick="refreshTick" height="220px" />
      <div v-else class="py-10 text-center text-xs text-slate-500">No chart configured</div>
    </div>
  </div>
</template>