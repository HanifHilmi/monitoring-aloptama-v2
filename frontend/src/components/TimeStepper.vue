<script setup>
// 24-hour HH:mm stepper. No typing — the hour and minute cells are bumped
// with chevron buttons (0-23 / 0-59, wrapping). UTC-only.
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '00:00' },
})
const emit = defineEmits(['update:modelValue'])

const parts = computed(() => (props.modelValue || '00:00').split(':'))
const hour = computed(() => Number(parts.value[0]) || 0)
const minute = computed(() => Number(parts.value[1]) || 0)
const pad = (n) => String(n).padStart(2, '0')

function setHour(delta) {
  emit('update:modelValue', `${pad((hour.value + delta + 24) % 24)}:${pad(minute.value)}`)
}
function setMinute(delta) {
  emit('update:modelValue', `${pad(hour.value)}:${pad((minute.value + delta + 60) % 60)}`)
}
</script>

<template>
  <div class="flex items-center gap-0.5 font-mono">
    <div class="stepper-unit">
      <button class="stepper-btn" aria-label="Increase hour" @click="setHour(1)"><span class="chev up" /></button>
      <span class="stepper-val">{{ pad(hour) }}</span>
      <button class="stepper-btn" aria-label="Decrease hour" @click="setHour(-1)"><span class="chev down" /></button>
    </div>
    <span class="text-slate-600">:</span>
    <div class="stepper-unit">
      <button class="stepper-btn" aria-label="Increase minute" @click="setMinute(1)"><span class="chev up" /></button>
      <span class="stepper-val">{{ pad(minute) }}</span>
      <button class="stepper-btn" aria-label="Decrease minute" @click="setMinute(-1)"><span class="chev down" /></button>
    </div>
  </div>
</template>

<style scoped>
.stepper-unit {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.stepper-val {
  background: #0b1220;
  color: #e2e8f0;
  font-size: 11px;
  line-height: 1;
  padding: 4px 5px;
  border-radius: 4px;
}
.stepper-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 14px;
  color: #94a3b8;
  border-radius: 3px;
}
.stepper-btn:hover {
  background: #1e2a45;
  color: #e2e8f0;
}
.chev {
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
}
.chev.up {
  border-bottom: 5px solid currentColor;
}
.chev.down {
  border-top: 5px solid currentColor;
}
</style>
