<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { api } from '@/api/client'

const nav = [
  { to: '/', label: 'Dashboard', exact: true },
  { to: '/runway/04', label: 'Runway 04' },
  { to: '/runway/22', label: 'Runway 22' },
  { to: '/runway/middle', label: 'Runway Middle' },
  { to: '/sla-ola', label: 'SLA / OLA' },
]

const health = ref(null)
const healthOpen = ref(false)
let healthTimer = null

const healthStatus = () => health.value?.status || 'unknown'
const healthClass = () => {
  const s = healthStatus()
  if (s === 'ok') return 'text-emerald-400'
  if (s === 'degraded') return 'text-amber-400'
  return 'text-red-400'
}
const dotClass = () => {
  const s = healthStatus()
  if (s === 'ok') return 'bg-emerald-400'
  if (s === 'degraded') return 'bg-amber-400'
  return 'bg-red-400'
}

async function loadHealth() {
  try {
    health.value = await api.getSystemHealth()
  } catch {
    health.value = null
  }
}

onMounted(() => {
  loadHealth()
  healthTimer = setInterval(loadHealth, 15_000)
})
onUnmounted(() => clearInterval(healthTimer))
</script>

<template>
  <div class="min-h-screen">
    <header class="sticky top-0 z-40 border-b border-runway-border bg-runway-dark/95 backdrop-blur">
      <div class="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
        <RouterLink to="/" class="flex items-center gap-2 text-lg font-semibold text-white">
          <span class="inline-block h-3 w-3 rounded-sm bg-emerald-400" />
          <span>AWOS Monitor</span>
        </RouterLink>
        <nav class="flex flex-1 items-center gap-1">
          <RouterLink
            v-for="item in nav"
            :key="item.to"
            :to="item.to"
            class="rounded-md px-3 py-1.5 text-sm text-slate-300 transition-colors hover:bg-runway-panel hover:text-white"
            active-class="bg-runway-panel text-white"
            :exact-active-class="item.exact ? 'bg-runway-panel text-white' : ''"
          >
            {{ item.label }}
          </RouterLink>
        </nav>
        <div class="relative flex items-center gap-2">
          <span class="inline-block h-2.5 w-2.5 rounded-full" :class="dotClass()" />
          <span class="text-xs font-semibold uppercase tracking-wide" :class="healthClass()">
            {{ healthStatus() }}
          </span>
          <button
            class="rounded-md border border-runway-border px-2 py-1 text-xs text-slate-300 hover:bg-runway-panel"
            @click="healthOpen = !healthOpen"
          >
            System
          </button>
          <div
            v-if="healthOpen"
            class="absolute right-0 top-full mt-2 w-72 rounded-lg border border-runway-border bg-runway-panel p-3 text-xs shadow-xl"
          >
            <div class="mb-2 flex items-baseline justify-between">
              <span class="font-semibold uppercase tracking-wide text-slate-400">System Health</span>
              <span class="text-[10px] text-slate-500">
                {{ health?.generated_at ? new Date(health.generated_at).toLocaleTimeString() : '—' }}
              </span>
            </div>
            <div v-if="health" class="space-y-2">
              <div class="flex justify-between">
                <span class="text-slate-400">API</span>
                <span :class="health.components?.api?.status === 'ok' ? 'text-emerald-400' : 'text-red-400'">
                  {{ health.components?.api?.status }}
                </span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">Database</span>
                <span :class="health.components?.database?.status === 'ok' ? 'text-emerald-400' : 'text-red-400'">
                  {{ health.components?.database?.status }}
                </span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">Worker</span>
                <span :class="health.components?.worker?.status === 'ok' ? 'text-emerald-400' : health.components?.worker?.status === 'unknown' ? 'text-amber-400' : 'text-red-400'">
                  {{ health.components?.worker?.status }}
                </span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">Telemetry rows</span>
                <span class="text-slate-200">{{ health.components?.data?.telemetry_rows ?? '—' }}</span>
              </div>
              <div class="border-t border-runway-border pt-2">
                <div class="mb-1 text-[10px] uppercase tracking-wide text-slate-500">CDP Config</div>
                <div class="text-[10px] text-slate-400">
                  CDP1: {{ health.config?.cdp1?.ip }} · {{ health.config?.cdp1?.mount_path }}
                </div>
                <div class="text-[10px] text-slate-400">
                  CDP2: {{ health.config?.cdp2?.ip }} · {{ health.config?.cdp2?.mount_path }}
                </div>
                <div class="text-[10px] text-slate-400">
                  Backfill: {{ health.config?.backfill_enabled ? 'on' : 'off' }} (from {{ health.config?.backfill_start }})
                </div>
              </div>
            </div>
            <div v-else class="py-3 text-center text-slate-500">Unreachable</div>
          </div>
        </div>
      </div>
    </header>
    <main class="mx-auto max-w-7xl px-4 py-6">
      <RouterView />
    </main>
  </div>
</template>