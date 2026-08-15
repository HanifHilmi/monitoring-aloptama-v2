<script setup>
import { api } from '@/api/client'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import EChart from '@/components/EChart.vue'
import { buildStringStateOption, buildStringHistogramOption } from '@/utils/chart'

const props = defineProps({
  sensor: { type: Object, required: true },
  siteSlug: { type: String, required: true },
  range: { type: String, default: '24h' },
  win: { type: Object, default: null },
})

const metrics = ref({})    // numeric: alias -> [{time, value}]
const textData = ref({})   // string: alias -> { transitions, counts }
const loading = ref(false)
const error = ref(null)
const refreshTick = ref(0)
let pollTimer = null

// Rolling window: keep the picker's start, but roll END to 'now' each poll
// so new /oneminute rows (past the originally-pinned end) appear live.
const liveWin = ref(props.win ? { ...props.win } : null)

const WIDE_COL = {
  TEMP: 'temp_c', DEWP: 'dewp_c', RH: 'rh_pct', QNH: 'qnh_hpa', DA: 'da_ft',
  WS: 'wind_speed_kt', WD: 'wind_dir_deg', WGS: 'gust_speed_kt', WGD: 'gust_dir_deg',
  RVR: 'rvr_m', VIS: 'vis_m', ALS: 'als_cd', 'D/N': 'als_dn',
  LR1: 'lr1_100ft', SKY: 'sky_condition', RA: 'precip_mm', PW: 'present_weather',
  SOL: 'solar_wm2', LTX: 'lightning',
}

// aliases whose underlying awos_metrics column holds TEXT (categorical) data.
const TEXT_COL = { als_dn: 'D/N', sky_condition: 'SKY', present_weather: 'PW', lightning: 'LTX' }

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

const numericMetrics = computed(() =>
  chartMetrics.value.filter((m) => !(WIDE_COL[m] && TEXT_COL[WIDE_COL[m]])),
)
const stringMetrics = computed(() =>
  chartMetrics.value.filter((m) => WIDE_COL[m] && TEXT_COL[WIDE_COL[m]]),
)

const isState = computed(() => props.sensor.is_state === true || props.sensor.code === 'DCP')

async function load() {
  if (isState.value) return  // state sensors (DCP) show a status chip, no chart
  const first = !hasData()
  if (first) loading.value = true
  error.value = null
  try {
    const aliases = chartMetrics.value
    const wide = await api.getWideTelemetry(props.siteSlug, aliases, liveWin.value, props.range)
    const merged = {}
    for (const m of aliases) {
      const col = WIDE_COL[m] || m
      merged[m] = (wide.series?.[col] || []).map((p) => ({ time: p.time, value: p.value }))
    }
    for (const m of aliases) if (!merged[m].length && metrics.value[m]) merged[m] = metrics.value[m]
    metrics.value = merged

    const td = {}
    for (const m of stringMetrics.value) {
      const col = WIDE_COL[m]
      td[m] = {
        transitions: wide.textSeries?.[col] || [],
        counts: wide.textCounts?.[col] || [],
      }
    }
    if (Object.keys(td).length) textData.value = td
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function hasData() {
  return numericMetrics.value.some((m) => (metrics.value[m] || []).length > 0) ||
    stringMetrics.value.some((m) => {
      const d = textData.value[m]
      return d && ((d.transitions && d.transitions.length) || (d.counts && d.counts.length))
    })
}

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
  RA: { ax: 0, unit: 'mm' }, LR1: { ax: 0, unit: '100ft' },
  SOL: { ax: 0, unit: 'W/m2' },
}
const COLORS = ['#38bdf8', '#a78bfa', '#34d399', '#fbbf24', '#f472b6', '#fb7185']

const chartOption = computed(() => {
  const win = liveWin.value || props.win || {}
  const xMin = win.start || undefined
  const xMax = win.end || undefined

  const axisNames = ['', '']
  for (const m of numericMetrics.value) {
    const meta = METRIC_META[m] || { ax: 0, unit: '' }
    if (meta.ax >= 0 && !axisNames[meta.ax]) {
      axisNames[meta.ax] = m === 'TEMP' ? '°C' : (m === 'DEWP' ? '°C' : (meta.unit || m))
    }
  }

  const yAxis = [
    { type: 'value', scale: true, name: axisNames[0] || 'value', nameGap: 6, nameTextStyle: { color: '#94a3b8', fontSize: 10 }, axisLabel: { color: '#64748b', fontSize: 11 }, splitLine: { lineStyle: { color: 'rgba(148,163,184,0.12)' } } },
    { type: 'value', scale: true, name: axisNames[1] || undefined, nameGap: 6, nameTextStyle: { color: '#94a3b8', fontSize: 10 }, axisLabel: { color: '#64748b', fontSize: 11 }, splitLine: { show: false } },
  ]

  const series = numericMetrics.value.map((m, i) => {
    const meta = METRIC_META[m] || { ax: 0, unit: '' }
    const color = COLORS[i % COLORS.length]
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
    grid: { left: 48, right: 16, top: 24, bottom: 0, containLabel: true },
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#94a3b8' }, top: 0, type: 'scroll' },
    xAxis: { type: 'time', min: xMin, max: xMax, axisLabel: { color: '#64748b', fontSize: 11 } },
    yAxis,
    series,
  }
})

// String/categorical charts: state strip when few distinct values (e.g. D/N),
// otherwise a minutes-per-value histogram (weather codes, sky, lightning).
const stringCharts = computed(() => {
  const win = liveWin.value || props.win || {}
  const out = []
  for (const m of stringMetrics.value) {
    const d = textData.value[m]
    if (!d) continue
    const transitions = d.transitions || []
    const counts = d.counts || []
    if (!transitions.length && !counts.length) continue
    let option
    let height
    if (counts.length <= 6) {
      option = buildStringStateOption({
        transitions,
        startIso: win.start,
        endIso: win.end,
        name: m,
      })
      height = '104px'
    } else {
      const bars = Math.min(counts.length, 8) + (counts.length > 8 ? 1 : 0)
      option = buildStringHistogramOption({ counts, name: m })
      height = `${48 + bars * 18}px`
    }
    out.push({ alias: m, option, height })
  }
  return out
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
load()

// Auto-refresh every 15s so the graph advances with the 1-minute /oneminute
// cadence. load() no longer clears metrics, and refreshTick++ forces EChart
// to re-render even if the option identity is unchanged.
async function poll() {
  // Roll the window END to the current time only for relative (preset)
  // ranges so live graphs keep advancing. A custom range pins an explicit
  // end (e.g. a historical month) and must NOT drift to today.
  if (liveWin.value && props.range !== 'custom') {
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

    <!-- Charts -->
    <div>
      <div v-if="loading && !hasData()" class="py-10 text-center text-xs text-slate-500">Loading…</div>
      <div v-else-if="error && !hasData()" class="py-10 text-center text-xs text-red-400">{{ error }}</div>
      <template v-else>
        <!-- Numeric trend chart (kept for ATRH/BARO/ANEM/RAIN/SOLR + numeric half of mixed sensors) -->
        <EChart v-if="numericMetrics.length" :option="chartOption" :refresh-tick="refreshTick" height="220px" />

        <!-- String/categorical chart(s) added to the same card -->
        <div v-for="sc in stringCharts" :key="sc.alias" class="mt-2">
          <div class="mb-1 text-[10px] uppercase tracking-wide text-slate-500">{{ sc.alias }}</div>
          <EChart :option="sc.option" :height="sc.height" />
        </div>

        <div v-if="!numericMetrics.length && !stringMetrics.length && !isState" class="py-10 text-center text-xs text-slate-500">No chart configured</div>
      </template>
    </div>
  </div>
</template>
