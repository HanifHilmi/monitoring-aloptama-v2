<script setup>
import { computed, ref, watch } from 'vue'
import {
  CATEGORIES, MONTHS, QUARTERS,
  yearWindow, monthWindow, quarterWindow, weekWindow,
  currentPeriod, defaultPeriod, daysInMonth,
} from '@/utils/period'

const props = defineProps({ modelValue: { type: Object, required: true } })
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
const shortMonths = MONTHS.map((m) => m.slice(0, 3))

function broadcast(win) {
  emit('update:modelValue', { ...win })
}

function pickCurrent() {
  broadcast(currentPeriod(category.value))
}

function pickYearStep(delta) {
  const idx = years.value.indexOf(year.value)
  const next = years.value[Math.max(0, Math.min(years.value.length - 1, idx + delta))]
  if (next !== undefined) { year.value = next; apply() }
}

function apply() {
  if (category.value === 'yearly') broadcast(yearWindow(year.value))
  else if (category.value === 'monthly') broadcast(monthWindow(year.value, monthIdx.value))
  else if (category.value === 'quarterly') broadcast(quarterWindow(year.value, quarterIdx.value))
  else broadcast(weekWindow(year.value, monthIdx.value, Math.min(day.value, days.value)))
}

watch([year, monthIdx, quarterIdx, day], apply)
watch(() => props.modelValue?.key, (k) => { if (k) category.value = k })

if (!props.modelValue?.start) {
  const w = defaultPeriod(category.value)
  emit('update:modelValue', { ...w })
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-2 rounded border border-runway-border bg-runway-panel p-1.5 text-xs">
    <!-- Category chips -->
    <button class="rounded px-2 py-1 text-sky-300 hover:bg-runway-dark" @click="pickCurrent">Current</button>
    <div class="flex gap-0.5">
      <button
        v-for="c in CATEGORIES"
        :key="c.key"
        class="rounded px-2 py-1 transition-colors"
        :class="category === c.key ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-runway-dark'"
        @click="category = c.key; apply()"
      >
        {{ c.label }}
      </button>
    </div>

    <!-- Year stepper -->
    <div class="flex items-center gap-1 rounded bg-runway-dark px-1 py-0.5">
      <button class="px-1 text-slate-400 hover:text-white" @click="pickYearStep(-1)">‹</button>
      <span class="min-w-[3.5ch] text-center font-semibold text-slate-200">{{ year }}</span>
      <button class="px-1 text-slate-400 hover:text-white" @click="pickYearStep(1)">›</button>
    </div>

    <!-- Monthly: 12-cell grid -->
    <div v-if="category === 'monthly'" class="grid grid-cols-6 gap-0.5">
      <button
        v-for="(m, i) in shortMonths"
        :key="m"
        class="rounded px-1.5 py-0.5 text-[11px] transition-colors"
        :class="monthIdx === i ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-runway-dark'"
        @click="monthIdx = i"
      >
        {{ m }}
      </button>
    </div>

    <!-- Quarterly: 4-cell grid -->
    <div v-else-if="category === 'quarterly'" class="grid grid-cols-4 gap-0.5">
      <button
        v-for="(q, i) in QUARTERS"
        :key="q"
        class="rounded px-2 py-0.5 transition-colors"
        :class="quarterIdx === i ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-runway-dark'"
        @click="quarterIdx = i"
      >
        {{ q }}
      </button>
    </div>

    <!-- Weekly: month grid + start-day grid -->
    <div v-else-if="category === 'weekly'" class="flex items-center gap-1">
      <select v-model="monthIdx" class="rounded bg-runway-dark px-1 py-0.5 text-slate-200">
        <option v-for="(m, i) in shortMonths" :key="m" :value="i">{{ m }}</option>
      </select>
      <div class="grid max-h-40 grid-cols-7 gap-0.5 overflow-y-auto">
        <button
          v-for="d in days"
          :key="d"
          class="h-5 w-5 rounded text-[10px] transition-colors"
          :class="day === d ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-runway-dark'"
          @click="day = d"
        >
          {{ d }}
        </button>
      </div>
      <span class="text-slate-500">+7d</span>
    </div>
  </div>
</template>