<script setup>
import { api } from '@/api/client'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import EChart from '@/components/EChart.vue'

const range = ref('month')
const bucket = ref('daily')
const span = ref('month')
const data = ref(null)
const history = ref([])
const timer = ref(null)

const slaPct = computed(() => data.value?.sla_pct ?? null)
const olaPct = computed(() => data.value?.ola_pct ?? null)
const cdps = computed(() => data.value?.cdp_uptime || [])
const sites = computed(() => data.value?.sites || [])

const historyOption = computed(() => {
  const rows = [...history.value].sort((a, b) => a.day.localeCompare(b.day))
  return {
    animation: false,
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
    const [d, h] = await Promise.all([api.getAvailability(range.value), api.getAvailabilityHistory(bucket.value, span.value)])
    data.value = d
    history.value = h.rows || []
  } catch {
    data.value = null
    history.value = []
  }
}

onMounted(() => {
  load()
  timer.value = setInterval(load, 30_000)
})
onUnmounted(() => clearInterval(timer.value))
</script>

<template>
  <div class="space-y-6">
    <!-- Row 1: SLA & OLA percentages -->
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold text-slate-200">SLA/OLA</h1>
      <select v-model="range" @change="load" class="rounded border border-runway-border bg-runway-panel px-2 py-1 text-xs text-slate-200">
        <option value="today">Today</option>
        <option value="week">This week</option>
        <option value="month">This month</option>
        <option value="year">This year</option>
      </select>
    </div>
    <div class="grid gap-4 md:grid-cols-2">
      <div class="panel">
        <div class="text-xs uppercase tracking-wide text-slate-400">SLA</div>
        <div class="mt-1 text-4xl font-bold" :class="(slaPct ?? 0) >= 99 ? 'text-emerald-400' : 'text-amber-400'">
          {{ slaPct === null ? '—' : slaPct.toFixed(2) + '%' }}
        </div>
        <div class="mt-1 text-xs text-slate-500">Avg of CDP1 + CDP2 uptime</div>
      </div>
      <div class="panel">
        <div class="text-xs uppercase tracking-wide text-slate-400">OLA</div>
        <div class="mt-1 text-4xl font-bold" :class="(olaPct ?? 0) >= 99 ? 'text-emerald-400' : 'text-amber-400'">
          {{ olaPct === null ? '—' : olaPct.toFixed(2) + '%' }}
        </div>
        <div class="mt-1 text-xs text-slate-500">Avg data availability of 3 runway sites</div>
      </div>
    </div>

    <!-- Row 2: SLA/OLA history graph -->
    <section class="panel">
      <div class="mb-2 flex items-center justify-between">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400">SLA / OLA History</h2>
        <div class="flex gap-2">
          <select v-model="bucket" @change="load" class="rounded border border-runway-border bg-runway-panel px-2 py-1 text-xs text-slate-200">
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
            <option value="yearly">Yearly</option>
          </select>
          <select v-model="span" @change="load" class="rounded border border-runway-border bg-runway-panel px-2 py-1 text-xs text-slate-200">
            <option value="month">In month range</option>
            <option value="year">In year range</option>
            <option value="5year">In 5 year range</option>
          </select>
        </div>
      </div>
      <EChart :option="historyOption" height="240px" />
    </section>

    <!-- Row 3: CDP Uptime & Downtime -->
    <section>
      <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">CDP Uptime</h2>
      <div class="grid gap-4 md:grid-cols-2">
        <div v-for="c in cdps" :key="c.cdp_id" class="panel">
          <div class="flex items-center justify-between">
            <span class="font-mono text-sm font-semibold text-slate-200">{{ c.name }}</span>
            <span class="text-xs text-slate-400">{{ c.ip_address }}</span>
          </div>
          <div class="mt-2 grid grid-cols-2 gap-2 text-xs">
            <div class="rounded bg-runway-dark px-2 py-1">
              <div class="text-slate-500">Uptime</div>
              <div class="font-semibold text-emerald-400">{{ c.uptime_pct.toFixed(2) }}%</div>
            </div>
            <div class="rounded bg-runway-dark px-2 py-1">
              <div class="text-slate-500">Downtime</div>
              <div class="font-semibold text-red-400">{{ (c.downtime_seconds / 60).toFixed(1) }} min</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Row 4: Sites (Data Availability) -->
    <section>
      <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">Sites — Data Availability</h2>
      <div class="grid gap-4 md:grid-cols-3">
        <RouterLink v-for="s in sites" :key="s.site_id" :to="`/runway/${s.slug}`" class="panel transition-colors hover:border-emerald-500/50">
          <div class="flex items-center justify-between">
            <span class="font-semibold text-slate-200">{{ s.name }}</span>
            <span class="text-lg font-bold" :class="s.data_availability_pct >= 99 ? 'text-emerald-400' : 'text-amber-400'">
              {{ s.data_availability_pct.toFixed(2) }}%
            </span>
          </div>
          <div class="mt-2 flex flex-wrap gap-1">
            <span v-for="comp in s.components" :key="comp.component" class="rounded bg-runway-dark px-1.5 py-0.5 text-[10px] text-slate-300">
              {{ comp.component }} {{ comp.uptime_pct.toFixed(1) }}%
            </span>
          </div>
        </RouterLink>
      </div>
    </section>
  </div>
</template>