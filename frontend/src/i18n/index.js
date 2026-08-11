// Minimal localization: labels/text only. Dates, charts, and timezones are
// ALWAYS UTC regardless of locale.
const MESSAGES = {
  en: {
    dashboard: 'Dashboard',
    cat3: 'AWOS CAT. III',
    cat1: 'AWOS CAT. I',
    aws: 'AWS Digitalisasi',
    system: 'System',
    runway04: 'Runway 04',
    runwayMiddle: 'Runway Middle',
    runway22: 'Runway 22',
    metar: 'METAR & METREPORT',
    garden: 'Meteorology Garden',
    comingSoon: 'Coming soon',
  },
  id: {
    dashboard: 'Dasbor',
    cat3: 'AWOS KAT. III',
    cat1: 'AWOS KAT. I',
    aws: 'AWS Digitalisasi',
    system: 'Sistem',
    runway04: 'Landasan 04',
    runwayMiddle: 'Landasan Tengah',
    runway22: 'Landasan 22',
    metar: 'METAR & METREPORT',
    garden: 'Taman Meteorologi',
    comingSoon: 'Segera hadir',
  },
}

export const LOCALES = ['en', 'id']

export function i18n(locale) {
  const m = MESSAGES[locale] || MESSAGES.en
  return (key) => m[key] ?? MESSAGES.en[key] ?? key
}