<script setup>
import { api } from '@/api/client'
import { formatDateTime } from '@/utils/timezone'
import { computed, onBeforeUnmount, onMounted, onUnmounted, ref, watch } from 'vue'
import SensorCard from '@/components/SensorCard.vue'

const props = defineProps({
  siteSlug: { type: String, required: true },
})

const overview = ref(null)
const timer = ref(null)
const range = ref('24h')  // unified time range for all sensor cards
const tzTick = ref(0)
function onTzChange() { tzTick.value++ }
onMounted(() => window.addEventListener('tzchange', onTzChange))
onBeforeUnmount(() => window.removeEventListener('tzchange', onTzChange))

const site = computed(() =>
  (overview.value?.sites || []).find((s) => s.slug === props.siteSlug),
)

const sensors = computed(() => (site.value?.sensors || []).filter((s) => s.is_enabled !== false))

const lastSampleIso = computed(() => {
  const ts = Math.max(0, ...sensors.value.map((s) => new Date(s.last_sample_time || 0).getTime()))
  return ts ? new Date(ts).toISOString() : null
})

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
  },
)

onMounted(() => {
  loadOverview()
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
            {{ formatDateTime(lastSampleIso) }}<span v-if="tzTick >= 0" class="hidden" />
          </div>
        </div>
        <div class="panel">
          <div class="text-xs text-slate-500">Online sensors</div>
          <div class="mt-1 text-2xl font-semibold text-white">
            {{ sensors.filter((s) => s.status === 'ok').length }}/{{ sensors.length }}
          </div>
        </div>
      </div>

      <!-- Sensor grid (dynamic from master table - no repetitive coding) -->
      <section>
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-400">Sensors</h2>
          <select v-model="range" class="rounded border border-runway-border bg-runway-panel px-2 py-1 text-xs text-slate-200 focus:outline-none">
            <option value="1h">Last 1 hour</option>
            <option value="6h">Last 6 hours</option>
            <option value="24h">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
        </div>
        <div class="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
          <SensorCard
            v-for="sensor in sensors"
            :key="sensor.id"
            :sensor="sensor"
            :site-slug="site.slug"
            :range="range"
          />
        </div>
      </section>
    </template>
    <div v-else class="flex h-40 items-center justify-center text-sm text-slate-500">
      Loading site…
    </div>
  </div>
</template>