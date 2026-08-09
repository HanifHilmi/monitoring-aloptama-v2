// Shared UTC/WIB state. Device timezone is NEVER used.
const state = { tz: 'UTC' }

export function setTz(tz) {
  state.tz = tz
  window.dispatchEvent(new Event('tzchange'))
}

export const getTz = () => state.tz

// ECharts 5.5 root `timezone` for time axes.
export const chartTimezone = () => (state.tz === 'WIB' ? 'Asia/Jakarta' : 'UTC')

const pad = (n) => String(n).padStart(2, '0')

// Display an ISO timestamp in UTC (default) or WIB (+7h), independent of
// the visitor's device timezone.
export function formatDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const t = new Date(d.getTime() + (state.tz === 'WIB' ? 7 * 3600 * 1000 : 0))
  return (
    `${t.getUTCFullYear()}-${pad(t.getUTCMonth() + 1)}-${pad(t.getUTCDate())} ` +
    `${pad(t.getUTCHours())}:${pad(t.getUTCMinutes())}:${pad(t.getUTCSeconds())} ${state.tz}`
  )
}