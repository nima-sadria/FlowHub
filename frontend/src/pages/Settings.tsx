import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth'
import { useServices } from '../services/ServiceContext'
import type { AppSettings } from '../services/types'
import { apiFetch, ApiError } from '../api/client'
import { authFetch } from '../api/authFetch'
import type { HealthResponse } from '../api/types'
import { useNotification } from '../notifications/NotificationProvider'
import Spinner from '../components/loading/Spinner'

const TIMEZONES = [
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

const CURRENCIES = ['IRR', 'IRT', 'USD', 'EUR', 'AED', 'TRY', 'GBP', 'JPY', 'CAD', 'AUD', 'CHF']

function Section({ title, description, children }: {
  title: string; description?: string; children: React.ReactNode
}) {
  return (
    <div className="bg-bg-card border border-border rounded-card shadow-card overflow-hidden">
      <div className="px-[22px] py-4 border-b border-border">
        <p className="text-[14px] font-semibold text-text-base">{title}</p>
        {description && <p className="text-[12px] text-wp-muted mt-0.5">{description}</p>}
      </div>
      <div className="px-[22px] py-5 flex flex-col gap-4">{children}</div>
    </div>
  )
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <label className="block text-[12px] font-medium text-text-base mb-1.5">{label}</label>
      <div className="px-3 py-2 text-[13px] border border-border rounded-lg bg-bg-base text-wp-muted font-mono select-all">
        {value}
      </div>
    </div>
  )
}

function SelectField({ label, value, options, onChange, disabled }: {
  label: string; value: string; options: string[]; onChange: (v: string) => void; disabled?: boolean
}) {
  return (
    <div>
      <label className="block text-[12px] font-medium text-text-base mb-1.5">{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        className="w-full px-3 py-2 text-[13px] border border-border rounded-lg bg-bg-base text-text-base focus:outline-none focus:border-accent transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}

function NumberField({ label, value, min, max, onChange }: {
  label: string; value: number; min: number; max: number; onChange: (v: number) => void
}) {
  return (
    <div>
      <label className="block text-[12px] font-medium text-text-base mb-1.5">{label}</label>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full px-3 py-2 text-[13px] border border-border rounded-lg bg-bg-base text-text-base focus:outline-none focus:border-accent transition-colors"
      />
    </div>
  )
}

function TextField({ label, value, onChange, type = 'text', placeholder }: {
  label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string
}) {
  return (
    <div>
      <label className="block text-[12px] font-medium text-text-base mb-1.5">{label}</label>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 text-[13px] border border-border rounded-lg bg-bg-base text-text-base focus:outline-none focus:border-accent transition-colors"
      />
    </div>
  )
}

function ConfiguredBadge({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-wp-green/10 text-wp-green">Configured</span>
  ) : (
    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-border/60 text-wp-muted">Not configured</span>
  )
}

function IntegrationSection({
  title, description, configured, url, children,
}: {
  title: string
  description: string
  configured: boolean
  url: string
  children: React.ReactNode
}) {
  const [expand, setExpand] = useState(false)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13px] font-semibold text-text-base">{title}</span>
            <ConfiguredBadge ok={configured} />
          </div>
          <p className="text-[12px] text-wp-muted mt-0.5">{description}</p>
          {configured && url && (
            <p className="text-[11px] font-mono text-wp-muted mt-1 truncate">{url}</p>
          )}
        </div>
        <button
          onClick={() => setExpand(e => !e)}
          className="flex-shrink-0 px-3 py-1.5 text-[12px] border border-border rounded-lg text-wp-muted hover:text-text-base hover:border-accent transition-colors"
        >
          {expand ? 'Cancel' : (configured ? 'Replace Credentials' : 'Configure')}
        </button>
      </div>
      {expand && children}
    </div>
  )
}

export default function Settings() {
  const { authFetch: ctxAuthFetch } = useAuth()
  const { settings } = useServices()
  const { success, error: notifyError } = useNotification()

  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthErr, setHealthErr] = useState(false)

  const [appSettings, setAppSettings] = useState<AppSettings | null>(null)
  const [draft, setDraft] = useState<AppSettings | null>(null)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

  // WC credential form
  const [wcUrl, setWcUrl] = useState('')
  const [wcKey, setWcKey] = useState('')
  const [wcSecret, setWcSecret] = useState('')
  const [wcSaving, setWcSaving] = useState(false)
  const [wcMsg, setWcMsg] = useState<{ ok: boolean; text: string } | null>(null)

  // NC credential form
  const [ncUrl, setNcUrl] = useState('')
  const [ncUser, setNcUser] = useState('')
  const [ncPass, setNcPass] = useState('')
  const [ncPath, setNcPath] = useState('')
  const [ncSaving, setNcSaving] = useState(false)
  const [ncMsg, setNcMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true)
    setHealthErr(false)
    try {
      const data = await apiFetch<HealthResponse>('/api/health', ctxAuthFetch)
      setHealth(data)
    } catch {
      setHealthErr(true)
    } finally {
      setHealthLoading(false)
    }
  }, [ctxAuthFetch])

  useEffect(() => { void fetchHealth() }, [fetchHealth])

  const loadSettings = useCallback(() => {
    settings.getSettings().then(s => {
      setAppSettings(s)
      setDraft(s)
    })
  }, [settings])

  useEffect(() => { loadSettings() }, [loadSettings])

  function updateDraft(patch: Partial<AppSettings>) {
    setDraft(d => d ? { ...d, ...patch } : d)
    setDirty(true)
  }

  async function handleSave() {
    if (!draft) return
    setSaving(true)
    try {
      await settings.updateSettings(draft)
      setAppSettings(draft)
      setDirty(false)
      success('Settings saved')
    } catch {
      notifyError('Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveWc() {
    setWcSaving(true)
    setWcMsg(null)
    try {
      const r = await authFetch('/api/v2/settings/woocommerce', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: wcUrl, key: wcKey, secret: wcSecret }),
      })
      const data = await r.json() as { ok: boolean; message: string }
      setWcMsg({ ok: data.ok, text: data.message })
      if (data.ok) { loadSettings(); success('WooCommerce credentials saved') }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Request failed'
      setWcMsg({ ok: false, text: msg })
    } finally {
      setWcSaving(false)
    }
  }

  async function handleSaveNc() {
    setNcSaving(true)
    setNcMsg(null)
    try {
      const r = await authFetch('/api/v2/settings/nextcloud', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: ncUrl, username: ncUser, password: ncPass, spreadsheet_path: ncPath }),
      })
      const data = await r.json() as { ok: boolean; message: string }
      setNcMsg({ ok: data.ok, text: data.message })
      if (data.ok) { loadSettings(); success('Nextcloud credentials saved') }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Request failed'
      setNcMsg({ ok: false, text: msg })
    } finally {
      setNcSaving(false)
    }
  }

  return (
    <div className="p-4 sm:p-7 flex flex-col gap-5 max-w-2xl">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[22px] font-bold text-text-base">Settings</h1>
          <p className="text-[13px] text-wp-muted mt-0.5">Application configuration</p>
        </div>
        {dirty && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setDraft(appSettings); setDirty(false) }}
              className="px-4 py-2 text-[13px] border border-border rounded-lg text-wp-muted hover:text-text-base hover:border-accent transition-colors"
            >
              Discard
            </button>
            <button
              onClick={() => void handleSave()}
              disabled={saving}
              className="px-4 py-2 text-[13px] bg-accent text-white rounded-lg font-medium hover:bg-accent-hover transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {saving && <Spinner size="sm" className="text-white" />}
              {saving ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        )}
      </div>

      {/* About */}
      <Section title="About" description="System version and environment information">
        {healthLoading ? (
          <div className="flex items-center gap-2 text-[13px] text-wp-muted"><Spinner size="sm" />Loading…</div>
        ) : healthErr ? (
          <div className="flex items-center justify-between">
            <p className="text-[13px] text-wp-red">Backend unavailable</p>
            <button onClick={() => void fetchHealth()} className="text-[12px] text-accent hover:underline">Retry</button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <ReadOnlyField label="Version" value={`v${health?.version ?? '—'}`} />
            <ReadOnlyField label="Environment" value={health?.env ?? '—'} />
            <ReadOnlyField label="Status" value={health?.status ?? '—'} />
          </div>
        )}
      </Section>

      {/* Sync Settings */}
      <Section title="Sync Settings" description="Configure how FlowHub synchronises prices">
        {!draft ? (
          <div className="flex items-center gap-2 text-[13px] text-wp-muted"><Spinner size="sm" />Loading…</div>
        ) : (
          <>
            <NumberField
              label="Sync interval (minutes)"
              value={draft.syncIntervalMinutes}
              min={5}
              max={1440}
              onChange={v => updateDraft({ syncIntervalMinutes: v })}
            />
            <SelectField
              label="Timezone"
              value={draft.timezone}
              options={TIMEZONES}
              onChange={v => updateDraft({ timezone: v })}
            />
            <SelectField
              label="Currency"
              value={draft.currency}
              options={CURRENCIES}
              onChange={v => updateDraft({ currency: v })}
            />
          </>
        )}
      </Section>

      {/* WooCommerce Integration */}
      <Section title="WooCommerce Integration" description="Connect your WooCommerce store">
        {!draft ? (
          <div className="flex items-center gap-2 text-[13px] text-wp-muted"><Spinner size="sm" />Loading…</div>
        ) : (
          <IntegrationSection
            title="WooCommerce"
            description="Products and current prices are read from WooCommerce."
            configured={draft.wcConfigured ?? false}
            url={draft.woocommerceUrl}
          >
            <div className="flex flex-col gap-3 pt-1 border-t border-border mt-1">
              <TextField label="Store URL" value={wcUrl} onChange={setWcUrl} placeholder="https://mystore.example.com" />
              <TextField label="Consumer Key" value={wcKey} onChange={setWcKey} placeholder="ck_…" />
              <TextField label="Consumer Secret" value={wcSecret} onChange={setWcSecret} type="password" placeholder="cs_…" />
              {wcMsg && (
                <p className={['text-[12px] font-medium', wcMsg.ok ? 'text-wp-green' : 'text-wp-red'].join(' ')}>
                  {wcMsg.text}
                </p>
              )}
              <button
                onClick={() => void handleSaveWc()}
                disabled={wcSaving || !wcUrl || !wcKey || !wcSecret}
                className="self-start px-4 py-2 text-[13px] bg-accent text-white rounded-lg font-medium hover:bg-accent-hover transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                {wcSaving && <Spinner size="sm" className="text-white" />}
                {wcSaving ? 'Testing…' : 'Save & Test'}
              </button>
            </div>
          </IntegrationSection>
        )}
      </Section>

      {/* Nextcloud Integration */}
      <Section title="Nextcloud Integration" description="Connect a Nextcloud XLSX spreadsheet as price source">
        {!draft ? (
          <div className="flex items-center gap-2 text-[13px] text-wp-muted"><Spinner size="sm" />Loading…</div>
        ) : (
          <IntegrationSection
            title="Nextcloud"
            description="Price lists are read from a Nextcloud XLSX spreadsheet."
            configured={draft.ncConfigured ?? false}
            url={draft.nextcloudUrl}
          >
            <div className="flex flex-col gap-3 pt-1 border-t border-border mt-1">
              <TextField label="Nextcloud URL" value={ncUrl} onChange={setNcUrl} placeholder="https://cloud.example.com" />
              <TextField label="Username" value={ncUser} onChange={setNcUser} placeholder="myuser" />
              <TextField label="App Password" value={ncPass} onChange={setNcPass} type="password" placeholder="xxxx-xxxx-xxxx-xxxx" />
              <TextField label="Spreadsheet Path" value={ncPath} onChange={setNcPath} placeholder="/prices/products.xlsx" />
              {ncMsg && (
                <p className={['text-[12px] font-medium', ncMsg.ok ? 'text-wp-green' : 'text-wp-red'].join(' ')}>
                  {ncMsg.text}
                </p>
              )}
              <button
                onClick={() => void handleSaveNc()}
                disabled={ncSaving || !ncUrl || !ncUser || !ncPass || !ncPath}
                className="self-start px-4 py-2 text-[13px] bg-accent text-white rounded-lg font-medium hover:bg-accent-hover transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                {ncSaving && <Spinner size="sm" className="text-white" />}
                {ncSaving ? 'Testing…' : 'Save & Test'}
              </button>
            </div>
          </IntegrationSection>
        )}
      </Section>
    </div>
  )
}
