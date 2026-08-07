<script setup>
import { api } from '@/api/client'
import { buildSlaTimelineOption } from '@/utils/chart'
import { fmtNumber, fmtTime, fmtUptime, statusColor } from '@/utils/format'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import EChart from '@/components/EChart.vue'

const overview = ref(null)
const slaSummary = ref(null)
const cdpCharts = ref({})
const timer = ref(null)
const error = ref(null)

const charts = computed(() => {
  const out = { 1: null, 2: null }
  for (const node of overview.value?.cdp_nodes || []) {
    const data = cdpCharts.value[node.id]
    if (!data?.samples?.length) continue
    const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString()
    out[node.id] = buildSlaTimelineOption({
      samples: data.samples,
      startIso: since,
      endIso: new Date().toISOString(),
    })
  }
  return out
})

async function load() {
  try {
    const [ov, sla] = await Promise.all([api.getStatusOverview(), api.getSlaOlaSummary('30d')])
    overview.value = ov
    slaSummary.value = sla
    for (const node of ov.cdp_nodes || []) {
      if (cdpCharts.value[node.id]) continue
      api.getCdpConnectivity(node.id, 24).then((d) => {
        cdpCharts.value[node.id] = d
      })
    }
  } catch (e) {
    error.value = e.message
  }
}

onMounted(() => {
  load()
  timer.value = setInterval(load, 15_000)
})
onUnmounted(() => clearInterval(timer.value))
</script>

<template>
  <div class="space-y-6">
    <p v-if="error" class="rounded bg-red-500/10 px-3 py-2 text-sm text-red-400">
      {{ error }}
    </p>

    <!-- CDP Nodes -->
    <section>
      <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">CDP Nodes (SLA)</h2>
      <div class="grid gap-4 md:grid-cols-2">
        <div v-for="node in overview?.cdp_nodes || []" :key="node.id" class="panel">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="status-dot" :class="`bg-${statusColor(node.status)}`" />
              <span class="font-mono text-sm font-semibold text-slate-200">{{ node.name }}</span>
            </div>
            <span class="text-xs text-slate-400">{{ node.ip }}</span>
          </div>
          <div class="mt-2 grid grid-cols-3 gap-2 text-xs">
            <div class="rounded bg-runway-dark px-2 py-1">
              <div class="text-slate-500">Status</div>
              <div class="font-semibold text-slate-200">{{ node.status }}</div>
            </div>
            <div class="rounded bg-runway-dark px-2 py-1">
              <div class="text-slate-500">Last seen</div>
              <div class="font-semibold text-slate-200">{{ fmtTime(node.last_seen) }}</div>
            </div>
            <div class="rounded bg-runway-dark px-2 py-1">
              <div class="text-slate-500">Uptime</div>
              <div class="font-semibold text-emerald-400">{{ fmtUptime(node.uptime_pct) }}</div>
            </div>
          </div>
          <EChart
            v-if="charts[node.id]"
            :option="charts[node.id]"
            height="120px"
            class="mt-3"
          />
          <div v-else-if="cdpCharts[node.id] === undefined" class="mt-3 flex h-[120px] items-center justify-center text-xs text-slate-500">
            Loading connectivity…
          </div>
          <div v-else class="mt-3 flex h-[120px] items-center justify-center text-xs text-slate-500">
            No connectivity samples in last 24h
          </div>
        </div>
      </div>
    </section>

    <!-- Sites -->
    <section>
      <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">Sites (OLA)</h2>
      <div class="grid gap-4 md:grid-cols-3">
        <RouterLink
          v-for="site in overview?.sites || []"
          :key="site.id"
          :to="`/runway/${site.slug}`"
          class="panel transition-colors hover:border-emerald-500/50"
        >
          <div class="flex items-center justify-between">
            <div>
              <div class="font-semibold text-slate-200">{{ site.name }}</div>
              <div class="text-xs text-slate-500">{{ site.code }}</div>
            </div>
            <span class="rounded-full bg-runway-dark px-2 py-0.5 text-xs text-slate-300">
              {{ site.online_sensors }}/{{ site.total_sensors }} online
            </span>
          </div>
          <div class="mt-3 flex flex-wrap gap-1.5">
            <span
              v-for="s in site.sensors"
              :key="s.id"
              class="inline-flex items-center gap-1 rounded bg-runway-dark px-2 py-0.5 font-mono text-[11px]"
            >
              <span class="status-dot h-1.5 w-1.5" :class="`bg-${statusColor(s.status)}`" />
              {{ s.code }}
            </span>
          </div>
        </RouterLink>
      </div>
    </section>

    <!-- SLA / OLA Summary -->
    <section v-if="slaSummary">
      <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">SLA / OLA Summary</h2>
      <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <div v-for="row in slaSummary.rows || []" :key="`${row.scope}-${row.entity_type}-${row.entity_id}`" class="panel">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold uppercase tracking-wide text-slate-400">{{ row.scope }}</span>
            <span class="text-xs text-slate-500">{{ row.entity }}</span>
          </div>
          <div class="mt-1 text-2xl font-semibold" :class="row.uptime_pct >= 99 && row.scope === 'sla' ? 'text-emerald-400' : 'text-sky-400'">
            {{ fmtUptime(row.uptime_pct) }}
          </div>
          <div class="mt-1 text-xs text-slate-500">
            Downtime {{ fmtNumber(row.downtime_seconds, 0) }}s
          </div>
        </div>
      </div>
    </section>

    <p class="text-xs text-slate-600">
      SLA measures CDP node reachability (independent of sensor data). OLA measures sensor data validity per site.
      Uptime % = ((Total Seconds − Downtime Seconds) / Total Seconds) × 100.
    </p>
  </div>
</template>