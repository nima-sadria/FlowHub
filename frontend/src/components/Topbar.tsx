import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { translate } from '../i18n'
import Icon from './Icon'
import IconButton from './IconButton'
import { useTheme } from '../theme/ThemeProvider'
import { useDirection } from '../direction'

interface Props {
  onMenuClick: () => void
  onToggleCollapse: () => void
  user: { username: string; role?: string } | null
  onLogout: () => void
}

const LANGUAGES = [
  { code: 'en', labelKey: 'settings:language.english', direction: 'ltr' as const },
  { code: 'fa', labelKey: 'settings:language.persian', direction: 'rtl' as const },
]

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
      className="h-5 w-5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
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
      className="h-5 w-5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
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
  onToggleCollapse,
  user,
  onLogout,
}: Props) {
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [langOpen, setLangOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const { theme, toggleTheme } = useTheme()
  const { language, setLanguage, setDirection } = useDirection()

  function handleSearchSubmit(event: FormEvent) {
    event.preventDefault()
    const term = searchTerm.trim()
    navigate(term ? `/products?q=${encodeURIComponent(term)}` : '/products')
  }

  function handleSelectLanguage(code: string) {
    const lang = LANGUAGES.find(entry => entry.code === code)
    if (lang) {
      setLanguage(lang.code)
      setDirection(lang.direction)
    }
    setLangOpen(false)
  }

  function handleLogout() {
    setMenuOpen(false)
    onLogout()
  }

  return (
    <header className="fh-topbar">
      <div className="fh-topbar-inner">
        <IconButton
          onClick={onMenuClick}
          className="md:hidden"
          label={translate('navigation:topbar.openNavigation')}
        >
          <MenuIcon />
        </IconButton>

        <button
          type="button"
          onClick={onToggleCollapse}
          aria-label={translate('navigation:sidebar.collapseSidebar')}
          className="fh-topbar-action hidden md:inline-flex"
        >
          <Icon name="panelToggle" size="lg" mirrorRtl />
        </button>

        <form
          onSubmit={handleSearchSubmit}
          className="fh-topbar-search hidden sm:block"
          role="search"
        >
          <Icon name="search" className="fh-topbar-search-icon" />
          <input
            type="search"
            aria-label={translate('activity:activity.search')}
            placeholder={translate('products:products.searchNameOrSku')}
            value={searchTerm}
            onChange={event => setSearchTerm(event.target.value)}
          />
        </form>

        <div className="ms-auto flex items-center gap-1.5 sm:gap-2">
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={
              theme === 'dark'
                ? translate('navigation:topbar.switchToLightMode')
                : translate('navigation:topbar.switchToDarkMode')
            }
            className="fh-topbar-action"
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>

          <button
            type="button"
            onClick={() => navigate('/activity')}
            aria-label={translate('notifications:notificationContainer.notifications')}
            className="fh-topbar-action"
          >
            <Icon name="bell" size="lg" />
          </button>

          <div
            className="relative"
            onBlur={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                setLangOpen(false)
              }
            }}
          >
            <button
              type="button"
              onClick={() => setLangOpen(open => !open)}
              aria-label={translate('settings:language.title')}
              aria-expanded={langOpen}
              className="fh-topbar-pill"
            >
              <Icon name="globe" size="lg" />
              <span className="uppercase">{language}</span>
              <Icon name="chevronDown" size="md" />
            </button>

            {langOpen && (
              <div className="fh-dropdown absolute end-0 top-full z-50 mt-2 min-w-[160px]">
                {LANGUAGES.map(lang => (
                  <button
                    key={lang.code}
                    type="button"
                    onClick={() => handleSelectLanguage(lang.code)}
                    className={[
                      'fh-dropdown-item',
                      lang.code === 'fa' ? 'fh-persian-text' : '',
                      lang.code === language ? 'text-accent' : '',
                    ].filter(Boolean).join(' ')}
                  >
                    {translate(lang.labelKey)}
                  </button>
                ))}
              </div>
            )}
          </div>

          {user && (
            <div
              className="relative"
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                  setMenuOpen(false)
                }
              }}
            >
              <button
                type="button"
                onClick={() => setMenuOpen(open => !open)}
                aria-label={translate('navigation:topbar.userMenu')}
                aria-expanded={menuOpen}
                className="flex items-center gap-2.5 rounded-lg py-1 ps-2 pe-1 hover:bg-bg-subtle"
              >
                <span className="fh-user-avatar">
                  {user.username.slice(0, 2).toUpperCase()}
                </span>

                <span className="hidden flex-col items-start sm:flex">
                  <span className="text-sm font-medium leading-5 text-text-base">
                    {user.username}
                  </span>
                  {user.role && (
                    <span className="text-xs leading-4 text-wp-muted capitalize">
                      {user.role}
                    </span>
                  )}
                </span>

                <Icon name="chevronDown" size="md" className="hidden text-wp-muted sm:inline-flex" />
              </button>

              {menuOpen && (
                <div className="fh-dropdown absolute end-0 top-full z-50 mt-2 w-56">
                  <div className="rounded-xl border border-border bg-bg-base px-3 py-3">
                    <div className="text-[13px] font-medium leading-5 text-text-base">
                      {user.username}
                    </div>
                    <div className="fh-text-caption mt-0.5 capitalize">
                      {user.role || translate('navigation:topbar.signedIn')}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={handleLogout}
                    className="fh-dropdown-item mt-1 text-wp-red hover:bg-wp-red/5 hover:text-wp-red"
                  >
                    <span className="fh-icon-md">
                      <SignOutIcon />
                    </span>
                    {translate('navigation:sidebar.signOut')}
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
