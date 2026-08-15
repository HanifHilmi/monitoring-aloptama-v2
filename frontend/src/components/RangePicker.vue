<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { PRESETS, presetWindow, toUtcIsoFromLocal, toLocalInput } from '@/utils/range'

const props = defineProps({
  // { key, start, end } (ISO)
  modelValue: { type: Object, required: true },
})

const emit = defineEmits(['update:modelValue'])

const root = ref(null)
const open = ref(false)
const mode = ref(props.modelValue?.key || '3h')
const customStart = ref(toLocalInput(props.modelValue?.start || presetWindow('3h').start))
const customEnd = ref(toLocalInput(props.modelValue?.end || presetWindow('3h').end))
const customMsg = ref('')
const todayInput = new Date().toISOString().slice(0, 16)

const label = computed(() => {
  if (mode.value === 'custom') return 'Custom'
  const p = PRESETS.find((x) => x.key === mode.value)
  return p ? p.label : mode.value
})

function applyPreset(key) {
  const w = presetWindow(key)
  mode.value = w.key
  emit('update:modelValue', { key: w.key, start: w.start, end: w.end })
  open.value = false
}

function applyCustom() {
  const s = toUtcIsoFromLocal(customStart.value)
  const e = toUtcIsoFromLocal(customEnd.value)
  if (!s || !e) {
    customMsg.value = 'Select both a From and To time.'
    return
  }
  const sMs = Date.parse(s)
  let eMs = Date.parse(e)
  if (eMs <= sMs) {
    customMsg.value = 'To must be after From.'
    return
  }
  const MAX = 30 * 24 * 3600 * 1000
  if (eMs - sMs > MAX) {
    eMs = sMs + MAX
    customEnd.value = toLocalInput(new Date(eMs).toISOString())
    customMsg.value = 'Range capped to 30 days.'
  } else {
    customMsg.value = ''
  }
  emit('update:modelValue', {
    key: 'custom',
    start: new Date(sMs).toISOString(),
    end: new Date(eMs).toISOString(),
  })
  mode.value = 'custom'
  open.value = false
}

watch(() => props.modelValue, (v) => {
  if (!v) return
  if (v.key && v.key !== 'custom') mode.value = v.key
  if (v.start) customStart.value = toLocalInput(v.start)
  if (v.end) customEnd.value = toLocalInput(v.end)
}, { deep: true })

function onDocMouseDown(e) {
  if (root.value && !root.value.contains(e.target)) open.value = false
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
      <div class="flex w-16 flex-col gap-0.5">
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

      <!-- Precise custom range (date + time), beside the presets -->
      <div class="flex w-56 flex-col gap-1.5 border-l border-runway-border pl-3">
        <label class="text-[10px] uppercase tracking-wide text-slate-500">From</label>
        <input
          type="datetime-local"
          v-model="customStart"
          :max="customEnd"
          class="rounded bg-runway-dark px-1.5 py-1 text-[11px] text-slate-200"
          @change="customMsg = ''"
        />
        <label class="text-[10px] uppercase tracking-wide text-slate-500">To</label>
        <input
          type="datetime-local"
          v-model="customEnd"
          :max="todayInput"
          class="rounded bg-runway-dark px-1.5 py-1 text-[11px] text-slate-200"
          @change="customMsg = ''"
        />
        <p v-if="customMsg" class="text-[10px] text-amber-400">{{ customMsg }}</p>
        <button
          class="mt-1 rounded bg-sky-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-sky-700"
          @click="applyCustom"
        >
          Apply
        </button>
      </div>
    </div>
  </div>
</template>
