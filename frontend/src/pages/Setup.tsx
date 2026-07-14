import { translate } from '../i18n'
import { useEffect, useRef, useState, type InputHTMLAttributes, type ReactNode } from 'react'
import type {
  ServerProfilePayload,
  DatabaseStatusResponse,
  SetupStatus,
  AdminPayload,
  SetupAdminResponse,
} from '../api/types'
import { inputHint } from '../utils/inputHint'

type Step = 'welcome' | 'server-profile' | 'database' | 'admin' | 'finish'

const STEP_LABEL_KEYS: Record<Step, string> = {
  welcome: 'settings:setup.welcome',
  'server-profile': 'settings:setup.serverProfile',
  database: 'settings:setup.database',
  admin: 'settings:setup.ownerAccount',
  finish: 'settings:setup.finish',
}

type SetupIcon = 'spark' | 'server' | 'database' | 'user' | 'check' | 'alert'

const STEP_DETAILS: Record<Step, { labelKey: string; descriptionKey: string; icon: SetupIcon }> = {
  welcome: {
    labelKey: 'settings:setup.welcome',
    descriptionKey: 'settings:setup.reviewTheInstallationPathBeforeFlowhubIs',
    icon: 'spark',
  },
  'server-profile': {
    labelKey: 'settings:setup.serverProfile',
    descriptionKey: 'settings:setup.setTheDomainTimezoneAndDefaultCurrency',
    icon: 'server',
  },
  database: {
    labelKey: 'settings:setup.database',
    descriptionKey: 'settings:setup.confirmThatTheDatabaseConnectionAndSchema',
    icon: 'database',
  },
  admin: {
    labelKey: 'settings:setup.ownerAccount',
    descriptionKey: 'settings:setup.createOrConfirmTheInitialOwnerAccount',
    icon: 'user',
  },
  finish: {
    labelKey: 'settings:setup.finish',
    descriptionKey: 'settings:setup.completeSetupAndOpenTheFlowhubWorkspace',
    icon: 'check',
  },
}

const SETUP_STEPS: Step[] = ['welcome', 'server-profile', 'database', 'admin', 'finish']

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

const TZ_OPTIONS = ALL_TIMEZONES.map(tz => ({ value: tz, label: tz }))
const EMAIL_ERROR_KEY = 'validation:setup.validEmailRequired'

export function validateSetupEmail(value: string): string | null {
  const email = value.trim()
  if (!email) return translate(EMAIL_ERROR_KEY)
  if (email.includes(' ') || (email.match(/@/g) ?? []).length !== 1) return translate(EMAIL_ERROR_KEY)

  const [local, domain] = email.split('@')
  if (!local || !domain || domain.length > 253 || !domain.includes('.')) return translate(EMAIL_ERROR_KEY)

  const labels = domain.split('.')
  const validLabels = labels.every(label => (
    label.length > 0 &&
    label.length <= 63 &&
    /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/.test(label)
  ))
  const tld = labels[labels.length - 1]
  if (!validLabels || !/^[A-Za-z]{2,63}$/.test(tld)) return translate(EMAIL_ERROR_KEY)
  if (!/^[^\s@]+$/.test(local)) return translate(EMAIL_ERROR_KEY)

  return null
}

function AppleSpinner({ size = 18 }: { size?: number }) {
  const half = size / 2
  const spokeH = Math.max(4, Math.round(size * 0.33))
  const spokeW = Math.max(2, Math.round(size * 0.11))
  return (
    <span
      aria-hidden="true"
      style={{ position: "relative", display: "inline-block", width: size, height: size, flexShrink: 0 }}
    >
      {Array.from({ length: 12 }, (_, i) => (
        <span
          key={i}
          style={{
            position: "absolute",
            left: '50%',
            top: '50%',
            width: spokeW,
            height: spokeH,
            marginLeft: -spokeW / 2,
            marginTop: -half,
            borderRadius: spokeW / 2,
            background: "currentColor",
            transformOrigin: `${spokeW / 2}px ${half}px`,
            transform: `rotate(${i * 30}deg)`,
            animation: "apple-spoke 1.2s linear infinite",
            animationDelay: `${(i * 0.1 - 1.2).toFixed(1)}s`,
          }}
        />
      ))}
    </span>
  )
}

function SetupIconGlyph({ icon, className = 'w-5 h-5' }: { icon: SetupIcon; className?: string }) {
  const common = {
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className} {...common}>
      {icon === "spark" && (
        <>
          <path d="M12 3l1.7 4.6L18 9.2l-4.3 1.6L12 15.5l-1.7-4.7L6 9.2l4.3-1.6L12 3Z" />
          <path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8L19 14Z" />
          <path d="M5 13l.7 1.8L7.5 15.5l-1.8.7L5 18l-.7-1.8-1.8-.7 1.8-.7L5 13Z" />
        </>
      )}
      {icon === "server" && (
        <>
          <rect x="4" y="4" width="16" height="6" rx="2" />
          <rect x="4" y="14" width="16" height="6" rx="2" />
          <path d="M8 7h.01" />
          <path d="M8 17h.01" />
          <path d="M12 7h4" />
          <path d="M12 17h4" />
        </>
      )}
      {icon === "database" && (
        <>
          <ellipse cx="12" cy="5" rx="7" ry="3" />
          <path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5" />
          <path d="M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" />
        </>
      )}
      {icon === "user" && (
        <>
          <path d="M20 21a8 8 0 0 0-16 0" />
          <circle cx="12" cy="8" r="4" />
        </>
      )}
      {icon === "check" && <path d="M20 6 9 17l-5-5" />}
      {icon === "alert" && (
        <>
          <path d="M12 9v4" />
          <path d="M12 17h.01" />
          <path d="M10.3 4.4 2.8 18a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3L13.7 4.4a2 2 0 0 0-3.4 0Z" />
        </>
      )}
    </svg>
  )
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
      className={["w-4 h-4 flex-shrink-0 text-wp-muted transition-transform", open ? "rotate-180" : ''].join(' ')}
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  )
}

export function SearchableListbox({
  id, label, options, value, onChange, disabled, template_variable,
}: {
  id?: string
  label: string
  options: { value: string; label: string }[]
  value: string
  onChange: (v: string) => void
  disabled?: boolean
  template_variable?: string
}) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const q = search.trim().toLowerCase()
  const filtered = q
    ? options.filter(o => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q))
    : options
  const selectedLabel = options.find(o => o.value === value)?.label ?? value

  useEffect(() => {
    if (!open) return
    searchRef.current?.focus()

    function closeOnOutsideClick(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false)
        setSearch('')
      }
    }

    document.addEventListener('mousedown', closeOnOutsideClick)
    return () => document.removeEventListener('mousedown', closeOnOutsideClick)
  }, [open])

  function handleSelect(nextValue: string) {
    onChange(nextValue)
    setSearch('')
    setOpen(false)
  }

  return (
    <div ref={rootRef} className="relative min-w-0">
      <label className="fh-label mb-1 block">{label}</label>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        onKeyDown={e => {
          if (e.key === 'Escape') {
            setOpen(false)
            setSearch('')
          }
        }}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={id}
        disabled={disabled}
        className="fh-input mb-1 min-w-0 flex items-center justify-between gap-2 text-left"
      >
        <span className="truncate">{selectedLabel}</span>
        <ChevronIcon open={open} />
      </button>
      {open && (
        <div
          className="absolute z-50 w-full rounded-lg border border-border bg-bg-card shadow-card overflow-hidden"
        >
          <div className="p-2 border-b border-border">
            <input
              ref={searchRef}
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Escape') {
                  setOpen(false)
                  setSearch('')
                }
                if (e.key === 'Enter' && filtered[0]) {
                  handleSelect(filtered[0].value)
                }
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
          ) : filtered.map(opt => (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={opt.value === value}
                onClick={() => handleSelect(opt.value)}
                disabled={disabled}
                className={[
                  "w-full text-left px-3 py-2 fh-text-body break-words flex items-center justify-between gap-3",
                  opt.value === value
                    ? "bg-fh-mist-100 text-accent font-medium"
                    : "bg-bg-card text-text-base hover:bg-bg-base",
                ].join(' ')}
              >
                <span>{opt.label}</span>
                {opt.value === value && (
                  <svg viewBox="0 0 24 24" className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Field({
  id, label, type = 'text', value, onChange, template_variable, disabled = false, hint, error,
  autoComplete = 'off', inputMode,
}: {
  id: string
  label: string
  type?: string
  value: string
  onChange: (v: string) => void
  template_variable?: string
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
        onChange={e => onChange(e.target.value)}
        {...inputHint(template_variable)}
        disabled={disabled}
        autoComplete={autoComplete}
        inputMode={inputMode}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={describedBy}
        className={[
          "fh-input",
          error ? "fh-input-error" : '',
        ].join(' ')}
      />
      {hint && <p id={`${id}-hint`} className="fh-help-text">{hint}</p>}
      {error && <p id={`${id}-error`} className="fh-field-error">{error}</p>}
    </div>
  )
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div role="alert" className="fh-error-alert mb-5">
      <SetupIconGlyph icon="alert" className="mt-0.5 h-4 w-4 flex-shrink-0" />
      <span>{message}</span>
    </div>
  )
}

function StepProgress({ current, steps }: { current: Step; steps: Step[] }) {
  const currentIdx = steps.indexOf(current)
  return (
    <>
      <ol className="flex items-center px-1 lg:hidden" aria-label={translate('settings:setup.setupProgress')}>
        {steps.map((s, idx) => (
          <li key={s} className="flex min-w-0 flex-1 items-center last:flex-none">
            <span
              aria-current={idx === currentIdx ? "step" : undefined}
              className={[
                "flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border text-xs font-semibold",

                idx <= currentIdx
                  ? "border-accent bg-accent text-white shadow-sm"
                  : "border-border bg-bg-card text-wp-muted",
              ].join(' ')}
              title={translate(STEP_DETAILS[s].labelKey)}
            >
              {idx < currentIdx ? <SetupIconGlyph icon="check" className="h-4 w-4" /> : idx + 1}
            </span>
            {idx < steps.length - 1 && (
              <span className={["mx-2 h-px flex-1", idx < currentIdx ? "bg-accent" : "bg-border"].join(' ')} />
            )}
          </li>
        ))}
      </ol>

      <ol className="hidden gap-1.5 lg:grid" aria-label={translate('settings:setup.setupProgress')}>
        {steps.map((s, idx) => (
          <li key={s}>
            <div
              aria-current={idx === currentIdx ? "step" : undefined}
              className={[
                "flex items-center gap-2.5 rounded-lg border px-2.5 py-2 transition-colors",
                idx === currentIdx
                  ? "border-accent bg-fh-mist-100 text-text-base"
                  : idx < currentIdx
                    ? "border-border bg-bg-card text-text-base"
                    : "border-transparent bg-transparent text-wp-muted",
              ].join(' ')}
            >
              <span className={[
                "flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg border",
                idx <= currentIdx ? "border-accent bg-accent text-white" : "border-border bg-bg-base text-wp-muted",
              ].join(' ')}>
                {idx < currentIdx ? (
                  <SetupIconGlyph icon="check" className="h-3.5 w-3.5" />
                ) : (
                  <SetupIconGlyph icon={STEP_DETAILS[s].icon} className="h-3.5 w-3.5" />
                )}
              </span>
              <span className="min-w-0">
                <span className="block truncate fh-text-body font-semibold">{translate(STEP_DETAILS[s].labelKey)}</span>
                <span className="block truncate fh-text-body-sm">
                  {idx < currentIdx ? translate('settings:setup.completed') : idx === currentIdx ? translate('settings:setup.inProgress') : translate('settings:setup.pending')}
                </span>
              </span>
            </div>
          </li>
        ))}
      </ol>
    </>
  )
}

function NavButtons({
  onBack, onNext, nextLabel = 'Continue', loading = false, hideBack = false, nextDisabled = false,
}: {
  onBack?: () => void
  onNext?: () => void
  nextLabel?: string
  loading?: boolean
  hideBack?: boolean
  nextDisabled?: boolean
}) {
  return (
    <div className="mt-5 flex flex-col-reverse gap-2.5 sm:flex-row sm:justify-end">
      {!hideBack && (
        <button
          type="button"
          onClick={onBack}
          disabled={loading}
          className="fh-button-secondary w-full sm:w-auto sm:min-w-24"
        >
          {translate('settings:setup.back')}
        </button>
      )}
      <button
        type="button"
        onClick={onNext}
        disabled={loading || nextDisabled}
        className="fh-button-primary w-full sm:w-auto sm:min-w-32"
      >
        {loading && <AppleSpinner size={16} />}
        {loading ? translate('settings:setup.pleaseWait') : nextLabel}
      </button>
    </div>
  )
}

function StepCard({
  title,
  subtitle,
  titleClassName = 'fh-section-title',
  subtitleClassName = 'fh-section-subtitle',
  children,
}: {
  title: string
  subtitle?: string
  titleClassName?: string
  subtitleClassName?: string
  children: ReactNode
}) {
  return (
    <div>
      <div className="mb-5">
        <h2 className={titleClassName}>{title}</h2>
        {subtitle && <p className={["mt-1", subtitleClassName].join(' ')}>{subtitle}</p>}
      </div>
      {children}
    </div>
  )
}

function StatusRow({
  label, hint, ok, okText, failText, neutral = false,
}: { label: string; hint?: string; ok: boolean; okText: string; failText: string; neutral?: boolean }) {
  const statusLabel = ok ? okText : failText
  const tone = neutral ? 'neutral' : ok ? 'success' : 'danger'
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-border bg-bg-card p-3">
      <div className="min-w-0">
        <p className="fh-text-body font-semibold">{label}</p>
        {hint && <p className="mt-1 fh-text-body-sm">{hint}</p>}
      </div>
      <span className={[
        "fh-badge flex-shrink-0 whitespace-nowrap",
        tone === "success" ? "fh-badge-success" : tone === "danger" ? "fh-badge-danger" : "fh-badge-neutral",
      ].join(' ')}>
        {statusLabel}
      </span>
    </div>
  )
}

function InfoPanel({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-bg-base px-3 py-2.5 fh-text-body-sm">
      {children}
    </div>
  )
}

function WelcomeStep({ onNext }: { onNext: () => void }) {
  const steps = SETUP_STEPS.filter(step => step !== 'welcome')
  return (
    <StepCard
      title={translate('settings:setup.welcomeToFlowhub')}
      subtitle="This wizard only captures the required system defaults. Connector setup stays available after sign-in."
      titleClassName="fh-page-title"
    >
      <div className="grid gap-2.5">
        {steps.map((stepName, idx) => (
          <div key={stepName} className="flex gap-2.5 rounded-lg border border-border bg-bg-base p-3">
            <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-fh-mist-100 text-accent">
              <SetupIconGlyph icon={STEP_DETAILS[stepName].icon} className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="fh-text-body font-semibold">
                {idx + 1}. {translate(STEP_DETAILS[stepName].labelKey)}
              </p>
              <p className="fh-text-body-sm">{translate(STEP_DETAILS[stepName].descriptionKey)}</p>
            </div>
          </div>
        ))}
      </div>
      <NavButtons onNext={onNext} nextLabel="Start Setup" hideBack />
    </StepCard>
  )
}

function ServerProfileStep({
  onNext, onBack,
}: { onNext: () => void; onBack: () => void }) {
  const [domain, setDomain] = useState('')
  const [timezone, setTimezone] = useState('UTC')
  const [currency, setCurrency] = useState('USD')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit() {
    setError(null)
    setLoading(true)
    try {
      const body: ServerProfilePayload = {
        domain: domain.trim() || 'localhost',
        timezone,
        currency,
      }
      const r = await fetch('/api/v2/setup/server-profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!r.ok) {
        const d = await r.json().catch(() => ({})) as { detail?: string }
        setError(d.detail ?? `Server error (HTTP ${r.status})`)
        return
      }
      onNext()
    } catch {
      setError('Network error. Check your connection and try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <StepCard title={translate('settings:setup.serverProfile')} subtitle="Configure how FlowHub identifies itself.">
      {error && <ErrorBanner message={error} />}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
        <Field
          id="sp-domain"
          label={translate('settings:setup.domain')}
          value={domain}
          onChange={setDomain}
          template_variable="yourdomain.com or localhost"
          hint="The domain where FlowHub is accessible. Used in links and notifications."
          disabled={loading}
        />
        </div>
        <SearchableListbox
          id="sp-tz"
          label={translate('settings:settings.timezone')}
          options={TZ_OPTIONS}
          value={timezone}
          onChange={setTimezone}
          disabled={loading}
          template_variable="Search timezones... (e.g. Tehran, London, UTC)"
        />
        <SearchableListbox
          id="sp-cur"
          label={translate('settings:settings.currency')}
          options={CURRENCIES.map(option => ({ value: option.value, label: translate(option.labelKey) }))}
          value={currency}
          onChange={setCurrency}
          disabled={loading}
          template_variable="Search currencies... (e.g. USD, IRR)"
        />
      </div>
      <NavButtons onBack={onBack} onNext={handleSubmit} loading={loading} />
    </StepCard>
  )
}

function DatabaseStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [status, setStatus] = useState<DatabaseStatusResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [checked, setChecked] = useState(false)

  async function checkDatabase() {
    setError(null)
    setLoading(true)
    try {
      const r = await fetch('/api/v2/setup/database', { method: 'POST' })
      const d = await r.json() as DatabaseStatusResponse
      if (!r.ok) {
        setError((d as unknown as { detail?: string }).detail ?? `HTTP ${r.status}`)
        return
      }
      setStatus(d)
      setChecked(true)
    } catch {
      setError('Network error while checking database.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <StepCard
      title={translate('settings:setup.database')}
      subtitle="Verify your database connection and schema status."
    >
      {error && <ErrorBanner message={error} />}

      {!checked && (
        <InfoPanel>
          {translate('settings:setup.click')} <strong>{translate('settings:setup.checkDatabase')}</strong> {translate('settings:setup.toVerifyTheConnection')}
        </InfoPanel>
      )}

      {status && (
        <div className="grid gap-3">
          <StatusRow
            label={translate('settings:setup.connection')}
            hint="Verifies the app can reach the database."
            ok={status.connected}
            okText="Connected"
            failText={status.error ?? "Failed"}
          />
          <StatusRow
            label={translate('settings:setup.databaseSchemaVersion')}
            hint="The schema version currently available to FlowHub."
            ok={!!status.current_revision}
            okText="Available"
            failText="Unable to verify"
            neutral
          />
          <StatusRow
            label={translate('settings:setup.schemaStatus')}
            hint="Compares the installed database schema with the version required by this FlowHub release."
            ok={status.is_current === true}
            okText="Up to date"
            failText={status.is_current === false ? "Needs update - run repair" : "Unable to verify"}
            neutral={status.is_current !== false && status.is_current !== true}
          />
        </div>
      )}

      {!checked ? (
        <NavButtons
          onBack={onBack}
          onNext={checkDatabase}
          nextLabel="Check Database"
          loading={loading}
        />
      ) : (
        <NavButtons
          onBack={onBack}
          onNext={status?.connected ? onNext : checkDatabase}
          nextLabel={status?.connected ? "Continue" : "Retry"}
          loading={loading}
          nextDisabled={!status?.connected || status.is_current !== true}
        />
      )}
    </StepCard>
  )
}

function AdminStep({
  hasAdmin, onAdminCreated, onNext, onBack,
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

  async function createAdmin() {
    if (hasAdmin) {
      onNext()
      return
    }
    if (emailError) {
      setEmailTouched(true)
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const body: AdminPayload = { username: username.trim(), email: email.trim(), password }
      const r = await fetch('/api/v2/setup/admin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json().catch(() => ({})) as Partial<SetupAdminResponse> & { detail?: string }
      if (!r.ok) {
        setError(d.detail ?? `Could not create administrator (HTTP ${r.status}).`)
        return
      }
      if (d.token) localStorage.setItem('wp_token', d.token)
      if (d.refresh_token) localStorage.setItem('wp_refresh_token', d.refresh_token)
      onAdminCreated()
      onNext()
    } catch {
      setError('Network error while creating administrator.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <StepCard
      title={translate('settings:setup.ownerAccount')}
      subtitle={hasAdmin ? "An owner or administrator account already exists." : "Create the initial owner account."}
    >
      {error && <ErrorBanner message={error} />}
      {hasAdmin ? (
        <InfoPanel>
          {translate('settings:setup.flowhubAlreadyHasAnOwnerOrAdministrator')}
        </InfoPanel>
      ) : (
        <div className="space-y-4">
          <Field
            id="admin-username"
            label={translate('settings:setup.username')}
            value={username}
            onChange={setUsername}
            template_variable="admin"
            disabled={loading}
          />
          <Field
            id="admin-email"
            label={translate('settings:setup.email')}
            type="email"
            value={email}
            onChange={(value) => { setEmail(value); setEmailTouched(true) }}
            template_variable="admin@example.com"
            disabled={loading}
            autoComplete="email"
            inputMode="email"
            error={emailTouched ? emailError : null}
          />
          <Field
            id="admin-password"
            label={translate('settings:setup.password')}
            type="password"
            value={password}
            onChange={setPassword}
            template_variable="At least 8 characters"
            disabled={loading}
          />
          <Field
            id="admin-confirm"
            label={translate('settings:setup.confirmPassword')}
            type="password"
            value={confirm}
            onChange={setConfirm}
            template_variable="Repeat password"
            disabled={loading}
          />
        </div>
      )}
      <NavButtons
        onBack={onBack}
        onNext={createAdmin}
        loading={loading}
        nextLabel={hasAdmin ? "Continue" : "Create Owner"}
        nextDisabled={!hasAdmin && (!username.trim() || !!emailError || password.length < 8 || confirm.length < 8)}
      />
    </StepCard>
  )
}

function FinishStep({ onComplete, onBack }: { onComplete: () => void; onBack: () => void }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function finishSetup() {
    setError(null)
    setLoading(true)
    try {
      const r = await fetch('/api/v2/setup/complete', { method: 'POST' })
      if (!r.ok) {
        const d = await r.json().catch(() => ({})) as { detail?: string }
        setError(d.detail ?? `Could not finish setup (HTTP ${r.status}).`)
        return
      }
      onComplete()
      window.location.assign(localStorage.getItem('wp_token') ? '/home' : '/login')
    } catch {
      setError('Network error while finishing setup.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <StepCard title={translate('settings:setup.finish')} subtitle="Complete setup and start using FlowHub.">
      {error && <ErrorBanner message={error} />}
      <InfoPanel>
        {translate('settings:setup.setupIsReadyToBeFinalizedConnector')}
      </InfoPanel>
      <NavButtons onBack={onBack} onNext={finishSetup} loading={loading} nextLabel="Finish Setup" />
    </StepCard>
  )
}

export default function Setup({ onComplete }: SetupProps) {
  const [step, setStep] = useState<Step>('welcome')
  const [statusChecked, setStatusChecked] = useState(false)
  const [hasAdmin, setHasAdmin] = useState(false)

  useEffect(() => {
    fetch('/api/v2/setup/status')
      .then(r => r.json() as Promise<SetupStatus>)
      .then(d => {
        setHasAdmin(d.has_admin)
        setStatusChecked(true)
      })
      .catch(() => setStatusChecked(true))
  }, [])

  function goNext() {
    const idx = SETUP_STEPS.indexOf(step)
    if (idx < SETUP_STEPS.length - 1) setStep(SETUP_STEPS[idx + 1])
  }

  function goBack() {
    const idx = SETUP_STEPS.indexOf(step)
    if (idx > 0) setStep(SETUP_STEPS[idx - 1])
  }

  const stepIndex = SETUP_STEPS.indexOf(step)

  if (!statusChecked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-base p-4">
        <div className="fh-card flex items-center gap-3 px-5 py-4 fh-text-body-sm">
          <AppleSpinner size={18} />
          <span>{translate('settings:setup.loadingSetupStatus')}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-bg-base p-3 sm:p-5 lg:p-7">
      <div className="mx-auto grid min-h-[calc(100vh-1.5rem)] w-full max-w-5xl items-center gap-4 lg:min-h-[calc(100vh-3.5rem)] lg:grid-cols-[minmax(260px,320px)_minmax(0,560px)] lg:justify-center">
        <aside className="fh-card overflow-hidden">
          <div className="border-b border-border p-4 sm:p-5">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-white shadow-sm">
                <SetupIconGlyph icon="spark" className="h-[18px] w-[18px]" />
              </div>
              <div>
                <h1 className="fh-section-title">{translate('settings:setup.flowhub')}</h1>
                <p className="fh-text-body-sm">{translate('settings:setup.setupConsole')}</p>
              </div>
            </div>
            <div className="rounded-lg border border-border bg-bg-base p-3">
              <p className="fh-section-label">{translate('settings:setup.currentStep')}</p>
              <div className="mt-2.5 flex items-start gap-2.5">
                <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-fh-mist-100 text-accent">
                  <SetupIconGlyph icon={STEP_DETAILS[step].icon} className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <p className="fh-text-body font-semibold">
                    {translate(STEP_LABEL_KEYS[step])}
                  </p>
                  <p className="mt-0.5 fh-text-body-sm">
                    {translate(STEP_DETAILS[step].descriptionKey)}
                  </p>
                </div>
              </div>
            </div>
          </div>
          <div className="p-3">
            <StepProgress current={step} steps={SETUP_STEPS} />
          </div>
        </aside>

        <main className="fh-card overflow-visible p-5 sm:p-6">
          <p className="mb-3 fh-section-label">{translate('settings:setup.step2')} {stepIndex + 1} {translate('settings:setup.of')} {SETUP_STEPS.length}</p>
          {step === "welcome" && <WelcomeStep onNext={goNext} />}
          {step === "server-profile" && <ServerProfileStep onNext={goNext} onBack={goBack} />}
          {step === "database" && <DatabaseStep onNext={goNext} onBack={goBack} />}
          {step === "admin" && <AdminStep hasAdmin={hasAdmin} onAdminCreated={() => setHasAdmin(true)} onNext={goNext} onBack={goBack} />}
          {step === "finish" && <FinishStep onComplete={onComplete} onBack={goBack} />}
        </main>
      </div>
    </div>
  )
}
