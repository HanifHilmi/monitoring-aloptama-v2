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
const MONTHS3 = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

function toDate(v) {
  const d = typeof v === 'number' || typeof v === 'string' ? new Date(Number.isFinite(+v) ? +v : v) : v
  return d instanceof Date && !Number.isNaN(d.getTime()) ? d : null
}

// Smart UTC axis label. No seconds. When the range spans long windows:
// - a 00:00 UTC tick shows the day (e.g. '01' for the 1st),
// - if the range covers multiple months, the transition tick shows the
//   month name (e.g. 'Aug') instead of the day.
// Honors ECharts' call pattern (params.value = epoch ms) and never uses the
// device timezone (all getUTC*).
function utcAxisTick(v, rangeDays) {
  const d = toDate(typeof v === 'object' && v && v.value != null ? v.value : v)
  if (!d) return String(v?.value ?? v ?? '')
  const hhmm = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`
  const isMidnight = d.getUTCHours() === 0 && d.getUTCMinutes() === 0
  if (!isMidnight) return hhmm
  const day = d.getUTCDate()
  const days = rangeDays ?? 0
  // > ~45 days => show month label at midnight transitions
  if (days > 45 && day === 1) return MONTHS3[d.getUTCMonth()]
  // multi-day range => day number; single-day/minute range => HH:MM
  return days > 1 ? String(day) : hhmm
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

  // Determine the span (days) used to pick the axis label style.
  // The AXIS min/max reflect the user's SELECTED window (e.g. '3 Days Ago'
  // pins xAxis.min/max to 3 days), so they take priority. The series span
  // is only a fallback for charts without axis bounds (auto range).
  const axes = Array.isArray(out.xAxis) ? out.xAxis : out.xAxis ? [out.xAxis] : []

  let seriesSpanDays = 0
  let sMin = null, sMax = null
  const seriesList = Array.isArray(out.series) ? out.series : out.series ? [out.series] : []
  for (const s of seriesList) {
    const pts = Array.isArray(s.data) ? s.data : []
    for (const p of pts) {
      const t = Array.isArray(p) ? p[0] : (p && (p.time ?? p.value0))
      const d = toDate(t)
      if (!d) continue
      if (sMin === null || d < sMin) sMin = d
      if (sMax === null || d > sMax) sMax = d
    }
  }
  if (sMin && sMax) seriesSpanDays = (sMax - sMin) / 86400000

  let changed = false
  const next = axes.map((ax) => {
    const a = { ...ax }
    if (a.type === 'time' && a.axisLabel && typeof a.axisLabel.formatter !== 'function') {
      const axMin = toDate(a.min)
      const axMax = toDate(a.max)
      // 1) selected axis window (user's pick) wins whenever it spans > 0.
      let rangeDays = 0
      if (axMin && axMax) {
        rangeDays = (axMax - axMin) / 86400000
      }
      // 2) fall back to series span (auto-range charts).
      if (!(rangeDays > 0)) rangeDays = seriesSpanDays
      a.axisLabel = { ...a.axisLabel, formatter: (v) => utcAxisTick(v, rangeDays) }
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