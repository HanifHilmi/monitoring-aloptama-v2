// UTC-only time handling. The app NEVER uses the visitor's device timezone
// and there is no WIB/UTC toggle — everything renders in UTC.

const pad = (n) => String(n).padStart(2, '0')

// ECharts 5.5 root `timezone` for time axes (always UTC).
export const chartTimezone = () => 'UTC'

// Display an ISO timestamp in UTC (device-timezone independent).
export function formatDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`
  )
}

// Tooltip formatter for charts (accepts ISO string or epoch number).
export function tooltipTime(iso) {
  if (!iso) return '—'
  let ts = iso
  if (typeof iso === 'number') ts = new Date(iso).toISOString()
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return '—'
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`
  )
}