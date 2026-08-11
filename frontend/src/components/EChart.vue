<script setup>
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { chartTimezone, tooltipTime } from '@/utils/timezone'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '280px' },
  autoresize: { type: Boolean, default: true },
})

const el = ref(null)
let chart = null
let observer = null

const pad = (n) => String(n).padStart(2, '0')

// Compact UTC label for a time-axis tick. Receives a ms epoch (or Date).
// Always derived with getUTC* so the DEVICE timezone can never affect it.
function utcAxisTick(v) {
  const d = typeof v === 'number' || typeof v === 'string' ? new Date(Number.isFinite(+v) ? +v : v) : v
  if (!(d instanceof Date) || Number.isNaN(d.getTime())) return String(v ?? '')
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`
}

// Deep-apply UTC rendering to a chart option WITHOUT changing the data.
// - time x-axes: set axisLabel.formatter ONLY when none is already set
// - tooltip axisPointer label: always UTC (the '01:39 vs 08:39' symptom)
function applyUtc(option) {
  if (!option || typeof option !== 'object') return option
  const out = { ...option }

  // tooltip bubble time
  if (out.tooltip && typeof out.tooltip === 'object') {
    const t = { ...out.tooltip }
    t.axisPointer = {
      ...(t.axisPointer || {}),
      label: {
        ...((t.axisPointer && t.axisPointer.label) || {}),
        formatter: (p) => tooltipTime(p.value),
      },
    }
    out.tooltip = t
  }

  // x-axes (single object or array)
  const axes = Array.isArray(out.xAxis) ? out.xAxis : out.xAxis ? [out.xAxis] : []
  let changed = false
  const next = axes.map((ax) => {
    const a = { ...ax }
    if (a.type === 'time' && a.axisLabel && typeof a.axisLabel.formatter !== 'function') {
      a.axisLabel = { ...a.axisLabel, formatter: utcAxisTick }
      changed = true
    }
    return a
  })
  if (changed) {
    out.xAxis = Array.isArray(out.xAxis) ? next : next[0]
  }

  return out
}

function currentOption() {
  // ECharts 5.5 root timezone (UTC) + explicit UTC label formatters above.
  const base = { timezone: chartTimezone(), ...props.option }
  return applyUtc(base)
}

function render() {
  if (!chart) return
  // notMerge:false keeps the chart mounted and merges new points in place.
  chart.setOption(currentOption(), { notMerge: false })
}

function resize() {
  chart?.resize()
}

onMounted(() => {
  chart = echarts.init(el.value, 'dark')
  render()
  if (props.autoresize && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(resize)
    observer.observe(el.value)
  }
  window.addEventListener('resize', resize)
})

watch(() => props.option, render, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="el" :style="{ height }" class="w-full" />
</template>