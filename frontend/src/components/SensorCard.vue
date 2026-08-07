<script setup>
import { api } from '@/api/client'
import { buildTimeSeriesOption } from '@/utils/chart'
import { fmtTime, statusColor } from '@/utils/format'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import EChart from './EChart.vue'

const props = defineProps({
  sensor: { type: Object, required: true },
  siteSlug: { type: String, required: true },
})

const range = ref('24h')
const loading = ref(false)
const error = ref(null)
const samples = ref([])
const timer = ref(null)

const chartOption = computed(() => {
  const sorted = [...samples.value].sort((a, b) => new Date(a.time) - new Date(b.time))
  return buildTimeSeriesOption({
    times: sorted.map((s) => s.time),
    series: sorted.map((s) => s.value),
    unit: props.sensor.unit || '',
    color: props.sensor.category === 'present_weather' ? '#a78bfa' : '#38bdf8',
  })
})

async function load() {
  loading.value = true
  error.value = null
  try {
    const data = await api.getTelemetry(props.siteSlug, props.sensor.code, range.value, 1000)
    samples.value = data.samples || []
  } catch (e) {
    error.value = e.message
    samples.value = []
  } finally {
    loading.value = false
  }
}

watch(range, load)

onMounted(() => {
  load()
  timer.value = setInterval(load, 30_000)
})

onUnmounted(() => clearInterval(timer.value))

<template>
  <div class="panel flex flex-col gap-2">
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <span class="status-dot" :class="`bg-${statusColor(sensor.status)}`" />
      <div class="flex items-center gap-1">
        <select
          v-model="range"
          class="rounded border border-runway-border bg-runway-dark px-1.5 py-0.5 text-xs text-slate-300 focus:outline-none"
        >

    <div class="flex items-center gap-3 text-xs text-slate-400">

    <div v-if="loading && samples.length === 0" class="flex h-[180px] items-center justify-center text-xs text-slate-500">
      Loading…
    <div v-else-if="error && samples.length === 0" class="flex h-[180px] items-center justify-center text-xs text-red-400">
      {{ error }}
    <div v-else-if="samples.length === 0" class="flex h-[180px] items-center justify-center text-xs text-slate-500">
      No telemetry in this range
    <EChart v-else :option="chartOption" height="180px" />
