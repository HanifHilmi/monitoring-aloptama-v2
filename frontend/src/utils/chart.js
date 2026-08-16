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
        sampling: 'lttb',
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
        sampling: 'lttb',
        data: left.map((p) => [shift(p.time), p.value]),
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#38bdf8' },
        itemStyle: { color: '#38bdf8' },
      },
      {
        name: rightName,
        type: 'line',
        sampling: 'lttb',
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

// State strip: colored segments over time for low-cardinality string data
// (e.g. D/N = day/night). transitions = [{time, value}] change points; a
// value of '' means "no state" and is rendered as a gap.
export function buildStringStateOption({ transitions, startIso, endIso, name = '' }) {
  const STATE_COLORS = ['#38bdf8', '#a78bfa', '#34d399', '#fbbf24', '#f472b6', '#fb7185']
  const distinct = []
  for (const t of transitions || []) {
    if (t.value && t.value !== '' && !distinct.includes(t.value)) distinct.push(t.value)
  }
  const colorOf = {}
  distinct.forEach((v, i) => { colorOf[v] = STATE_COLORS[i % STATE_COLORS.length] })

  const markAreaData = []
  for (let i = 0; i < (transitions || []).length; i++) {
    const cur = transitions[i]
    if (!cur.value || cur.value === '') continue
    const next = transitions[i + 1]
    const end = next ? next.time : endIso
    if (new Date(end) <= new Date(cur.time)) continue
    markAreaData.push([
      { xAxis: cur.time, name: cur.value, itemStyle: { color: colorOf[cur.value], opacity: 0.6 } },
      { xAxis: end, itemStyle: { color: colorOf[cur.value], opacity: 0 } },
    ])
  }

  return {
    animation: true,
    animationDuration: 400,
    grid: { left: 12, right: 16, top: 8, bottom: 0, containLabel: true },
    tooltip: {
      ...baseTooltip(),
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0] : params
        return `<b>${p.name || '—'}</b>`
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
      data: distinct,
      axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      splitLine: { show: false },
    },
    series: [
      {
        name,
        type: 'line',
        data: [],
        showSymbol: false,
        lineStyle: { color: '#10b981', width: 2 },
        markArea: { data: markAreaData },
      },
    ],
  }
}

// Wind rose: polar stacked bar showing, per 16-direction sector, the minutes
// split into speed bands. windrose = [{sector 0..15, calm, light, moderate,
// strong, gale}].
export function buildWindRoseOption({ windrose }) {
  const DIRECTIONS = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
  const CATS = [
    { key: 'calm', label: 'Calm <1', color: '#64748b' },
    { key: 'light', label: '1–9', color: '#38bdf8' },
    { key: 'moderate', label: '10–19', color: '#34d399' },
    { key: 'strong', label: '20–29', color: '#fbbf24' },
    { key: 'gale', label: '≥30', color: '#f472b6' },
  ]
  const data = windrose || []
  const maxRadius = Math.max(1, ...data.map((r) => CATS.reduce((s, c) => s + (r[c.key] || 0), 0)))

  return {
    animation: true,
    animationDuration: 400,
    polar: {},
    legend: {
      bottom: 0,
      textStyle: { color: '#94a3b8', fontSize: 10 },
      itemWidth: 10,
      itemHeight: 8,
      data: CATS.map((c) => c.label),
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: '#0b1220',
      borderColor: '#1e2a45',
      textStyle: { color: '#e2e8f0', fontSize: 11 },
      formatter: (params) => `${params.name} · ${params.seriesName}: <b>${params.value}</b> min`,
    },
    angleAxis: {
      type: 'category',
      data: DIRECTIONS,
      startAngle: 90,
      boundaryGap: false,
      axisLine: { lineStyle: { color: AXIS_COLOR } },
      axisTick: { show: false },
      axisLabel: { color: AXIS_COLOR, fontSize: 9 },
      splitLine: { lineStyle: { color: SPLIT_COLOR } },
    },
    radiusAxis: {
      min: 0,
      max: maxRadius,
      axisLabel: { show: false },
      splitLine: { lineStyle: { color: SPLIT_COLOR } },
    },
    series: CATS.map((c) => ({
      name: c.label,
      type: 'bar',
      coordinateSystem: 'polar',
      stack: 'wind',
      data: data.map((r) => r[c.key] || 0),
      itemStyle: { color: c.color },
    })),
  }
}

// Ring gauge: single availability % as a full ring, health-colored arc, and
// the value centered. Used for per-component availability in the DCP panel.
export function buildGaugeOption({ value }) {
  const v = Math.min(100, Math.max(0, value))
  const color = v >= 99 ? '#10b981' : v >= 95 ? '#fbbf24' : '#ef4444'
  return {
    animation: true,
    animationDuration: 400,
    series: [
      {
        type: 'gauge',
        startAngle: 90,
        endAngle: -270,
        radius: '95%',
        center: ['50%', '55%'],
        min: 0,
        max: 100,
        pointer: { show: false },
        progress: {
          show: true,
          overlap: false,
          roundCap: true,
          clip: false,
          itemStyle: { color, width: 8 },
        },
        axisLine: { lineStyle: { width: 8, color: [[1, '#1e2a45']] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        detail: {
          valueAnimation: false,
          offsetCenter: [0, 0],
          fontSize: 15,
          fontWeight: 700,
          color,
          formatter: (val) => `${Number(val).toFixed(2)}%`,
        },
        data: [{ value: v }],
      },
    ],
  }
}

// DCP section: minutes each component was missing data in the period.
// items = [{ label, missing }]. Bars are color-coded by severity so the
// problem reads at a glance (dark = none, amber = some, red = a lot).
export function buildTotalMissingOption({ items }) {
  const labels = items.map((i) => i.label)
  const colorFor = (m) => (m <= 0 ? '#1e2a45' : m < 60 ? '#fbbf24' : '#ef4444')
  return {
    animation: true,
    animationDuration: 400,
    grid: { left: 8, right: 16, top: 24, bottom: 0, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#0b1220',
      borderColor: '#1e2a45',
      textStyle: { color: '#e2e8f0', fontSize: 11 },
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0] : params
        return `${p.name}<br/>Missing: <b>${p.value}</b> min`
      },
    },
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: AXIS_COLOR } },
      axisTick: { show: false },
      axisLabel: { color: AXIS_COLOR, fontSize: 10, rotate: 30 },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: AXIS_COLOR, fontSize: 10 },
      splitLine: { lineStyle: { color: SPLIT_COLOR } },
    },
    series: [
      {
        type: 'bar',
        barWidth: '55%',
        data: items.map((i) => ({
          value: i.missing,
          itemStyle: { color: colorFor(i.missing), borderRadius: [3, 3, 0, 0] },
        })),
      },
    ],
  }
}

// Histogram of minutes-per-value for high-cardinality string data (weather
// codes, cloud layers, lightning). Top 8 values + "other".
export function buildStringHistogramOption({ counts, name = '' }) {
  const MAX_BARS = 8
  const items = (counts || []).slice()
  let others = 0
  if (items.length > MAX_BARS) {
    others = items.slice(MAX_BARS).reduce((s, x) => s + x.count, 0)
    items.length = MAX_BARS
  }
  const labels = items.map((x) => x.value)
  const values = items.map((x) => x.count)
  if (others > 0) { labels.push('other'); values.push(others) }

  return {
    animation: true,
    grid: { left: 8, right: 16, top: 8, bottom: 0, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#0b1220',
      borderColor: '#1e2a45',
      textStyle: { color: '#e2e8f0', fontSize: 12 },
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0] : params
        return `${p.name}<br/><b>${p.value}</b> min`
      },
    },
    xAxis: {
      type: 'value',
      axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      splitLine: { lineStyle: { color: SPLIT_COLOR } },
    },
    yAxis: {
      type: 'category',
      data: labels,
      axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      splitLine: { show: false },
    },
    series: [
      {
        name,
        type: 'bar',
        data: values,
        barWidth: '60%',
        itemStyle: { color: '#38bdf8', borderRadius: [0, 3, 3, 0] },
      },
    ],
  }
}
