import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth'
import { apiFetch, ApiError } from '../api/client'
import { authFetch } from '../api/authFetch'
import type { HealthResponse } from '../api/types'
import { useNotification } from '../notifications/NotificationProvider'
import Spinner from '../components/loading/Spinner'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import type { ChannelHealthItem, ChannelHealthResponse, ChannelHealthLevel } from '../services/types'

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
  channelHealth?: ChannelHealthResponse
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
  if (['healthy', 'ok', 'connected', 'active', 'operational'].includes(s)) return 'ok'
  if (['warning', 'degraded', 'rate_limited', 'unable to check'].includes(s)) return 'warning'
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
        <div className="fh-text-body font-medium text-text-base truncate">{row.label}</div>
        {row.detail && <div className="fh-text-caption mt-0.5">{row.detail}</div>}
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="fh-text-body font-medium">{row.value}</span>
        <div className="flex items-center gap-1.5">
          <span className={['w-2 h-2 rounded-full flex-shrink-0', dot].join(' ')} />
          <span className="fh-text-caption">{label}</span>
        </div>
      </div>
    </div>
  )
}

function metricValue(value: number | null | undefined, suffix = ''): string {
  if (value === null || value === undefined) return 'Unavailable'
  return `${value}${suffix}`
}

function channelLabel(channel: ChannelHealthItem): string {
  if (channel.channelType === 'woocommerce') return 'WooCommerce'
  if (channel.channelType === 'snappshop') return 'SnappShop'
  if (channel.channelType === 'tapsishop') return 'TapsiShop'
  return channel.channelType
}

function statusBadgeClass(status: ChannelHealthLevel): string {
  if (status === 'Operational') return 'bg-green-50 text-green-700 border-green-200'
  if (status === 'Error') return 'bg-red-50 text-red-700 border-red-200'
  if (status === 'Disabled') return 'bg-gray-50 text-gray-600 border-gray-200'
  return 'bg-yellow-50 text-yellow-700 border-yellow-200'
}

export default function Diagnostics() {
  const { authFetch: ctxAuthFetch } = useAuth()
  const { success, error: notifyError } = useNotification()
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [diag, setDiag] = useState<DiagnosticsStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)
  const [refreshingChannel, setRefreshingChannel] = useState<string | null>(null)

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

  const refreshChannel = useCallback(async (channelId: string) => {
    setRefreshingChannel(channelId)
    try {
      const data = await apiFetch<ChannelHealthResponse>(
        '/api/v2/diagnostics/channels/health/refresh',
        authFetch,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ channelId }),
        },
        REQUEST_TIMEOUT_MS,
      )
      setDiag(current => current ? { ...current, channelHealth: data } : current)
      setCheckedAt(new Date())
      success('Channel health refreshed')
    } catch (e) {
      const msg = e instanceof ApiError
        ? `Channel health refresh failed (HTTP ${e.status})`
        : e instanceof Error && e.message === 'request_timeout'
          ? 'Channel health refresh timed out.'
          : 'Channel health refresh failed.'
      notifyError(msg)
    } finally {
      setRefreshingChannel(null)
    }
  }, [success, notifyError])

  useEffect(() => { void runCheck() }, [runCheck])

  const backendStatus: StatusRowData['status'] = loading ? 'loading' : err ? 'error' : 'ok'
  const connectors = diag?.connectors ?? []
  const channelHealth = diag?.channelHealth
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
          className="fh-button-secondary"
        >
          {loading ? <Spinner size="sm" /> : (
            <Icon name="refresh" />
          )}
          {loading ? 'Loading' : 'Re-check'}
        </button>
      </div>

      {err && (
        <div className="fh-alert fh-alert-danger">
          {err}
        </div>
      )}

      <div className="fh-card fh-card-pad">
        <p className="fh-section-label mb-3">System</p>
        {systemRows.map(row => <Row key={row.label} row={row} />)}
      </div>

      <div className="fh-card fh-card-pad">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <p className="fh-section-label">Channel Health</p>
            {channelHealth?.checkedAt && (
              <p className="fh-text-caption mt-1">Checked {new Date(channelHealth.checkedAt).toLocaleString()}</p>
            )}
          </div>
          {channelHealth && (
            <span className={['inline-flex rounded-full border px-2.5 py-1 fh-text-caption font-medium', statusBadgeClass(channelHealth.summary.overall)].join(' ')}>
              {channelHealth.summary.overall}
            </span>
          )}
        </div>
        {loading && !channelHealth ? (
          <div className="flex items-center gap-2 py-2 fh-text-body-sm">
            <Spinner size="sm" />Loading channel health
          </div>
        ) : !channelHealth || channelHealth.items.length === 0 ? (
          <Empty title="No channel health data" />
        ) : (
          <div className="space-y-3">
            {channelHealth.items.map(channel => (
              <div key={channel.channelId} className="rounded-md border border-border p-3">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="fh-text-body font-semibold">{channelLabel(channel)}</p>
                      <span className={['inline-flex rounded-full border px-2 py-0.5 fh-text-caption font-medium', statusBadgeClass(channel.status)].join(' ')}>
                        {channel.status}
                      </span>
                      <span className="fh-text-caption">{channel.accessMode}</span>
                    </div>
                    <p className="fh-text-caption mt-1">{channel.summary}</p>
                    <p className="fh-text-caption mt-1">Next action: {channel.nextRecommendedAction}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void refreshChannel(channel.channelId)}
                    disabled={refreshingChannel !== null}
                    className="fh-button-secondary self-start"
                  >
                    {refreshingChannel === channel.channelId ? <Spinner size="sm" /> : <Icon name="refresh" />}
                    Refresh
                  </button>
                </div>
                <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
                  {Object.entries(channel.dimensions).map(([key, dimension]) => (
                    <div key={key} className="rounded border border-border px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="fh-text-caption font-medium text-text-base">{key}</span>
                        <span className={['inline-flex rounded-full border px-2 py-0.5 fh-text-caption', statusBadgeClass(dimension.status)].join(' ')}>
                          {dimension.status}
                        </span>
                      </div>
                      {dimension.message && <p className="fh-text-caption mt-1">{dimension.message}</p>}
                    </div>
                  ))}
                </div>
                <div className="mt-3 grid grid-cols-1 gap-2 fh-text-caption sm:grid-cols-2 lg:grid-cols-4">
                  <span>Last checked: {channel.lastChecked ? new Date(channel.lastChecked).toLocaleString() : 'Unavailable'}</span>
                  <span>Latency: {metricValue(channel.latency, ' ms')}</span>
                  <span>Last success: {channel.lastSuccessfulOperation ? new Date(channel.lastSuccessfulOperation).toLocaleString() : 'Unavailable'}</span>
                  <span>Error category: {channel.lastErrorCategory ?? 'None'}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="fh-card fh-card-pad">
        <p className="fh-section-label mb-3">Connectors</p>
        {loading && !diag ? (
          <div className="flex items-center gap-2 py-2 fh-text-body-sm">
            <Spinner size="sm" />Loading connectors
          </div>
        ) : connectors.length === 0 ? (
          <Empty
            title="No connectors configured"
            description="Connector setup is available from Commerce Hub."
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
        <p className="fh-text-body mt-1">
          <span className="text-wp-muted">Status: </span>
          <span className="font-medium">{health?.status ?? '-'}</span>
        </p>
      </div>
    </PageShell>
  )
}
