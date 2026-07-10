import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth'
import { apiFetch, ApiError } from '../api/client'
import { authFetch } from '../api/authFetch'
import type { HealthResponse } from '../api/types'
import { useNotification } from '../notifications/NotificationProvider'
import Spinner from '../components/loading/Spinner'
import Empty from '../components/Empty'
import PageShell from '../components/PageShell'

const REQUEST_TIMEOUT_MS = 10_000

function relTime(d: Date): string {
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}

interface ConnectorStatus {
  id?: string
  name?: string
  connector_type?: string
  enabled?: boolean
  status?: string
  health?: string | { status?: string; message?: string; checked_at?: string | null } | null
  last_checked_at?: string | null
}

interface DiagnosticsStatusResponse {
  overall_status?: string
  checkedAt?: string
  connectors?: ConnectorStatus[]
  rateLimiter?: {
    settings?: {
      read_requests_per_minute?: number
      write_requests_per_minute?: number
      read_delay_ms?: number
      write_delay_ms?: number
    }
    queue_length?: number
    average_request_duration_ms?: number
    average_latency_ms?: number | null
    throttle_count?: number
    last_throttle?: string | null
    last_connector_delay_ms?: number | null
    last_limiter_delay_ms?: number | null
    requests_completed?: number
    requests_delayed?: number
    estimated_completion_seconds?: number | null
  }
  external_call_performed?: boolean
}

interface StatusRowData {
  label: string
  value: string
  status: 'ok' | 'warning' | 'error' | 'loading' | 'pending'
  detail?: string
}

function normalizeStatus(status: string | undefined): StatusRowData['status'] {
  if (!status) return 'pending'
  const s = status.toLowerCase()
  if (['healthy', 'ok', 'connected', 'active'].includes(s)) return 'ok'
  if (['warning', 'degraded', 'rate_limited'].includes(s)) return 'warning'
  if (['error', 'failed', 'authentication_failed', 'timeout'].includes(s)) return 'error'
  if (['disabled', 'unconfigured'].includes(s)) return 'pending'
  return 'pending'
}

function connectorHealth(connector: ConnectorStatus): string | undefined {
  if (typeof connector.health === 'string') return connector.health
  return connector.health?.status ?? connector.status
}

function Row({ row }: { row: StatusRowData }) {
  const dot =
    row.status === 'ok'      ? 'bg-wp-green' :
    row.status === 'warning' ? 'bg-wp-yellow' :
    row.status === 'error'   ? 'bg-wp-red' :
    row.status === 'loading' ? 'bg-wp-yellow animate-pulse' :
    'bg-border'

  const label =
    row.status === 'ok'      ? 'Operational' :
    row.status === 'warning' ? 'Warning' :
    row.status === 'error'   ? 'Error' :
    row.status === 'loading' ? 'Loading' :
    'Unable to check'

  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-border last:border-0">
      <div className="min-w-0">
        <div className="text-[13px] font-medium text-text-base truncate">{row.label}</div>
        {row.detail && <div className="text-[11px] text-wp-muted mt-0.5">{row.detail}</div>}
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="text-[13px] text-text-base font-medium">{row.value}</span>
        <div className="flex items-center gap-1.5">
          <span className={['w-2 h-2 rounded-full flex-shrink-0', dot].join(' ')} />
          <span className="text-[11px] text-wp-muted">{label}</span>
        </div>
      </div>
    </div>
  )
}

function metricValue(value: number | null | undefined, suffix = ''): string {
  if (value === null || value === undefined) return 'Unavailable'
  return `${value}${suffix}`
}

export default function Diagnostics() {
  const { authFetch: ctxAuthFetch } = useAuth()
  const { success, error: notifyError } = useNotification()
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [diag, setDiag] = useState<DiagnosticsStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)

  const runCheck = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const [healthData, diagnosticsData] = await Promise.all([
        apiFetch<HealthResponse>('/api/health', ctxAuthFetch, undefined, REQUEST_TIMEOUT_MS),
        apiFetch<DiagnosticsStatusResponse>('/api/v2/diagnostics/status', authFetch, undefined, REQUEST_TIMEOUT_MS),
      ])
      setHealth(healthData)
      setDiag(diagnosticsData)
      setCheckedAt(new Date())
      success('Diagnostics refreshed')
    } catch (e) {
      const msg = e instanceof ApiError
        ? `Diagnostics unavailable (HTTP ${e.status})`
        : e instanceof Error && e.message === 'request_timeout'
          ? 'Unable to check diagnostics. Request timed out.'
          : 'Unable to check diagnostics.'
      setErr(msg)
      notifyError(msg)
    } finally {
      setLoading(false)
    }
  }, [ctxAuthFetch, success, notifyError])

  useEffect(() => { void runCheck() }, [runCheck])

  const backendStatus: StatusRowData['status'] = loading ? 'loading' : err ? 'error' : 'ok'
  const connectors = diag?.connectors ?? []
  const limiter = diag?.rateLimiter
  const systemRows: StatusRowData[] = [
    {
      label: 'Backend',
      value: loading ? 'Loading' : health ? 'Online' : 'Unavailable',
      status: backendStatus,
      detail: health ? 'Application service is responding' : undefined,
    },
    {
      label: 'Diagnostics',
      value: loading ? 'Loading' : err ? 'Unable to check' : diag?.overall_status === 'error' ? 'Error' : 'Operational',
      status: loading ? 'loading' : normalizeStatus(diag?.overall_status ?? (err ? 'error' : 'ok')),
      detail: diag?.checkedAt ? `Last checked ${new Date(diag.checkedAt).toLocaleString()}` : undefined,
    },
  ]

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">Diagnostics</h1>
          <p className="fh-page-subtitle">
            {checkedAt ? `Last checked ${relTime(checkedAt)}` : loading ? 'Loading' : 'Unable to check'}
          </p>
        </div>
        <button
          onClick={() => void runCheck()}
          disabled={loading}
          className="fh-button-secondary px-3"
        >
          {loading ? <Spinner size="sm" /> : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
          )}
          {loading ? 'Loading' : 'Re-check'}
        </button>
      </div>

      {err && (
        <div className="bg-wp-red/10 border border-wp-red/30 rounded-card p-4 text-[13px] text-wp-red">
          {err}
        </div>
      )}

      <div className="fh-card fh-card-pad">
        <p className="fh-section-label mb-3">System</p>
        {systemRows.map(row => <Row key={row.label} row={row} />)}
      </div>

      <div className="fh-card fh-card-pad">
        <p className="fh-section-label mb-3">Connectors</p>
        {loading && !diag ? (
          <div className="flex items-center gap-2 text-[13px] text-wp-muted py-2">
            <Spinner size="sm" />Loading connectors
          </div>
        ) : connectors.length === 0 ? (
          <Empty
            title="No connectors configured"
            description="Connector setup is available from Settings."
          />
        ) : connectors.map(connector => {
          const status = connectorHealth(connector)
          return (
            <Row
              key={connector.id ?? connector.name ?? connector.connector_type ?? 'connector'}
              row={{
                label: connector.name ?? connector.connector_type ?? 'Connector',
                value: connector.enabled === false ? 'Disabled' : status ?? 'Unknown',
                status: connector.enabled === false ? 'pending' : normalizeStatus(status),
                detail: connector.last_checked_at ? `Last checked ${new Date(connector.last_checked_at).toLocaleString()}` : undefined,
              }}
            />
          )
        })}
      </div>

      <div className="fh-card fh-card-pad">
        <p className="fh-section-label mb-3">Rate Limiter</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Row row={{
            label: 'Read Requests / Minute',
            value: loading ? 'Loading' : String(limiter?.settings?.read_requests_per_minute ?? '-'),
            status: loading ? 'loading' : 'ok',
            detail: limiter?.settings?.read_delay_ms ? `Delay ${limiter.settings.read_delay_ms} ms` : undefined,
          }} />
          <Row row={{
            label: 'Write Requests / Minute',
            value: loading ? 'Loading' : String(limiter?.settings?.write_requests_per_minute ?? '-'),
            status: loading ? 'loading' : 'ok',
            detail: limiter?.settings?.write_delay_ms ? `Delay ${limiter.settings.write_delay_ms} ms` : undefined,
          }} />
          <Row row={{
            label: 'Queue length',
            value: loading ? 'Loading' : String(limiter?.queue_length ?? 0),
            status: loading ? 'loading' : 'ok',
          }} />
          <Row row={{
            label: 'Request duration',
            value: loading ? 'Loading' : metricValue(limiter?.average_request_duration_ms, ' ms'),
            status: loading ? 'loading' : 'pending',
          }} />
          <Row row={{
            label: 'Limiter delay',
            value: loading ? 'Loading' : metricValue(limiter?.last_limiter_delay_ms ?? limiter?.last_connector_delay_ms, ' ms'),
            status: loading ? 'loading' : (limiter?.last_limiter_delay_ms ? 'warning' : 'ok'),
          }} />
          <Row row={{
            label: 'ETA',
            value: loading ? 'Loading' : metricValue(limiter?.estimated_completion_seconds, ' s'),
            status: loading ? 'loading' : 'pending',
          }} />
          <Row row={{
            label: 'Throttle events',
            value: loading ? 'Loading' : String(limiter?.throttle_count ?? 0),
            status: loading ? 'loading' : (limiter?.throttle_count ? 'warning' : 'ok'),
            detail: limiter?.last_throttle ? `Last ${new Date(limiter.last_throttle).toLocaleString()}` : undefined,
          }} />
        </div>
      </div>

      <div className="fh-card fh-card-pad">
        <p className="fh-section-label mb-2">About</p>
        <p className="text-[13px] text-text-base mt-1">
          <span className="text-wp-muted">Status: </span>
          <span className="font-medium">{health?.status ?? '-'}</span>
        </p>
      </div>
    </PageShell>
  )
}
