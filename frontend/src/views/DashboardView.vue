<script setup>
import { api } from '@/api/client'
import { computed, onBeforeUnmount, onMounted, onUnmounted, ref } from 'vue'
import { formatDateTime } from '@/utils/timezone'
import { buildUptimeStateMapOption } from '@/utils/chart'
import { currentPeriod } from '@/utils/period'
import EChart from '@/components/EChart.vue'
import PeriodPicker from '@/components/PeriodPicker.vue'

// Independent period pickers.
const slaPeriod = ref(currentPeriod('monthly'))   // SLA/OLA section
const cdpPeriod = ref(currentPeriod('weekly'))    // CDP Uptime section

// SLA/OLA history keeps its own dropdown (bucket/span) — independent.
const bucket = ref('daily')
const span = ref('month')

const live = ref(null)          // /status/overview (real-time)
const slaOla = ref(null)        // /sla-ola/summary (historical)
const history = ref([])
const connectivity = ref({})   // cdp_id -> samples[]
const timer = ref(null)
const error = ref(null)
const tzTick = ref(0)
function onTzChange() { tzTick.value++ }
onMounted(() => window.addEventListener('tzchange', onTzChange))
onBeforeUnmount(() => window.removeEventListener('tzchange', onTzChange))

// ---- Live SLA/OLA (only when the historical summary is unavailable) ----
const liveSla = computed(() => {
  const nodes = live.value?.cdp_nodes || []
  if (!nodes.length) return null
  const vals = nodes.map((n) => (n.status === 'online' ? 100 : 0))
  return vals.reduce((a, b) => a + b, 0) / vals.length
})

const liveOla = computed(() => {
  const sites = live.value?.sites || []
  if (!sites.length) return null
  const vals = sites.map((s) =>
    s.total_sensors ? (s.online_sensors / s.total_sensors) * 100 : 0,
  )
  return vals.reduce((a, b) => a + b, 0) / vals.length
})

// For the chosen period: whenever the historical summary exists we use its
// values even if 0 (no data in period = DOWN, as agreed). Only fall back to
// the live snapshot when the summary endpoint is unavailable.
const slaPct = computed(() => (slaOla.value ? slaOla.value.sla_pct : liveSla.value))
const olaPct = computed(() => (slaOla.value ? slaOla.value.ola_pct : liveOla.value))

const cdps = computed(() => live.value?.cdp_nodes || slaOla.value?.cdp_uptime || [])
const sites = computed(() => {
  const liveSites = (live.value?.sites || []).map((s) => ({
    site_id: s.id,
    slug: s.slug,
    code: s.code,
    name: s.name,
    data_availability_pct: s.total_sensors
      ? (s.online_sensors / s.total_sensors) * 100
      : 0,
    sensors: s.sensors || [],
  }))
  if (liveSites.length) return liveSites
  return slaOla.value?.sites || []
})

// UPTIME HISTORY state-map follows the CDP Uptime period picker.
const cdpStateMaps = computed(() => {
  const end = cdpPeriod.value.end
  const start = cdpPeriod.value.start
  const maps = {}
  for (const c of cdps.value) {
    const id = c.cdp_id ?? c.id
    const samples = (connectivity.value[id] || []).map((s) => ({
      time: s.time,
      reachable: s.reachable === true,
    }))
    maps[id] = {
      option: buildUptimeStateMapOption({ samples, startIso: start, endIso: end }),
      has: samples.length > 0,
    }
  }
  return maps
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

async function loadCdpConnectivity() {
  try {
    const nodes = live.value?.cdp_nodes || []
    const hours = Math.max(1, Math.ceil((new Date(cdpPeriod.value.end) - new Date(cdpPeriod.value.start)) / 3600000))
    const entries = await Promise.all(
      nodes.map(async (c) => {
        const id = c.cdp_id ?? c.id
        const data = await api.getCdpConnectivity(id, hours).catch(() => ({ samples: [] }))
        return [id, data.samples || []]
      }),
    )
    connectivity.value = Object.fromEntries(entries)
  } catch {
    connectivity.value = {}
  }
}

function onSlaPeriod() { loadSummary() }
function onCdpPeriod() { loadCdpConnectivity() }

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
    error.value = null
  } catch (e) {
    error.value = e.message
  }
}

async function loadAll() {
  await loadSummary()
  await loadCdpConnectivity()
}

onMounted(() => {
  loadAll()
  timer.value = setInterval(loadAll, 30_000)
})
onUnmounted(() => clearInterval(timer.value))
</script>

<template>
  <div class="space-y-6">
    <p v-if="error" class="rounded bg-red-500/10 px-3 py-2 text-xs text-red-400">{{ error }}</p>

    <!-- SLA & OLA percentages (own period picker) -->
    <section>
      <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400">SLA / OLA</h2>
        <PeriodPicker v-model="slaPeriod" @update:model-value="onSlaPeriod" />
      </div>
      <div class="grid gap-4 md:grid-cols-2">
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

    <!-- CDP Uptime cards + uptime history (own period picker) -->
    <section>
      <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400">CDP Uptime</h2>
        <PeriodPicker v-model="cdpPeriod" @update:model-value="onCdpPeriod" />
      </div>
      <div class="grid gap-4 md:grid-cols-2">
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
        <div v-if="!cdps.length" class="panel text-center text-sm text-slate-500">No CDP nodes configured</div>
      </div>

      <!-- UPTIME HISTORY: untouched for now -->
      <div v-if="cdps.length" class="mt-4">
        <h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Uptime History ({{ cdpPeriod.label }})
        </h3>
        <div class="grid gap-4 md:grid-cols-2">
          <div v-for="c in cdps" :key="'map-' + (c.cdp_id ?? c.id)" class="panel">
            <div class="mb-1 flex items-center justify-between">
              <span class="font-mono text-xs font-semibold text-slate-200">{{ c.name }}</span>
              <span class="text-xs text-slate-400">{{ c.ip_address || c.ip }}</span>
            </div>
            <EChart
              v-if="cdpStateMaps[c.cdp_id ?? c.id]?.has"
              :option="cdpStateMaps[c.cdp_id ?? c.id].option"
              height="90px"
            />
            <div v-else class="flex h-[90px] items-center justify-center text-xs text-slate-500">
              No history yet — run Backfill CDP uptime
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Sites (Data Availability, live sensor health) -->
    <section>
      <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">Sites — Data Availability</h2>
      <div class="grid gap-4 md:grid-cols-3">
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
        <div v-if="!sites.length" class="panel text-center text-sm text-slate-500">No sites configured</div>
      </div>
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