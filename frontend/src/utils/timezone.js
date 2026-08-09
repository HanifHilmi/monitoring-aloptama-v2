// Shared UTC/WIB toggle for charts. Device timezone is never used.
const state = { tz: 'UTC' }

export function setTz(tz) {
  state.tz = tz
  window.dispatchEvent(new Event('tzchange'))
}

export const getTz = () => state.tz

// ECharts root `timezone` (v5.5+): renders every time axis in a fixed zone.
export const chartTimezone = () => (state.tz === 'WIB' ? 'Asia/Jakarta' : 'UTC')