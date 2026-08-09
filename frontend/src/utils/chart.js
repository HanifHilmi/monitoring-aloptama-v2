import { tooltipTime } from './timezone'

const AXIS_COLOR = '#64748b'
const SPLIT_COLOR = 'rgba(148, 163, 184, 0.12)'

function baseGrid() {
  return { left: 12, right: 16, top: 12, bottom: 0, containLabel: true }
}

function baseTooltip() {
  return {
    trigger: 'axis',
    backgroundColor: '#0b1220',
    borderColor: '#1e2a45',
    textStyle: { color: '#e2e8f0', fontSize: 12 },
    axisPointer: {
      type: 'cross',
      lineStyle: { color: '#334155' },
      // Crosshair label: display the hovered time in the selected zone.
      label: {
        formatter: (p) => tooltipTime(p.value),
        backgroundColor: '#1e2a45',
        color: '#e2e8f0',
        fontSize: 11,
      },
    },
  }
}

// Data timestamps are UTC; the display offset (WIB = +7h) is handled by
// ECharts' root `timezone` option in EChart.vue, so no client-side shift.
const shift = (t) => new Date(t).toISOString()

export function buildTimeSeriesOption({ times, series, unit = '', color = '#38bdf8', xMin = null, xMax = null }) {
  const shifted = times.map(shift)
  return {
    animation: true,
    animationDuration: 500,
    animationDurationUpdate: 500,
    animationEasing: 'linear',
    animationEasingUpdate: 'linear',
    grid: baseGrid(),
    tooltip: baseTooltip(),
    xAxis: {
      type: 'time',
      min: xMin,
      max: xMax,
      axisLine: { lineStyle: { color: AXIS_COLOR } },
      axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      splitLine: { lineStyle: { color: SPLIT_COLOR } },
      name: unit,
      nameTextStyle: { color: AXIS_COLOR, fontSize: 11 },
    },
    series: [
      {
        type: 'line',
        data: shifted.map((t, i) => [t, series[i]]),
        showSymbol: false,
        lineStyle: { width: 1.5, color },
        itemStyle: { color },
        areaStyle: { color: 'rgba(56, 189, 248, 0.08)' },
        connectNulls: false,
      },
    ],
  }
}

// Dual-axis line chart (ATRH TEMP/RH, ANEM WS/WD).
export function buildDualAxisOption({ left, right, leftName = '', rightName = '', xMin = null, xMax = null }) {
  return {
    animation: true,
    animationDuration: 500,
    animationDurationUpdate: 500,
    animationEasing: 'linear',
    animationEasingUpdate: 'linear',
    grid: baseGrid(),
    tooltip: baseTooltip(),
    xAxis: {
      type: 'time',
      min: xMin,
      max: xMax,
      axisLine: { lineStyle: { color: AXIS_COLOR } },
      axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      splitLine: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        scale: true,
        axisLabel: { color: AXIS_COLOR, fontSize: 11 },
        splitLine: { lineStyle: { color: SPLIT_COLOR } },
        name: leftName,
        nameTextStyle: { color: AXIS_COLOR, fontSize: 11 },
      },
      {
        type: 'value',
        scale: true,
        axisLabel: { color: AXIS_COLOR, fontSize: 11 },
        splitLine: { show: false },
        name: rightName,
        nameTextStyle: { color: AXIS_COLOR, fontSize: 11 },
      },
    ],
    series: [
      {
        name: leftName,
        type: 'line',
        data: left.map((p) => [shift(p.time), p.value]),
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#38bdf8' },
        itemStyle: { color: '#38bdf8' },
      },
      {
        name: rightName,
        type: 'line',
        yAxisIndex: 1,
        data: right.map((p) => [shift(p.time), p.value]),
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#a78bfa' },
        itemStyle: { color: '#a78bfa' },
      },
    ],
  }
}

// Dot (scatter) chart for ceilometer LR1 (zeros excluded by caller).
export function buildDotOption({ points, name = '', color = '#34d399', xMin = null, xMax = null }) {
  return {
    animation: true,
    animationDuration: 500,
    grid: baseGrid(),
    tooltip: baseTooltip(),
    xAxis: {
      type: 'time',
      min: xMin,
      max: xMax,
      axisLine: { lineStyle: { color: AXIS_COLOR } },
      axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      splitLine: { lineStyle: { color: SPLIT_COLOR } },
      name,
      nameTextStyle: { color: AXIS_COLOR, fontSize: 11 },
    },
    series: [
      {
        type: 'scatter',
        data: points.map((p) => [shift(p.time), p.value]),
        symbolSize: 5,
        itemStyle: { color },
      },
    ],
  }
}

// CDP uptime state-map: green=UP, red=DOWN over the sampled history.
export function buildUptimeStateMapOption({ samples, startIso, endIso }) {
  const bands = []
  let runStart = null
  let runUp = null
  for (const s of samples) {
    if (s.reachable === runUp) continue
    if (runStart !== null) {
      bands.push({ start: runStart, end: s.time, up: runUp })
    }
    runStart = s.time
    runUp = s.reachable
  }
  if (runStart !== null) {
    bands.push({ start: runStart, end: endIso, up: runUp })
  }
  const markAreaData = bands
    .filter((b) => b.end > b.start)
    .map((b) => [
      { xAxis: b.start, itemStyle: { color: b.up ? '#10b981' : '#ef4444', opacity: b.up ? 0.15 : 0.35 } },
      { xAxis: b.end, itemStyle: { color: b.up ? '#10b981' : '#ef4444', opacity: 0 } },
    ])

  return {
    animation: true,
    animationDuration: 400,
    grid: baseGrid(),
    tooltip: {
      ...baseTooltip(),
      formatter() {
        return `Uptime state-map · ${startIso} → ${endIso} (${tooltipTime(startIso)} – ${tooltipTime(endIso)})`
      },
    },
    xAxis: {
      type: 'time',
      min: startIso,
      max: endIso,
      axisLine: { lineStyle: { color: AXIS_COLOR } },
      axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'category',
      data: ['DOWN', 'UP'],
      axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      splitLine: { show: false },
    },
    series: [
      {
        type: 'line',
        data: [],
        showSymbol: false,
        lineStyle: { color: '#10b981', width: 2 },
        markArea: { silent: true, data: markAreaData },
      },
    ],
  }
}