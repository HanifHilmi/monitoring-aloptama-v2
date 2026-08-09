<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '@/api/client'
import { tooltipTime } from '@/utils/timezone'

const props = defineProps({})
const rows = ref([])
const year = ref(new Date().getUTCFullYear())
const loading = ref(false)
const Y_MIN = 2026
const Y_MAX = new Date().getUTCFullYear()

async function load() {
  loading.value = true
  try {
    const d = await api.getDowntimeMap(year.value)
    rows.value = d.rows || []
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
}

const cells = computed(() => {
  const map = {}
  for (const r of rows.value) map[r.day] = r.downtime_minutes
  return map
})

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const monthWeeks = computed(() => {
  const out = []
  for (let m = 0; m < 12; m++) {
    const first = new Date(Date.UTC(year.value, m, 1))
    const daysInMonth = new Date(Date.UTC(year.value, m + 1, 0)).getUTCDate()
    const lead = first.getUTCDay()
    const cellsArr = []
    for (let i = 0; i < lead; i++) cellsArr.push(null)
    for (let d = 1; d <= daysInMonth; d++) {
      const iso = `${year.value}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
      // don't render future days in the current year
      const dateObj = new Date(Date.UTC(year.value, m, d))
      const now = new Date()
      const future = year.value > now.getUTCFullYear() ||
        (year.value === now.getUTCFullYear() && (m > now.getUTCMonth() || (m === now.getUTCMonth() && d > now.getUTCDate())))
      cellsArr.push({ d, iso, minutes: cells.value[iso] ?? 0, future })
    }
    while (cellsArr.length % 7 !== 0) cellsArr.push(null)
    out.push({ name: MONTHS[m], cells: cellsArr })
  }
  return out
})

const maxMinutes = computed(() => {
  let mx = 0
  for (const r of rows.value) mx = Math.max(mx, r.downtime_minutes)
  return mx || 1
})

// hotter red for more downtime
function color(minutes) {
  if (minutes <= 0) return '#1e293b'
  const t = Math.min(1, minutes / (maxMinutes.value * 2))
  const r = 239 + Math.round((255 - 239) * t)
  const g = 68 - Math.round(68 * t)
  const b = 68 - Math.round(68 * t)
  return `rgb(${r},${g},${b})`
}

function onDocKey() {}

onMounted(load)
</script>

<template>
  <div class="panel">
    <div class="mb-3 flex items-center justify-between">
      <h3 class="text-xs font-semibold uppercase tracking-wide text-slate-500">Downtime Map (minutes/day)</h3>
      <select v-model="year" @change="load" class="rounded border border-runway-border bg-runway-panel px-2 py-1 text-xs text-slate-200">
        <option v-for="y in Y_MAX - Y_MIN + 1" :key="y" :value="Y_MAX - (y - 1)">{{ Y_MAX - (y - 1) }}</option>
      </select>
    </div>
    <div v-if="loading" class="py-10 text-center text-xs text-slate-500">Loading…</div>
    <div v-else class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      <div v-for="mo in monthWeeks" :key="mo.name" class="rounded bg-runway-dark p-2">
        <div class="mb-1 text-[11px] font-semibold text-slate-400">{{ mo.name }}</div>
        <div class="grid grid-cols-7 gap-0.5">
          <span v-for="(c, i) in mo.cells" :key="i" class="block" style="font-size:0">
            <span
              v-if="c"
              class="inline-block h-3 w-3 rounded-sm"
              :style="{ backgroundColor: c.future ? '#111827' : color(c.minutes) }"
              :title="`${c.iso}: ${c.minutes} min`"
            />
          </span>
        </div>
      </div>
    </div>
    <div class="mt-2 flex items-center gap-1 text-[10px] text-slate-500">
      <span>Less</span>
      <span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:#1e293b" />
      <span v-for="t in [0.2,0.4,0.6,0.8,1]" :key="t" class="inline-block h-2.5 w-2.5 rounded-sm" :style="{ backgroundColor: color(maxMinutes * t) }" />
      <span>More</span>
    </div>
  </div>
</template>