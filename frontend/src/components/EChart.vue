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
  chart.setOption(props.option, { notMerge: true })
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

<template>
  <div ref="el" :style="{ height }" class="w-full" />
