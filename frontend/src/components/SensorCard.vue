<script setup>
import { api } from '@/api/client'
import { buildTimeSeriesOption, buildDotOption, buildDualAxisOption } from '@/utils/chart'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import EChart from './EChart.vue'

const props = defineProps({
  sensor: { type: Object, required: true },
  siteSlug: { type: String, required: true },
  range: { type: String, default: '24h' },
})

// Multi-metric data: { TSI: samples, RH: samples, ..., WGS: samples }
const metrics = ref({})
const loading = ref(false)
const error = ref(null)
const timer = ref(null)

const isTextSensor = computed(() =>
  ['present_weather', 'lightning_detector'].includes(props.sensor.category),
)

// Numeric metric for the main chart. ATRH => TEMP, ANEM => WS, etc.
const primaryMetric = computed(() => {
  const m = Object.keys(metrics.value)
  const order = ['TEMP', 'WS', 'QNH', 'RVR', 'VIS', 'SOL', 'RA', 'LR1', 'ALS_INT']
  return order.find((x) => m.includes(x)) || m[0] || null
})

// Number of metrics with data (for text sensor display)
const textSamples = computed(() => {
  const out = []
  for (const [metric, samples] of Object.entries(metrics.value)) {
    out.push({ metric, samples })
  }
  return out
})

const chartOption = computed(() => {
  if (!primaryMetric.value) return null
  const samples = metrics.value[primaryMetric.value] || []
  const pts = samples
    .filter((s) => s.value !== null && s.value !== undefined)
    .map((s) => ({ time: s.time, value: s.value }))
  if (!pts.length) return null

  const isDual = props.sensor.code === 'ATRH' && metrics.value.RH?.length
  if (isDual) {
    const rh = metrics.value.RH
      .filter((s) => s.value !== null)
      .map((s) => ({ time: s.time, value: s.value }))
    return buildDualAxisOption({
      left: pts,
      right: rh,
      leftName: 'TEMP °C',
      rightName: 'RH %',
    })
  }
  if (props.sensor.code === 'CEL') {
    // dot graph: don't include zero values
    const dots = pts.filter((p) => p.value !== 0)
    return buildDotOption({ points: dots, name: 'LR1 ft' })
  }
  return buildTimeSeriesOption({
    times: pts.map((p) => p.time),
    series: pts.map((p) => p.value),
    unit: props.sensor.unit || '',
  })
})

const windGustPanel = computed(() => {
  if (props.sensor.code !== 'ANEM' || !metrics.value.WGS) return null
  const gusts = metrics.value.WGS.filter((s) => s.is_valid && s.value !== null)
  if (!gusts.length) return null
  const maxGust = Math.max(...gusts.map((s) => s.value))
  return { count: gusts.length, maxGust }
})

async function load() {
  loading.value = true
  error.value = null
  try {
    metrics.value = {}
    const data = await api.getTelemetry(props.siteSlug, props.sensor.code, props.range, 1500)
    // Group samples by metric - need metrics list but API returns selected one
    const all = await Promise.all(
      (data.metrics || []).map((m) =>
        api.getTelemetry(props.siteSlug, props.sensor.code, props.range, 1500, m),
      ),
    )
    for (const d of all) {
      metrics.value[d.metric] = d.samples || []
    }
    if (!Object.keys(metrics.value).length && data.samples) {
      metrics.value[data.metric] = data.samples
    }
  } catch (e) {
    error.value = e.message
    metrics.value = {}
  } finally {
    loading.value = false
  }
}

watch(() => props.range, load)

onMounted(() => {
  load()
  timer.value = setInterval(load, 30_000)
})
onUnmounted(() => clearInterval(timer.value))
</script>

<template>
  <div class="panel flex flex-col gap-2">
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <span class="status-dot" :class="props.sensor.status === 'ok' ? 'bg-emerald-400' : 'bg-amber-400'" />
        <span class="font-mono text-sm font-semibold text-slate-200">{{ props.sensor.code }}</span>
        <span class="text-xs text-slate-400">{{ props.sensor.name }}</span>
      </div>
    </div>

    <!-- Wind gust panel (ANEM) -->
    <div v-if="windGustPanel" class="grid grid-cols-2 gap-2 rounded bg-runway-dark p-2 text-xs">
      <div class="text-slate-400">Wind gusts</div>
      <div class="text-right text-sky-300">{{ windGustPanel.count }} events</div>
      <div class="text-slate-400">Max gust</div>
      <div class="text-right font-semibold text-white">{{ windGustPanel.maxGust }} kt</div>
    </div>
    <div v-else-if="props.sensor.code === 'ANEM' && !loading" class="rounded bg-runway-dark p-2 text-xs text-slate-500">
      No wind gusts in this range
    </div>

    <div v-if="loading && !Object.keys(metrics.value).length" class="flex h-[160px] items-center justify-center text-xs text-slate-500">
      Loading…
    </div>
    <div v-else-if="error" class="flex h-[160px] items-center justify-center text-xs text-red-400">
      {{ error }}
    </div>
    <!-- Text sensors: show latest text samples -->
    <div v-else-if="isTextSensor && textSamples.length" class="space-y-1">
      <div v-for="t in textSamples" :key="t.metric" class="flex justify-between rounded bg-runway-dark px-2 py-1 text-xs">
        <span class="text-slate-400">{{ t.metric }}</span>
        <span class="font-mono text-slate-200">
          {{ (t.samples.filter((s) => s.text_value).pop() || {}).text_value || '—' }}
        </span>
      </div>
    </div>
    <EChart v-else-if="chartOption" :option="chartOption" height="160px" />
    <div v-else class="flex h-[160px] items-center justify-center text-xs text-slate-500">
      No telemetry in this range
    </div>
  </div>
</template>