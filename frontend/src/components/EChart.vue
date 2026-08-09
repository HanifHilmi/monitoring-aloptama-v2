<script setup>
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, onUnmounted, ref, watch } from 'vue'
import { chartTimezone } from '@/utils/timezone'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '280px' },
  autoresize: { type: Boolean, default: true },
})

const el = ref(null)
let chart = null
let observer = null

function currentOption() {
  // ECharts 5.5 root `timezone`: renders every time axis in a fixed zone
  // (UTC by default, Asia/Jakarta when the WIB toggle is on) — the
  // visitor's device timezone is never used.
  return { timezone: chartTimezone(), ...props.option }
}

function render() {
  if (!chart) return
  // notMerge:false -> merge new data in-place so the graph just appends
  // the new points instead of replacing the chart (no card blink/fade).
  chart.setOption(currentOption(), { notMerge: false })
}

function onTzChange() {
  if (!chart) return
  chart.clear()
  chart.setOption(currentOption(), { notMerge: true })
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
window.addEventListener('tzchange', onTzChange)

onBeforeUnmount(() => {
  window.removeEventListener('tzchange', onTzChange)
  observer?.disconnect()
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="el" :style="{ height }" class="w-full" />
</template>