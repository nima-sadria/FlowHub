import { useState, useEffect, type FormEvent, type ReactNode } from 'react'
import type {
  ServerProfilePayload,
  AdminPayload,
  WooCommercePayload,
  NextcloudPayload,
  SetupAdminResponse,
  DatabaseStatusResponse,
  ConnectionTestResponse,
  SetupStatus,
} from '../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

type Step = 'welcome' | 'server-profile' | 'database' | 'admin' | 'integrations' | 'complete'

const STEP_LABELS: Record<Step, string> = {
  welcome: 'Welcome',
  'server-profile': 'Server Profile',
  database: 'Database',
  admin: 'Administrator',
  integrations: 'Integrations',
  complete: 'Complete',
}

const STEPS_WITH_ADMIN: Step[] = ['welcome', 'server-profile', 'database', 'admin', 'integrations', 'complete']
const STEPS_NO_ADMIN: Step[] = ['welcome', 'server-profile', 'database', 'integrations', 'complete']

interface SetupProps {
  onComplete: () => void
}

// ── Timezone & Currency data ──────────────────────────────────────────────────

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
  { value: 'IRR', label: 'IRR — Iranian Rial' },
  { value: 'IRT', label: 'IRT — Iranian Toman' },
  { value: 'USD', label: 'USD — US Dollar' },
  { value: 'EUR', label: 'EUR — Euro' },
  { value: 'AED', label: 'AED — UAE Dirham' },
  { value: 'TRY', label: 'TRY — Turkish Lira' },
  { value: 'GBP', label: 'GBP — British Pound' },
  { value: 'JPY', label: 'JPY — Japanese Yen' },
  { value: 'CAD', label: 'CAD — Canadian Dollar' },
  { value: 'AUD', label: 'AUD — Australian Dollar' },
  { value: 'CHF', label: 'CHF — Swiss Franc' },
]

const TZ_OPTIONS = ALL_TIMEZONES.map(tz => ({ value: tz, label: tz }))

// ── Shared UI helpers ─────────────────────────────────────────────────────────

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
  id, label, options, value, onChange, disabled, placeholder,
}: {
  id?: string
  label: string
  options: { value: string; label: string }[]
  value: string
  onChange: (v: string) => void
  disabled?: boolean
  placeholder?: string
}) {
  const [search, setSearch] = useState('')
  const q = search.trim().toLowerCase()
  const filtered = q
    ? options.filter(o => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q))
    : options
  const selectedLabel = options.find(o => o.value === value)?.label ?? value

  return (
    <div>
      <label className="block text-[13px] font-medium text-text-base mb-1.5">{label}</label>
      <input
        type="text"
        value={search || selectedLabel}
        onChange={e => setSearch(e.target.value)}
        onFocus={e => e.currentTarget.select()}
        placeholder={placeholder ?? `Search ${label.toLowerCase()}…`}
        disabled={disabled}
        autoComplete="off"
        className="w-full min-w-0 mb-1.5 border border-border rounded-lg px-3 py-1.5 text-[13px] bg-bg-base text-text-base focus:outline-none focus:border-accent placeholder:text-wp-muted disabled:opacity-60 truncate"
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
  id, label, type = 'text', value, onChange, placeholder, required = false, disabled = false, hint,
}: {
  id: string; label: string; type?: string; value: string; onChange: (v: string) => void
  placeholder?: string; required?: boolean; disabled?: boolean; hint?: string
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-[13px] font-medium text-text-base mb-1.5">
        {label}{required && <span className="text-wp-red ml-0.5">*</span>}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        disabled={disabled}
        autoComplete="off"
        className="w-full border border-border rounded-lg px-3 py-2 text-[14px] bg-bg-base text-text-base focus:outline-none focus:border-accent placeholder:text-wp-muted disabled:opacity-60"
      />
      {hint && <p className="mt-1 text-[11.5px] text-wp-muted">{hint}</p>}
    </div>
  )
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div role="alert" className="mb-4 bg-[#fee2e2] border border-[#ef4444]/30 rounded-lg px-4 py-3 text-[13px] text-[#dc2626]">
      {message}
    </div>
  )
}

function SuccessBanner({ message }: { message: string }) {
  return (
    <div className="mb-4 bg-[#dcfce7] border border-[#22c55e]/30 rounded-lg px-4 py-3 text-[13px] text-[#16a34a]">
      {message}
    </div>
  )
}

function StepDots({ current, steps }: { current: Step; steps: Step[] }) {
  const currentIdx = steps.indexOf(current)
  const visibleSteps = steps.filter(s => s !== 'complete')
  return (
    <div className="flex items-center gap-2 mb-8">
      {visibleSteps.map((s, idx) => (
        <div key={s} className="flex items-center gap-2">
          <div className={[
            'w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold transition-colors',
            idx < currentIdx ? 'bg-accent text-white' :
            idx === currentIdx ? 'bg-accent text-white ring-2 ring-accent/30' :
            'bg-border text-wp-muted',
          ].join(' ')}>
            {idx < currentIdx ? '✓' : idx + 1}
          </div>
          {idx < visibleSteps.length - 1 && (
            <div className={['h-px w-8 transition-colors', idx < currentIdx ? 'bg-accent' : 'bg-border'].join(' ')} />
          )}
        </div>
      ))}
    </div>
  )
}

function NavButtons({
  onBack, onNext, nextLabel = 'Next', loading = false, nextDisabled = false, hideBack = false,
}: {
  onBack?: () => void; onNext?: () => void; nextLabel?: string; loading?: boolean
  nextDisabled?: boolean; hideBack?: boolean
}) {
  return (
    <div className="flex gap-3 mt-6">
      {!hideBack && onBack && (
        <button
          type="button"
          onClick={onBack}
          disabled={loading}
          className="px-4 py-2 rounded-lg border border-border text-[13px] font-medium text-wp-muted hover:border-accent hover:text-text-base transition-colors disabled:opacity-50"
        >
          Back
        </button>
      )}
      <button
        type={onNext ? 'button' : 'submit'}
        onClick={onNext}
        disabled={loading || nextDisabled}
        className="flex-1 bg-accent text-white py-2 rounded-lg text-[14px] font-semibold hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {loading ? <><AppleSpinner size={16} /> Please wait</> : nextLabel}
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

// ── Step: Welcome ─────────────────────────────────────────────────────────────

function WelcomeStep({ onNext, hasAdmin }: { onNext: () => void; hasAdmin: boolean }) {
  const steps = hasAdmin
    ? [
        ['Server Profile', 'Configure your domain, timezone, and currency.'],
        ['Database', 'Verify your database connection.'],
        ['Integrations', 'Optionally connect WooCommerce and Nextcloud.'],
      ]
    : [
        ['Server Profile', 'Configure your domain, timezone, and currency.'],
        ['Database', 'Verify your database connection.'],
        ['Administrator', 'Create your administrator account.'],
        ['Integrations', 'Optionally connect WooCommerce and Nextcloud.'],
      ]

  return (
    <StepCard
      title="Welcome to FlowHub"
      subtitle="This wizard will guide you through the initial setup. It takes about 2 minutes."
    >
      <div className="space-y-3 mb-6">
        {steps.map(([label, desc]) => (
          <div key={label} className="flex gap-3 p-3 bg-bg-base rounded-lg border border-border">
            <span className="text-accent mt-0.5 flex-shrink-0">→</span>
            <div>
              <p className="text-[13px] font-semibold text-text-base">{label}</p>
              <p className="text-[12px] text-wp-muted">{desc}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="p-3 bg-[#eff6ff] border border-[#4880FF]/20 rounded-lg mb-4 text-[12px] text-[#1e40af]">
        FlowHub Beta is <strong>read-only</strong>. No changes will be made to your WooCommerce store during setup.
      </div>
      <NavButtons onNext={onNext} nextLabel="Start Setup" hideBack />
    </StepCard>
  )
}

// ── Step: Server Profile ──────────────────────────────────────────────────────

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
          placeholder="yourdomain.com or localhost"
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
          placeholder="Search timezones… (e.g. Tehran, London, UTC)"
        />
        <SearchableListbox
          id="sp-cur"
          label="Currency"
          options={CURRENCIES}
          value={currency}
          onChange={setCurrency}
          disabled={loading}
          placeholder="Search currencies… (e.g. USD, IRR)"
        />
      </div>
      <NavButtons onBack={onBack} onNext={handleSubmit} loading={loading} />
    </StepCard>
  )
}

// ── Step: Database ────────────────────────────────────────────────────────────

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
      subtitle="Verify your database connection and migration status."
    >
      {error && <ErrorBanner message={error} />}

      <div className="mb-4 p-3 bg-[#eff6ff] border border-[#4880FF]/20 rounded-lg text-[12px] text-[#1e40af]">
        The database is configured and managed by the installer. This step only verifies the connection and migrations.
      </div>

      {!checked && (
        <div className="mb-4 p-4 bg-bg-base border border-border rounded-lg text-[13px] text-wp-muted">
          Click <strong>Check Database</strong> to verify the connection.
        </div>
      )}

      {status && (
        <div className="space-y-2 mb-4">
          {status.database_name && (
            <div className="flex items-center justify-between p-3 bg-bg-base border border-border rounded-lg">
              <span className="text-[13px] text-text-base">Database</span>
              <span className="text-[12px] font-medium text-wp-muted font-mono">{status.database_name}</span>
            </div>
          )}
          <StatusRow
            label="Connection"
            hint="Verifies the app can reach the database."
            ok={status.connected}
            okText="Connected"
            failText={status.error ?? 'Failed'}
          />
          <StatusRow
            label="Current revision"
            hint="The Alembic revision currently recorded in the database."
            ok={!!status.current_revision}
            okText={status.current_revision ?? '—'}
            failText="Not available"
            neutral
          />
          <StatusRow
            label="Latest revision"
            hint="The latest FlowHub migration available to this build."
            ok={!!status.latest_revision}
            okText={status.latest_revision ?? '—'}
            failText="Not available"
            neutral
          />
          <StatusRow
            label="Schema status"
            hint="Schema status compares the database revision with the latest FlowHub migration."
            ok={status.is_current === true}
            okText="Up to date"
            failText={status.is_current === false ? 'Needs update — run repair' : 'Unable to verify'}
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
          nextDisabled={!status?.connected}
        />
      )}
    </StepCard>
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
        'text-[12px] font-medium flex-shrink-0 mt-0.5',
        neutral ? 'text-wp-muted' : ok ? 'text-wp-green' : 'text-wp-red',
      ].join(' ')}>
        {ok ? okText : failText}
      </span>
    </div>
  )
}

// ── Step: Administrator (recovery mode only) ──────────────────────────────────

function AdminStep({
  onNext, onBack,
}: { onNext: (token: string, refreshToken: string) => void; onBack: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const body: AdminPayload = { username: username.trim(), password }
      const r = await fetch('/api/v2/setup/admin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json() as SetupAdminResponse & { detail?: string }
      if (!r.ok) {
        setError(d.detail ?? `Server error (HTTP ${r.status})`)
        return
      }
      onNext(d.token, d.refresh_token)
    } catch {
      setError('Network error. Check your connection and try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <StepCard
      title="Administrator Account"
      subtitle="No admin account was found. Create the first administrator to continue."
    >
      {error && <ErrorBanner message={error} />}
      <form onSubmit={e => { void handleSubmit(e) }} className="space-y-4">
        <Field
          id="adm-user"
          label="Username"
          value={username}
          onChange={setUsername}
          placeholder="admin"
          required
          disabled={loading}
          hint="3–50 characters: letters, numbers, underscores, hyphens, and dots."
        />
        <Field
          id="adm-pass"
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          placeholder="Minimum 8 characters"
          required
          disabled={loading}
        />
        <Field
          id="adm-conf"
          label="Confirm Password"
          type="password"
          value={confirm}
          onChange={setConfirm}
          placeholder="Repeat the password"
          required
          disabled={loading}
        />
        <NavButtons onBack={onBack} loading={loading} nextLabel="Create Account" />
      </form>
    </StepCard>
  )
}

// ── Step: Optional Integrations ───────────────────────────────────────────────

function IntegrationsStep({
  onNext, onBack,
}: { onNext: () => void; onBack: () => void }) {
  // WooCommerce
  const [wcUrl, setWcUrl] = useState('')
  const [wcKey, setWcKey] = useState('')
  const [wcSecret, setWcSecret] = useState('')
  const [wcResult, setWcResult] = useState<ConnectionTestResponse | null>(null)
  const [wcLoading, setWcLoading] = useState(false)

  // Nextcloud
  const [ncUrl, setNcUrl] = useState('')
  const [ncUser, setNcUser] = useState('')
  const [ncPass, setNcPass] = useState('')
  const [ncPath, setNcPath] = useState('')
  const [ncResult, setNcResult] = useState<ConnectionTestResponse | null>(null)
  const [ncLoading, setNcLoading] = useState(false)

  const [configureNow, setConfigureNow] = useState(false)
  const [finishError, setFinishError] = useState<string | null>(null)
  const [finishLoading, setFinishLoading] = useState(false)

  async function saveAndTestWC() {
    setWcLoading(true)
    setWcResult(null)
    try {
      const body: WooCommercePayload = { url: wcUrl.trim(), key: wcKey.trim(), secret: wcSecret.trim() }
      const r = await fetch('/api/v2/setup/integrations/woocommerce', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json() as ConnectionTestResponse
      setWcResult(d)
    } catch {
      setWcResult({ ok: false, message: 'Network error.' })
    } finally {
      setWcLoading(false)
    }
  }

  async function saveAndTestNC() {
    setNcLoading(true)
    setNcResult(null)
    try {
      const body: NextcloudPayload = {
        url: ncUrl.trim(),
        username: ncUser.trim(),
        password: ncPass,
        spreadsheet_path: ncPath.trim(),
      }
      const r = await fetch('/api/v2/setup/integrations/nextcloud', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json() as ConnectionTestResponse
      setNcResult(d)
    } catch {
      setNcResult({ ok: false, message: 'Network error.' })
    } finally {
      setNcLoading(false)
    }
  }

  async function handleFinishSetup() {
    setFinishError(null)
    setFinishLoading(true)
    try {
      const r = await fetch('/api/v2/setup/complete', { method: 'POST' })
      if (!r.ok) {
        const d = await r.json().catch(() => ({})) as { detail?: string }
        setFinishError(d.detail ?? `Could not complete setup (HTTP ${r.status}). Please try again.`)
        return
      }
      onNext()
    } catch {
      setFinishError('Network error while completing setup. Check your connection and try again.')
    } finally {
      setFinishLoading(false)
    }
  }

  if (!configureNow) {
    return (
      <StepCard
        title="Integrations"
        subtitle="Both are optional — you can configure them later from Settings."
      >
        <div className="space-y-3 mb-6">
          {[
            ['WooCommerce', 'Connect your store to read products and current prices.'],
            ['Nextcloud', 'Connect a spreadsheet as a price reference source.'],
          ].map(([label, desc]) => (
            <div key={label} className="flex gap-3 p-3 bg-bg-base rounded-lg border border-border">
              <span className="text-accent mt-0.5 flex-shrink-0">→</span>
              <div>
                <p className="text-[13px] font-semibold text-text-base">{label}</p>
                <p className="text-[12px] text-wp-muted">{desc}</p>
              </div>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setConfigureNow(true)}
          className="w-full mb-3 py-2 rounded-lg border border-border text-[13px] font-medium text-wp-muted hover:border-accent hover:text-text-base transition-colors"
        >
          Configure now →
        </button>
        {finishError && <ErrorBanner message={finishError} />}
        <NavButtons
          onBack={onBack}
          onNext={() => { void handleFinishSetup() }}
          nextLabel="Skip — Configure Later"
          loading={finishLoading}
        />
      </StepCard>
    )
  }

  return (
    <StepCard
      title="Integrations"
      subtitle="Connect your data sources. Both are optional — you can configure them later in Settings."
    >
      {/* WooCommerce */}
      <div className="mb-6 p-4 border border-border rounded-lg">
        <h3 className="text-[14px] font-semibold text-text-base mb-3">WooCommerce</h3>
        <div className="space-y-3">
          <Field id="wc-url" label="Store URL" value={wcUrl} onChange={setWcUrl}
            placeholder="https://mystore.com" disabled={wcLoading} />
          <Field id="wc-key" label="Consumer Key" value={wcKey} onChange={setWcKey}
            placeholder="ck_..." disabled={wcLoading} />
          <Field id="wc-secret" label="Consumer Secret" type="password" value={wcSecret}
            onChange={setWcSecret} placeholder="cs_..." disabled={wcLoading} />
        </div>
        {wcResult && (wcResult.ok
          ? <SuccessBanner message={wcResult.message} />
          : <ErrorBanner message={wcResult.message} />
        )}
        <button
          type="button"
          onClick={() => { void saveAndTestWC() }}
          disabled={wcLoading || !wcUrl || !wcKey || !wcSecret}
          className="mt-3 w-full py-2 rounded-lg border border-accent text-accent text-[13px] font-medium hover:bg-accent/5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {wcLoading ? 'Testing…' : 'Save & Test Connection'}
        </button>
      </div>

      {/* Nextcloud */}
      <div className="mb-4 p-4 border border-border rounded-lg">
        <h3 className="text-[14px] font-semibold text-text-base mb-3">Nextcloud</h3>
        <div className="space-y-3">
          <Field id="nc-url" label="Nextcloud URL" value={ncUrl} onChange={setNcUrl}
            placeholder="https://cloud.example.com" disabled={ncLoading} />
          <Field id="nc-user" label="Username" value={ncUser} onChange={setNcUser}
            placeholder="your Nextcloud username" disabled={ncLoading} />
          <Field id="nc-pass" label="App Password" type="password" value={ncPass}
            onChange={setNcPass} placeholder="Generate from Nextcloud security settings"
            disabled={ncLoading} hint="Use an App Password, not your Nextcloud login password." />
          <Field id="nc-path" label="Spreadsheet Path" value={ncPath} onChange={setNcPath}
            placeholder="/prices/products.xlsx" disabled={ncLoading}
            hint="Path to the price list spreadsheet inside your Nextcloud Files." />
        </div>
        {ncResult && (ncResult.ok
          ? <SuccessBanner message={ncResult.message} />
          : <ErrorBanner message={ncResult.message} />
        )}
        <button
          type="button"
          onClick={() => { void saveAndTestNC() }}
          disabled={ncLoading || !ncUrl || !ncUser || !ncPass}
          className="mt-3 w-full py-2 rounded-lg border border-accent text-accent text-[13px] font-medium hover:bg-accent/5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {ncLoading ? 'Testing…' : 'Save & Test Connection'}
        </button>
      </div>

      {finishError && <ErrorBanner message={finishError} />}
      <NavButtons
        onBack={() => setConfigureNow(false)}
        onNext={() => { void handleFinishSetup() }}
        nextLabel="Finish Setup"
        loading={wcLoading || ncLoading || finishLoading}
      />
    </StepCard>
  )
}

// ── Step: Complete ────────────────────────────────────────────────────────────

function CompleteStep({ onDone }: { onDone: () => void }) {
  return (
    <StepCard title="Setup Complete">
      <div className="text-center py-6">
        <div className="w-16 h-16 rounded-full bg-[#dcfce7] flex items-center justify-center mx-auto mb-4">
          <svg viewBox="0 0 24 24" className="w-8 h-8 text-wp-green" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
        <h3 className="text-[16px] font-bold text-text-base mb-2">FlowHub is ready</h3>
        <p className="text-[13px] text-wp-muted mb-6">
          Setup is complete. Sign in with the administrator account created during installation.
          Integrations and additional settings can be configured from the Settings page.
        </p>
        <button
          type="button"
          onClick={onDone}
          className="w-full bg-accent text-white py-2.5 rounded-lg text-[14px] font-semibold hover:bg-accent/90 transition-colors"
        >
          Go to Sign In
        </button>
      </div>
    </StepCard>
  )
}

// ── Main Setup component ──────────────────────────────────────────────────────

export default function Setup({ onComplete }: SetupProps) {
  const [step, setStep] = useState<Step>('welcome')
  const [hasAdmin, setHasAdmin] = useState(true)
  const [statusChecked, setStatusChecked] = useState(false)

  useEffect(() => {
    fetch('/api/v2/setup/status')
      .then(r => r.json() as Promise<SetupStatus>)
      .then(d => {
        setHasAdmin(d.has_admin)
        setStatusChecked(true)
      })
      .catch(() => {
        setHasAdmin(false)
        setStatusChecked(true)
      })
  }, [])

  const stepOrder = hasAdmin ? STEPS_NO_ADMIN : STEPS_WITH_ADMIN

  function goNext() {
    const idx = stepOrder.indexOf(step)
    if (idx < stepOrder.length - 1) setStep(stepOrder[idx + 1])
  }

  function goBack() {
    const idx = stepOrder.indexOf(step)
    if (idx > 0) setStep(stepOrder[idx - 1])
  }

  function handleAdminCreated(token: string, refreshToken: string) {
    localStorage.setItem('wp_token', token)
    localStorage.setItem('wp_refresh_token', refreshToken)
    goNext()
  }

  const stepIndex = stepOrder.indexOf(step)

  if (!statusChecked) {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <p className="text-[13px] text-wp-muted">Loading…</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-bg-base flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="mb-6 text-center">
          <h1 className="text-[24px] font-bold text-text-base">FlowHub</h1>
          <p className="text-[13px] text-wp-muted mt-0.5">
            {step === 'complete' ? 'Setup complete' : `Step ${stepIndex + 1} of ${stepOrder.length - 1} — ${STEP_LABELS[step]}`}
          </p>
        </div>

        {step !== 'complete' && <StepDots current={step} steps={stepOrder} />}

        <div className="bg-bg-card border border-border rounded-card shadow-card p-7">
          {step === 'welcome' && (
            <WelcomeStep onNext={goNext} hasAdmin={hasAdmin} />
          )}
          {step === 'server-profile' && (
            <ServerProfileStep onNext={goNext} onBack={goBack} />
          )}
          {step === 'database' && (
            <DatabaseStep onNext={goNext} onBack={goBack} />
          )}
          {step === 'admin' && (
            <AdminStep onNext={handleAdminCreated} onBack={goBack} />
          )}
          {step === 'integrations' && (
            <IntegrationsStep onNext={goNext} onBack={goBack} />
          )}
          {step === 'complete' && (
            <CompleteStep onDone={onComplete} />
          )}
        </div>
      </div>
    </div>
  )
}
