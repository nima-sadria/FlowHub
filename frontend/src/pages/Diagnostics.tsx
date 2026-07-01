import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth'
import { apiFetch, ApiError } from '../api/client'
import { authFetch } from '../api/authFetch'
import type { HealthResponse } from '../api/types'
import { useNotification } from '../notifications/NotificationProvider'
import Spinner from '../components/loading/Spinner'
import Empty from '../components/Empty'

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
  external_call_performed?: boolean
}

interface StatusRowData {
  label: string
  value: string
  status: 'ok' | 'error' | 'loading' | 'pending'
  detail?: string
}

function normalizeStatus(status: string | undefined): StatusRowData['status'] {
  if (!status) return 'pending'
  const s = status.toLowerCase()
  if (['healthy', 'ok', 'connected', 'active'].includes(s)) return 'ok'
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
    row.status === 'error'   ? 'bg-wp-red' :
    row.status === 'loading' ? 'bg-wp-yellow animate-pulse' :
    'bg-border'

  const label =
    row.status === 'ok'      ? 'OK' :
    row.status === 'error'   ? 'Needs attention' :
    row.status === 'loading' ? 'Checking...' :
    'Not configured'

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
      const [healthData, diagResp] = await Promise.all([
        apiFetch<HealthResponse>('/api/health', ctxAuthFetch),
        authFetch('/api/v2/diagnostics/status'),
      ])
      if (!diagResp.ok) throw new ApiError(diagResp.status, await diagResp.text())
      setHealth(healthData)
      setDiag(await diagResp.json() as DiagnosticsStatusResponse)
      setCheckedAt(new Date())
      success('Diagnostics refreshed')
    } catch (e) {
      const msg = e instanceof ApiError ? `Diagnostics unavailable (HTTP ${e.status})` : 'Failed to reach diagnostics'
      setErr(msg)
      notifyError(msg)
    } finally {
      setLoading(false)
    }
  }, [ctxAuthFetch, success, notifyError])

  useEffect(() => { void runCheck() }, [runCheck])

  const backendStatus: StatusRowData['status'] = loading ? 'loading' : err ? 'error' : 'ok'
  const connectors = diag?.connectors ?? []
  const systemRows: StatusRowData[] = [
    {
      label: 'Backend',
      value: loading ? 'Checking...' : health ? 'Online' : 'Unavailable',
      status: backendStatus,
      detail: health ? 'Application service is responding' : undefined,
    },
    {
      label: 'Diagnostics',
      value: loading ? 'Checking...' : diag?.overall_status === 'error' ? 'Attention needed' : 'Ready',
      status: loading ? 'loading' : normalizeStatus(diag?.overall_status ?? (err ? 'error' : 'ok')),
      detail: diag?.checkedAt ? `Last checked ${new Date(diag.checkedAt).toLocaleString()}` : undefined,
    },
  ]

  return (
    <div className="p-4 sm:p-7 flex flex-col gap-5 max-w-2xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold text-text-base">Diagnostics</h1>
          <p className="text-[13px] text-wp-muted mt-0.5">
            {checkedAt ? `Last checked ${relTime(checkedAt)}` : 'Checking...'}
          </p>
        </div>
        <button
          onClick={() => void runCheck()}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-[13px] font-medium text-wp-muted hover:text-text-base hover:border-accent transition-colors disabled:opacity-50"
        >
          {loading ? <Spinner size="sm" /> : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
          )}
          {loading ? 'Checking...' : 'Re-check'}
        </button>
      </div>

      {err && (
        <div className="bg-wp-red/10 border border-wp-red/30 rounded-card p-4 text-[13px] text-wp-red">
          {err}
        </div>
      )}

      <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px]">
        <p className="text-[11.5px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">System</p>
        {systemRows.map(row => <Row key={row.label} row={row} />)}
      </div>

      <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px]">
        <p className="text-[11.5px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">Connectors</p>
        {loading && !diag ? (
          <div className="flex items-center gap-2 text-[13px] text-wp-muted py-2">
            <Spinner size="sm" />Checking connectors...
          </div>
        ) : connectors.length === 0 ? (
          <Empty
            title="No connectors configured"
            description="Connector setup is available from Integrations."
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

      <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px]">
        <p className="text-[11.5px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-2">About</p>
        <p className="text-[13px] text-text-base">
          <span className="text-wp-muted">Version: </span>
          <span className="font-mono">{health?.version ?? '-'}</span>
        </p>
        <p className="text-[13px] text-text-base mt-1">
          <span className="text-wp-muted">Status: </span>
          <span className="font-medium">{health?.status ?? '-'}</span>
        </p>
      </div>
    </div>
  )
}
