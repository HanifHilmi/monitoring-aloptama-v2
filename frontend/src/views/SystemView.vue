<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '@/api/client'

const overview = ref(null)
const timer = ref(null)

async function load() {
  try { overview.value = await api.getStatusOverview() } catch { overview.value = null }
}
onMounted(() => {
  load()
  timer.value = setInterval(load, 15_000)
})
onBeforeUnmount(() => clearInterval(timer.value))
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold text-slate-200">System — CDPs</h1>
    <div class="grid gap-4 md:grid-cols-2">
      <div v-for="n in overview?.cdp_nodes || []" :key="n.id" class="panel">
        <div class="flex items-center justify-between">
          <span class="flex items-center gap-2">
            <span class="inline-block h-2.5 w-2.5 rounded-full" :class="n.status === 'online' ? 'bg-emerald-400' : 'bg-red-400'" />
            <span class="font-mono text-sm font-semibold text-slate-200">{{ n.name }}</span>
          </span>
          <span class="text-xs text-slate-400">{{ n.ip_address }}</span>
        </div>
        <div class="mt-2 text-xs text-slate-400">{{ n.role }} · {{ n.status }}</div>
      </div>
      <div v-if="!(overview?.cdp_nodes || []).length" class="panel text-center text-sm text-slate-500">
        No CDP nodes configured
      </div>
    </div>
  </div>
</template>