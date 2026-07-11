import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import Badge from './Badge'
import IconButton from './IconButton'
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

interface Props {
  onMenuClick: () => void
  health: 'ok' | 'error' | 'loading'
  user: { username: string } | null
  onLogout: () => void
}

function MenuIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="15" y2="18" />
    </svg>
  )
}

function SunIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-[18px] w-[18px]"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4.5" />
      <path d="M12 2.5v2.5M12 19v2.5M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M2.5 12H5M19 12h2.5M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-[18px] w-[18px]"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7.2 7.2 0 0 0 9.8 9.8Z" />
    </svg>
  )
}

function SignOutIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="m16 17 5-5-5-5" />
      <path d="M21 12H9" />
    </svg>
  )
}

export default function Topbar({
  onMenuClick,
  health,
  user,
  onLogout,
}: Props) {
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const { theme, toggleTheme } = useTheme()
  const title = PAGE_TITLES[location.pathname] ?? 'FlowHub'

  const healthLabel =
    health === 'ok'
      ? 'Connected'
      : health === 'error'
        ? 'Offline'
        : 'Checking'

  const healthVariant =
    health === 'ok'
      ? 'success'
      : health === 'error'
        ? 'error'
        : 'neutral'

  function handleLogout() {
    setMenuOpen(false)
    onLogout()
  }

  return (
    <header className="fh-topbar">
      <div className="fh-topbar-inner">
        <div className="flex min-w-0 items-center gap-3">
          <IconButton
            onClick={onMenuClick}
            className="md:hidden"
            label="Open navigation"
          >
            <MenuIcon />
          </IconButton>

          <div className="min-w-0">
            <div className="fh-text-caption">FlowHub / {title}</div>
            <p className="truncate text-[20px] font-semibold leading-7 text-text-base">
              {title}
            </p>
          </div>
        </div>

        <div className="ms-auto flex items-center gap-2 sm:gap-3">
          <div className="hidden sm:flex">
            <Badge dot variant={healthVariant}>
              {healthLabel}
            </Badge>
          </div>

          <IconButton
            onClick={toggleTheme}
            label={
              theme === 'dark'
                ? 'Switch to light mode'
                : 'Switch to dark mode'
            }
            size="sm"
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </IconButton>

          {user && (
            <div
              className="relative"
              onBlur={(event) => {
                if (
                  !event.currentTarget.contains(
                    event.relatedTarget as Node | null,
                  )
                ) {
                  setMenuOpen(false)
                }
              }}
            >
              <button
                type="button"
                onClick={() => setMenuOpen((open) => !open)}
                aria-label="User menu"
                aria-expanded={menuOpen}
                className="fh-user-chip"
              >
                <div className="hidden text-left sm:block">
                  <div className="text-xs font-medium leading-4 text-text-base">
                    {user.username}
                  </div>
                  <div className="fh-text-caption uppercase tracking-[0.06em]">
                    {healthLabel}
                  </div>
                </div>

                <span className="fh-user-avatar">
                  {user.username.slice(0, 2).toUpperCase()}
                </span>
              </button>

              {menuOpen && (
                <div className="fh-dropdown absolute end-0 top-full z-50 mt-2 w-56">
                  <div className="rounded-xl border border-border bg-bg-base px-3 py-3">
                    <div className="text-[13px] font-medium leading-5 text-text-base">
                      {user.username}
                    </div>
                    <div className="fh-text-caption mt-0.5">Signed in</div>
                  </div>

                  <button
                    type="button"
                    onClick={handleLogout}
                    className="fh-dropdown-item mt-1 text-wp-red hover:bg-wp-red/5 hover:text-wp-red"
                  >
                    <span className="fh-icon-md">
                      <SignOutIcon />
                    </span>
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