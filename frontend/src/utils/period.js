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
  // Selected start date; window = that day + 7 days (end exclusive).
  const start = new Date(Date.UTC(year, monthIdx, day, 0, 0, 0, 0))
  const end = new Date(start.getTime() + 7 * MS_DAY)
  return {
    key: 'weekly', label: `${day} ${MONTHS[monthIdx]} ${year} (+7d)`,
    start: start.toISOString(), end: end.toISOString(),
  }
}

// Quick "current" window for each category.
export function currentPeriod(category) {
  const now = new Date()
  const y = now.getUTCFullYear()
  const m = now.getUTCMonth()
  if (category === 'yearly') return { label: `Current Year (${y})`, ...yearWindow(y) }
  if (category === 'monthly') {
    const w = monthWindow(y, m)
    return { label: `Current Month (${w.label})`, ...w }
  }
  if (category === 'quarterly') {
    const q = Math.floor(m / 3)
    const w = quarterWindow(y, q)
    return { label: `Current Quarter (${w.label})`, ...w }
  }
  // weekly: "Current Week" = last 7 days (per user note)
  const start = new Date(now.getTime() - 6 * MS_DAY)
  start.setUTCHours(0, 0, 0, 0)
  return { key: 'weekly', label: 'Current Week (last 7d)', start: start.toISOString(), end: now.toISOString() }
}

export function daysInMonth(year, monthIdx) {
  return new Date(Date.UTC(year, monthIdx + 1, 0)).getUTCDate()
}

// Default window for a category when opened (current period).
export function defaultPeriod(category) {
  return currentPeriod(category)
}