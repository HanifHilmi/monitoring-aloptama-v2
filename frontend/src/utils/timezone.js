// Shared timezone state (UTC <-> WIB) read by chart builders.
// WIB = UTC+7, so timestamps displayed are shifted +7h when WIB active.
const state = { tz: 'UTC' }

export function setTz(tz) {
  state.tz = tz
  window.dispatchEvent(new Event('tzchange'))
}

export const getTz = () => state.tz

// Shift an ISO timestamp for display (+7h for WIB).
export function displayTime(iso) {
  const d = new Date(iso)
  if (state.tz === 'WIB') return new Date(d.getTime() + 7 * 3600 * 1000).toISOString()
  return iso
}