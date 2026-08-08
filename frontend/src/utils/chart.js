import { displayTime } from './timezone'

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

// Normalize a raw time (ISO or Date) to UTC+? shifted display ISO.
const shift = (t) => displayTime(new Date(t).toISOString())

export function buildTimeSeriesOption({ times, series, unit = '', color = '#38bdf8' }) {
  const shifted = times.map(shift)
  return {
    animation: true,
    animationDuration: 500,
    animationDurationUpdate: 500,
    animationEasing: 'linear',
    animationEasingUpdate: 'linear',
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

// Dual-axis line chart (ATRH TEMP/RH, ANEM WS/WD). Honours UTC/WIB shift.
export function buildDualAxisOption({ left, right, leftName = '', rightName = '' }) {
  return {
    animation: true,
    animationDuration: 500,
    animationDurationUpdate: 500,
    animationEasing: 'linear',
    animationEasingUpdate: 'linear',
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
export function buildDotOption({ points, name = '', color = '#34d399' }) {
  return {
    animation: true,
    animationDuration: 500,
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
        data: points.map((p) => [shift(p.time), p.value]),
        symbolSize: 5,
        itemStyle: { color },
      },
    ],
  }
}