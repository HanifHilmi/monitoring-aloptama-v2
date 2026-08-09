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
const YEAR_MIN = 2026 // AWOS did not exist in 2025
const YEAR_MAX = 2099

const nowYear = new Date().getUTCFullYear()
const nowMonth = new Date().getUTCMonth()
const nowDay = new Date().getUTCDate()

const years = computed(() => {
  const list = []
  for (let y = YEAR_MIN; y <= YEAR_MAX; y++) list.push(y)
  return list
})
const shortMonths = MONTHS.map((m) => m.slice(0, 3))
const days = computed(() => daysInMonth(year.value, monthIdx.value))
const weekdays = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']
const leadingBlanks = computed(() => new Date(Date.UTC(year.value, monthIdx.value, 1)).getUTCDay())

function navPopYear(delta) {
  const idx = years.value.indexOf(year.value)
  const n = years.value[Math.max(0, Math.min(years.value.length - 1, idx + delta))]
  if (n !== undefined && n <= nowYear) { year.value = n; apply() }
}

// "This year so far" / "This quarter so far" / "This month so far" window.
function yearSoFar(y) {
  return {
    key: 'yearly', label: `Year ${y} (so far)`,
    start: new Date(Date.UTC(y, 0, 1)).toISOString(),
    end: new Date().toISOString(),
  }
}
function quarterSoFar(y, q) {
  return {
    key: 'quarterly', label: `${QUARTERS[q]} ${y} (so far)`,
    start: new Date(Date.UTC(y, q * 3, 1)).toISOString(),
    end: new Date().toISOString(),
  }
}
function monthSoFar(y, m) {
  return {
    key: 'monthly', label: `${MONTHS[m]} ${y} (so far)`,
    start: new Date(Date.UTC(y, m, 1)).toISOString(),
    end: new Date().toISOString(),
  }
}

function broadcast(win) { emit('update:modelValue', { ...win }) }

function apply() {
  if (category.value === 'yearly') {
    broadcast(year.value === nowYear ? yearSoFar(nowYear) : yearWindow(year.value))
  } else if (category.value === 'monthly') {
    broadcast(year.value === nowYear && monthIdx.value === nowMonth ? monthSoFar(nowYear, nowMonth) : monthWindow(year.value, monthIdx.value))
  } else if (category.value === 'quarterly') {
    const curQ = Math.floor(nowMonth / 3)
    broadcast(year.value === nowYear && quarterIdx.value === curQ ? quarterSoFar(nowYear, curQ) : quarterWindow(year.value, quarterIdx.value))
  } else {
    broadcast(weekWindow(year.value, monthIdx.value, day.value))
  }
}

function pickCategory(k) { category.value = k; openFor.value = null; apply() }

// "Current": end = now (month/quarter/year so far) + picker state follows.
function pickCurrent() {
  year.value = nowYear
  monthIdx.value = nowMonth
  quarterIdx.value = Math.floor(nowMonth / 3)
  day.value = nowDay
  if (category.value === 'yearly') broadcast(yearSoFar(nowYear))
  else if (category.value === 'monthly') broadcast(monthSoFar(nowYear, nowMonth))
  else if (category.value === 'quarterly') broadcast(quarterSoFar(nowYear, Math.floor(nowMonth / 3)))
  else broadcast(currentPeriod(category.value))
}

function togglePop(k) { openFor.value = openFor.value === k ? null : k }

function navMonth(delta) {
  let m = monthIdx.value + delta
  let y = year.value
  if (m < 0) { m = 11; y-- } else if (m > 11) { m = 0; y++ }
  if (y >= YEAR_MIN && y <= YEAR_MAX) { monthIdx.value = m; year.value = y; apply() }
}

function isMonthAvailable(y, m) { return y < nowYear || (y === nowYear && m <= nowMonth) }
function isDayDisabled(d) {
  return year.value > nowYear ||
    (year.value === nowYear && (monthIdx.value > nowMonth ||
      (monthIdx.value === nowMonth && d > nowDay)))
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

    <!-- Year dropdown: scrollable 8-per-view pages (native select covers it) -->
    <select v-model="year" @change="apply" class="rounded bg-runway-dark px-1.5 py-1 text-slate-200" size="1">
      <option v-for="y in years" :key="y" :value="y" :disabled="y > nowYear">{{ y }}</option>
    </select>

    <!-- Monthly popover -->
    <div v-if="category === 'monthly'" class="relative">
      <button class="rounded bg-runway-dark px-2 py-1 text-slate-200" @click="togglePop('monthly')">
        {{ MONTHS[monthIdx].slice(0, 3) }} ▾
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
            v-for="(m, i) in MONTHS"
            :key="m"
            class="rounded px-1 py-1 text-[11px] transition-colors"
            :disabled="!isMonthAvailable(year, i)"
            :class="monthIdx === i ? 'bg-sky-600 text-white' : isMonthAvailable(year, i) ? 'text-slate-300 hover:bg-runway-dark' : 'text-slate-700 cursor-not-allowed'"
            @click="monthIdx = i; apply(); openFor = null"
          >
            {{ m.slice(0, 3) }}
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
            :disabled="year === nowYear && i > Math.floor(nowMonth / 3)"
            :class="quarterIdx === i ? 'bg-sky-600 text-white' : (year === nowYear && i > Math.floor(nowMonth / 3)) ? 'text-slate-700 cursor-not-allowed' : 'text-slate-300 hover:bg-runway-dark'"
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
        {{ day }} {{ MONTHS[monthIdx].slice(0, 3) }} {{ year }} ▾
      </button>
      <div v-if="openFor === 'weekly'"
        class="absolute left-0 top-full z-30 mt-1 w-56 rounded-md border border-runway-border bg-runway-panel p-2 shadow-xl">
        <div class="mb-1 flex items-center justify-between">
          <button class="px-1 text-slate-400 hover:text-white" @click="navMonth(-1)">‹</button>
          <span class="text-xs font-semibold text-slate-200">{{ MONTHS[monthIdx].slice(0, 3) }} {{ year }}</span>
          <button class="px-1 text-slate-400 hover:text-white" :disabled="year === nowYear && monthIdx === nowMonth" @click="navMonth(1)">›</button>
        </div>
        <div class="grid grid-cols-7 gap-0.5 text-center text-[10px] text-slate-500">
          <span v-for="wd in ['Su','Mo','Tu','We','Th','Fr','Sa']" :key="wd">{{ wd }}</span>
        </div>
        <div class="grid grid-cols-7 gap-0.5">
          <span v-for="(blank, i) in leadingBlanks" :key="'b'+i" />
          <button
            v-for="d in days"
            :key="d"
            class="h-6 w-6 rounded text-[10px] transition-colors"
            :disabled="isDayDisabled(d)"
            :class="day === d ? 'bg-sky-600 text-white' : isDayDisabled(d) ? 'text-slate-700 cursor-not-allowed' : 'text-slate-300 hover:bg-runway-dark'"
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