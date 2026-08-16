<script setup>
import { api } from '@/api/client'
import { formatDateTime } from '@/utils/timezone'
import { computed, onBeforeUnmount, onMounted, onUnmounted, ref, watch } from 'vue'
import EChart from '@/components/EChart.vue'
import PeriodPicker from '@/components/PeriodPicker.vue'
import RangePicker from '@/components/RangePicker.vue'
import SensorCard from '@/components/SensorCard.vue'
import { currentPeriod } from '@/utils/period'
import { buildTotalMissingOption } from '@/utils/chart'

const props = defineProps({
  siteSlug: { type: String, required: true },
})

const overview = ref(null)
const timer = ref(null)
const range = ref({ key: '3h', start: new Date(Date.now() - 3*3600*1000).toISOString(), end: new Date().toISOString() })  // unified window
const site = computed(() =>
  (overview.value?.sites || []).find((s) => s.slug === props.siteSlug),
)

const sensors = computed(() => (site.value?.sensors || []).filter((s) => s.is_enabled !== false))
const sensorCards = computed(() => sensors.value.filter((s) => !(s.is_state === true || s.code === 'DCP')))

const lastSampleIso = computed(() => {
  const ts = Math.max(0, ...sensors.value.map((s) => new Date(s.last_sample_time || 0).getTime()))
  return ts ? new Date(ts).toISOString() : null
})

// ---- DCP section: own period picker + component availability summary ----
const dcpPeriod = ref(currentPeriod('monthly'))
const dcpSummary = ref(null)

const dcpSensor = computed(() => sensors.value.find((s) => s.code === 'DCP' || s.is_state))
const dcpOnline = computed(() => (dcpSensor.value ? dcpSensor.value.status === 'ok' : null))

const COMPONENT_NAMES = {
  DCP: 'DCP', ATRH: 'Air Temp & RH', BARO: 'Barometer', ANEM: 'Anemometer',
  RVR: 'RVR', CEL: 'Ceilometer', PWX: 'Present Weather',
  RAIN: 'Rain Gauge', SOLR: 'Solar Radiation', LIGH: 'Lightning',
}

const dcpComponents = computed(() => {
  const comps = dcpSummary.value?.components || []
  const totalMin = Math.max(
    1,
    Math.round((new Date(dcpPeriod.value.end) - new Date(dcpPeriod.value.start)) / 60000),
  )
  const rows = comps.map((c) => ({
    code: c.component,
    name: COMPONENT_NAMES[c.component] || c.component,
    pct: c.uptime_pct ?? 0,
    missing: Math.max(0, totalMin - (c.samples || 0)),
  }))
  // Platform first, then the sensors.
  return [...rows.filter((r) => r.code === 'DCP'), ...rows.filter((r) => r.code !== 'DCP')]
})

const dcpAvg = computed(() =>
  dcpSummary.value ? dcpSummary.value.data_availability_pct : null,
)

const missingOption = computed(() => {
  if (!dcpComponents.value.length) return null
  return buildTotalMissingOption({
    items: dcpComponents.value.map((c) => ({ label: c.code, missing: c.missing })),
  })
})

async function loadDcp() {
  try {
    const s = await api.getAvailability('custom', dcpPeriod.value)
    dcpSummary.value = (s?.sites || []).find((x) => x.slug === props.siteSlug) || null
  } catch {
    dcpSummary.value = null
  }
}

function pctClass(p) {
  if (p == null) return 'text-slate-500'
  if (p >= 99) return 'text-emerald-400'
  if (p >= 95) return 'text-amber-400'
  return 'text-red-400'
}
function barColor(p) {
  if (p >= 99) return 'bg-emerald-400'
  if (p >= 95) return 'bg-amber-400'
  return 'bg-red-400'
}

async function loadOverview() {
  try {
    overview.value = await api.getStatusOverview()
  } catch {
    overview.value = null
  }
}

watch(
  () => props.siteSlug,
  () => {
    loadOverview()
    loadDcp()
  },
)
watch(() => dcpPeriod.value, () => loadDcp(), { deep: true })

onMounted(() => {
  loadOverview()
  loadDcp()
  timer.value = setInterval(loadOverview, 15_000)
})
onUnmounted(() => clearInterval(timer.value))
</script>

<template>
  <div class="space-y-6">
    <template v-if="site">
      <!-- Site header stats -->
      <div class="grid gap-4 md:grid-cols-4">
        <div class="panel">
          <div class="text-xs text-slate-500">Site</div>
          <div class="mt-1 text-2xl font-semibold text-emerald-400">
            {{ site.name }}
          </div>
        </div>
        <div class="panel">
          <div class="text-xs text-slate-500">Code</div>
          <div class="mt-1 text-2xl font-semibold text-sky-400">
            {{ site.code }}
          </div>
        </div>
        <div class="panel">
          <div class="text-xs text-slate-500">Last sample</div>
          <div class="mt-1 text-2xl font-semibold text-sky-400">
            {{ formatDateTime(lastSampleIso) }}
          </div>
        </div>
        <div class="panel">
          <div class="text-xs text-slate-500">Online Components</div>
          <div class="mt-1 text-2xl font-semibold text-white">
            {{ sensors.filter((s) => s.status === 'ok').length }}/{{ sensors.length }}
          </div>
        </div>
      </div>

      <!-- DCP platform section: own period picker + component availability -->
      <section>
        <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400">DCP</h2>
          <PeriodPicker v-model="dcpPeriod" />
        </div>
        <div class="panel">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span class="font-semibold text-slate-200">Data Collection Platform (DCP)</span>
              <span v-if="dcpOnline === true" class="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 text-[11px] font-bold text-emerald-400">● ONLINE</span>
              <span v-else-if="dcpOnline === false" class="inline-flex items-center gap-1 rounded bg-red-500/10 px-1.5 py-0.5 text-[11px] font-bold text-red-400">● OFFLINE</span>
              <span v-else class="text-[11px] text-slate-500">● …</span>
            </div>
            <span class="text-[10px] text-slate-500">{{ dcpPeriod.label }}</span>
          </div>

          <!-- Average over the 7 components -->
          <div class="mt-3 flex items-baseline gap-3">
            <span class="text-xs uppercase tracking-wide text-slate-500">Sites - Data Availability</span>
            <span class="text-2xl font-bold" :class="pctClass(dcpAvg)">
              {{ dcpAvg == null ? '—' : dcpAvg.toFixed(2) + '%' }}
            </span>
          </div>

          <div class="mt-3 grid gap-4 lg:grid-cols-2">
            <!-- Per-component availability bars -->
            <div class="flex flex-col gap-1.5">
              <div v-for="c in dcpComponents" :key="c.code" class="flex items-center gap-1.5 text-xs">
                <span class="w-24 shrink-0 truncate text-slate-400" :title="c.name">{{ c.name }}</span>
                <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-runway-dark">
                  <div class="h-full rounded-full transition-all" :class="barColor(c.pct)" :style="{ width: Math.min(100, c.pct) + '%' }"></div>
                </div>
                <span class="w-12 shrink-0 text-right font-mono" :class="pctClass(c.pct)">{{ c.pct.toFixed(2) }}%</span>
              </div>
              <div v-if="!dcpComponents.length" class="py-4 text-center text-xs text-slate-500">Loading DCP availability…</div>
            </div>

            <!-- Total data missing chart -->
            <div class="rounded bg-runway-dark p-1.5">
              <div class="mb-1 text-[10px] uppercase tracking-wide text-slate-500">Total Data Missing</div>
              <EChart v-if="missingOption" :option="missingOption" height="140px" />
              <div v-else class="flex h-[140px] items-center justify-center text-xs text-slate-500">No data</div>
            </div>
          </div>
        </div>
      </section>

      <!-- Sensor grid (dynamic from master table - no repetitive coding) -->
      <section>
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400">Sensors</h2>
          <RangePicker v-model="range" />
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <SensorCard
            v-for="sensor in sensorCards"
            :key="sensor.id"
            :sensor="sensor"
            :site-slug="site.slug"
            :range="range.key"
            :win="range"
          />
        </div>
      </section>
    </template>
    <div v-else class="flex h-40 items-center justify-center text-sm text-slate-500">
      Loading site…
    </div>
  </div>
</template>
