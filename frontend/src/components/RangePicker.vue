<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { PRESETS, presetWindow, combineUtc, MAX_RANGE_MS } from '@/utils/range'

const props = defineProps({
  // { key, start, end } (ISO)
  modelValue: { type: Object, required: true },
})

const emit = defineEmits(['update:modelValue'])

const pad = (n) => String(n).padStart(2, '0')
const MAX_MS = MAX_RANGE_MS
const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

const root = ref(null)
const open = ref(false)
const mode = ref(props.modelValue?.key || '3h')

// Custom range state (date 'YYYY-MM-DD' + time 'HH:mm', all UTC).
const customStartDate = ref('')
const customStartTime = ref('')
const customEndDate = ref('')
const customEndTime = ref('')
const customMsg = ref('')

// Shared calendar range picker (one popover for both From and To).
const calMode = ref(false)
const calYear = ref(new Date().getUTCFullYear())
const calMonth = ref(new Date().getUTCMonth())
const selStart = ref('')
const selEnd = ref('')

const label = computed(() => {
  if (mode.value === 'custom') return 'Custom'
  const p = PRESETS.find((x) => x.key === mode.value)
  return p ? p.label : mode.value
})

const calLeading = computed(() => new Date(Date.UTC(calYear.value, calMonth.value, 1)).getUTCDay())
const calDays = computed(() => new Date(Date.UTC(calYear.value, calMonth.value + 1, 0)).getUTCDate())
const calMonthName = computed(() => MONTHS[calMonth.value])

const nowYear = new Date().getUTCFullYear()
const nowMonth = new Date().getUTCMonth()
const nowDay = new Date().getUTCDate()

function initFromModel(v) {
  if (!v) return
  if (v.key && v.key !== 'custom') mode.value = v.key
  if (v.start) {
    customStartDate.value = v.start.slice(0, 10)
    customStartTime.value = v.start.slice(11, 16)
  }
  if (v.end) {
    customEndDate.value = v.end.slice(0, 10)
    customEndTime.value = v.end.slice(11, 16)
  }
}

function applyPreset(key) {
  const w = presetWindow(key)
  mode.value = w.key
  emit('update:modelValue', { key: w.key, start: w.start, end: w.end })
  open.value = false
}

function syncCustom() {
  const s = combineUtc(customStartDate.value, customStartTime.value)
  const e = combineUtc(customEndDate.value, customEndTime.value)
  if (!s || !e) {
    customMsg.value = 'Select both a From and To time.'
    return false
  }
  const sMs = s.getTime()
  let eMs = e.getTime()
  if (eMs <= sMs) {
    customMsg.value = 'To must be after From.'
    return false
  }
  if (eMs - sMs > MAX_MS) {
    eMs = sMs + MAX_MS
    customEndDate.value = new Date(eMs).toISOString().slice(0, 10)
    customEndTime.value = new Date(eMs).toISOString().slice(11, 16)
    customMsg.value = 'Range capped to 31 days.'
  } else {
    customMsg.value = ''
  }
  emit('update:modelValue', {
    key: 'custom',
    start: new Date(sMs).toISOString(),
    end: new Date(eMs).toISOString(),
  })
  mode.value = 'custom'
  return true
}

// ---- Shared calendar range picker ----
function openCalendar() {
  const anchor = customStartDate.value || new Date().toISOString().slice(0, 10)
  calYear.value = Number(anchor.slice(0, 4))
  calMonth.value = Number(anchor.slice(5, 7)) - 1
  selStart.value = customStartDate.value
  selEnd.value = customEndDate.value
  customMsg.value = ''
  calMode.value = true
}

function navCal(delta) {
  let m = calMonth.value + delta
  let y = calYear.value
  if (m < 0) { m = 11; y-- }
  else if (m > 11) { m = 0; y++ }
  if (y < 2026) return
  if (y > nowYear || (y === nowYear && m > nowMonth)) return
  calMonth.value = m
  calYear.value = y
}

function isCalDayDisabled(d) {
  return calYear.value > nowYear ||
    (calYear.value === nowYear && (calMonth.value > nowMonth ||
      (calMonth.value === nowMonth && d > nowDay)))
}

function isInSel(d) {
  const dateStr = `${calYear.value}-${pad(calMonth.value + 1)}-${pad(d)}`
  if (!selStart.value) return false
  const s = selStart.value
  const e = selEnd.value || s
  return dateStr >= (s < e ? s : e) && dateStr <= (s < e ? e : s)
}

function pickCalDay(d) {
  const dateStr = `${calYear.value}-${pad(calMonth.value + 1)}-${pad(d)}`
  if (!selStart.value || (selStart.value && selEnd.value)) {
    selStart.value = dateStr
    selEnd.value = ''
    return
  }
  let s = selStart.value
  let e = dateStr
  if (e < s) { const t = s; s = e; e = t }
  const eMs = Date.parse(`${e}T00:00:00Z`)
  if (eMs - Date.parse(`${s}T00:00:00Z`) > MAX_MS) {
    e = new Date(Date.parse(`${s}T00:00:00Z`) + MAX_MS).toISOString().slice(0, 10)
    customMsg.value = 'Range capped to 31 days.'
  }
  selStart.value = s
  selEnd.value = e
  customStartDate.value = s
  customEndDate.value = e
  calMode.value = false
  if (syncCustom()) open.value = false
}

watch(() => props.modelValue, (v) => initFromModel(v), { deep: true })
initFromModel(props.modelValue || presetWindow('3h'))

function onDocMouseDown(e) {
  if (root.value && !root.value.contains(e.target)) {
    open.value = false
    calMode.value = false
  }
}
onMounted(() => document.addEventListener('mousedown', onDocMouseDown))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocMouseDown))
</script>

<template>
  <div ref="root" class="relative">
    <button
      class="rounded border border-runway-border bg-runway-panel px-2 py-1 text-xs text-slate-200 hover:bg-runway-dark"
      @click="open = !open"
    >
      {{ label }} ▾
    </button>
    <div
      v-if="open"
      class="absolute right-0 top-full z-30 mt-1 flex gap-3 rounded-md border border-runway-border bg-runway-panel p-2 shadow-xl"
    >
      <!-- Vertical quick presets -->
      <div class="flex w-28 flex-col gap-0.5">
        <button
          v-for="p in PRESETS"
          :key="p.key"
          class="rounded px-2 py-1 text-left text-[11px] transition-colors"
          :class="mode === p.key ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-runway-dark'"
          @click="applyPreset(p.key)"
        >
          {{ p.label }}
        </button>
      </div>

      <!-- Custom range: date+time (24h) with a shared calendar range popover -->
      <div class="flex w-60 flex-col gap-1.5 border-l border-runway-border pl-3">
        <template v-if="!calMode">
          <label class="text-[10px] uppercase tracking-wide text-slate-500">From</label>
          <div class="flex items-center gap-1">
            <button
              class="shrink-0 rounded bg-runway-dark px-1.5 py-1 text-[11px] text-slate-300 hover:bg-runway-border"
              title="Pick range"
              @click="openCalendar"
            >📅</button>
            <span class="flex-1 rounded bg-runway-dark px-1.5 py-1 font-mono text-[11px] text-slate-200">{{ customStartDate }}</span>
            <input
              type="time"
              v-model="customStartTime"
              @change="syncCustom"
              class="w-[4.6rem] rounded bg-runway-dark px-1 py-1 text-[11px] text-slate-200"
            />
          </div>
          <label class="text-[10px] uppercase tracking-wide text-slate-500">To</label>
          <div class="flex items-center gap-1">
            <button
              class="shrink-0 rounded bg-runway-dark px-1.5 py-1 text-[11px] text-slate-300 hover:bg-runway-border"
              title="Pick range"
              @click="openCalendar"
            >📅</button>
            <span class="flex-1 rounded bg-runway-dark px-1.5 py-1 font-mono text-[11px] text-slate-200">{{ customEndDate }}</span>
            <input
              type="time"
              v-model="customEndTime"
              @change="syncCustom"
              class="w-[4.6rem] rounded bg-runway-dark px-1 py-1 text-[11px] text-slate-200"
            />
          </div>
          <p v-if="customMsg" class="text-[10px] text-amber-400">{{ customMsg }}</p>
        </template>

        <!-- Shared calendar: pick From then To, applies immediately -->
        <template v-else>
          <div class="flex items-center justify-between">
            <button class="px-1 text-slate-400 hover:text-white" @click="navCal(-1)">‹</button>
            <span class="text-[11px] font-semibold text-slate-200">{{ calMonthName }} {{ calYear }}</span>
            <button
              class="px-1 text-slate-400 hover:text-white disabled:opacity-40"
              :disabled="calYear === nowYear && calMonth === nowMonth"
              @click="navCal(1)"
            >›</button>
          </div>
          <div class="grid grid-cols-7 gap-0.5 text-center text-[10px] text-slate-500">
            <span v-for="wd in WEEKDAYS" :key="wd">{{ wd }}</span>
          </div>
          <div class="grid grid-cols-7 gap-0.5">
            <span v-for="(b, i) in calLeading" :key="'b' + i" />
            <button
              v-for="d in calDays"
              :key="d"
              class="h-6 w-6 rounded text-[10px] transition-colors"
              :disabled="isCalDayDisabled(d)"
              :class="isInSel(d) ? 'bg-sky-600 text-white' : isCalDayDisabled(d) ? 'text-slate-700 cursor-not-allowed' : 'text-slate-300 hover:bg-runway-dark'"
              @click="pickCalDay(d)"
            >{{ d }}</button>
          </div>
          <div class="mt-1 border-t border-runway-border pt-1 text-[10px] text-slate-500">
            Pick From then To (max 31 days)
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
