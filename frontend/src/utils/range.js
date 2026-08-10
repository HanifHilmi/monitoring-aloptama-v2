// Shared time-range model. All timestamps computed in UTC.

export const PRESETS = [
  { key: '15m', label: '15 Minutes' },
  { key: '30m', label: '30 Minutes' },
  { key: '1h', label: '1 Hour' },
  { key: '3h', label: '3 Hours' },
  { key: '12h', label: '12 Hours' },
  { key: 'today', label: 'Today' },
  { key: '3d', label: '3 Days Ago' },
  { key: 'week', label: 'This Week' },
  { key: 'month', label: 'This Month' },
]

export const MAX_RANGE_MS = 31 * 24 * 3600 * 1000 // 1 month max

export function presetWindow(key) {
  const now = new Date()
  if (key === 'today') {
    const s = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, 0, 0, 0))
    return { start: s.toISOString(), end: now.toISOString(), key }
  }
  const MIN = 60 * 1000
  const HOUR = 60 * MIN
  const DAY = 24 * HOUR
  const mins = { '15m': 15, '30m': 30, '1h': 60, '3h': 180, '12h': 720 }[key]
  if (mins != null) {
    return {
      start: new Date(now.getTime() - mins * MIN).toISOString(),
      end: now.toISOString(),
      key,
    }
  }
  const days = key === '3d' ? 3 : key === 'week' ? 7 : 30
  return {
    start: new Date(now.getTime() - days * DAY).toISOString(),
    end: now.toISOString(),
    key,
  }
}

export function clampCustom(startIso, endIso) {
  const s = new Date(startIso)
  const e = new Date(endIso)
  if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return { start: startIso, end: endIso }
  if (s >= e) {
    return { start: new Date(e.getTime() - 24 * 3600 * 1000).toISOString(), end: e.toISOString() }
  }
  if (e.getTime() - s.getTime() > MAX_RANGE_MS) {
    return { start: new Date(e.getTime() - MAX_RANGE_MS).toISOString(), end: e.toISOString() }
  }
  return { start: startIso, end: endIso }
}

// Normalize every picker value to { key, startIso, endIso }.
export function normalizeRange(value) {
  if (value && typeof value === 'object' && value.start && value.end) {
    return { key: value.key || 'custom', ...clampCustom(value.start, value.end) }
  }
  const key = (value && value.key) || 'month' in value ? value.key : (value || 'month')
  return { ...presetWindow(key), key }
}