<script setup>
import { computed, ref, watch } from 'vue'
import {
  CATEGORIES, MONTHS, QUARTERS,
  yearWindow, monthWindow, quarterWindow, weekWindow,
  currentPeriod, defaultPeriod, daysInMonth,
} from '@/utils/period'

const props = defineProps({ modelValue: { type: Object, required: true } }) // { key, label, start, end }
const emit = defineEmits(['update:modelValue'])

const category = ref(props.modelValue?.key || 'monthly')
const year = ref(new Date().getUTCFullYear())
const monthIdx = ref(new Date().getUTCMonth())
const day = ref(1)
const quarterIdx = ref(Math.floor(new Date().getUTCMonth() / 3))

const years = computed(() => {
  const cur = new Date().getUTCFullYear()
  const list = []
  for (let y = cur; y >= 2025; y--) list.push(y)
  return list
})
const days = computed(() => daysInMonth(year.value, monthIdx.value))

function broadcast(win) {
  emit('update:modelValue', { ...win })
}

function pickCurrent() {
  broadcast(currentPeriod(category.value))
}
function pickYear() {
  day.value = Math.min(day.value, days.value)
  if (category.value === 'yearly') broadcast(yearWindow(year.value))
  else if (category.value === 'monthly') broadcast(monthWindow(year.value, monthIdx.value))
  else if (category.value === 'quarterly') broadcast(quarterWindow(year.value, quarterIdx.value))
  else broadcast(weekWindow(year.value, monthIdx.value, day.value))
}

// Recompute when any selector changes (unless yearly, just year).
watch([year, monthIdx, quarterIdx, day], pickYear)

// Watch modelValue for external category changes.
watch(() => props.modelValue?.key, (k) => { if (k) category.value = k })

// On mount, emit a default current period matching the initial category.
if (!props.modelValue?.start) {
  const w = defaultPeriod(category.value)
  emit('update:modelValue', { ...w })
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-1 rounded border border-runway-border bg-runway-panel p-1 text-xs">
    <button class="rounded px-2 py-1 text-sky-300 hover:bg-runway-dark" @click="pickCurrent">Current</button>
    <select v-model="category" @change="pickYear" class="rounded bg-runway-dark px-1 py-0.5 text-slate-200">
      <option v-for="c in CATEGORIES" :key="c.key" :value="c.key">{{ c.label }}</option>
    </select>
    <select v-model="year" class="rounded bg-runway-dark px-1 py-0.5 text-slate-200">
      <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
    </select>
    <template v-if="category === 'weekly'">
      <select v-model="monthIdx" class="rounded bg-runway-dark px-1 py-0.5 text-slate-200">
        <option v-for="(m, i) in MONTHS" :key="m" :value="i">{{ m }}</option>
      </select>
      <select v-model="day" class="rounded bg-runway-dark px-1 py-0.5 text-slate-200">
        <option v-for="d in days" :key="d" :value="d">{{ d }}</option>
      </select>
      <span class="text-slate-500">→ +7d</span>
    </template>
    <template v-else-if="category === 'monthly'">
      <select v-model="monthIdx" class="rounded bg-runway-dark px-1 py-0.5 text-slate-200">
        <option v-for="(m, i) in MONTHS" :key="m" :value="i">{{ m }}</option>
      </select>
    </template>
    <template v-else-if="category === 'quarterly'">
      <select v-model="quarterIdx" class="rounded bg-runway-dark px-1 py-0.5 text-slate-200">
        <option v-for="(q, i) in QUARTERS" :key="q" :value="i">{{ q }}</option>
      </select>
    </template>
  </div>
</template>