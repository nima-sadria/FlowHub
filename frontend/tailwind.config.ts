import type { Config } from 'tailwindcss'

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'fh-navy-950': 'var(--fh-brand-navy-950)',
        'fh-navy-900': 'var(--fh-brand-navy-900)',
        'fh-navy-800': 'var(--fh-brand-navy-800)',
        'fh-blue-700': 'var(--fh-brand-blue-700)',
        'fh-blue-600': 'var(--fh-brand-blue-600)',
        'fh-blue-500': 'var(--fh-brand-blue-500)',
        'fh-blue-400': 'var(--fh-brand-blue-400)',
        'fh-sky-300': 'var(--fh-brand-sky-300)',
        'fh-ice-200': 'var(--fh-brand-ice-200)',
        'fh-mist-100': 'var(--fh-brand-mist-100)',
        'fh-surface-50': 'var(--fh-brand-surface-50)',
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
        'bg-subtle': 'var(--fh-ui-surface-subtle)',
        border: 'var(--color-border)',
        'text-base': 'var(--color-text-base)',
      },
      fontFamily: {
        sans: ['Outfit', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
      },
      borderRadius: {
        card: '10px',
      },
      boxShadow: {
        card: '0 1px 2px var(--fh-ui-shadow-blue)',
        blue: '0 1px 2px var(--fh-ui-shadow-blue)',
      },
      transitionTimingFunction: {
        DEFAULT: 'cubic-bezier(0.4, 0, 0.6, 1)',
      },
      transitionDuration: {
        DEFAULT: '320ms',
      },
    },
  },
  plugins: [],
} satisfies Config
