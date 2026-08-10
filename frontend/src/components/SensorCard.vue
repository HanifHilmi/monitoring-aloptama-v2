<script setup>
import { api } from '@/api/client'
import { computed, ref, watch } from 'vue'
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
  loading.value = true
  error.value = null
  try {
    const all = await Promise.all(
      chartMetrics.value.map(async (m) => {
        try {
          const d = await api.getTelemetry(props.siteSlug, props.sensor.code, props.range, 1500, m, props.win)
          return [m, d.points || d.samples || []]
        } catch {
          return [m, []]
        }
      }),
    )
    metrics.value = Object.fromEntries(all)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
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

const chartOption = computed(() => {
  const code = props.sensor.code
  const pts = {}
  for (const m of chartMetrics.value) pts[m] = metrics.value[m] || []

  const win = props.win || {}
  const xMin = win.start || undefined
  const xMax = win.end || undefined

  // Combined series option from a list of {metric, unit, color, yAxis?}
  const colors = ['#38bdf8', '#a78bfa', '#34d399', '#fbbf24', '#f472b6', '#fb7185']
  const series = []
  const yAxis = [{ type: 'value', scale: true, name: 'value', axisLabel: { color: '#64748b', fontSize: 11 }, splitLine: { lineStyle: { color: 'rgba(148,163,184,0.12)' } } }, { type: 'value', scale: true, axisLabel: { color: '#64748b', fontSize: 11 }, splitLine: { show: false } }]
  chartMetrics.value.forEach((m, i) => {
    series.push({
      name: m,
      type: 'line',
      yAxisIndex: i >= 2 ? 1 : 0,
      showSymbol: false,
      data: (pts[m] || []).map((p) => [p.time, p.value]),
      lineStyle: { width: 1.5, color: colors[i % colors.length] },
      itemStyle: { color: colors[i % colors.length] },
      connectNulls: false,
    })
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

watch(() => [props.range, props.sensor.id, props.win?.start, props.win?.end], load, { deep: true })
load()  // ALWAYS load — never skip data fetching for any component
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
      <div v-if="loading" class="py-10 text-center text-xs text-slate-500">Loading…</div>
      <div v-else-if="error" class="py-10 text-center text-xs text-red-400">{{ error }}</div>
      <EChart v-else-if="chartMetrics.length" :option="chartOption" height="220px" />
      <div v-else class="py-10 text-center text-xs text-slate-500">No chart configured</div>
    </div>
  </div>
</template>