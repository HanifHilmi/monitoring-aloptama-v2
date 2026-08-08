<script setup>
import { api } from '@/api/client'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import EChart from '@/components/EChart.vue'

const range = ref('month')
const bucket = ref('daily')
const span = ref('month')
const live = ref(null)          // /status/overview (real-time)
const slaOla = ref(null)        // /sla-ola/summary (historical)
const history = ref([])
const timer = ref(null)
const error = ref(null)

// ---- Live SLA/OLA (always available from real-time status) ----
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

// Prefer live values; fall back to history summary when available.
const slaPct = computed(() => slaOla.value?.sla_pct ?? liveSla.value)
const olaPct = computed(() => slaOla.value?.ola_pct ?? liveOla.value)

const cdps = computed(() => live.value?.cdp_nodes || slaOla.value?.cdp_uptime || [])
const sites = computed(() => {
  // Real-time site sensor health from /status/overview.
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
      { name: 'SLA', type: 'line', showSymbol: false, data: rows.map((r) => [r.day, r.sla_pct]), lineStyle: { color: '#10b981' }, itemStyle: { color: '#10b981' } },
      { name: 'OLA', type: 'line', showSymbol: false, data: rows.map((r) => [r.day, r.ola_pct]), lineStyle: { color: '#38bdf8' }, itemStyle: { color: '#38bdf8' } },
    ],
  }
})

async function load() {
  try {
    const [lv, so, h] = await Promise.all([
      api.getStatusOverview(),
      api.getAvailability(range.value).catch(() => null),
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

onMounted(() => {
  load()
  timer.value = setInterval(load, 15_000)  // real-time refresh
})
onUnmounted(() => clearInterval(timer.value))
</script>

<template>
  <div class="space-y-6">
    <p v-if="error" class="rounded bg-red-500/10 px-3 py-2 text-xs text-red-400">{{ error }}</p>

    <!-- Row 1: SLA & OLA percentages (live) -->
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold text-slate-200">SLA/OLA</h1>
      <span class="text-xs text-slate-500">Live · refreshes every 15s</span>
    </div>
    <div class="grid gap-4 md:grid-cols-2">
      <div class="panel">
        <div class="flex items-center justify-between">
          <span class="text-xs uppercase tracking-wide text-slate-400">SLA</span>
          <span class="text-[10px] text-slate-500">Avg of CDP1 + CDP2 uptime</span>
        </div>
        <div class="mt-1 text-4xl font-bold" :class="(slaPct ?? 0) >= 99 ? 'text-emerald-400' : 'text-amber-400'">
          {{ slaPct === null ? '—' : slaPct.toFixed(2) + '%' }}
        </div>
      </div>
      <div class="panel">
        <div class="flex items-center justify-between">
          <span class="text-xs uppercase tracking-wide text-slate-400">OLA</span>
          <span class="text-[10px] text-slate-500">Avg data availability of 3 runway sites</span>
        </div>
        <div class="mt-1 text-4xl font-bold" :class="(olaPct ?? 0) >= 99 ? 'text-emerald-400' : 'text-amber-400'">
          {{ olaPct === null ? '—' : olaPct.toFixed(2) + '%' }}
        </div>
      </div>
    </div>

    <!-- Row 3: CDP Uptime & Downtime (live, always renders) -->
    <section>
      <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">CDP Uptime</h2>
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
              <div class="font-semibold text-slate-200">{{ c.last_seen || c.last_check ? new Date(c.last_seen || c.last_check).toLocaleTimeString() : '—' }}</div>
            </div>
          </div>
        </div>
        <div v-if="!cdps.length" class="panel text-center text-sm text-slate-500">No CDP nodes configured</div>
      </div>
    </section>

    <!-- Row 4: Sites (Data Availability, live sensor health) -->
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

    <!-- History graph (non-blocking; empty when no backfill yet) -->
    <section class="panel" v-if="history.length">
      <div class="mb-2 flex items-center justify-between">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400">SLA / OLA History</h2>
        <div class="flex gap-2">
          <select v-model="bucket" @change="load" class="rounded border border-runway-border bg-runway-panel px-2 py-1 text-xs text-slate-200">
            <option value="daily">Daily</option><option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option><option value="yearly">Yearly</option>
          </select>
          <select v-model="span" @change="load" class="rounded border border-runway-border bg-runway-panel px-2 py-1 text-xs text-slate-200">
            <option value="month">In month range</option><option value="year">In year range</option><option value="5year">In 5 year range</option>
          </select>
        </div>
      </div>
      <EChart :option="historyOption" height="240px" />
    </section>
  </div>
</template>