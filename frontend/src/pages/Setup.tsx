import { useEffect, useState, type InputHTMLAttributes, type ReactNode } from 'react'
import type {
  ServerProfilePayload,
  DatabaseStatusResponse,
  SetupStatus,
  AdminPayload,
  SetupAdminResponse,
} from '../api/types'
import { inputHint } from '../utils/inputHint'

type Step = 'welcome' | 'server-profile' | 'database' | 'admin' | 'finish'

const STEP_LABELS: Record<Step, string> = {
  welcome: 'Welcome',
  'server-profile': 'Server Profile',
  database: 'Database',
  admin: 'Admin Account',
  finish: 'Finish',
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
  { value: 'IRR', label: 'IRR - Iranian Rial' },
  { value: 'IRT', label: 'IRT - Iranian Toman' },
  { value: 'USD', label: 'USD - US Dollar' },
  { value: 'EUR', label: 'EUR - Euro' },
  { value: 'AED', label: 'AED - UAE Dirham' },
  { value: 'TRY', label: 'TRY - Turkish Lira' },
  { value: 'GBP', label: 'GBP - British Pound' },
  { value: 'JPY', label: 'JPY - Japanese Yen' },
  { value: 'CAD', label: 'CAD - Canadian Dollar' },
  { value: 'AUD', label: 'AUD - Australian Dollar' },
  { value: 'CHF', label: 'CHF - Swiss Franc' },
]

const TZ_OPTIONS = ALL_TIMEZONES.map(tz => ({ value: tz, label: tz }))
const EMAIL_ERROR = 'Enter a valid email address.'

export function validateSetupEmail(value: string): string | null {
  const email = value.trim()
  if (!email) return EMAIL_ERROR
  if (email.includes(' ') || (email.match(/@/g) ?? []).length !== 1) return EMAIL_ERROR

  const [local, domain] = email.split('@')
  if (!local || !domain || domain.length > 253 || !domain.includes('.')) return EMAIL_ERROR

  const labels = domain.split('.')
  const validLabels = labels.every(label => (
    label.length > 0 &&
    label.length <= 63 &&
    /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/.test(label)
  ))
  const tld = labels[labels.length - 1]
  if (!validLabels || !/^[A-Za-z]{2,63}$/.test(tld)) return EMAIL_ERROR
  if (!/^[^\s@]+$/.test(local)) return EMAIL_ERROR

  return null
}

function AppleSpinner({ size = 18 }: { size?: number }) {
  const half = size / 2
  const spokeH = Math.max(4, Math.round(size * 0.33))
  const spokeW = Math.max(2, Math.round(size * 0.11))
  return (
    <span
      aria-hidden="true"
      style={{ position: 'relative', display: 'inline-block', width: size, height: size, flexShrink: 0 }}
    >
      {Array.from({ length: 12 }, (_, i) => (
        <span
          key={i}
          style={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            width: spokeW,
            height: spokeH,
            marginLeft: -spokeW / 2,
            marginTop: -half,
            borderRadius: spokeW / 2,
            background: 'currentColor',
            transformOrigin: `${spokeW / 2}px ${half}px`,
            transform: `rotate(${i * 30}deg)`,
            animation: 'apple-spoke 1.2s linear infinite',
            animationDelay: `${(i * 0.1 - 1.2).toFixed(1)}s`,
          }}
        />
      ))}
    </span>
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
  const q = search.trim().toLowerCase()
  const filtered = q
    ? options.filter(o => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q))
    : options
  const selectedLabel = options.find(o => o.value === value)?.label ?? value

  return (
    <div className="min-w-0">
      <label className="block text-[13px] font-medium text-text-base mb-1.5">{label}</label>
      <input
        type="text"
        value={search || selectedLabel}
        onChange={e => setSearch(e.target.value)}
        onFocus={e => e.currentTarget.select()}
        {...inputHint(template_variable ?? `Search ${label.toLowerCase()}...`)}
        disabled={disabled}
        autoComplete="off"
        className="w-full min-w-0 mb-1.5 border border-border rounded-lg px-3 py-1.5 text-[13px] bg-bg-base text-text-base focus:outline-none focus:border-accent disabled:opacity-60 truncate"
      />
      <div
        id={id}
        role="listbox"
        aria-label={label}
        className="max-h-40 overflow-y-auto border border-border rounded-lg"
      >
        {filtered.length === 0 ? (
          <div className="px-3 py-2 text-[13px] text-wp-muted">No matches</div>
        ) : filtered.map(opt => (
          <button
            key={opt.value}
            type="button"
            role="option"
            aria-selected={opt.value === value}
            onClick={() => { onChange(opt.value); setSearch('') }}
            disabled={disabled}
            className={[
              'w-full text-left px-3 py-2 text-[13px] leading-snug break-words',
              opt.value === value
                ? 'bg-accent text-white font-medium'
                : 'bg-bg-base text-text-base hover:bg-border',
            ].join(' ')}
          >
            {opt.label}
          </button>
        ))}
      </div>
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
    <div>
      <label htmlFor={id} className="block text-[13px] font-medium text-text-base mb-1.5">{label}</label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        {...inputHint(template_variable)}
        disabled={disabled}
        autoComplete={autoComplete}
        inputMode={inputMode}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
        className={[
          'w-full border rounded-lg px-3 py-2 text-[14px] bg-bg-base text-text-base focus:outline-none focus:border-accent disabled:opacity-60',
          error ? 'border-wp-red' : 'border-border',
        ].join(' ')}
      />
      {hint && <p id={`${id}-hint`} className="mt-1 text-[11.5px] text-wp-muted">{hint}</p>}
      {error && <p id={`${id}-error`} className="mt-1 text-[11.5px] text-wp-red">{error}</p>}
    </div>
  )
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div role="alert" className="fh-error-alert mb-4 rounded-lg px-4 py-3 text-[13px]">
      {message}
    </div>
  )
}

function StepDots({ current, steps }: { current: Step; steps: Step[] }) {
  const currentIdx = steps.indexOf(current)
  return (
    <div className="flex items-center gap-2 mb-8">
      {steps.map((s, idx) => (
        <div key={s} className="flex items-center gap-2">
          <div className={[
            'w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold transition-colors',
            idx < currentIdx ? 'bg-accent text-white' :
            idx === currentIdx ? 'bg-accent text-white ring-2 ring-accent/30' :
            'bg-border text-wp-muted',
          ].join(' ')}>
            {idx < currentIdx ? 'OK' : idx + 1}
          </div>
          {idx < steps.length - 1 && (
            <div className={['h-px w-8 transition-colors', idx < currentIdx ? 'bg-accent' : 'bg-border'].join(' ')} />
          )}
        </div>
      ))}
    </div>
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
    <div className="flex gap-3 mt-6">
      {!hideBack && (
        <button
          type="button"
          onClick={onBack}
          disabled={loading}
          className="flex-1 py-2.5 rounded-lg border border-border text-[14px] font-medium text-wp-muted hover:text-text-base hover:border-accent transition-colors disabled:opacity-50"
        >
          Back
        </button>
      )}
      <button
        type="button"
        onClick={onNext}
        disabled={loading || nextDisabled}
        className="flex-1 py-2.5 rounded-lg bg-accent text-white text-[14px] font-semibold hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {loading && <AppleSpinner size={16} />}
        {loading ? 'Please wait...' : nextLabel}
      </button>
    </div>
  )
}

function StepCard({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div>
      <h2 className="text-[18px] font-bold text-text-base mb-1">{title}</h2>
      {subtitle && <p className="text-[13px] text-wp-muted mb-6">{subtitle}</p>}
      {children}
    </div>
  )
}

function StatusRow({
  label, hint, ok, okText, failText, neutral = false,
}: { label: string; hint?: string; ok: boolean; okText: string; failText: string; neutral?: boolean }) {
  return (
    <div className="flex items-start justify-between p-3 bg-bg-base border border-border rounded-lg gap-3">
      <div>
        <p className="text-[13px] text-text-base leading-tight">{label}</p>
        {hint && <p className="text-[11px] text-wp-muted mt-0.5">{hint}</p>}
      </div>
      <span className={[
        'text-[12px] font-medium flex-shrink-0 mt-0.5 text-right',
        neutral ? 'text-wp-muted' : ok ? 'text-wp-green' : 'text-wp-red',
      ].join(' ')}>
        {ok ? okText : failText}
      </span>
    </div>
  )
}

function WelcomeStep({ onNext }: { onNext: () => void }) {
  const steps = [
    ['Server Profile', 'Configure your domain, timezone, and currency.'],
    ['Database', 'Verify your database connection.'],
    ['Admin Account', 'Create the first administrator account.'],
    ['Finish', 'Lock setup and continue to FlowHub.'],
  ]

  return (
    <StepCard
      title="Welcome to FlowHub"
      subtitle="This wizard will guide you through initial setup."
    >
      <div className="space-y-3 mb-6">
        {steps.map(([label, desc]) => (
          <div key={label} className="flex gap-3 p-3 bg-bg-base rounded-lg border border-border">
            <span className="text-accent mt-0.5 flex-shrink-0">{'->'}</span>
            <div>
              <p className="text-[13px] font-semibold text-text-base">{label}</p>
              <p className="text-[12px] text-wp-muted">{desc}</p>
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
    <StepCard title="Server Profile" subtitle="Configure how FlowHub identifies itself.">
      {error && <ErrorBanner message={error} />}
      <div className="space-y-4">
        <Field
          id="sp-domain"
          label="Domain"
          value={domain}
          onChange={setDomain}
          template_variable="yourdomain.com or localhost"
          hint="The domain where FlowHub is accessible. Used in links and notifications."
          disabled={loading}
        />
        <SearchableListbox
          id="sp-tz"
          label="Timezone"
          options={TZ_OPTIONS}
          value={timezone}
          onChange={setTimezone}
          disabled={loading}
          template_variable="Search timezones... (e.g. Tehran, London, UTC)"
        />
        <SearchableListbox
          id="sp-cur"
          label="Currency"
          options={CURRENCIES}
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
      title="Database"
      subtitle="Verify your database connection and schema status."
    >
      {error && <ErrorBanner message={error} />}

      {!checked && (
        <div className="mb-4 p-4 bg-bg-base border border-border rounded-lg text-[13px] text-wp-muted">
          Click <strong>Check Database</strong> to verify the connection.
        </div>
      )}

      {status && (
        <div className="space-y-2 mb-4">
          <StatusRow
            label="Connection"
            hint="Verifies the app can reach the database."
            ok={status.connected}
            okText="Connected"
            failText={status.error ?? 'Failed'}
          />
          <StatusRow
            label="Database Schema Version"
            hint="The schema version currently available to FlowHub."
            ok={!!status.current_revision}
            okText="Available"
            failText="Unable to verify"
            neutral
          />
          <StatusRow
            label="Schema status"
            hint="Compares the installed database schema with the version required by this FlowHub release."
            ok={status.is_current === true}
            okText="Up to date"
            failText={status.is_current === false ? 'Needs update - run repair' : 'Unable to verify'}
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
          nextLabel={status?.connected ? 'Continue' : 'Retry'}
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
      title="Admin Account"
      subtitle={hasAdmin ? 'An administrator account already exists.' : 'Create the first administrator account.'}
    >
      {error && <ErrorBanner message={error} />}
      {hasAdmin ? (
        <div className="mb-4 p-4 bg-bg-base border border-border rounded-lg text-[13px] text-wp-muted">
          FlowHub already has an administrator account. Continue to finish setup.
        </div>
      ) : (
        <div className="space-y-4">
          <Field
            id="admin-username"
            label="Username"
            value={username}
            onChange={setUsername}
            template_variable="admin"
            disabled={loading}
          />
          <Field
            id="admin-email"
            label="Email"
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
            label="Password"
            type="password"
            value={password}
            onChange={setPassword}
            template_variable="At least 8 characters"
            disabled={loading}
          />
          <Field
            id="admin-confirm"
            label="Confirm password"
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
        nextLabel={hasAdmin ? 'Continue' : 'Create Admin'}
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
    <StepCard title="Finish" subtitle="Complete setup and start using FlowHub.">
      {error && <ErrorBanner message={error} />}
      <div className="mb-4 p-4 bg-bg-base border border-border rounded-lg text-[13px] text-wp-muted">
        Setup is ready to be finalized. Connector configuration is available from Settings after sign-in.
      </div>
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
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <p className="text-[13px] text-wp-muted">Loading...</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-bg-base flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        <div className="mb-6 text-center">
          <h1 className="text-[24px] font-bold text-text-base">FlowHub</h1>
          <p className="text-[13px] text-wp-muted mt-0.5">
            Step {stepIndex + 1} of {SETUP_STEPS.length} - {STEP_LABELS[step]}
          </p>
        </div>

        <StepDots current={step} steps={SETUP_STEPS} />

        <div className="bg-bg-card border border-border rounded-card shadow-card p-7">
          {step === 'welcome' && <WelcomeStep onNext={goNext} />}
          {step === 'server-profile' && <ServerProfileStep onNext={goNext} onBack={goBack} />}
          {step === 'database' && <DatabaseStep onNext={goNext} onBack={goBack} />}
          {step === 'admin' && <AdminStep hasAdmin={hasAdmin} onAdminCreated={() => setHasAdmin(true)} onNext={goNext} onBack={goBack} />}
          {step === 'finish' && <FinishStep onComplete={onComplete} onBack={goBack} />}
        </div>
      </div>
    </div>
  )
}
