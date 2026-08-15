<script setup>
import { use, init } from 'echarts/core'
import { LineChart, BarChart, ScatterChart, HeatmapChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, TitleComponent, LegendComponent,
  VisualMapComponent, CalendarComponent, MarkAreaComponent,
  PolarComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

use([
  LineChart, BarChart, ScatterChart, HeatmapChart,
  GridComponent, TooltipComponent, TitleComponent, LegendComponent,
  VisualMapComponent, CalendarComponent, MarkAreaComponent,
  PolarComponent,
  CanvasRenderer,
])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '280px' },
  autoresize: { type: Boolean, default: true },
  refreshTick: { type: Number, default: 0 },
})

const el = ref(null)
let chart = null
let observer = null

function render() {
  if (!chart) return
  chart.setOption({ timezone: 'UTC', ...props.option }, { notMerge: false })
}

function resize() {
  chart?.resize()
}

onMounted(() => {
  chart = init(el.value)
  render()
  if (props.autoresize && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(resize)
    observer.observe(el.value)
  }
  window.addEventListener('resize', resize)
})

watch(() => props.option, render)
// Explicit refresh trigger: parents bump refreshTick to force a re-render
// even when the option object identity is unchanged (guarantees live updates).
watch(() => props.refreshTick, render)

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