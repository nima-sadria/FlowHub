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
  hasUnreadNotifications?: boolean
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
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'unavailable'>('loading')

  useEffect(() => {
    let active = true
    const load = () => service.getLatest()
      .then(data => {
        if (!active) return
        const nextRates = data.rates.slice(0, 3)
        setRates(nextRates)
        setLoadState(nextRates.length > 0 ? 'ready' : 'unavailable')
      })
      .catch(() => {
        if (!active) return
        setRates([])
        setLoadState('unavailable')
      })
    void load()
    const interval = window.setInterval(load, 5 * 60 * 1000)
    const onUpdated = () => { void load() }
    window.addEventListener('flowhub:exchange-rates-updated', onUpdated)
    return () => { active = false; window.clearInterval(interval); window.removeEventListener('flowhub:exchange-rates-updated', onUpdated) }
  }, [service])

  const locale = language.startsWith('fa') ? 'fa-IR' : 'en-US'
  const label = translate('settings:exchangeRates.title')
  const availabilityLabel = loadState === 'loading'
    ? translate('common:status.loading')
    : translate('common:status.unavailable')
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
  const unavailableItem = (
    <span className="fh-topbar-rate fh-topbar-rate-unavailable" data-state={loadState} role="status">
      <span className="fh-topbar-rate-name">{label}</span>
      <span className="fh-topbar-rate-value">{availabilityLabel}</span>
    </span>
  )
  const renderedItems = rates.length > 0 ? rateItems : unavailableItem

  return (
    <>
      <div className="fh-topbar-rates hidden xl:flex" aria-label={label}>{renderedItems}</div>
      <details className="fh-topbar-rates-compact xl:hidden">
        <summary className="fh-topbar-control" aria-label={label} data-state={loadState}>
          <Icon name="rateLimits" size="md" />
          <span className="sr-only">{label}</span>
          {rates.length > 0 && (
            <span className="fh-topbar-control-badge" aria-label={String(rates.length)}>
              {rates.length}
            </span>
          )}
        </summary>
        <div className="fh-topbar-rates-compact-menu">{renderedItems}</div>
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
  hasUnreadNotifications = false,
}: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [langOpen, setLangOpen] = useState(false)
  const [mobileActionsOpen, setMobileActionsOpen] = useState(false)
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
      <div className="fh-topbar-primary">
        <IconButton
          onClick={onMenuClick}
          className="fh-topbar-ghost xl:hidden"
          label={translate('navigation:topbar.openNavigation')}
        >
          <Icon name="menu" size="lg" strokeWidth={1.75} />
        </IconButton>

        <button
          type="button"
          className="fh-topbar-mobile-brand xl:hidden"
          onClick={() => navigate('/home')}
          aria-label={translate('navigation:sidebar.flowhub')}
          dir="ltr"
        >
          <img
            src="/static/logos/FlowHub%20Transparent%20WebP%20%20Logo.webp?v=1"
            alt=""
            aria-hidden="true"
          />
          <span>{translate('navigation:sidebar.flowhub')}</span>
        </button>

        <button
          type="button"
          onClick={onToggleCollapse}
          aria-label={translate(sidebarCollapsed
            ? 'navigation:sidebar.expandSidebar'
            : 'navigation:sidebar.collapseSidebar')}
          className="fh-topbar-ghost hidden xl:inline-flex"
        >
          <Icon name="panelToggle" size="lg" mirrorRtl strokeWidth={1.75} />
        </button>

        <form
          onSubmit={handleSearchSubmit}
          className="fh-topbar-search hidden xl:block"
          role="search"
        >
          <Icon name="search" className="fh-topbar-search-icon" />
          <input
            id="global-search"
            name="global-search"
            type="search"
            aria-label={translate('activity:activity.search')}
            {...inputHint(translate('navigation:topbar.globalSearchHint'))}
            value={searchTerm}
            onChange={event => setSearchTerm(event.target.value)}
          />
        </form>

        <IconButton
          onClick={() => setMobileActionsOpen(open => !open)}
          className="fh-topbar-ghost fh-topbar-more xl:hidden"
          label={translate('common:action.actions')}
          aria-controls="topbar-mobile-actions"
          aria-expanded={mobileActionsOpen}
        >
          <Icon name="more" size="lg" strokeWidth={1.75} />
        </IconButton>

        <div
          id="topbar-mobile-actions"
          className={[
            'fh-topbar-actions',
            mobileActionsOpen ? 'fh-topbar-actions-open' : '',
          ].filter(Boolean).join(' ')}
        >
          {exchangeRates && <ExchangeRateStrip service={exchangeRates} language={language} />}

          <button
            type="button"
            onClick={toggleTheme}
            aria-label={
              theme === 'dark'
                ? translate('navigation:topbar.switchToLightMode')
                : translate('navigation:topbar.switchToDarkMode')
            }
            className="fh-topbar-control"
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size="lg" />
          </button>

          <button
            type="button"
            onClick={() => navigate('/activity')}
            aria-label={translate('notifications:notificationContainer.notifications')}
            className="fh-topbar-control fh-topbar-notification"
            data-unread={hasUnreadNotifications ? 'true' : undefined}
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
              className="fh-topbar-control fh-topbar-language"
            >
              <Icon name="globe" size="lg" />
              <span className="fh-topbar-language-label">{translate('navigation:topbar.languageBadge')}</span>
              <Icon name="chevronDown" size="md" className="fh-topbar-language-chevron" />
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
                className="fh-topbar-user"
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

                <span className="fh-topbar-user-chevron" aria-hidden="true">
                  <Icon name="chevronDown" size="sm" />
                </span>
              </button>

              {menuOpen && (
                <div className="fh-dropdown fh-topbar-account-menu absolute end-0 top-full z-50 mt-2">
                  <div className="fh-topbar-account-profile">
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
                      <Icon name="signOut" size="lg" />
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
