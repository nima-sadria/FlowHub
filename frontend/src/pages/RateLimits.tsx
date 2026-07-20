import { translate } from '../i18n'
import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import { useAuth } from '../auth'
import Icon from '../components/Icon'
import Spinner from '../components/loading/Spinner'
import PageShell from '../components/PageShell'
import { formatNumber } from '../i18n/format'
import SettingsNav from '../components/SettingsNav'
import { useNotification } from '../notifications/NotificationProvider'
import { useServices } from '../services/ServiceContext'
import type { RateLimitSettings } from '../services/types'

const MIN_RPM = 1
const MAX_RPM = 1000

function delayLabel(rpm: number): string {
  if (!rpm || rpm < MIN_RPM) return '-'
  const seconds = 60 / rpm
  return seconds >= 1
    ? translate('settings:rateLimits.seconds', { value: formatNumber(seconds, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) })
    : translate('settings:rateLimits.milliseconds', { value: formatNumber(seconds * 1000, { maximumFractionDigits: 0 }) })
}

interface RateLimitDiagnostics {
  requests_completed?: number
  requests_delayed?: number
  queue_length?: number
  throttle_count?: number
}

function NumberField({ label, value, onChange }: {
  label: string
  value: number
  onChange: (value: number) => void
}) {
  return (
    <div className="fh-field">
      <label className="fh-help-text">{label}</label>
      <input type="number" min={MIN_RPM} max={MAX_RPM} value={value} onChange={event => onChange(Number(event.target.value))} className="fh-input" />
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="fh-stat-tile"><div className="fh-stat-tile-label uppercase tracking-[0.08em]">{label}</div><div className="fh-stat-tile-value">{value}</div></div>
}

interface DiagnosticsResponse {
  rateLimiter?: RateLimitDiagnostics
}

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)))
}

function CapacityCard({ label, value, percent, tone = 'success' }: {
  label: string
  value: string
  percent: number
  tone?: 'success' | 'warning'
}) {
  return (
    <div className="fh-card flex min-h-[112px] min-w-0 flex-1 flex-col gap-2 p-3.5">
      <p className="text-xs font-medium leading-4 text-[color:var(--fh-text-secondary)]">{label}</p>
      <p className="text-[22px] font-semibold leading-7 text-text-base">{value}</p>
      <div className="h-1 w-full overflow-hidden rounded bg-[color:var(--fh-ui-surface-subtle)]" aria-hidden="true">
        <div
          className={['h-full rounded', tone === 'warning' ? 'bg-wp-yellow' : 'bg-wp-green'].join(' ')}
          style={{ width: `${clampPercent(percent)}%` }}
        />
      </div>
    </div>
  )
}

function StepperField({ label, value, disabled, onChange }: {
  label: string
  value: number
  disabled?: boolean
  onChange: (value: number) => void
}) {
  return (
    <label className="flex min-w-0 flex-1 flex-col gap-1.5">
      <span className="text-xs font-medium leading-4 text-[color:var(--fh-text-secondary)]">{label}</span>
      <span className="flex h-10 items-center overflow-hidden rounded-md border border-border bg-bg-card ps-2.5 pe-1.5">
        <input
          type="number"
          min={MIN_RPM}
          max={MAX_RPM}
          value={value}
          disabled={disabled}
          onChange={event => onChange(Number(event.target.value))}
          className="min-w-0 flex-1 border-0 bg-transparent text-[13px] leading-[18px] text-text-base outline-none"
        />
        <button type="button" onClick={() => onChange(Math.max(MIN_RPM, value - 1))} disabled={disabled || value <= MIN_RPM} className="inline-flex h-[30px] w-[30px] items-center justify-center rounded bg-[color:var(--fh-ui-surface-muted)] text-sm font-medium text-wp-muted">−</button>
        <button type="button" onClick={() => onChange(Math.min(MAX_RPM, value + 1))} disabled={disabled || value >= MAX_RPM} className="ms-1 inline-flex h-[30px] w-[30px] items-center justify-center rounded bg-[color:var(--fh-ui-surface-muted)] text-sm font-medium text-wp-muted">+</button>
      </span>
    </label>
  )
}

export function RateLimitsPanel({ embedded = false }: { embedded?: boolean }) {
  const { settings } = useServices()
  const { user, authFetch } = useAuth()
  const { success, error: notifyError } = useNotification()
  const [current, setCurrent] = useState<RateLimitSettings | null>(null)
  const [readRpm, setReadRpm] = useState(60)
  const [writeRpm, setWriteRpm] = useState(30)
  const [diagnostics, setDiagnostics] = useState<RateLimitDiagnostics | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const canEdit = Boolean(user?.is_admin || user?.is_super_admin)

  useEffect(() => {
    let active = true
    async function load() {
      setLoading(true)
      try {
        const [limits, diagnosticResponse] = await Promise.all([
          settings.getRateLimits(),
          apiFetch<DiagnosticsResponse>('/api/v2/diagnostics/status', authFetch).catch(() => null),
        ])
        if (!active) return
        setCurrent(limits)
        setReadRpm(limits.read_requests_per_minute)
        setWriteRpm(limits.write_requests_per_minute)
        setDiagnostics(diagnosticResponse?.rateLimiter ?? null)
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
  }, [authFetch, notifyError, settings])

  const validation = useMemo(() => {
    if (readRpm < MIN_RPM || readRpm > MAX_RPM) return translate('validation:rateLimits.readRequestsRange', { min: MIN_RPM, max: MAX_RPM })
    if (writeRpm < MIN_RPM || writeRpm > MAX_RPM) return translate('validation:rateLimits.writeRequestsRange', { min: MIN_RPM, max: MAX_RPM })
    return null
  }, [readRpm, writeRpm])

  const dirty = Boolean(current && (
    readRpm !== current.read_requests_per_minute
    || writeRpm !== current.write_requests_per_minute
  ))

  function reset() {
    if (!current) return
    setReadRpm(current.read_requests_per_minute)
    setWriteRpm(current.write_requests_per_minute)
  }

  async function save() {
    if (!canEdit || validation) return
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
          <Stat label={translate('settings:rateLimits.scope')} value={translate('common:status.global')} />
          <Stat label={translate('settings:rateLimits.overrides')} value={translate('common:status.disabled')} />
          <Stat label={translate('settings:rateLimits.scheduler')} value={translate('common:status.disabled')} />
          <Stat label={translate('settings:rateLimits.automaticSync')} value={translate('common:status.disabled')} />
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

  const completed = diagnostics?.requests_completed ?? 0
  const delayed = diagnostics?.requests_delayed ?? 0
  const queued = diagnostics?.queue_length ?? 0
  const combinedCapacity = Math.max(readRpm + writeRpm, 1)
  const completedPercent = clampPercent((completed / combinedCapacity) * 100)
  const delayedPercent = completed > 0 ? clampPercent((delayed / completed) * 100) : 0
  const queuedPercent = clampPercent((queued / Math.max(Math.min(readRpm, writeRpm), 1)) * 100)

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('settings:rateLimits.globalApiRateLimits')}</h1>
          <p className="fh-page-subtitle">{translate('settings:rateLimits.inheritedByEverySourceAndChannel')}</p>
        </div>
      </div>

      <div className="flex flex-col items-start gap-4 lg:flex-row">
        <SettingsNav active="rateLimits" />

        <div className="flex w-full max-w-[820px] min-w-0 flex-col gap-3.5">
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
            <CapacityCard label={translate('settings:rateLimits.requestsCompleted')} value={loading ? '—' : completed.toLocaleString()} percent={completedPercent} />
            <CapacityCard label={translate('settings:rateLimits.requestsDelayed')} value={loading ? '—' : delayed.toLocaleString()} percent={delayedPercent} tone={delayed > 0 ? 'warning' : 'success'} />
            <CapacityCard label={translate('settings:rateLimits.queueLength')} value={loading ? '—' : queued.toLocaleString()} percent={queuedPercent} tone={queued > 0 ? 'warning' : 'success'} />
          </div>

          <section className={['fh-card min-h-[310px] p-[18px]', dirty ? 'border-accent' : ''].join(' ')}>
            <h2 className="text-base font-semibold leading-[22px] text-text-base">{translate('settings:rateLimits.operationalLimits')}</h2>
            <p className="mt-2 text-xs leading-4 text-[color:var(--fh-text-secondary)]">{translate('settings:rateLimits.operationalLimitsDescription')}</p>

            {loading || !current ? (
              <div className="mt-5 flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />{translate('settings:rateLimits.loadingOperationalLimits')}</div>
            ) : (
              <>
                {!canEdit && (
                  <div className="fh-alert fh-alert-info mt-4">
                    <Icon name="info" />
                    <span>{translate('settings:rateLimits.adminRequiredOperationalLimits')}</span>
                  </div>
                )}
                <div className="mt-3.5 flex flex-col gap-2.5 sm:flex-row">
                  <StepperField label={translate('settings:rateLimits.operationalReadRequestsMinute')} value={readRpm} disabled={!canEdit || saving} onChange={setReadRpm} />
                  <StepperField label={translate('settings:rateLimits.operationalWriteRequestsMinute')} value={writeRpm} disabled={!canEdit || saving} onChange={setWriteRpm} />
                </div>
                <label className="mt-3 flex w-full flex-col gap-1.5 sm:w-[calc(50%-5px)]">
                  <span className="text-xs font-medium leading-4 text-[color:var(--fh-text-secondary)]">{translate('settings:rateLimits.limitResetPolicy')}</span>
                  <select value="rolling" disabled className="fh-select !min-h-[36px] rounded-md !px-3 !py-2 text-[13px]">
                    <option value="rolling">{translate('settings:rateLimits.rollingWindow')}</option>
                  </select>
                </label>
                {validation && <div className="fh-alert fh-alert-danger mt-3" role="alert"><Icon name="error" />{validation}</div>}
                <div className="mt-4 flex justify-end gap-2">
                  <button type="button" onClick={reset} disabled={!dirty || saving} className="fh-button-ghost fh-button-sm">{translate('settings:rateLimits.reset')}</button>
                  <button type="button" onClick={() => void save()} disabled={!dirty || saving || Boolean(validation) || !canEdit} className="fh-button-primary fh-button-sm">
                    {saving && <Spinner size="sm" className="text-white" />}
                    {saving ? translate('settings:rateLimits.saving') : translate('settings:rateLimits.saveLimits')}
                  </button>
                </div>
              </>
            )}
          </section>
        </div>
      </div>
    </PageShell>
  )
}

export default function RateLimits() {
  return <RateLimitsPanel />
}
