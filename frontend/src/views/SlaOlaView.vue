<script setup>
import { api } from '@/api/client'
import EChart from '@/components/EChart.vue'
import { buildSlaTimelineOption } from '@/utils/chart'
import { fmtDateTime, fmtDuration, fmtUptime } from '@/utils/format'
import { computed, onMounted, ref, watch } from 'vue'

const props = defineProps({
  initialScope: { type: String, default: 'ola' },
})

const range = ref('30d')
const summary = ref(null)
const daily = ref([])
const scope = ref(props.initialScope)
const entityKey = ref('')
const events = ref([])
const loadingDaily = ref(false)
const loadingEvents = ref(false)

const entityOptions = computed(() => {
  const rows = summary.value?.rows || []
  return rows
    .filter((r) => r.scope === scope.value)
    .map((r) => ({
      key: `${r.entity_type}:${r.entity_id}`,
      label: `${r.scope.toUpperCase()} — ${r.entity}`,
      entity_type: r.entity_type,
      entity_id: r.entity_id,
    }))
})

const selected = computed(() => entityOptions.value.find((o) => o.key === entityKey.value) || entityOptions.value[0])

const dailyChartOption = computed(() => {
  const rows = [...daily.value].sort((a, b) => new Date(a.day) - new Date(b.day))
  return {
    animation: false,
    grid: { left: 12, right: 16, top: 24, bottom: 0, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0b1220',
      borderColor: '#1e2a45',
      textStyle: { color: '#e2e8f0', fontSize: 12 },
      formatter: (params) => {
        const p = params[0]
      },
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: '#64748b' } },
      axisLabel: { color: '#64748b', fontSize: 11 },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      min: 90,
      max: 100,
      axisLabel: { color: '#64748b', fontSize: 11, formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.12)' } },
    },
    series: [
      {
        type: 'bar',
        data: rows.map((r) => ({
          value: r.uptime_pct,
          downtime: r.downtime_seconds,
          itemStyle: { color: r.uptime_pct >= 99.9 ? '#10b981' : r.uptime_pct >= 99 ? '#38bdf8' : '#ef4444' },
        })),
        barWidth: '60%',
      },
    ],
  }
})

const refMap = ref({})

const slaChartOption = computed(() => {
  const connectivity = refMap.value[selected.value?.entity_id]
  const samples = connectivity?.samples || []
  if (!samples.length) return null
  const end = new Date().toISOString()
  const start = new Date(Date.now() - Number(range.value.replace('d', '')) * 24 * 3600 * 1000).toISOString()
  return buildSlaTimelineOption({ samples, startIso: start, endIso: end })
})

async function loadSummary() {
  summary.value = await api.getSlaOlaSummary(range.value)
  if (!selected.value) return
  await Promise.all([loadDaily(), loadEvents()])
}

async function loadDaily() {
  if (!selected.value) return
  loadingDaily.value = true
  try {
    const days = range.value === '7d' ? 7 : range.value === '24h' ? 1 : 30
    const data = await api.getDailyRollup(scope.value, selected.value.entity_type, selected.value.entity_id, days)
    daily.value = data.rows || []
  } catch {
    daily.value = []
  } finally {
    loadingDaily.value = false
  }
}

async function loadEvents() {
  if (!selected.value) return
  loadingEvents.value = true
  try {
    const data = await api.getDowntimeEvents(scope.value, null, null, 200)
    events.value = (data.events || []).filter((e) => {
      if (scope.value === 'sla') return e.cdp_id === selected.value.entity_id
      return e.sensor_id === selected.value.entity_id
    })
  } catch {
    events.value = []
  } finally {
    loadingEvents.value = false
  }
}

async function loadConnectivity() {
  if (scope.value !== 'sla') return
  refMap.value = {}
  const rows = summary.value?.rows || []
  for (const r of rows.filter((x) => x.scope === 'sla')) {
    try {
      const data = await api.getCdpConnectivity(r.entity_id, 24)
      refMap.value[r.entity_id] = data
    } catch {
      refMap.value[r.entity_id] = null
    }
  }
}

watch([scope, entityKey, range], async () => {
  if (!selected.value) return
  await Promise.all([loadDaily(), loadEvents()])
  if (scope.value === 'sla') await loadConnectivity()
})

watch(scope, async () => {
  const first = entityOptions.value[0]
  entityKey.value = first?.key || ''
})

onMounted(loadSummary)

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div class="flex gap-2">
        <select v-model="scope" class="rounded border border-runway-border bg-runway-panel px-3 py-1.5 text-sm text-slate-200 focus:outline-none">
        <select v-model="range" class="rounded border border-runway-border bg-runway-panel px-3 py-1.5 text-sm text-slate-200 focus:outline-none">

    <!-- Summary cards -->
    <div v-if="summary" class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <div v-for="row in summary.rows.filter((r) => r.scope === scope)" :key="row.entity_id" class="panel" :class="{ 'ring-1 ring-emerald-500/40': selected?.entity_id === row.entity_id }">
        <div class="flex items-center justify-between">
        <div class="mt-1 text-xs text-slate-500">
          Downtime {{ fmtDuration(row.downtime_seconds) }}
        <button
          class="mt-2 rounded bg-runway-dark px-2 py-1 text-xs text-sky-400 hover:bg-runway-border"
          @click="entityKey = `${row.entity_type}:${row.entity_id}`"
        >
          Analyze

    <!-- CDP SLA timeline -->
    <section v-if="scope === 'sla'" class="panel">
      <EChart v-if="slaChartOption" :option="slaChartOption" height="160px" />

    <!-- Daily rollup -->
    <section class="panel">
      <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Daily Uptime — {{ selected?.label || '—' }}
      <EChart v-else-if="daily.length" :option="dailyChartOption" height="240px" />

    <!-- Events table -->
    <section class="panel">
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="border-b border-runway-border text-slate-500">
          <tbody>
            <tr v-for="ev in events" :key="ev.id" class="border-b border-runway-border/50">
              <td class="py-2">
