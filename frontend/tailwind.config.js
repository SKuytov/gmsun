/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Onest Variable"', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['"JetBrains Mono Variable"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        bg: 'hsl(var(--bg) / <alpha-value>)',
        surface: 'hsl(var(--surface) / <alpha-value>)',
        'surface-2': 'hsl(var(--surface-2) / <alpha-value>)',
        line: 'hsl(var(--line) / <alpha-value>)',
        ink: 'hsl(var(--ink) / <alpha-value>)',
        'ink-2': 'hsl(var(--ink-2) / <alpha-value>)',
        'ink-3': 'hsl(var(--ink-3) / <alpha-value>)',
        sun: 'hsl(var(--sun) / <alpha-value>)',
        'sun-ink': 'hsl(var(--sun-ink) / <alpha-value>)',
        'sun-soft': 'hsl(var(--sun-soft) / <alpha-value>)',
        ok: 'hsl(var(--ok) / <alpha-value>)',
        warn: 'hsl(var(--warn) / <alpha-value>)',
        bad: 'hsl(var(--bad) / <alpha-value>)',
      },
      borderRadius: { sm: '4px', DEFAULT: '6px', md: '8px', lg: '12px', xl: '16px' },
      boxShadow: {
        card: '0 1px 2px hsl(30 10% 10% / 0.06), 0 1px 3px hsl(30 10% 10% / 0.04)',
        pop: '0 8px 24px hsl(30 10% 10% / 0.14), 0 2px 6px hsl(30 10% 10% / 0.08)',
      },
    },
  },
  plugins: [],
}
