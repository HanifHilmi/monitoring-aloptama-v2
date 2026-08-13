<script setup>
import { api } from '@/api/client'
import EChart from '@/components/EChart.vue'
import { buildSlaTimelineOption } from '@/utils/chart'
import { fmtDateTime, fmtDuration, fmtUptime } from '@/utils/format'
import { computed, onMounted, ref, watch } from 'vue'

const props = defineProps({
  initialScope: { type: String, default: 'ola' },
})

const range = ref('30d')
const summary = ref(null)
const daily = ref([])
const scope = ref(props.initialScope)
const entityKey = ref('')
const events = ref([])
const loadingDaily = ref(false)
const loadingSummary = ref(false)
const loadingEvents = ref(false)

const entityOptions = computed(() => {
  const rows = summary.value?.rows || []
  return rows
    .filter((r) => r.scope === scope.value)
    .map((r) => ({
      key: `${r.entity_type}:${r.entity_id}`,
      label: `${r.scope.toUpperCase()} — ${r.entity}`,
      entity_type: r.entity_type,
      entity_id: r.entity_id,
    }))
})

const selected = computed(() => entityOptions.value.find((o) => o.key === entityKey.value) || entityOptions.value[0])

const dailyChartOption = computed(() => {
  const rows = [...daily.value].sort((a, b) => new Date(a.day) - new Date(b.day))
  return {
    animation: false,
    grid: { left: 12, right: 16, top: 24, bottom: 0, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0b1220',
      borderColor: '#1e2a45',
      textStyle: { color: '#e2e8f0', fontSize: 12 },
      formatter: (params) => {
        const p = params[0]
        return `${p.name}<br/>Uptime: ${p.value}%<br/>Downtime: ${p.data.downtime}s`
      },
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: '#64748b' } },
      axisLabel: { color: '#64748b', fontSize: 11 },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      min: 90,
      max: 100,
      axisLabel: { color: '#64748b', fontSize: 11, formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.12)' } },
    },
    series: [
      {
        type: 'bar',
        data: rows.map((r) => ({
          value: r.uptime_pct,
          downtime: r.downtime_seconds,
          itemStyle: { color: r.uptime_pct >= 99.9 ? '#10b981' : r.uptime_pct >= 99 ? '#38bdf8' : '#ef4444' },
        })),
        barWidth: '60%',
      },
    ],
  }
})

const refMap = ref({})

const slaChartOption = computed(() => {
  const connectivity = refMap.value[selected.value?.entity_id]
  const samples = connectivity?.samples || []
  if (!samples.length) return null
  const end = new Date().toISOString()
  const start = new Date(Date.now() - Number(range.value.replace('d', '')) * 24 * 3600 * 1000).toISOString()
  return buildSlaTimelineOption({ samples, startIso: start, endIso: end })
})

async function loadSummary() {
  if (summary.value) loadingSummary.value = true
  try {
  summary.value = await api.getSlaOlaSummary(range.value)
  if (!selected.value) return
  await Promise.all([loadDaily(), loadEvents()])
  } finally { loadingSummary.value = false }
}

async function loadDaily() {
  if (!selected.value) return
  loadingDaily.value = true
  try {
    const days = range.value === '7d' ? 7 : range.value === '24h' ? 1 : 30
    const data = await api.getDailyRollup(scope.value, selected.value.entity_type, selected.value.entity_id, days)
    daily.value = data.rows || []
  } catch {
    daily.value = []
  } finally {
    loadingDaily.value = false
  }
}

async function loadEvents() {
  if (!selected.value) return
  loadingEvents.value = true
  try {
    const data = await api.getDowntimeEvents(scope.value, null, null, 200)
    events.value = (data.events || []).filter((e) => {
      if (scope.value === 'sla') return e.cdp_id === selected.value.entity_id
      return e.sensor_id === selected.value.entity_id
    })
  } catch {
    events.value = []
  } finally {
    loadingEvents.value = false
  }
}

async function loadConnectivity() {
  if (scope.value !== 'sla') return
  refMap.value = {}
  const rows = summary.value?.rows || []
  for (const r of rows.filter((x) => x.scope === 'sla')) {
    try {
      const data = await api.getCdpConnectivity(r.entity_id, 24)
      refMap.value[r.entity_id] = data
    } catch {
      refMap.value[r.entity_id] = null
    }
  }
}

watch(range, async () => { await loadSummary() })
watch([scope, entityKey, range], async () => {
  if (!selected.value) return
  await Promise.all([loadDaily(), loadEvents()])
  if (scope.value === 'sla') await loadConnectivity()
})

watch(scope, async () => {
  const first = entityOptions.value[0]
  entityKey.value = first?.key || ''
})

onMounted(loadSummary)
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold text-slate-200">SLA / OLA</h1>
      <div class="flex gap-2">
        <select v-model="scope" class="rounded border border-runway-border bg-runway-panel px-3 py-1.5 text-sm text-slate-200 focus:outline-none">
          <option value="sla">SLA (CDP)</option>
          <option value="ola">OLA (Sensors)</option>
        </select>
        <select v-model="range" class="rounded border border-runway-border bg-runway-panel px-3 py-1.5 text-sm text-slate-200 focus:outline-none">
          <option value="24h">24h</option>
          <option value="7d">7d</option>
          <option value="30d">30d</option>
        </select>
      </div>
    </div>

    <!-- Summary cards -->
    <div v-if="summary" class="relative">
      <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3" :class="{ 'opacity-40 pointer-events-none': loadingSummary }">
      <div v-for="row in summary.rows.filter((r) => r.scope === scope)" :key="row.entity_id" class="panel" :class="{ 'ring-1 ring-emerald-500/40': selected?.entity_id === row.entity_id }">
        <div class="flex items-center justify-between">
          <span class="text-sm font-semibold text-slate-200">{{ row.entity }}</span>
          <span class="text-xs text-slate-500">{{ row.entity_type }}</span>
        </div>
        <div class="mt-1 text-2xl font-semibold text-emerald-400">
          {{ fmtUptime(row.uptime_pct) }}
        </div>
        <div class="mt-1 text-xs text-slate-500">
          Downtime {{ fmtDuration(row.downtime_seconds) }}
        </div>
        <button
          class="mt-2 rounded bg-runway-dark px-2 py-1 text-xs text-sky-400 hover:bg-runway-border"
          @click="entityKey = `${row.entity_type}:${row.entity_id}`"
        >
          Analyze
        </button>
        </div>
      </div>
      <div v-if="loadingSummary" class="absolute inset-0 z-10 flex items-center justify-center" style="background: rgba(11,18,32,0.55)">
        <div class="flex items-center gap-2 rounded bg-runway-panel px-4 py-2 text-sm text-slate-200 shadow-lg">
          <span class="inline-block h-4 w-4 animate-spin rounded-full border-2 border-sky-400 border-t-transparent"></span>
          Loading…
        </div>
      </div>
    </div>

    <!-- CDP SLA timeline -->
    <section v-if="scope === 'sla'" class="panel">
      <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">CDP Connectivity</h2>
      <EChart v-if="slaChartOption" :option="slaChartOption" height="160px" />
      <div v-else class="flex h-[160px] items-center justify-center text-xs text-slate-500">
        No connectivity samples
      </div>
    </section>

    <!-- Daily rollup -->
    <section class="panel">
      <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Daily Uptime — {{ selected?.label || '—' }}
      </h2>
      <div v-if="loadingDaily" class="flex h-[240px] items-center justify-center text-xs text-slate-500">
        Loading…
      </div>
      <EChart v-else-if="daily.length" :option="dailyChartOption" height="240px" />
      <div v-else class="flex h-[240px] items-center justify-center text-xs text-slate-500">
        No daily rollup data
      </div>
    </section>

    <!-- Events table -->
    <section class="panel">
      <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">Downtime Events</h2>
      <div v-if="loadingEvents" class="flex h-24 items-center justify-center text-xs text-slate-500">
        Loading…
      </div>
      <div v-else-if="events.length" class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-runway-border text-slate-500">
              <th class="py-2 pr-4">Start</th>
              <th class="py-2 pr-4">End</th>
              <th class="py-2 pr-4">Duration</th>
              <th class="py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ev in events" :key="ev.id" class="border-b border-runway-border/50">
              <td class="py-2 pr-4 text-slate-300">{{ fmtDateTime(ev.start_time) }}</td>
              <td class="py-2 pr-4 text-slate-300">{{ ev.end_time ? fmtDateTime(ev.end_time) : '—' }}</td>
              <td class="py-2 pr-4 text-slate-300">{{ fmtDuration(ev.duration_seconds) }}</td>
              <td class="py-2">
                <span class="rounded bg-runway-dark px-2 py-0.5 text-[11px]" :class="ev.end_time ? 'text-emerald-400' : 'text-red-400'">
                  {{ ev.end_time ? 'resolved' : 'open' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="flex h-24 items-center justify-center text-xs text-slate-500">
        No downtime events
      </div>
    </section>
  </div>
</template>