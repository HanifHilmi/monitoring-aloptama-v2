<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { PRESETS, presetWindow, clampCustom } from '@/utils/range'

const props = defineProps({
  // { key, start, end } (ISO)
  modelValue: { type: Object, required: true },
})

const emit = defineEmits(['update:modelValue'])

const root = ref(null)
const open = ref(false)
const mode = ref(props.modelValue?.key || '3h')
const customStart = ref((props.modelValue?.start || presetWindow('3h').start).slice(0, 10))
const customEnd = ref((props.modelValue?.end || presetWindow('3h').end).slice(0, 10))
const todayIso = new Date().toISOString().slice(0, 10)

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
  const start = new Date(`${customStart.value}T00:00:00Z`).toISOString()
  const end = new Date(`${customEnd.value}T23:59:59Z`).toISOString()
  const c = clampCustom(start, end)
  const normalized = { key: 'custom', ...c }
  emit('update:modelValue', normalized)
  mode.value = 'custom'
  open.value = false
}

watch(() => props.modelValue, (v) => {
  if (!v) return
  if (v.key && v.key !== 'custom') mode.value = v.key
  if (v.start) customStart.value = v.start.slice(0, 10)
  if (v.end) customEnd.value = v.end.slice(0, 10)
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
      class="absolute right-0 top-full z-30 mt-1 w-64 rounded-md border border-runway-border bg-runway-panel p-2 shadow-xl"
    >
      <div class="grid grid-cols-3 gap-1">
        <button
          v-for="p in PRESETS"
          :key="p.key"
          class="rounded px-2 py-1 text-[11px] transition-colors"
          :class="mode === p.key ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-runway-dark'"
          @click="applyPreset(p.key)"
        >
          {{ p.label }}
        </button>
      </div>
      <div class="mt-2 flex items-center gap-1 border-t border-runway-border pt-2">
        <input
          type="date"
          v-model="customStart"
          :max="customEnd"
          class="w-28 rounded bg-runway-dark px-1 py-0.5 text-[11px] text-slate-200"
          @change="applyCustom"
        />
        <span class="text-slate-500">→</span>
        <input
          type="date"
          v-model="customEnd"
          :max="todayIso"
          class="w-28 rounded bg-runway-dark px-1 py-0.5 text-[11px] text-slate-200"
          @change="applyCustom"
        />
      </div>
      <div class="mt-1 text-[10px] text-slate-500">Custom range max 30 days</div>
    </div>
  </div>
</template>
