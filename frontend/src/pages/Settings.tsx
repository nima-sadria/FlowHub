import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth'
import { useServices } from '../services/ServiceContext'
import type { AppSettings } from '../services/types'
import { apiFetch } from '../api/client'
import type { HealthResponse } from '../api/types'
import { useNotification } from '../notifications/NotificationProvider'
import Icon from '../components/Icon'
import Spinner from '../components/loading/Spinner'
import PageShell from '../components/PageShell'
import { RateLimitsPanel } from './RateLimits'

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
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <div className="fh-card overflow-hidden">
      <div className="fh-panel-header !min-h-0 !items-start">
        <div>
          <p className="fh-section-title">{title}</p>
          {description && <p className="fh-section-subtitle mt-1">{description}</p>}
        </div>
      </div>
      <div className="fh-panel-body flex flex-col gap-4">{children}</div>
    </div>
  )
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="fh-field">
      <label className="fh-help-text">{label}</label>
      <div className="rounded-lg border border-border bg-bg-base px-3 py-2 fh-text-body-sm font-mono select-all">
        {value}
      </div>
    </div>
  )
}

function SelectField({ label, value, options, onChange, disabled }: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
  disabled?: boolean
}) {
  return (
    <div className="fh-field">
      <label className="fh-help-text">{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        className="fh-select"
      >
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}

function NumberField({ label, value, min, max, onChange }: {
  label: string
  value: number
  min: number
  max: number
  onChange: (v: number) => void
}) {
  return (
    <div className="fh-field">
      <label className="fh-help-text">{label}</label>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={e => onChange(Number(e.target.value))}
        className="fh-input"
      />
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

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">Settings</h1>
          <p className="fh-page-subtitle">Application settings</p>
        </div>
        {dirty && (
          <div className="fh-actions">
            <button
              onClick={() => { setDraft(appSettings); setDirty(false) }}
              className="fh-button-secondary"
            >
              <Icon name="close" />
              Discard
            </button>
            <button
              onClick={() => void handleSave()}
              disabled={saving}
              className="fh-button-primary"
            >
              {saving && <Spinner size="sm" className="text-white" />}
              {!saving && <Icon name="save" />}
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        )}
      </div>

      <Section title="General" description="Configure display and synchronization preferences">
        {!draft ? (
          <div className="flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />Loading...</div>
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

      <RateLimitsPanel embedded />

      <Section title="About" description="Application information">
        {healthLoading ? (
          <div className="flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />Loading...</div>
        ) : healthErr ? (
          <div className="flex items-center justify-between">
            <p className="fh-text-body-sm text-wp-red">Backend unavailable</p>
            <button onClick={() => void fetchHealth()} className="fh-toolbar-link">
              <Icon name="retry" />
              Retry
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <ReadOnlyField label="Version" value={`v${health?.version ?? '-'}`} />
            <ReadOnlyField label="Status" value={health?.status ?? '-'} />
          </div>
        )}
      </Section>
    </PageShell>
  )
}
