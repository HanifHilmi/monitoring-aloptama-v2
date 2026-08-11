<script setup>
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
// timezone handled via device-offset shift in applyUtc()

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '280px' },
  autoresize: { type: Boolean, default: true },
})

const el = ref(null)
let chart = null
let observer = null

const pad = (n) => String(n).padStart(2, '0')

// Display-only: shift chart timestamps by the DEVICE timezone offset so that
// ECharts' default (device-TZ) rendering shows the ORIGINAL UTC wall-clock.
// offset (ms) = getTimezoneOffset()*60000. For WIB (UTC+7) getTimezoneOffset()
// is -420 min; adding it shifts data -7h, and ECharts adds +7h back -> UTC.
function tzOffsetMs() {
  return new Date().getTimezoneOffset() * 60000
}

function toEpoch(v) {
  if (v == null) return null
  const d = v instanceof Date ? v : new Date(typeof v === 'number' || typeof v === 'string' ? (Number.isFinite(+v) ? +v : v) : v)
  return d instanceof Date && !Number.isNaN(d.getTime()) ? d.getTime() : null
}

// Apply the device-offset shift to a chart option WITHOUT changing stored data.
function applyUtc(option) {
  if (!option || typeof option !== 'object') return option
  const out = { ...option }
  const off = tzOffsetMs()
  if (off === 0) return out  // device already UTC -> nothing to do

  // Shift every series timestamp so ECharts default rendering shows UTC.
  const seriesList = Array.isArray(out.series) ? out.series : out.series ? [out.series] : []
  if (seriesList.length) {
    out.series = seriesList.map((s) => {
      const data = Array.isArray(s.data) ? s.data.map((p) => {
        if (Array.isArray(p)) {
          const e = toEpoch(p[0])
          return e != null ? [e + off, p[1]] : p
        }
        if (p && typeof p === 'object' && (p.time != null)) {
          const e = toEpoch(p.time)
          return e != null ? { ...p, time: e + off } : p
        }
        return p
      }) : s.data
      return { ...s, data }
    })
  }

  // Shift axis bounds (min/max) as well.
  const shiftAxis = (ax) => {
    const a = { ...ax }
    if (a.min != null) { const e = toEpoch(a.min); if (e != null) a.min = e + off }
    if (a.max != null) { const e = toEpoch(a.max); if (e != null) a.max = e + off }
    return a
  }
  if (out.xAxis) {
    out.xAxis = Array.isArray(out.xAxis) ? out.xAxis.map(shiftAxis) : shiftAxis(out.xAxis)
  }

  // Let ECharts use its DEFAULT (device-TZ) labels — after the shift they
  // display UTC, and its smart formatter (day/month at midnight) returns too.
  return out
}

function currentOption() {
  // No forced root timezone: apply the display-only device-offset shift so
  // ECharts' default rendering shows UTC (and keeps smart day/month labels).
  return applyUtc(props.option)
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