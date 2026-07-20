import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type InputHTMLAttributes,
  type ReactNode,
} from 'react'
import type {
  AdminPayload,
  DatabaseStatusResponse,
  ServerProfilePayload,
  SetupAdminResponse,
  SetupStatus,
} from '../api/types'
import Spinner from '../components/loading/Spinner'
import { useDirection } from '../direction'
import { translate } from '../i18n'
import { useTheme } from '../theme/ThemeProvider'
import { inputHint } from '../utils/inputHint'

type Step = 'workspace' | 'database' | 'owner' | 'review'

const SETUP_STEPS: Step[] = ['workspace', 'database', 'owner', 'review']
const STEP_DETAILS: Record<Step, { labelKey: string; checklistKey: string }> = {
  workspace: { labelKey: 'settings:setup.workspace', checklistKey: 'settings:setup.workspaceDefaults' },
  database: { labelKey: 'settings:setup.database', checklistKey: 'settings:setup.verifyDatabase' },
  owner: { labelKey: 'settings:setup.owner', checklistKey: 'settings:setup.createOwnerAccount' },
  review: { labelKey: 'settings:setup.review', checklistKey: 'settings:setup.reviewSetup' },
}

interface SetupProps {
  onComplete: () => void
}

const ALL_TIMEZONES = [
  'UTC',
  'Africa/Cairo', 'Africa/Johannesburg', 'Africa/Lagos', 'Africa/Nairobi',
  'America/Bogota', 'America/Buenos_Aires', 'America/Chicago', 'America/Denver',
  'America/Los_Angeles', 'America/Mexico_City', 'America/New_York',
  'America/Sao_Paulo', 'America/Toronto', 'America/Vancouver',
  'Asia/Bangkok', 'Asia/Dubai', 'Asia/Hong_Kong', 'Asia/Jakarta',
  'Asia/Karachi', 'Asia/Kolkata', 'Asia/Kuala_Lumpur', 'Asia/Manila',
  'Asia/Riyadh', 'Asia/Seoul', 'Asia/Shanghai', 'Asia/Singapore',
  'Asia/Taipei', 'Asia/Tehran', 'Asia/Tokyo',
  'Atlantic/Reykjavik',
  'Australia/Melbourne', 'Australia/Perth', 'Australia/Sydney',
  'Europe/Amsterdam', 'Europe/Athens', 'Europe/Berlin', 'Europe/Brussels',
  'Europe/Bucharest', 'Europe/Dublin', 'Europe/Helsinki', 'Europe/Istanbul',
  'Europe/Kiev', 'Europe/Lisbon', 'Europe/London', 'Europe/Madrid',
  'Europe/Moscow', 'Europe/Oslo', 'Europe/Paris', 'Europe/Prague',
  'Europe/Rome', 'Europe/Stockholm', 'Europe/Vienna', 'Europe/Warsaw',
  'Europe/Zurich',
  'Pacific/Auckland', 'Pacific/Honolulu',
]

const CURRENCIES = [
  { value: 'IRR', labelKey: 'settings:setup.irrIranianRial' },
  { value: 'IRT', labelKey: 'settings:setup.irtIranianToman' },
  { value: 'USD', labelKey: 'settings:setup.usdUsDollar' },
  { value: 'EUR', labelKey: 'settings:setup.eurEuro' },
  { value: 'AED', labelKey: 'settings:setup.aedUaeDirham' },
  { value: 'TRY', labelKey: 'settings:setup.tryTurkishLira' },
  { value: 'GBP', labelKey: 'settings:setup.gbpBritishPound' },
  { value: 'JPY', labelKey: 'settings:setup.jpyJapaneseYen' },
  { value: 'CAD', labelKey: 'settings:setup.cadCanadianDollar' },
  { value: 'AUD', labelKey: 'settings:setup.audAustralianDollar' },
  { value: 'CHF', labelKey: 'settings:setup.chfSwissFranc' },
]

const TZ_OPTIONS = ALL_TIMEZONES.map(timezone => ({ value: timezone, label: timezone }))
const LANGUAGE_OPTIONS = [
  { value: 'en', labelKey: 'settings:language.english' },
  { value: 'fa', labelKey: 'settings:language.persian' },
]

export function validateSetupEmail(value: string): string | null {
  const email = value.trim()
  if (!email || email.includes(' ') || (email.match(/@/g) ?? []).length !== 1) {
    return translate('settings:setup.validEmail')
  }

  const [local, domain] = email.split('@')
  if (!local || !domain || domain.length > 253 || !domain.includes('.')) {
    return translate('settings:setup.validEmail')
  }

  const labels = domain.split('.')
  const validLabels = labels.every(label => (
    label.length > 0
    && label.length <= 63
    && /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/.test(label)
  ))
  const tld = labels[labels.length - 1]
  if (!validLabels || !/^[A-Za-z]{2,63}$/.test(tld) || !/^[^\s@]+$/.test(local)) {
    return translate('settings:setup.validEmail')
  }
  return null
}

function ChevronIcon({ open }: { open?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={['h-4 w-4 shrink-0 text-wp-muted transition-transform', open ? 'rotate-180' : ''].join(' ')}
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  )
}

export function SearchableListbox({
  id,
  label,
  options,
  value,
  onChange,
  disabled,
  template_variable,
}: {
  id?: string
  label: string
  options: { value: string; label: string }[]
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  template_variable?: string
}) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const query = search.trim().toLowerCase()
  const filtered = query
    ? options.filter(option => (
      option.label.toLowerCase().includes(query) || option.value.toLowerCase().includes(query)
    ))
    : options
  const selectedLabel = options.find(option => option.value === value)?.label ?? value

  useEffect(() => {
    if (!open) return
    searchRef.current?.focus()
    function closeOnOutsideClick(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', closeOnOutsideClick)
    return () => document.removeEventListener('mousedown', closeOnOutsideClick)
  }, [open])

  function select(nextValue: string) {
    onChange(nextValue)
    setSearch('')
    setOpen(false)
  }

  return (
    <div ref={rootRef} className="relative min-w-0">
      <label className="fh-label mb-1.5 block">{label}</label>
      <button
        type="button"
        onClick={() => setOpen(current => !current)}
        onKeyDown={event => {
          if (event.key === 'Escape') {
            setOpen(false)
            setSearch('')
          }
        }}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={id}
        disabled={disabled}
        className="fh-input flex min-w-0 items-center justify-between gap-2 text-start"
      >
        <span className="truncate">{selectedLabel}</span>
        <ChevronIcon open={open} />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full overflow-hidden rounded-md border border-border bg-bg-card shadow-card">
          <div className="border-b border-border p-2">
            <input
              ref={searchRef}
              type="text"
              value={search}
              onChange={event => setSearch(event.target.value)}
              onKeyDown={event => {
                if (event.key === 'Escape') {
                  setOpen(false)
                  setSearch('')
                }
                if (event.key === 'Enter' && filtered[0]) select(filtered[0].value)
              }}
              {...inputHint(template_variable ?? translate('settings:setup.search', { value1: label.toLowerCase() }))}
              autoComplete="off"
              spellCheck={false}
              className="fh-input shadow-none"
            />
          </div>
          <div id={id} role="listbox" aria-label={label} className="max-h-44 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-3 py-2 fh-text-body-sm">{translate('settings:setup.noMatches')}</div>
            ) : filtered.map(option => (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={option.value === value}
                onClick={() => select(option.value)}
                disabled={disabled}
                className={[
                  'flex w-full items-center justify-between gap-3 px-3 py-2 text-start fh-text-body',
                  option.value === value
                    ? 'bg-fh-mist-100 font-medium text-accent'
                    : 'bg-bg-card text-text-base hover:bg-bg-base',
                ].join(' ')}
              >
                <span>{option.label}</span>
                {option.value === value && <span aria-hidden="true">✓</span>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Field({
  id,
  label,
  type = 'text',
  value,
  onChange,
  templateVariable,
  disabled = false,
  hint,
  error,
  autoComplete = 'off',
  inputMode,
}: {
  id: string
  label: string
  type?: string
  value: string
  onChange: (value: string) => void
  templateVariable?: string
  disabled?: boolean
  hint?: string
  error?: string | null
  autoComplete?: string
  inputMode?: InputHTMLAttributes<HTMLInputElement>['inputMode']
}) {
  const describedBy = [
    hint ? `${id}-hint` : null,
    error ? `${id}-error` : null,
  ].filter(Boolean).join(' ') || undefined

  return (
    <div className="fh-field">
      <label htmlFor={id} className="fh-label">{label}</label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={event => onChange(event.target.value)}
        {...inputHint(templateVariable)}
        disabled={disabled}
        autoComplete={autoComplete}
        inputMode={inputMode}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
        className={['fh-input', error ? 'fh-input-error' : ''].join(' ')}
      />
      {hint && <p id={`${id}-hint`} className="fh-help-text">{hint}</p>}
      {error && <p id={`${id}-error`} className="fh-field-error">{error}</p>}
    </div>
  )
}

function ErrorBanner({ message }: { message: string }) {
  return <div role="alert" className="fh-alert fh-alert-danger mb-4">{message}</div>
}

function StepProgress({ current }: { current: Step }) {
  const currentIndex = SETUP_STEPS.indexOf(current)
  return (
    <ol className="flex min-w-0 items-center" aria-label={translate('settings:setup.setupProgress')}>
      {SETUP_STEPS.map((step, index) => (
        <li key={step} className="flex min-w-0 flex-1 items-center last:flex-none">
          <div className="flex shrink-0 items-center gap-2">
            <span
              aria-current={index === currentIndex ? 'step' : undefined}
              className={[
                'flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-medium',
                index <= currentIndex
                  ? 'bg-accent text-white'
                  : 'bg-[color:var(--fh-ui-surface-muted)] text-[color:var(--fh-text-secondary)]',
              ].join(' ')}
            >
              {index < currentIndex ? '✓' : index + 1}
            </span>
            <span className={[
              'hidden whitespace-nowrap text-xs sm:block',
              index === currentIndex ? 'font-semibold text-text-base' : 'text-[color:var(--fh-text-secondary)]',
            ].join(' ')}>
              {translate(STEP_DETAILS[step].labelKey)}
            </span>
          </div>
          {index < SETUP_STEPS.length - 1 && (
            <span className={[
              'mx-2.5 h-px min-w-3 flex-1',
              index < currentIndex ? 'bg-accent' : 'bg-border',
            ].join(' ')} />
          )}
        </li>
      ))}
    </ol>
  )
}

function SetupChecklist({ current }: { current: Step }) {
  const currentIndex = SETUP_STEPS.indexOf(current)
  return (
    <aside className="min-h-[300px] rounded-lg bg-bg-base p-4">
      <h2 className="text-sm font-semibold leading-[22px] text-text-base">{translate('settings:setup.setupChecklist')}</h2>
      <div className="mt-3 space-y-3">
        {SETUP_STEPS.map((step, index) => {
          const state = index < currentIndex ? 'complete' : index === currentIndex ? 'active' : 'pending'
          return (
            <div key={step} className="flex items-center justify-between gap-3">
              <span className="min-w-0 text-xs leading-4 text-[color:var(--fh-text-secondary)]">
                {translate(STEP_DETAILS[step].checklistKey)}
              </span>
              <span className={[
                'fh-badge shrink-0',
                state === 'complete'
                  ? 'fh-badge-success'
                  : state === 'active'
                    ? 'fh-badge-info'
                    : 'fh-badge-neutral',
              ].join(' ')}>
                {translate(`settings:setup.${state}`)}
              </span>
            </div>
          )
        })}
      </div>
      <p className="mt-4 text-[11px] leading-4 text-wp-muted">{translate('settings:setup.resumeLater')}</p>
    </aside>
  )
}

function StepSection({ title, subtitle, children }: {
  title: string
  subtitle: string
  children: ReactNode
}) {
  return (
    <section>
      <h2 className="text-base font-semibold leading-[22px] text-text-base">{title}</h2>
      <p className="mt-2 text-xs leading-4 text-[color:var(--fh-text-secondary)]">{subtitle}</p>
      <div className="mt-3.5">{children}</div>
    </section>
  )
}

function Actions({
  onBack,
  onNext,
  nextLabel,
  loading,
  nextDisabled,
}: {
  onBack?: () => void
  onNext: () => void
  nextLabel: string
  loading: boolean
  nextDisabled?: boolean
}) {
  return (
    <div className="mt-4 flex flex-col-reverse justify-end gap-2 sm:flex-row">
      {onBack && (
        <button type="button" onClick={onBack} disabled={loading} className="fh-button-secondary fh-button-sm">
          {translate('settings:setup.back')}
        </button>
      )}
      <button
        type="button"
        onClick={onNext}
        disabled={loading || nextDisabled}
        className="fh-button-primary fh-button-sm"
      >
        {loading && <Spinner size="sm" className="text-white" />}
        {loading ? translate('settings:setup.pleaseWait') : nextLabel}
      </button>
    </div>
  )
}

async function responseError(response: Response, fallback: string): Promise<string> {
  const payload = await response.json().catch(() => ({})) as { detail?: string }
  return payload.detail ?? fallback
}

function WorkspaceStep({ onNext }: { onNext: () => void }) {
  const { language, setLanguage, setDirection } = useDirection()
  const detectedTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const [domain, setDomain] = useState(() => window.location.hostname || 'localhost')
  const [timezone, setTimezone] = useState(
    ALL_TIMEZONES.includes(detectedTimezone) ? detectedTimezone : 'UTC',
  )
  const [currency, setCurrency] = useState('USD')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const languageOptions = LANGUAGE_OPTIONS.map(option => ({
    value: option.value,
    label: translate(option.labelKey),
  }))
  const currencyOptions = CURRENCIES.map(option => ({
    value: option.value,
    label: translate(option.labelKey),
  }))

  async function submit(event?: FormEvent) {
    event?.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const body: ServerProfilePayload = {
        domain: domain.trim() || 'localhost',
        timezone,
        currency,
      }
      const response = await fetch('/api/v2/setup/server-profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!response.ok) {
        setError(await responseError(response, translate('settings:setup.serverErrorHttp', { status: response.status })))
        return
      }
      onNext()
    } catch {
      setError(translate('settings:setup.networkError'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <StepSection
      title={translate('settings:setup.workspaceDetails')}
      subtitle={translate('settings:setup.workspaceDetailsDescription')}
    >
      {error && <ErrorBanner message={error} />}
      <form onSubmit={event => { void submit(event) }}>
        <Field
          id="setup-domain"
          label={translate('settings:setup.workspaceDomain')}
          value={domain}
          onChange={setDomain}
          templateVariable="flowhub.example.com"
          disabled={loading}
        />
        <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
          <SearchableListbox
            id="setup-language"
            label={translate('settings:language.title')}
            options={languageOptions}
            value={language}
            onChange={nextLanguage => {
              setLanguage(nextLanguage)
              setDirection(nextLanguage === 'fa' ? 'rtl' : 'ltr')
            }}
            disabled={loading}
          />
          <SearchableListbox
            id="setup-timezone"
            label={translate('settings:settings.timezone')}
            options={TZ_OPTIONS}
            value={timezone}
            onChange={setTimezone}
            disabled={loading}
            template_variable={translate('settings:setup.searchTimezones')}
          />
        </div>
        <div className="mt-3 sm:max-w-[calc(50%-5px)]">
          <SearchableListbox
            id="setup-currency"
            label={translate('settings:setup.defaultCurrency')}
            options={currencyOptions}
            value={currency}
            onChange={setCurrency}
            disabled={loading}
            template_variable={translate('settings:setup.searchCurrencies')}
          />
        </div>
        <Actions onNext={() => { void submit() }} nextLabel={translate('settings:setup.continueToDatabase')} loading={loading} />
      </form>
    </StepSection>
  )
}

function DatabaseStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [status, setStatus] = useState<DatabaseStatusResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function checkDatabase() {
    setError(null)
    setLoading(true)
    try {
      const response = await fetch('/api/v2/setup/database', { method: 'POST' })
      if (!response.ok) {
        setError(await responseError(response, translate('settings:setup.databaseCheckFailedHttp', { status: response.status })))
        return
      }
      setStatus(await response.json() as DatabaseStatusResponse)
    } catch {
      setError(translate('settings:setup.databaseNetworkError'))
    } finally {
      setLoading(false)
    }
  }

  const ready = Boolean(status?.connected && status.is_current === true)
  return (
    <StepSection title={translate('settings:setup.databaseReadiness')} subtitle={translate('settings:setup.databaseReadinessDescription')}>
      {error && <ErrorBanner message={error} />}
      <div className="space-y-2.5">
        <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-bg-card p-3">
          <div>
            <p className="text-[13px] font-medium text-text-base">{translate('settings:setup.connection')}</p>
            <p className="mt-1 text-xs text-[color:var(--fh-text-secondary)]">{translate('settings:setup.connectionDescription')}</p>
          </div>
          <span className={['fh-badge', status?.connected ? 'fh-badge-success' : 'fh-badge-neutral'].join(' ')}>
            {status?.connected ? translate('settings:setup.connected') : translate('settings:setup.notChecked')}
          </span>
        </div>
        <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-bg-card p-3">
          <div>
            <p className="text-[13px] font-medium text-text-base">{translate('settings:setup.schema')}</p>
            <p className="mt-1 text-xs text-[color:var(--fh-text-secondary)]">{translate('settings:setup.schemaDescription')}</p>
          </div>
          <span className={[
            'fh-badge',
            status?.is_current === true
              ? 'fh-badge-success'
              : status?.is_current === false
                ? 'fh-badge-danger'
                : 'fh-badge-neutral',
          ].join(' ')}>
            {status?.is_current === true
              ? translate('settings:setup.upToDate')
              : status?.is_current === false
                ? translate('settings:setup.updateRequired')
                : translate('settings:setup.notChecked')}
          </span>
        </div>
      </div>
      <Actions
        onBack={onBack}
        onNext={ready ? onNext : () => { void checkDatabase() }}
        nextLabel={ready
          ? translate('settings:setup.continueToOwner')
          : status
            ? translate('settings:setup.retryDatabaseCheck')
            : translate('settings:setup.checkDatabase')}
        loading={loading}
      />
    </StepSection>
  )
}

function OwnerStep({
  hasAdmin,
  onAdminCreated,
  onNext,
  onBack,
}: {
  hasAdmin: boolean
  onAdminCreated: () => void
  onNext: () => void
  onBack: () => void
}) {
  const [username, setUsername] = useState('admin')
  const [email, setEmail] = useState('')
  const [emailTouched, setEmailTouched] = useState(false)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const emailError = hasAdmin ? null : validateSetupEmail(email)

  async function createOwner() {
    if (hasAdmin) {
      onNext()
      return
    }
    if (emailError) {
      setEmailTouched(true)
      return
    }
    if (password !== confirm) {
      setError(translate('settings:setup.passwordsDoNotMatch'))
      return
    }
    setError(null)
    setLoading(true)
    try {
      const body: AdminPayload = { username: username.trim(), email: email.trim(), password }
      const response = await fetch('/api/v2/setup/admin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!response.ok) {
        setError(await responseError(response, translate('settings:setup.createOwnerFailedHttp', { status: response.status })))
        return
      }
      const payload = await response.json() as SetupAdminResponse
      localStorage.setItem('wp_token', payload.token)
      localStorage.setItem('wp_refresh_token', payload.refresh_token)
      onAdminCreated()
      onNext()
    } catch {
      setError(translate('settings:setup.ownerNetworkError'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <StepSection
      title={translate('settings:setup.ownerAccount')}
      subtitle={hasAdmin
        ? translate('settings:setup.ownerAlreadyExists')
        : translate('settings:setup.createInitialOwner')}
    >
      {error && <ErrorBanner message={error} />}
      {hasAdmin ? (
        <div className="fh-alert fh-alert-info">{translate('settings:setup.existingOwnerUsed')}</div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field id="owner-username" label={translate('settings:setup.username')} value={username} onChange={setUsername} templateVariable="admin" disabled={loading} />
          </div>
          <div className="sm:col-span-2">
            <Field
              id="owner-email"
              label={translate('settings:setup.email')}
              type="email"
              value={email}
              onChange={value => { setEmail(value); setEmailTouched(true) }}
              templateVariable="admin@example.com"
              disabled={loading}
              autoComplete="email"
              inputMode="email"
              error={emailTouched ? emailError : null}
            />
          </div>
          <Field id="owner-password" label={translate('settings:setup.password')} type="password" value={password} onChange={setPassword} templateVariable={translate('settings:setup.passwordHint')} disabled={loading} />
          <Field id="owner-confirm" label={translate('settings:setup.confirmPassword')} type="password" value={confirm} onChange={setConfirm} templateVariable={translate('settings:setup.confirmPasswordHint')} disabled={loading} />
        </div>
      )}
      <Actions
        onBack={onBack}
        onNext={() => { void createOwner() }}
        nextLabel={hasAdmin ? translate('settings:setup.continueToReview') : translate('settings:setup.createOwner')}
        loading={loading}
        nextDisabled={!hasAdmin && (!username.trim() || Boolean(emailError) || password.length < 8 || confirm.length < 8)}
      />
    </StepSection>
  )
}

function ReviewStep({ onComplete, onBack }: { onComplete: () => void; onBack: () => void }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function finishSetup() {
    setError(null)
    setLoading(true)
    try {
      const response = await fetch('/api/v2/setup/complete', { method: 'POST' })
      if (!response.ok) {
        setError(await responseError(response, translate('settings:setup.finishFailedHttp', { status: response.status })))
        return
      }
      onComplete()
      window.location.assign(localStorage.getItem('wp_token') ? '/home' : '/login')
    } catch {
      setError(translate('settings:setup.finishNetworkError'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <StepSection title={translate('settings:setup.reviewSetup')} subtitle={translate('settings:setup.reviewReadyDescription')}>
      {error && <ErrorBanner message={error} />}
      <div className="rounded-lg bg-bg-base p-4">
        <h3 className="text-sm font-semibold text-text-base">{translate('settings:setup.readyToFinish')}</h3>
        <p className="mt-2 text-xs leading-5 text-[color:var(--fh-text-secondary)]">
          {translate('settings:setup.finishDescription')}
        </p>
      </div>
      <Actions onBack={onBack} onNext={() => { void finishSetup() }} nextLabel={translate('settings:setup.finishSetup')} loading={loading} />
    </StepSection>
  )
}

function ThemeGlyph({ theme }: { theme: 'light' | 'dark' }) {
  return theme === 'dark' ? (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z" />
    </svg>
  )
}

export default function Setup({ onComplete }: SetupProps) {
  const [step, setStep] = useState<Step>('workspace')
  const [statusChecked, setStatusChecked] = useState(false)
  const [hasAdmin, setHasAdmin] = useState(false)
  const { language, setLanguage, setDirection } = useDirection()
  const { theme, toggleTheme } = useTheme()

  useEffect(() => {
    fetch('/api/v2/setup/status')
      .then(response => response.json() as Promise<SetupStatus>)
      .then(status => {
        setHasAdmin(status.has_admin)
        setStatusChecked(true)
      })
      .catch(() => setStatusChecked(true))
  }, [])

  function goNext() {
    const index = SETUP_STEPS.indexOf(step)
    if (index < SETUP_STEPS.length - 1) setStep(SETUP_STEPS[index + 1])
  }

  function goBack() {
    const index = SETUP_STEPS.indexOf(step)
    if (index > 0) setStep(SETUP_STEPS[index - 1])
  }

  if (!statusChecked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-base p-4">
        <div className="fh-card flex items-center gap-2.5 px-5 py-4 fh-text-body-sm">
          <Spinner size="sm" />
          <span>{translate('settings:setup.loadingSetupStatus')}</span>
        </div>
      </div>
    )
  }

  const stepIndex = SETUP_STEPS.indexOf(step)
  return (
    <div className="min-h-screen bg-bg-base px-4 py-6 sm:px-8">
      <header className="mx-auto flex h-10 w-full max-w-[1376px] items-center">
        <div className="flex items-center gap-1.5">
          <img src="/static/logos/FlowHub%20favicon.png?v=4" alt="" className="h-[34px] w-[34px] object-contain" />
          <span className="text-[22px] font-semibold leading-[30px] text-text-base">FlowHub</span>
        </div>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => {
            const nextLanguage = language === 'fa' ? 'en' : 'fa'
            setLanguage(nextLanguage)
            setDirection(nextLanguage === 'fa' ? 'rtl' : 'ltr')
          }}
          className="px-2 text-xs font-medium text-[color:var(--fh-text-secondary)]"
          aria-label={translate('settings:setup.switchLanguage')}
        >
          {language === 'fa' ? 'FA' : 'EN'}
        </button>
        <button
          type="button"
          onClick={toggleTheme}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-[color:var(--fh-text-secondary)] hover:bg-[color:var(--fh-ui-surface-muted)]"
          aria-label={theme === 'dark'
            ? translate('navigation:topbar.switchToLightMode')
            : translate('navigation:topbar.switchToDarkMode')}
        >
          <ThemeGlyph theme={theme} />
        </button>
      </header>

      <main className="fh-card mx-auto mt-5 min-h-[690px] w-full max-w-[900px] overflow-visible p-5 sm:p-6">
        <div className="flex items-center justify-between gap-4">
          <h1 className="text-[22px] font-semibold leading-[30px] text-text-base">{translate('settings:setup.setUpWorkspace')}</h1>
          <span className="fh-badge fh-badge-info shrink-0">{translate('settings:setup.stepOf', { step: stepIndex + 1, total: SETUP_STEPS.length })}</span>
        </div>

        <div className="mt-[18px]">
          <StepProgress current={step} />
        </div>

        <div className="mt-[18px] grid min-h-[480px] items-start gap-[18px] md:grid-cols-[minmax(0,550px)_284px]">
          <div className="min-w-0">
            {step === 'workspace' && <WorkspaceStep onNext={goNext} />}
            {step === 'database' && <DatabaseStep onNext={goNext} onBack={goBack} />}
            {step === 'owner' && (
              <OwnerStep
                hasAdmin={hasAdmin}
                onAdminCreated={() => setHasAdmin(true)}
                onNext={goNext}
                onBack={goBack}
              />
            )}
            {step === 'review' && <ReviewStep onComplete={onComplete} onBack={goBack} />}
          </div>
          <SetupChecklist current={step} />
        </div>
      </main>
    </div>
  )
}
