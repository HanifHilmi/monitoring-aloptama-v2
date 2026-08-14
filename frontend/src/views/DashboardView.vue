<script setup>
import { api } from '@/api/client'
import { computed, onBeforeUnmount, onMounted, onUnmounted, ref } from 'vue'
import { formatDateTime } from '@/utils/timezone'
import { currentPeriod } from '@/utils/period'
import DowntimeMap from '@/components/DowntimeMap.vue'
import EChart from '@/components/EChart.vue'
import PeriodPicker from '@/components/PeriodPicker.vue'

// Independent period pickers.
const slaPeriod = ref(currentPeriod('monthly'))   // SLA/OLA section
const cdpPeriod = ref(currentPeriod('weekly'))    // CDP Uptime section

// SLA/OLA history keeps its own dropdown (bucket/span) — independent.
const bucket = ref('daily')
const span = ref('month')

const live = ref(null)          // /status/overview (real-time)
const slaOla = ref(null)        // /sla-ola/summary (historical) - SLA period
const cdpOla = ref(null)        // /sla-ola/summary (historical) - CDP period
const history = ref([])
const timer = ref(null)
const fastTimer = ref(null)
const error = ref(null)
const loadingSla = ref(false)
const loadingCdp = ref(false)

// SLA/OLA come EXCLUSIVELY from the backend /sla-ola/summary which computes
// UP-minutes / period-minutes (missing minute = DOWN). No live fallback:
// online-now must never inflate a period without backfilled data.
const slaPct = computed(() => (slaOla.value ? slaOla.value.sla_pct : null))
const olaPct = computed(() => (slaOla.value ? slaOla.value.ola_pct : null))

// CDP cards show uptime from the CDP-period summary (UP-min/period-min).
const cdps = computed(() => {
  const list = live.value?.cdp_nodes || slaOla.value?.cdp_uptime || []
  return list.map((c) => {
    const id = c.cdp_id ?? c.id
    const sum = (cdpOla.value?.cdp_uptime || []).find((x) => (x.cdp_id ?? x.id) === id)
    return sum ? { ...c, uptime_pct: sum.uptime_pct, downtime_seconds: sum.downtime_seconds } : c
  })
})
// Sites — Data Availability tied to the CDP Uptime period picker
// (cdpOla summary provides period-based %, missing=DOWN). Sensor dots
// come from the live overview so the per-sensor indicators always show.
const sites = computed(() => {
  const liveBySlug = {}
  for (const s of live.value?.sites || []) liveBySlug[s.slug] = s
  const fromHist = (cdpOla.value?.sites || [])
    .map((s) => ({
      site_id: s.site_id ?? s.id,
      slug: s.slug,
      code: s.code,
      name: s.name,
      data_availability_pct: s.data_availability_pct ?? 0,
      sensors: liveBySlug[s.slug]?.sensors || [],
    }))
  if (fromHist.length) return fromHist
  // fallback: live overview (sensor health) when no historical summary yet
  return (live.value?.sites || []).map((s) => ({
    site_id: s.id,
    slug: s.slug,
    code: s.code,
    name: s.name,
    data_availability_pct: s.total_sensors
      ? (s.online_sensors / s.total_sensors) * 100
      : 0,
    sensors: s.sensors || [],
  }))
})

// SLA/OLA history BAR chart driven only by its own dropdowns.
const historyOption = computed(() => {
  const rows = [...history.value].sort((a, b) => a.day.localeCompare(b.day))
  return {
    animation: true,
    grid: { left: 12, right: 16, top: 24, bottom: 0, containLabel: true },
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#94a3b8' }, top: 0 },
    xAxis: { type: 'time', axisLabel: { color: '#64748b', fontSize: 11 } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { color: '#64748b', fontSize: 11, formatter: '{value}%' } },
    series: [
      { name: 'SLA', type: 'bar', data: rows.map((r) => [r.day, r.sla_pct]), itemStyle: { color: '#10b981', opacity: 0.75 } },
      { name: 'OLA', type: 'bar', data: rows.map((r) => [r.day, r.ola_pct]), itemStyle: { color: '#38bdf8', opacity: 0.55 } },
    ],
  }
})

function onSlaPeriod() { loadingSla.value = true; loadSummary() }
function onCdpPeriod() { loadingCdp.value = true; loadSummary() }  // cdpPeriod drives CDP cards + Sites

async function loadSummary() {
  try {
    const [lv, so, h] = await Promise.all([
      api.getStatusOverview(),
      api.getAvailability('custom', slaPeriod.value).catch(() => null),
      api.getAvailabilityHistory(bucket.value, span.value).catch(() => ({ rows: [] })),
    ])
    live.value = lv
    slaOla.value = so
    history.value = h.rows || []
    // CDP-period summary for the CDP Uptime cards (0% when no data).
    cdpOla.value = await api.getAvailability('custom', cdpPeriod.value).catch(() => null)
    error.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    loadingSla.value = false
    loadingCdp.value = false
  }
}

async function loadAll() {
  await loadSummary()
}

// Fast 10s poll: refreshes ONLY the SLA/OLA summary + CDP cards so the
// numbers update live while a CDP backfill streams new rows (the 30s
// loadAll blocks on the heavier history call).
async function loadSummaryFast() {
  try {
    const [lv, so] = await Promise.all([
      api.getStatusOverview(),
      api.getAvailability('custom', slaPeriod.value).catch(() => null),
    ])
    live.value = lv
    slaOla.value = so
  } catch {}
}

onMounted(() => {
  // Show loading fades + placeholders during the FIRST load too, so the
  // page never looks "empty/broken" while the summaries resolve.
  loadingSla.value = true
  loadingCdp.value = true
  loadAll()
  timer.value = setInterval(loadAll, 30_000)
  fastTimer.value = setInterval(loadSummaryFast, 10_000)
})
onUnmounted(() => {
  clearInterval(timer.value)
  clearInterval(fastTimer.value)
})
</script>

<template>
  <div class="space-y-6">
    <p v-if="error" class="rounded bg-red-500/10 px-3 py-2 text-xs text-red-400">{{ error }}</p>

    <!-- SLA & OLA percentages (own period picker) -->
    <section>
      <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400">
          SLA / OLA
          <span v-if="loadingSla" class="ml-2 inline-flex items-center gap-1 text-[11px] font-normal text-sky-400">
            <span class="inline-block h-3 w-3 animate-spin rounded-full border-2 border-sky-400 border-t-transparent"></span>Loading…
          </span>
        </h2>
        <PeriodPicker v-model="slaPeriod" :disabled="loadingSla" @update:model-value="onSlaPeriod" />
      </div>
      <div class="grid gap-4 md:grid-cols-2" :class="{ 'opacity-40 pointer-events-none': loadingSla }">
        <div class="panel">
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-wide text-slate-400">SLA</span>
            <span class="text-[10px] text-slate-500">Avg of CDP1 + CDP2 uptime · {{ slaPeriod.label }}</span>
          </div>
          <div class="mt-1 text-4xl font-bold" :class="(slaPct ?? 0) >= 99 ? 'text-emerald-400' : 'text-amber-400'">
            {{ slaPct === null || slaPct === undefined ? '—' : slaPct.toFixed(2) + '%' }}
          </div>
        </div>
        <div class="panel">
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-wide text-slate-400">OLA</span>
            <span class="text-[10px] text-slate-500">Avg data availability · {{ slaPeriod.label }}</span>
          </div>
          <div class="mt-1 text-4xl font-bold" :class="(olaPct ?? 0) >= 99 ? 'text-emerald-400' : 'text-amber-400'">
            {{ olaPct === null || olaPct === undefined ? '—' : olaPct.toFixed(2) + '%' }}
          </div>
        </div>
      </div>
    </section>

    <!-- CDP Uptime cards (own period picker) -->
    <section>
      <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400">
          CDP Uptime
          <span v-if="loadingCdp" class="ml-2 inline-flex items-center gap-1 text-[11px] font-normal text-sky-400">
            <span class="inline-block h-3 w-3 animate-spin rounded-full border-2 border-sky-400 border-t-transparent"></span>Loading…
          </span>
        </h2>
        <PeriodPicker v-model="cdpPeriod" :disabled="loadingCdp" @update:model-value="onCdpPeriod" />
      </div>
      <div class="grid gap-4 md:grid-cols-2" :class="{ 'opacity-40 pointer-events-none': loadingCdp }">
        <div v-for="c in cdps" :key="c.cdp_id ?? c.id" class="panel">
          <div class="flex items-center justify-between">
            <span class="flex items-center gap-2">
              <span class="inline-block h-2.5 w-2.5 rounded-full" :class="(c.status ?? 'offline') === 'online' ? 'bg-emerald-400' : 'bg-red-400'" />
              <span class="font-mono text-sm font-semibold text-slate-200">{{ c.name }}</span>
            </span>
            <span class="text-xs text-slate-400">{{ c.ip_address || c.ip }}</span>
          </div>
          <div class="mt-2 grid grid-cols-3 gap-2 text-xs">
            <div class="rounded bg-runway-dark px-2 py-1">
              <div class="text-slate-500">Status</div>
              <div class="font-semibold" :class="(c.status ?? 'offline') === 'online' ? 'text-emerald-400' : 'text-red-400'">
                {{ c.status ?? 'offline' }}
              </div>
            </div>
            <div class="rounded bg-runway-dark px-2 py-1">
              <div class="text-slate-500">Uptime</div>
              <div class="font-semibold text-emerald-400">{{ (c.uptime_pct ?? 0).toFixed(2) }}%</div>
            </div>
            <div class="rounded bg-runway-dark px-2 py-1">
              <div class="text-slate-500">Last seen</div>
              <div class="font-semibold text-slate-200">{{ formatDateTime(c.last_seen || c.last_check) }}</div>
            </div>
          </div>
        </div>
        <!-- Greyed placeholders while the CDP summary is still loading -->
        <div v-if="!cdps.length && loadingCdp" v-for="n in 2" :key="'cdp'+n" class="panel animate-pulse">
          <div class="h-3 w-1/3 rounded bg-runway-dark"></div>
          <div class="mt-3 h-8 w-1/2 rounded bg-runway-dark"></div>
        </div>
        <div v-if="!cdps.length && !loadingCdp" class="panel text-center text-sm text-slate-500">No CDP nodes configured</div>
      </div>
    </section>

    <!-- Sites (Data Availability) -->
    <section>
      <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Sites — Data Availability
          <span v-if="loadingCdp" class="ml-2 inline-flex items-center gap-1 text-[11px] font-normal text-sky-400">
            <span class="inline-block h-3 w-3 animate-spin rounded-full border-2 border-sky-400 border-t-transparent"></span>Loading…
          </span>
        </h2>
      </div>
      <div class="grid gap-4 md:grid-cols-3" :class="{ 'opacity-40 pointer-events-none': loadingCdp }">
        <RouterLink v-for="s in sites" :key="s.site_id ?? s.slug" :to="`/runway/${s.slug}`" class="panel transition-colors hover:border-emerald-500/50">
          <div class="flex items-center justify-between">
            <span class="font-semibold text-slate-200">{{ s.name }}</span>
            <span class="text-lg font-bold" :class="(s.data_availability_pct ?? 0) >= 99 ? 'text-emerald-400' : 'text-amber-400'">
              {{ (s.data_availability_pct ?? 0).toFixed(2) }}%
            </span>
          </div>
          <div class="mt-2 flex flex-wrap gap-1">
            <span v-for="sensor in s.sensors || []" :key="sensor.code ?? sensor.id" class="inline-flex items-center gap-1 rounded bg-runway-dark px-1.5 py-0.5 text-[10px] text-slate-300">
              <span class="inline-block h-1.5 w-1.5 rounded-full" :class="(sensor.status ?? '') === 'ok' ? 'bg-emerald-400' : 'bg-amber-400'" />
              {{ sensor.code }}
            </span>
          </div>
        </RouterLink>
        <!-- Greyed placeholders while the CDP summary is still loading -->
        <div v-if="!sites.length && loadingCdp" v-for="n in 3" :key="'site'+n" class="panel animate-pulse">
          <div class="h-3 w-2/3 rounded bg-runway-dark"></div>
          <div class="mt-3 h-6 w-1/2 rounded bg-runway-dark"></div>
          <div class="mt-3 flex gap-1">
            <span class="h-2 w-8 rounded bg-runway-dark"></span><span class="h-2 w-8 rounded bg-runway-dark"></span>
          </div>
        </div>
        <div v-if="!sites.length && !loadingCdp" class="panel text-center text-sm text-slate-500">No sites configured</div>
      </div>
    </section>

    <!-- DOWNTIME MAP: own section, per-CDP ECharts calendar heatmap -->
    <section>
      <DowntimeMap />
    </section>

    <!-- SLA/OLA HISTORY: own dropdown, independent -->
    <section class="panel">
      <div class="mb-2 flex items-center justify-between">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400">SLA / OLA History</h2>
        <div class="flex gap-2">
          <select v-model="bucket" @change="onSlaPeriod" class="rounded border border-runway-border bg-runway-panel px-2 py-1 text-xs text-slate-200">
            <option value="daily">Daily</option><option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option><option value="yearly">Yearly</option>
          </select>
          <select v-model="span" @change="onSlaPeriod" class="rounded border border-runway-border bg-runway-panel px-2 py-1 text-xs text-slate-200">
            <option value="month">In month range</option><option value="year">In year range</option><option value="5year">In 5 year range</option>
          </select>
        </div>
      </div>
      <EChart :option="historyOption" height="240px" />
    </section>
  </div>
</template>