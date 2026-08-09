<script setup>
import { ref, watch } from 'vue'
import { PRESETS, presetWindow, clampCustom } from '@/utils/range'

const props = defineProps({
  // { key, start, end } (ISO)
  modelValue: { type: Object, required: true },
})

const emit = defineEmits(['update:modelValue'])

const mode = ref(props.modelValue?.key || 'month')
const customStart = ref((props.modelValue?.start || presetWindow('month').start).slice(0, 10))
const customEnd = ref((props.modelValue?.end || presetWindow('month').end).slice(0, 10))

function applyPreset(key) {
  const w = presetWindow(key)
  emit('update:modelValue', { key: w.key, start: w.start, end: w.end })
}

function applyCustom() {
  const start = new Date(`${customStart.value}T00:00:00Z`).toISOString()
  const end = new Date(`${customEnd.value}T23:59:59Z`).toISOString()
  const c = clampCustom(start, end)
  const normalized = { key: 'custom', ...c }
  emit('update:modelValue', normalized)
  mode.value = 'custom'
}

watch(() => props.modelValue, (v) => {
  if (v?.key && v.key !== 'custom') mode.value = v.key
}, { deep: true })
</script>

<template>
  <div class="flex items-center gap-1 rounded border border-runway-border bg-runway-panel p-1 text-xs">
    <button
      v-for="p in PRESETS"
      :key="p.key"
      class="rounded px-2 py-1 transition-colors"
      :class="mode === p.key ? 'bg-sky-600 text-white' : 'text-slate-300 hover:bg-runway-dark'"
      @click="mode = p.key; applyPreset(p.key)"
    >
      {{ p.label }}
    </button>
    <span class="mx-1 h-4 w-px bg-runway-border" />
    <input
      type="date"
      v-model="customStart"
      class="rounded bg-runway-dark px-1 py-0.5 text-slate-200"
      :max="customEnd"
      @change="applyCustom"
    />
    <span class="text-slate-500">→</span>
    <input
      type="date"
      v-model="customEnd"
      class="rounded bg-runway-dark px-1 py-0.5 text-slate-200"
      :max="new Date().toISOString().slice(0, 10)"
      @change="applyCustom"
    />
  </div>
</template>