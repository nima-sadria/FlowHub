import { translate } from '../i18n'
import { useEffect, useMemo, useState } from 'react'
import { useServices } from '../services/ServiceContext'
import type { RateLimitSettings } from '../services/types'
import { useNotification } from '../notifications/NotificationProvider'
import Icon from '../components/Icon'
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
        if (active) notifyError({
          title: translate('settings:rateLimits.unableToLoadSettings'),
          description: translate('settings:rateLimits.pleaseTryAgain'),
        })
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => { active = false }
  }, [settings])

  const validation = useMemo(() => {
    if (readRpm < MIN_RPM || readRpm > MAX_RPM) return translate('validation:rateLimits.readRequestsRange', { min: MIN_RPM, max: MAX_RPM })
    if (writeRpm < MIN_RPM || writeRpm > MAX_RPM) return translate('validation:rateLimits.writeRequestsRange', { min: MIN_RPM, max: MAX_RPM })
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
      success({
        title: translate('settings:rateLimits.settingsSavedSuccessfully'),
        description: translate('settings:rateLimits.yourChangesHaveBeenApplied'),
      })
    } catch {
      notifyError({
        title: translate('settings:rateLimits.unableToSaveSettings'),
        description: translate('settings:rateLimits.pleaseTryAgain'),
      })
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
        <Icon name="close" />
        {translate('settings:rateLimits.discard')}
      </button>
      <button
        onClick={() => void save()}
        disabled={saving || Boolean(validation)}
        className="fh-button-primary"
      >
        {saving && <Spinner size="sm" className="text-white" />}
        {!saving && <Icon name="save" />}
        {saving ? translate('settings:rateLimits.saving') : translate('settings:rateLimits.saveChanges')}
      </button>
    </div>
  )

  const editor = (
    <>
      <div className="fh-card fh-card-pad">
        {loading ? (
          <div className="flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />{translate('settings:rateLimits.loading')}</div>
        ) : (
          <div className="flex flex-col gap-4">
            <NumberField label={translate('settings:rateLimits.readRequestsMinute')} value={readRpm} onChange={setReadRpm} />
            <NumberField label={translate('settings:rateLimits.writeRequestsMinute')} value={writeRpm} onChange={setWriteRpm} />
            {validation && (
              <div className="fh-alert fh-alert-danger">
                {validation}
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Stat label={translate('settings:rateLimits.readDelay')} value={delayLabel(readRpm)} />
              <Stat label={translate('settings:rateLimits.writeDelay')} value={delayLabel(writeRpm)} />
            </div>
          </div>
        )}
      </div>

      <div className="fh-card fh-card-pad">
        <p className="fh-section-label mb-3">{translate('settings:rateLimits.policy')}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Stat label={translate('settings:rateLimits.scope')} value="Global" />
          <Stat label={translate('settings:rateLimits.overrides')} value="Disabled" />
          <Stat label={translate('settings:rateLimits.scheduler')} value="Disabled" />
          <Stat label={translate('settings:rateLimits.automaticSync')} value="Disabled" />
        </div>
      </div>
    </>
  )

  if (embedded) {
    return (
      <section id="rate-limits" className="flex flex-col gap-4">
        <div className="fh-page-header">
          <div>
            <h2 className="fh-section-title">{translate('settings:rateLimits.globalApiRateLimits')}</h2>
            <p className="fh-section-subtitle mt-0.5">{translate('settings:rateLimits.inheritedByEverySourceAndChannel')}</p>
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
          <h1 className="fh-page-title">{translate('settings:rateLimits.globalApiRateLimits')}</h1>
          <p className="fh-page-subtitle">{translate('settings:rateLimits.inheritedByEverySourceAndChannel')}</p>
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
