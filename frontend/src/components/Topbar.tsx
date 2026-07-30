import { useEffect, useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router'
import i18n, { translate } from '../i18n'
import Icon from './Icon'
import IconButton from './IconButton'
import { useTheme } from '../theme/ThemeProvider'
import { useDirection } from '../direction'
import { inputHint } from '../utils/inputHint'
import type { ExchangeRateService } from '../services/exchangeRates/ExchangeRateService'
import type { ExchangeRateSnapshotView } from '../services/types'

interface Props {
  onMenuClick: () => void
  onToggleCollapse: () => void
  sidebarCollapsed: boolean
  user: { username: string; role?: string } | null
  onLogout: () => void
  exchangeRates?: ExchangeRateService
}

const LANGUAGES = [
  { code: 'en', labelKey: 'settings:language.english', direction: 'ltr' as const },
  { code: 'fa', labelKey: 'settings:language.persian', direction: 'rtl' as const },
]

// Deterministic role labels through the existing i18n catalogs; unknown role
// values fall back to the raw authenticated value untranslated.
function roleLabel(role: string): string {
  const normalized = role.trim().toLowerCase()
  const camel = normalized.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase())
  for (const key of [`common:role.${camel}`, `settings:users.role.${normalized}`]) {
    if (i18n.exists(key)) return translate(key)
  }
  return role
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

function formatDecimalString(value: string, locale: string): string {
  const match = value.trim().match(/^([+-]?)(\d+)(?:\.(\d+))?$/)
  if (!match) return value
  const [, sign, integerPart, rawFraction = ''] = match
  const fraction = rawFraction.replace(/0+$/, '')
  const grouped = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(BigInt(integerPart))
  const decimalSeparator = new Intl.NumberFormat(locale)
    .formatToParts(1.1)
    .find(part => part.type === 'decimal')?.value ?? '.'
  const localizedSign = sign === '-' ? '−' : sign
  return `${localizedSign}${grouped}${fraction ? `${decimalSeparator}${fraction}` : ''}`
}

function ExchangeRateStrip({ service, language }: { service: ExchangeRateService; language: string }) {
  const [rates, setRates] = useState<ExchangeRateSnapshotView[]>([])

  useEffect(() => {
    let active = true
    const load = () => service.getLatest().then(data => { if (active) setRates(data.rates.slice(0, 3)) }).catch(() => { if (active) setRates([]) })
    void load()
    const interval = window.setInterval(load, 5 * 60 * 1000)
    const onUpdated = () => { void load() }
    window.addEventListener('flowhub:exchange-rates-updated', onUpdated)
    return () => { active = false; window.clearInterval(interval); window.removeEventListener('flowhub:exchange-rates-updated', onUpdated) }
  }, [service])

  if (rates.length !== 3) return null
  const locale = language.startsWith('fa') ? 'fa-IR' : 'en-US'
  const label = locale === 'fa-IR' ? 'نرخ ارز' : 'Exchange rates'
  const rateItems = rates.map(rate => {
    const name = locale === 'fa-IR' ? rate.display_name_fa : rate.display_name
    const increased = rate.change !== null && !rate.change.trim().startsWith('-')
    const direction = rate.change !== null ? (increased ? '↑' : '↓') : ''
    const freshness = rate.status === 'stale'
      ? (locale === 'fa-IR' ? 'داده قدیمی' : 'Stale')
      : rate.status === 'unavailable'
        ? (locale === 'fa-IR' ? 'در دسترس نیست' : 'Unavailable')
        : rate.status === 'disabled'
          ? (locale === 'fa-IR' ? 'ارائه‌دهنده غیرفعال است' : 'Provider disabled')
          : ''
    const tooltip = [
      name,
      freshness,
      rate.fetched_at ? new Date(rate.fetched_at).toLocaleString(locale) : '',
    ].filter(Boolean).join(' · ')
    return (
      <span
        key={`${rate.provider}-${rate.external_symbol}`}
        className={['fh-topbar-rate', rate.status === 'stale' ? 'fh-topbar-rate-stale' : ''].join(' ')}
        title={tooltip}
        aria-label={tooltip || name}
      >
        <span className="fh-topbar-rate-name">{name}</span>
        <span className="fh-topbar-rate-value">{rate.value === null ? '—' : formatDecimalString(rate.value, locale)}</span>
        {direction && (
          <span className="fh-topbar-rate-change" aria-label={increased ? 'increased' : 'decreased'}>
            {direction}
          </span>
        )}
      </span>
    )
  })
  return (
    <>
      <div className="fh-topbar-rates hidden lg:flex" aria-label={label}>{rateItems}</div>
      <details className="fh-topbar-rates-compact lg:hidden">
        <summary aria-label={label}>
          <span>{label}</span>
          <span aria-hidden="true">3</span>
        </summary>
        <div className="fh-topbar-rates-compact-menu">{rateItems}</div>
      </details>
    </>
  )
}

export default function Topbar({
  onMenuClick,
  onToggleCollapse,
  sidebarCollapsed,
  user,
  onLogout,
  exchangeRates,
}: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [langOpen, setLangOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const { theme, toggleTheme } = useTheme()
  const { language, setLanguage, setDirection } = useDirection()

  function handleSearchSubmit(event: FormEvent) {
    event.preventDefault()
    const term = searchTerm.trim()
    const params = location.pathname === '/products'
      ? new URLSearchParams(location.search)
      : new URLSearchParams()
    if (term) params.set('q', term)
    else params.delete('q')
    const query = params.toString()
    navigate(query ? `/products?${query}` : '/products')
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
          aria-label={translate(sidebarCollapsed
            ? 'navigation:sidebar.expandSidebar'
            : 'navigation:sidebar.collapseSidebar')}
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
            {...inputHint(translate('navigation:topbar.globalSearchHint'))}
            value={searchTerm}
            onChange={event => setSearchTerm(event.target.value)}
          />
        </form>

        {exchangeRates && <ExchangeRateStrip service={exchangeRates} language={language} />}

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
              className="fh-topbar-pill rtl:flex-row-reverse"
            >
              <Icon name="globe" size="lg" />
              <span>{translate('navigation:topbar.languageBadge')}</span>
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
                className="flex items-center gap-2.5 rounded-lg py-1 ps-2 pe-1 hover:bg-bg-subtle rtl:flex-row-reverse"
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
                      {roleLabel(user.role)}
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
                      {user.role ? roleLabel(user.role) : translate('navigation:topbar.signedIn')}
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
