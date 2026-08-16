// Composable for the recent custom-range history (persisted in localStorage).
// Clicking an entry re-applies that exact custom range immediately.

import { ref } from 'vue'

const KEY = 'monitoring_aloptama:recent_ranges'
const MAX = 5

function load() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '[]')
    return Array.isArray(raw) ? raw : []
  } catch {
    return []
  }
}

export function useRecentRanges() {
  const ranges = ref(load())

  function add(entry) {
    const next = [
      entry,
      ...ranges.value.filter((r) => r.start !== entry.start || r.end !== entry.end),
    ].slice(0, MAX)
    ranges.value = next
    try {
      localStorage.setItem(KEY, JSON.stringify(next))
    } catch {
      /* storage unavailable — history stays in memory */
    }
  }

  return { ranges, add }
}
