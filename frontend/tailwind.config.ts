import type { Config } from 'tailwindcss'

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        accent: 'var(--color-accent)',
        'accent-hover': 'var(--color-accent-hover)',
        'wp-green': 'var(--color-wp-green)',
        'wp-red': 'var(--color-wp-red)',
        'wp-yellow': 'var(--color-wp-yellow)',
        'wp-orange': 'var(--color-wp-orange)',
        'wp-purple': 'var(--color-wp-purple)',
        'wp-muted': 'var(--color-wp-muted)',
        'bg-base': 'var(--color-bg-base)',
        'bg-card': 'var(--color-bg-card)',
        border: 'var(--color-border)',
        'text-base': 'var(--color-text-base)',
      },
      fontFamily: {
        sans: ['IRANYekanX', 'sans-serif'],
      },
      borderRadius: {
        card: '12px',
      },
      boxShadow: {
        card: '0 1px 4px rgba(0,0,0,.06)',
      },
    },
  },
  plugins: [],
} satisfies Config
