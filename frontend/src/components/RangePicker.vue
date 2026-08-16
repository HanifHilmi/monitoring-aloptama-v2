<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import TimeStepper from '@/components/TimeStepper.vue'
import { useRecentRanges } from '@/composables/useRecentRanges'
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

// Recent custom ranges (persisted history, click to re-apply).
const { ranges, add } = useRecentRanges()

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

// Apply the custom range: validate, clamp to MAX_MS, emit, save to Recent,
// and close. This is the only place a custom range triggers a data load.
function applyCustom() {
  const s = combineUtc(customStartDate.value, customStartTime.value)
  const e = combineUtc(customEndDate.value, customEndTime.value)
  if (!s || !e) {
    customMsg.value = 'Select both a From and To time.'
    return
  }
  const sMs = s.getTime()
  let eMs = e.getTime()
  if (eMs <= sMs) {
    customMsg.value = 'To must be after From.'
    return
  }
  if (eMs - sMs > MAX_MS) {
    eMs = sMs + MAX_MS
    customEndDate.value = new Date(eMs).toISOString().slice(0, 10)
    customEndTime.value = new Date(eMs).toISOString().slice(11, 16)
    customMsg.value = 'Range capped to 31 days.'
  } else {
    customMsg.value = ''
  }
  const entry = {
    start: new Date(sMs).toISOString(),
    end: new Date(eMs).toISOString(),
  }
  entry.label = `${entry.start.slice(0, 10)} ${entry.start.slice(11, 16)} → ${entry.end.slice(0, 10)} ${entry.end.slice(11, 16)}`
  emit('update:modelValue', { key: 'custom', start: entry.start, end: entry.end })
  add(entry)
  mode.value = 'custom'
  open.value = false
}

// Re-apply a range from the Recent list (loads immediately).
function applyRecent(r) {
  customStartDate.value = r.start.slice(0, 10)
  customStartTime.value = r.start.slice(11, 16)
  customEndDate.value = r.end.slice(0, 10)
  customEndTime.value = r.end.slice(11, 16)
  emit('update:modelValue', { key: 'custom', start: r.start, end: r.end })
  mode.value = 'custom'
  customMsg.value = ''
  open.value = false
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

// Picking From then To fills the date fields and closes the calendar. The
// data does NOT load here — the operator reviews times and hits Apply Range.
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
  selStart.value = s
  selEnd.value = e
  customStartDate.value = s
  customEndDate.value = e
  calMode.value = false
  customMsg.value = ''
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

      <!-- Custom range: 24h steppers + shared calendar + Apply + Recent -->
      <div class="flex w-64 flex-col gap-1.5 border-l border-runway-border pl-3">
        <template v-if="!calMode">
          <label class="text-[10px] uppercase tracking-wide text-slate-500">From</label>
          <div class="flex items-center gap-1">
            <button
              class="shrink-0 rounded bg-runway-dark px-1.5 py-1 text-[11px] text-slate-300 hover:bg-runway-border"
              title="Pick From date"
              @click="openCalendar"
            >📅</button>
            <button
              class="flex-1 rounded bg-runway-dark px-1.5 py-1 text-left font-mono text-[11px] text-slate-200 transition-colors hover:bg-runway-border"
              title="Pick From date"
              @click="openCalendar"
            >{{ customStartDate }}</button>
            <TimeStepper v-model="customStartTime" />
          </div>

          <label class="text-[10px] uppercase tracking-wide text-slate-500">To</label>
          <div class="flex items-center gap-1">
            <button
              class="shrink-0 rounded bg-runway-dark px-1.5 py-1 text-[11px] text-slate-300 hover:bg-runway-border"
              title="Pick To date"
              @click="openCalendar"
            >📅</button>
            <button
              class="flex-1 rounded bg-runway-dark px-1.5 py-1 text-left font-mono text-[11px] text-slate-200 transition-colors hover:bg-runway-border"
              title="Pick To date"
              @click="openCalendar"
            >{{ customEndDate }}</button>
            <TimeStepper v-model="customEndTime" />
          </div>

          <p v-if="customMsg" class="text-[10px] text-amber-400">{{ customMsg }}</p>

          <button
            class="mt-1 rounded bg-sky-600 px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-sky-700"
            @click="applyCustom"
          >
            Apply Range
          </button>

          <!-- Recent custom ranges (click to re-apply immediately) -->
          <div v-if="ranges.length" class="mt-1.5 border-t border-runway-border pt-1.5">
            <div class="mb-1 text-[10px] uppercase tracking-wide text-slate-500">Recent</div>
            <div class="flex flex-col gap-0.5">
              <button
                v-for="r in ranges"
                :key="r.label"
                class="rounded bg-runway-dark px-1.5 py-1 text-left font-mono text-[10px] text-slate-300 transition-colors hover:bg-runway-border"
                @click="applyRecent(r)"
              >{{ r.label }}</button>
            </div>
          </div>
        </template>

        <!-- Shared calendar: pick From then To (loads only on Apply) -->
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
          <div class="mt-1 flex items-center justify-between border-t border-runway-border pt-1 text-[10px] text-slate-500">
            <span>Pick From then To (max 31 days)</span>
            <button class="text-sky-400 hover:text-white" @click="calMode = false">← Back</button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
