import { useEffect, useMemo, useState } from 'react'
import { useServices } from '../services/ServiceContext'
import type { RateLimitSettings } from '../services/types'
import { useNotification } from '../notifications/NotificationProvider'
import Spinner from '../components/loading/Spinner'
import PageShell from '../components/PageShell'

const MIN_RPM = 1
const MAX_RPM = 1000

function delayLabel(rpm: number): string {
  if (!rpm || rpm < MIN_RPM) return '-'
  const seconds = 60 / rpm
  return seconds >= 1 ? `${seconds.toFixed(2)} seconds` : `${(seconds * 1000).toFixed(0)} ms`
}

function NumberField({ label, value, onChange }: {
  label: string
  value: number
  onChange: (value: number) => void
}) {
  return (
    <div className="fh-field">
      <label className="fh-help-text">{label}</label>
      <input
        type="number"
        min={MIN_RPM}
        max={MAX_RPM}
        value={value}
        onChange={event => onChange(Number(event.target.value))}
        className="fh-input"
      />
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="fh-stat-tile">
      <div className="fh-stat-tile-label uppercase tracking-[0.08em]">{label}</div>
      <div className="fh-stat-tile-value">{value}</div>
    </div>
  )
}

export function RateLimitsPanel({ embedded = false }: { embedded?: boolean }) {
  const { settings } = useServices()
  const { success, error: notifyError } = useNotification()
  const [current, setCurrent] = useState<RateLimitSettings | null>(null)
  const [readRpm, setReadRpm] = useState(60)
  const [writeRpm, setWriteRpm] = useState(30)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let active = true
    async function load() {
      setLoading(true)
      try {
        const data = await settings.getRateLimits()
        if (!active) return
        setCurrent(data)
        setReadRpm(data.read_requests_per_minute)
        setWriteRpm(data.write_requests_per_minute)
      } catch {
        if (active) notifyError('Failed to load rate limits')
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => { active = false }
  }, [settings])

  const validation = useMemo(() => {
    if (readRpm < MIN_RPM || readRpm > MAX_RPM) return 'Read Requests / Minute must be between 1 and 1000.'
    if (writeRpm < MIN_RPM || writeRpm > MAX_RPM) return 'Write Requests / Minute must be between 1 and 1000.'
    return null
  }, [readRpm, writeRpm])

  const dirty = current
    ? readRpm !== current.read_requests_per_minute || writeRpm !== current.write_requests_per_minute
    : false

  async function save() {
    if (validation) return
    setSaving(true)
    try {
      const updated = await settings.updateRateLimits({
        read_requests_per_minute: readRpm,
        write_requests_per_minute: writeRpm,
      })
      setCurrent(updated)
      setReadRpm(updated.read_requests_per_minute)
      setWriteRpm(updated.write_requests_per_minute)
      success('Rate limits saved')
    } catch {
      notifyError('Failed to save rate limits')
    } finally {
      setSaving(false)
    }
  }

  const actions = dirty && (
    <div className="fh-actions">
      <button
        onClick={() => {
          if (!current) return
          setReadRpm(current.read_requests_per_minute)
          setWriteRpm(current.write_requests_per_minute)
        }}
        className="fh-button-secondary"
      >
        Discard
      </button>
      <button
        onClick={() => void save()}
        disabled={saving || Boolean(validation)}
        className="fh-button-primary"
      >
        {saving && <Spinner size="sm" className="text-white" />}
        {saving ? 'Saving...' : 'Save Changes'}
      </button>
    </div>
  )

  const editor = (
    <>
      <div className="fh-card fh-card-pad">
        {loading ? (
          <div className="flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />Loading...</div>
        ) : (
          <div className="flex flex-col gap-4">
            <NumberField label="Read Requests / Minute" value={readRpm} onChange={setReadRpm} />
            <NumberField label="Write Requests / Minute" value={writeRpm} onChange={setWriteRpm} />
            {validation && (
              <div className="fh-alert fh-alert-danger">
                {validation}
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Stat label="Read delay" value={delayLabel(readRpm)} />
              <Stat label="Write delay" value={delayLabel(writeRpm)} />
            </div>
          </div>
        )}
      </div>

      <div className="fh-card fh-card-pad">
        <p className="fh-section-label mb-3">Policy</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Stat label="Scope" value="Global" />
          <Stat label="Overrides" value="Disabled" />
          <Stat label="Scheduler" value="Disabled" />
          <Stat label="Automatic sync" value="Disabled" />
        </div>
      </div>
    </>
  )

  if (embedded) {
    return (
      <section id="rate-limits" className="flex flex-col gap-4">
        <div className="fh-page-header">
          <div>
            <h2 className="fh-section-title">Global API Rate Limits</h2>
            <p className="fh-section-subtitle mt-0.5">Inherited by every Source and Channel</p>
          </div>
          {actions}
        </div>
        {editor}
      </section>
    )
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">Global API Rate Limits</h1>
          <p className="fh-page-subtitle">Inherited by every Source and Channel</p>
        </div>
        {actions}
      </div>

      {editor}
    </PageShell>
  )
}

export default function RateLimits() {
  return <RateLimitsPanel />
}
