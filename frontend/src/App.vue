<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { api } from '@/api/client'
import { i18n, LOCALES } from '@/i18n'

// ---- Collapsible top bar navigation (routing plan) ----
const navGroups = [
  { to: '/', key: 'dashboard' },
  {
    key: 'cat3',
    to: '/cat3',
    children: [
      { to: '/cat3/system', key: 'system' },
      { to: '/cat3/runway/04', key: 'runway04' },
      { to: '/cat3/runway/middle', key: 'runwayMiddle' },
      { to: '/cat3/runway/22', key: 'runway22' },
      { to: '/cat3/metar', key: 'metar' },
    ],
  },
]

// ---- Localization (labels only; UTC never affected) ----
const locale = ref('en')
const t = computed(() => i18n(locale.value))
function toggleLocale() {
  const i = LOCALES.indexOf(locale.value)
  locale.value = LOCALES[(i + 1) % LOCALES.length]
}

// Collapse state for the group menu.
const openMenu = ref(null)
function toggleMenu(key) {
  openMenu.value = openMenu.value === key ? null : key
}

// ---- System health (green dot expands) ----
const health = ref(null)
const healthOpen = ref(false)
let healthTimer = null
const healthStatus = () => health.value?.status || 'unknown'
const dotClass = () => (healthStatus() === 'ok' ? 'bg-emerald-400' : healthStatus() === 'degraded' ? 'bg-amber-400' : 'bg-red-400')
async function loadHealth() {
  try { health.value = await api.getSystemHealth() } catch { health.value = null }
}

// ---- Settings (gear) ----
const settingsOpen = ref(false)
const settingTab = ref('backfill')
const backfillLog = ref('')
const backfilling = ref('')

async function runBackfill(kind) {
  if (backfilling.value) return
  backfilling.value = kind
  backfillLog.value = ''
  const onLine = (l) => { backfillLog.value += l + '\n' }
  try {
    if (kind === 'cdp') await api.backfillCdp(onLine)
    else await api.backfillDcp(onLine)
  } catch (e) {
    backfillLog.value += 'ERROR: ' + e.message + '\n'
  } finally {
    backfilling.value = ''
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
      <div class="mx-auto flex max-w-7xl items-center gap-5 px-4 py-3">
        <RouterLink to="/" class="flex items-center gap-2 text-lg font-semibold text-white">
          <span class="inline-block h-3 w-3 rounded-sm bg-emerald-400" />
          <span>AWOS Monitor</span>
        </RouterLink>
        <nav class="flex flex-1 items-center gap-1">
          <RouterLink
            to="/"
            class="rounded-md px-3 py-1.5 text-sm text-slate-300 transition-colors hover:bg-runway-panel hover:text-white"
            active-class="bg-runway-panel text-white"
            exact-active-class="bg-runway-panel text-white"
          >
            {{ t('dashboard') }}
          </RouterLink>
          <div
            v-for="g in navGroups.filter((x) => x.children)"
            :key="g.key"
            class="relative"
          >
            <button
              class="rounded-md px-3 py-1.5 text-sm text-slate-300 transition-colors hover:bg-runway-panel hover:text-white"
              @click="toggleMenu(g.key)"
            >
              {{ t(g.key) }} ▾
            </button>
            <div
              v-if="openMenu === g.key"
              class="absolute left-0 top-full z-30 mt-1 w-52 rounded-md border border-runway-border bg-runway-panel p-1 shadow-xl"
            >
              <RouterLink
                v-for="c in g.children"
                :key="c.to"
                :to="c.to"
                class="block rounded px-2 py-1.5 text-xs text-slate-300 transition-colors hover:bg-runway-dark hover:text-white"
                active-class="bg-runway-dark text-white"
              >
                {{ t(c.key) }}
              </RouterLink>
            </div>
          </div>
          <button
            class="rounded-md border border-runway-border px-2 py-1 text-xs text-slate-300 hover:bg-runway-panel"
            :title="t('comingSoon')"
            @click="toggleLocale"
          >
            {{ locale.toUpperCase() }}
          </button>
        </nav>
        <div class="relative flex items-center gap-2">
          <!-- Green status dot expands on hover to show system health -->
          <span
            class="inline-block h-2.5 w-2.5 rounded-full cursor-pointer"
            :class="dotClass()"
            @mouseenter="healthOpen = true"
            @mouseleave="healthOpen = false"
          />
          <div
            v-if="healthOpen && health"
            class="absolute right-0 top-full mt-2 w-60 rounded-lg border border-runway-border bg-runway-panel p-3 text-xs shadow-xl"
          >
            <div class="space-y-1">
              <div class="flex justify-between"><span class="text-slate-400">API</span><span class="text-emerald-400">{{ health.components?.api?.status }}</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Database</span><span :class="health.components?.database?.status === 'ok' ? 'text-emerald-400' : 'text-red-400'">{{ health.components?.database?.status }}</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Worker</span><span :class="health.components?.worker?.status === 'ok' ? 'text-emerald-400' : 'text-amber-400'">{{ health.components?.worker?.status }}</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Telemetry rows</span><span class="text-slate-200">{{ health.components?.data?.telemetry_rows ?? '—' }}</span></div>
            </div>
          </div>
          <!-- Gear settings (contains Backfill) -->
          <button
            class="rounded-md border border-runway-border px-2 py-1 text-xs text-slate-300 hover:bg-runway-panel"
            @click="settingsOpen = !settingsOpen"
          >
            ⚙ Settings
          </button>
        </div>
      </div>
    </header>

    <!-- Settings drawer -->
    <div v-if="settingsOpen" class="fixed inset-0 z-50 flex justify-end bg-black/50" @click.self="settingsOpen = false">
      <div class="h-full w-full max-w-md overflow-y-auto border-l border-runway-border bg-runway-dark p-5">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="text-lg font-semibold text-slate-200">Settings</h2>
          <button class="text-slate-400 hover:text-white" @click="settingsOpen = false">✕</button>
        </div>
        <div class="mb-4 flex gap-2">
          <button
            class="rounded px-3 py-1 text-xs"
            :class="settingTab === 'backfill' ? 'bg-runway-panel text-white' : 'text-slate-400'"
            @click="settingTab = 'backfill'"
          >Backfill</button>
        </div>

        <div v-if="settingTab === 'backfill'">
          <div class="mb-3 text-xs text-slate-400">Backfill historical data into the database from the CDP oneminute logs.</div>
          <div class="flex gap-2">
            <button
              class="rounded bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
              :disabled="!!backfilling"
              @click="runBackfill('cdp')"
            >Backfill CDP uptime</button>
            <button
              class="rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
              :disabled="!!backfilling"
              @click="runBackfill('dcp')"
            >Backfill DCP Data</button>
          </div>
          <div class="mt-4">
            <div class="mb-1 text-xs text-slate-400">Log</div>
            <pre class="h-72 overflow-auto rounded border border-runway-border bg-black/40 p-2 text-[10px] leading-relaxed text-emerald-300">{{ backfillLog || '— idle —' }}</pre>
          </div>
        </div>
      </div>
    </div>

    <main class="mx-auto max-w-7xl px-4 py-6">
      <RouterView />
    </main>
  </div>
</template>