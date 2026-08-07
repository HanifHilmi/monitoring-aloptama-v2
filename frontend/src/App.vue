<script setup>
import { RouterLink, RouterView } from 'vue-router'

const nav = [
  { to: '/', label: 'Dashboard', exact: true },
  { to: '/runway/04', label: 'Runway 04' },
  { to: '/runway/22', label: 'Runway 22' },
  { to: '/runway/middle', label: 'Runway Middle' },
  { to: '/sla-ola', label: 'SLA / OLA' },
]

<template>
  <div class="min-h-screen">
    <header class="sticky top-0 z-40 border-b border-runway-border bg-runway-dark/95 backdrop-blur">
      <div class="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
        <RouterLink to="/" class="flex items-center gap-2 text-lg font-semibold text-white">
          <span class="inline-block h-3 w-3 rounded-sm bg-emerald-400" />
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
    <main class="mx-auto max-w-7xl px-4 py-6">
      <RouterView />
