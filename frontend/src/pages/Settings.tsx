import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth'
import { useServices } from '../services/ServiceContext'
import type { AppSettings } from '../services/types'
import { apiFetch } from '../api/client'
import type { HealthResponse } from '../api/types'
import { useNotification } from '../notifications/NotificationProvider'
import Spinner from '../components/loading/Spinner'

const TIMEZONES = [
  'UTC', 'Asia/Tehran', 'Asia/Dubai', 'Europe/London', 'Europe/Berlin',
  'America/New_York', 'America/Los_Angeles',
]

const CURRENCIES = ['USD', 'EUR', 'GBP', 'IRR', 'AED']

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

export default function Settings() {
  const { authFetch } = useAuth()
  const { settings } = useServices()
  const { success, error: notifyError } = useNotification()

  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthErr, setHealthErr] = useState(false)

  const [appSettings, setAppSettings] = useState<AppSettings | null>(null)
  const [draft, setDraft] = useState<AppSettings | null>(null)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true)
    setHealthErr(false)
    try {
      const data = await apiFetch<HealthResponse>('/api/health', authFetch)
      setHealth(data)
    } catch {
      setHealthErr(true)
    } finally {
      setHealthLoading(false)
    }
  }, [authFetch])

  useEffect(() => { void fetchHealth() }, [fetchHealth])

  useEffect(() => {
    settings.getSettings().then(s => {
      setAppSettings(s)
      setDraft(s)
    })
  }, [settings])

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

  function handleDiscard() {
    setDraft(appSettings)
    setDirty(false)
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
              onClick={handleDiscard}
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

      {/* About — real /api/health data */}
      <Section title="About" description="System version and environment information">
        {healthLoading ? (
          <div className="flex items-center gap-2 text-[13px] text-wp-muted">
            <Spinner size="sm" />
            Loading…
          </div>
        ) : healthErr ? (
          <div className="flex items-center justify-between">
            <p className="text-[13px] text-wp-red">Backend unavailable</p>
            <button
              onClick={() => void fetchHealth()}
              className="text-[12px] text-accent hover:underline"
            >
              Retry
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <ReadOnlyField label="Version" value={`v${health?.version ?? '—'}`} />
            <ReadOnlyField label="Environment" value={health?.env ?? '—'} />
            <ReadOnlyField label="Status" value={health?.status ?? '—'} />
          </div>
        )}
      </Section>

      {/* Sync Settings — mock, persisted to sessionStorage */}
      <Section title="Sync Settings" description="Configure how WooPrice synchronises prices">
        {!draft ? (
          <div className="flex items-center gap-2 text-[13px] text-wp-muted">
            <Spinner size="sm" />
            Loading…
          </div>
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

      {/* Connections — read-only */}
      <Section title="Connections" description="Source connection settings are configured via environment or CLI">
        <div className="p-4 bg-bg-base border border-border rounded-lg">
          <div className="flex items-start gap-3">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4 text-wp-muted flex-shrink-0 mt-0.5">
              <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            <p className="text-[12px] text-wp-muted leading-relaxed">
              Nextcloud and WooCommerce connection credentials are configured via environment variables or the server configuration file.
              Editing them here is not available in BU3.
            </p>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <ReadOnlyField label="Nextcloud" value="Configured via env" />
          <ReadOnlyField label="WooCommerce" value="Configured via env" />
        </div>
      </Section>
    </div>
  )
}
