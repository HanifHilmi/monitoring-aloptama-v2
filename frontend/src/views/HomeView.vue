<script setup>
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-lg font-semibold text-slate-200">Dashboard</h1>
    <p class="text-xs text-slate-500">Summary of all monitored systems.</p>
    <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <RouterLink to="/cat3" class="panel block hover:border-emerald-500/50">
        <div class="text-sm font-semibold text-slate-200">AWOS CAT. III</div>
        <div class="text-xs text-slate-500">SLA/OLA · CDP Uptime · Runways · METAR</div>
      </RouterLink>
      <div class="panel opacity-60">
        <div class="text-sm font-semibold text-slate-400">AWOS CAT. I</div>
        <div class="text-xs text-slate-500">Coming soon</div>
      </div>
      <div class="panel opacity-60">
        <div class="text-sm font-semibold text-slate-400">AWS Digitalisasi</div>
        <div class="text-xs text-slate-500">Coming soon</div>
      </div>
    </div>
  </div>
</template>