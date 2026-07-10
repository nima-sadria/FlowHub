import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useTheme } from '../theme/ThemeProvider'

const PAGE_TITLES: Record<string, string> = {
  '/home': 'Dashboard',
  '/workspace': 'Workspace',
  '/products': 'Products',
  '/sources': 'Sources',
  '/sources/new': 'Add Source',
  '/commerce': 'Commerce Hub',
  '/activity': 'Activity',
  '/diagnostics': 'Diagnostics',
  '/rate-limits': 'Global API Rate Limits',
  '/settings': 'Settings',
}

const SIGNOUT_ICON = (
  <svg viewBox="0 0 24 24" className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </svg>
)

interface Props {
  onMenuClick: () => void
  health: 'ok' | 'error' | 'loading'
  user: { username: string } | null
  onLogout: () => void
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  )
}

export default function Topbar({ onMenuClick, health, user, onLogout }: Props) {
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const { theme, toggleTheme } = useTheme()
  const title = PAGE_TITLES[location.pathname] ?? 'FlowHub'

  const healthDot =
    health === 'ok' ? 'bg-wp-green' :
    health === 'error' ? 'bg-wp-red' :
    'bg-border'

  const healthLabel =
    health === 'ok' ? 'Connected' :
    health === 'error' ? 'Offline' :
    'Checking'

  function handleLogout() {
    setMenuOpen(false)
    onLogout()
  }

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-bg-card/95 backdrop-blur">
      <div className="flex min-h-[68px] items-center gap-3 px-4 py-3 md:min-h-[72px] md:px-6 md:py-4">
      {/* Hamburger - mobile only */}
      <button
        onClick={onMenuClick}
        className="md:hidden flex items-center justify-center w-10 h-10 rounded-xl border border-border bg-bg-card text-wp-muted shadow-sm hover:text-accent hover:border-accent transition-colors"
        aria-label="Open navigation"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      {/* Breadcrumb */}
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 text-[12px] text-wp-muted">
          <span>FlowHub</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3 h-3 text-wp-muted rtl:rotate-180">
            <path d="m9 18 6-6-6-6" />
          </svg>
          <span className="truncate">{title}</span>
        </div>
        <p className="mt-1 truncate text-[18px] font-semibold leading-7 text-text-base">{title}</p>
      </div>

      <div className="ms-auto flex items-center gap-3">
        {/* Health indicator */}
        <div className="hidden sm:flex items-center gap-2 rounded-full border border-border bg-bg-base px-3 py-1.5 text-[12px] font-medium text-wp-muted">
          <span className={['w-2 h-2 rounded-full flex-shrink-0', healthDot].join(' ')} />
          <span>{healthLabel}</span>
        </div>

        {/* Dark mode toggle */}
        <button
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          className="w-10 h-10 md:w-10 md:h-10 flex items-center justify-center rounded-xl border border-border bg-bg-card text-wp-muted shadow-sm hover:text-accent hover:border-accent transition-colors"
        >
          {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
        </button>

        {/* Avatar - click opens user menu */}
        {user && (
          <div
            className="relative"
            onBlur={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
                setMenuOpen(false)
              }
            }}
          >
            <button
              onClick={() => setMenuOpen(o => !o)}
              aria-label="User menu"
              aria-expanded={menuOpen}
              className="w-10 h-10 md:w-10 md:h-10 rounded-full bg-accent flex items-center justify-center text-white text-xs font-semibold select-none shadow-sm hover:ring-2 hover:ring-accent/25 transition-shadow"
            >
              {user.username.slice(0, 2).toUpperCase()}
            </button>

            {menuOpen && (
              <div className="absolute end-0 top-full mt-2 w-52 bg-bg-card border border-border rounded-card shadow-card py-1 z-50">
                <div className="px-3 py-3 text-[12px] text-wp-muted border-b border-border truncate">
                  {user.username}
                </div>
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-2 px-3 py-2.5 text-[13px] text-wp-red hover:bg-bg-base transition-colors"
                >
                  {SIGNOUT_ICON}
                  Sign out
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      </div>
    </header>
  )
}
