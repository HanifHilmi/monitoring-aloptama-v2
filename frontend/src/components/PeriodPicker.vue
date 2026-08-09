<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  CATEGORIES, MONTHS, QUARTERS,
  yearWindow, monthWindow, quarterWindow, weekWindow,
  currentPeriod, daysInMonth,
} from '@/utils/period'

const props = defineProps({ modelValue: { type: Object, required: true } })
const emit = defineEmits(['update:modelValue'])

const root = ref(null)
const category = ref(props.modelValue?.key || 'monthly')
const year = ref(new Date().getUTCFullYear())
const monthIdx = ref(new Date().getUTCMonth())
const day = ref(1)
const quarterIdx = ref(Math.floor(new Date().getUTCMonth() / 3))
const openFor = ref(null) // 'weekly' | 'monthly' | 'quarterly' | null

const years = computed(() => {
  const cur = new Date().getUTCFullYear()
  const list = []
  for (let y = cur; y >= 2025; y--) list.push(y)
  return list
})
const shortMonths = MONTHS.map((m) => m.slice(0, 3))
const days = computed(() => daysInMonth(year.value, monthIdx.value))
const weekdays = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']
const leadingBlanks = computed(() => new Date(Date.UTC(year.value, monthIdx.value, 1)).getUTCDay())

function broadcast(win) { emit('update:modelValue', { ...win }) }

function apply() {
  if (category.value === 'yearly') broadcast(yearWindow(year.value))
  else if (category.value === 'monthly') broadcast(monthWindow(year.value, monthIdx.value))
  else if (category.value === 'quarterly') broadcast(quarterWindow(year.value, quarterIdx.value))
  else broadcast(weekWindow(year.value, monthIdx.value, day.value))
}

function pickCategory(k) { category.value = k; openFor.value = null; apply() }
function pickCurrent() { broadcast(currentPeriod(category.value)) }

function togglePop(k) { openFor.value = openFor.value === k ? null : k }
function navMonth(delta) {
  let m = monthIdx.value + delta
  let y = year.value
  if (m < 0) { m = 11; y-- } else if (m > 11) { m = 0; y++ }
  if (y >= 2025 && y <= new Date().getUTCFullYear()) { monthIdx.value = m; year.value = y; apply() }
}
function navPopYear(delta) {
  const idx = years.value.indexOf(year.value)
  const n = years.value[Math.max(0, Math.min(years.value.length - 1, idx + delta))]
  if (n !== undefined) { year.value = n; apply() }
}

function onDocMouseDown(e) {
  if (root.value && !root.value.contains(e.target)) openFor.value = null
}
onMounted(() => document.addEventListener('mousedown', onDocMouseDown))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocMouseDown))
</script>

<template>
  <div ref="root" class="relative flex flex-wrap items-center gap-1.5 rounded border border-runway-border bg-runway-panel p-1.5 text-xs">
    <button class="rounded px-2 py-1 text-sky-300 hover:bg-runway-dark" @click="pickCurrent">Current</button>

    <!-- Category chips -->
    <button
      v-for="c in CATEGORIES"
      :key="c.key"
      class="rounded px-2 py-1 transition-colors"
      :class="category === c.key ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-runway-dark'"
      @click="pickCategory(c.key)"
    >
      {{ c.label }}
    </button>

    <!-- Year dropdown (native select, compact) -->
    <select v-model="year" @change="apply" class="rounded bg-runway-dark px-1.5 py-1 text-slate-200">
      <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
    </select>

    <!-- Monthly popover -->
    <div v-if="category === 'monthly'" class="relative">
      <button class="rounded bg-runway-dark px-2 py-1 text-slate-200" @click="togglePop('monthly')">
        {{ shortMonths[monthIdx] }} ▾
      </button>
      <div v-if="openFor === 'monthly'"
        class="absolute left-0 top-full z-30 mt-1 w-44 rounded-md border border-runway-border bg-runway-panel p-2 shadow-xl">
        <div class="mb-1 flex items-center justify-between">
          <button class="px-1 text-slate-400 hover:text-white" @click="navPopYear(-1)">‹</button>
          <span class="text-xs font-semibold text-slate-200">{{ year }}</span>
          <button class="px-1 text-slate-400 hover:text-white" @click="navPopYear(1)">›</button>
        </div>
        <div class="grid grid-cols-4 gap-0.5">
          <button
            v-for="(m, i) in shortMonths"
            :key="m"
            class="rounded px-1 py-1 text-[11px] transition-colors"
            :class="monthIdx === i && year === year ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-runway-dark'"
            @click="monthIdx = i; apply(); openFor = null"
          >
            {{ m }}
          </button>
        </div>
      </div>
    </div>

    <!-- Quarterly popover -->
    <div v-else-if="category === 'quarterly'" class="relative">
      <button class="rounded bg-runway-dark px-2 py-1 text-slate-200" @click="togglePop('quarterly')">
        {{ QUARTERS[quarterIdx] }} ▾
      </button>
      <div v-if="openFor === 'quarterly'"
        class="absolute left-0 top-full z-30 mt-1 w-40 rounded-md border border-runway-border bg-runway-panel p-2 shadow-xl">
        <div class="mb-1 flex items-center justify-between">
          <button class="px-1 text-slate-400 hover:text-white" @click="navPopYear(-1)">‹</button>
          <span class="text-xs font-semibold text-slate-200">{{ year }}</span>
          <button class="px-1 text-slate-400 hover:text-white" @click="navPopYear(1)">›</button>
        </div>
        <div class="grid grid-cols-2 gap-0.5">
          <button
            v-for="(q, i) in QUARTERS"
            :key="q"
            class="rounded px-2 py-1 transition-colors"
            :class="quarterIdx === i ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-runway-dark'"
            @click="quarterIdx = i; apply(); openFor = null"
          >
            {{ q }}
          </button>
        </div>
      </div>
    </div>

    <!-- Weekly calendar popover -->
    <div v-else-if="category === 'weekly'" class="relative">
      <button class="rounded bg-runway-dark px-2 py-1 text-slate-200" @click="togglePop('weekly')">
        {{ day }} {{ shortMonths[monthIdx] }} {{ year }} ▾
      </button>
      <div v-if="openFor === 'weekly'"
        class="absolute left-0 top-full z-30 mt-1 w-56 rounded-md border border-runway-border bg-runway-panel p-2 shadow-xl">
        <div class="mb-1 flex items-center justify-between">
          <button class="px-1 text-slate-400 hover:text-white" @click="navMonth(-1)">‹</button>
          <span class="text-xs font-semibold text-slate-200">{{ shortMonths[monthIdx] }} {{ year }}</span>
          <button class="px-1 text-slate-400 hover:text-white" @click="navMonth(1)">›</button>
        </div>
        <div class="grid grid-cols-7 gap-0.5 text-center text-[10px] text-slate-500">
          <span v-for="wd in weekdays" :key="wd">{{ wd }}</span>
        </div>
        <div class="grid grid-cols-7 gap-0.5">
          <span v-for="(blank, i) in leadingBlanks" :key="'b'+i" />
          <button
            v-for="d in days"
            :key="d"
            class="h-6 w-6 rounded text-[10px] transition-colors"
            :class="day === d ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-runway-dark'"
            @click="day = d; apply(); openFor = null"
          >
            {{ d }}
          </button>
        </div>
      </div>
    </div>

    <span v-if="category === 'weekly'" class="text-slate-500">+7d</span>
  </div>
</template>