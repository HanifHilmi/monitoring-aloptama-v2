/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // AWOS monitoring theme
        runway: {
          dark: '#0b1220',
          panel: '#111a2e',
          border: '#1e2a45',
        },
        status: {
          ok: '#10b981',
          corrupt: '#f59e0b',
          missing: '#ef4444',
          stale: '#64748b',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
}