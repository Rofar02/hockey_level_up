/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'dark-bg': '#111827',
        'dark-card': '#171F30',
        'accent-ice': '#D7EFFF',
        'accent-persimmon': '#FF5C34',
        'text-primary': '#F2F5F8',
        'text-secondary': '#8B96AB',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        // Condensed, bold-by-design -- the "number on a jersey" face for
        // level/stat values (hockey design pass, 2026-08-28). Deliberately
        // separate from `font-mono`: mono stays for tabular/utility digits
        // (timers, the streak counter) where digit-width stability matters,
        // display is for numbers that ARE the content (rank, stat value).
        display: ['Oswald', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        DEFAULT: '4px',
        md: '6px',
      },
    },
  },
  plugins: [],
}
