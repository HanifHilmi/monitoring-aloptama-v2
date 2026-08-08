<script setup>
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '280px' },
  autoresize: { type: Boolean, default: true },
})

const el = ref(null)
let chart = null
let observer = null

function render() {
  if (!chart) return
  // notMerge:false -> merge new data in-place so the graph just appends
  // the new points instead of replacing the chart (no card blink/fade).
  chart.setOption(props.option, { notMerge: false })
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