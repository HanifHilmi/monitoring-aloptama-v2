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
    axisPointer: { type: 'cross', lineStyle: { color: '#334155' } },
  }
}

export function buildTimeSeriesOption({ times, series, unit = '', color = '#38bdf8' }) {
  return {
    animation: false,
    grid: baseGrid(),
    tooltip: {
      ...baseTooltip(),
      valueFormatter: (v) => (v === null || v === undefined ? '—' : `${v}${unit ? ` ${unit}` : ''}`),
    },
    xAxis: {
      type: 'time',
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
        data: times.map((t, i) => [t, series[i]]),
        showSymbol: false,
        lineStyle: { width: 1.5, color },
        itemStyle: { color },
        areaStyle: { color: 'rgba(56, 189, 248, 0.08)' },
        connectNulls: false,
      },
    ],
  }
}

// Dual-axis line chart for sensors with two units (e.g. ATRH: TEMP <-> RH).
export function buildDualAxisOption({ left, right, leftName = '', rightName = '' }) {
  return {
    animation: false,
    grid: baseGrid(),
    tooltip: { ...baseTooltip() },
    xAxis: {
      type: 'time',
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
        data: left.map((p) => [p.time, p.value]),
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#38bdf8' },
        itemStyle: { color: '#38bdf8' },
      },
      {
        name: rightName,
        type: 'line',
        yAxisIndex: 1,
        data: right.map((p) => [p.time, p.value]),
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#a78bfa' },
        itemStyle: { color: '#a78bfa' },
      },
    ],
  }
}

// Dot (scatter) chart for e.g. ceilometer LR1; zeros excluded by caller.
export function buildDotOption({ points, name = '', color = '#34d399' }) {
  return {
    animation: false,
    grid: baseGrid(),
    tooltip: { ...baseTooltip() },
    xAxis: {
      type: 'time',
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
        data: points.map((p) => [p.time, p.value]),
        symbolSize: 5,
        itemStyle: { color },
      },
    ],
  }
}

export function buildOlaTimelineOption({ events, startIso, endIso, colorOk = '#10b981', colorDown = '#ef4444' }) {
  const downBands = events
    .filter((e) => e.end_time)
    .map((e) => [
      { xAxis: e.start_time, itemStyle: { color: colorDown, opacity: 0.18 } },
      { xAxis: e.end_time, itemStyle: { color: colorDown, opacity: 0.0 } },
    ])

  return {
    animation: false,
    grid: baseGrid(),
    tooltip: {
      ...baseTooltip(),
      formatter(params) {
        if (Array.isArray(params) && params.length === 2 && params[0].componentType === 'markArea') {
          const [a, b] = params
          return `${a.value}<br/>DOWN<br/>${a.value} → ${b.value}`
        }
        if (!Array.isArray(params) && params.componentType === 'markLine') {
          return `DOWN since<br/>${params.value}`
        }
        return ''
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
      data: ['DOWN', 'OK'],
      axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      splitLine: { show: false },
    },
    series: [
      {
        type: 'line',
        data: [],
        showSymbol: false,
        lineStyle: { color: colorOk, width: 3 },
        markArea: { silent: true, data: downBands, itemStyle: { color: colorDown, opacity: 0.18 } },
        markLine: {
          silent: true,
          symbol: 'none',
          label: { show: false },
          lineStyle: { color: colorDown, width: 1, type: 'dashed' },
          data: events
            .filter((e) => e.end_time === null)
            .map((e) => ({ xAxis: e.start_time })),
        },
      },
    ],
  }
}

export function buildSlaTimelineOption({ samples, startIso, endIso, colorOk = '#10b981', colorDown = '#ef4444' }) {
  const bands = []
  let runStart = null
  let runState = null
  for (const s of samples) {
    if (s.reachable === runState) continue
    if (runStart !== null) {
      bands.push({ start: runStart, end: s.time, reachable: runState })
    }
    runStart = s.time
    runState = s.reachable
  }
  if (runStart !== null) {
    bands.push({ start: runStart, end: endIso, reachable: runState })
  }

  const markAreaData = []
  for (const b of bands) {
    if (b.end <= b.start) continue
    const color = b.reachable ? colorOk : colorDown
    markAreaData.push([
      { xAxis: b.start, itemStyle: { color, opacity: b.reachable ? 0.10 : 0.28 } },
      { xAxis: b.end, itemStyle: { color, opacity: 0 } },
    ])
  }

  return {
    animation: false,
    grid: baseGrid(),
    tooltip: {
      ...baseTooltip(),
      formatter(params) {
        if (Array.isArray(params) && params.length === 2 && params[0].componentType === 'markArea') {
          const [a, b] = params
          return `${a.value}<br/>${a.value} → ${b.value}`
        }
        return ''
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
      data: ['DOWN', 'OK'],
      axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      splitLine: { show: false },
    },
    series: [
      {
        type: 'line',
        data: [],
        showSymbol: false,
        lineStyle: { color: colorOk, width: 3 },
        markArea: { silent: true, data: markAreaData },
      },
    ],
  }
}