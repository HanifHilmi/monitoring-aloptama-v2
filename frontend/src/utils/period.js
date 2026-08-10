// Calendar-period window helpers (all UTC).

export const CATEGORIES = [
  { key: 'weekly', label: 'Weekly' },
  { key: 'monthly', label: 'Monthly' },
  { key: 'quarterly', label: 'Quarterly' },
  { key: 'yearly', label: 'Yearly' },
]

export const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]
export const QUARTERS = ['Q1', 'Q2', 'Q3', 'Q4']
const MS_DAY = 24 * 3600 * 1000

export function yearWindow(year) {
  return {
    key: 'yearly', label: String(year),
    start: new Date(Date.UTC(year, 0, 1)).toISOString(),
    end: new Date(Date.UTC(year + 1, 0, 1)).toISOString(),
  }
}

export function monthWindow(year, monthIdx) {
  return {
    key: 'monthly', label: `${MONTHS[monthIdx]} ${year}`,
    start: new Date(Date.UTC(year, monthIdx, 1)).toISOString(),
    end: new Date(Date.UTC(year, monthIdx + 1, 1)).toISOString(),
  }
}

export function quarterWindow(year, qIdx) {
  return {
    key: 'quarterly', label: `${QUARTERS[qIdx]} ${year}`,
    start: new Date(Date.UTC(year, qIdx * 3, 1)).toISOString(),
    end: new Date(Date.UTC(year, qIdx * 3 + 3, 1)).toISOString(),
  }
}

export function weekWindow(year, monthIdx, day) {
  // 7-day window ENDING NOW: [day-6 00:00 .. now) so a fresh deploy counts
  // today's live connectivity rows (an exclusive end at today-midnight
  // excluded everything written today -> weekly showed 0.00% while monthly
  // counted them -> 0.04%).
  const endNow = new Date()
  const start = new Date(Date.UTC(year, monthIdx, day, 0, 0, 0, 0) - 6 * MS_DAY)
  const end = endNow
  const fmt = (d) => `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()].slice(0, 3)}`
  return {
    key: 'weekly',
    label: `${fmt(start)} – ${fmt(end)} ${end.getUTCFullYear()}`,
    start: start.toISOString(), end: end.toISOString(),
  }
}

// Quick "current" window for each category.
export function currentPeriod(category) {
  const now = new Date()
  const y = now.getUTCFullYear()
  const m = now.getUTCMonth()
  if (category === 'yearly') {
    const w = yearSoFar(y)
    return { key: 'yearly', label: `${w.label}`, start: w.start, end: w.end }
  }
  if (category === 'monthly') {
    const w = monthSoFar(y, m)
    return { key: 'monthly', label: `${w.label}`, start: w.start, end: w.end }
  }
  if (category === 'quarterly') {
    const q = Math.floor(m / 3)
    const w = quarterSoFar(y, q)
    return { key: 'quarterly', label: `${w.label}`, start: w.start, end: w.end }
  }
  // weekly: same window as the week picker (ends at now).
  const w = weekWindow(y, m, now.getUTCDate())
  return { key: 'weekly', label: 'Current Week (last 7d)', start: w.start, end: w.end }
}

export function daysInMonth(year, monthIdx) {
  return new Date(Date.UTC(year, monthIdx + 1, 0)).getUTCDate()
}

// Default window for a category when opened (current period).
export function defaultPeriod(category) {
  return currentPeriod(category)
}