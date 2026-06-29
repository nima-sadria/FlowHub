import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth'
import { apiFetch, ApiError } from '../api/client'
import { authFetch } from '../api/authFetch'
import type { HealthResponse } from '../api/types'
import { useNotification } from '../notifications/NotificationProvider'
import Spinner from '../components/loading/Spinner'

function relTime(d: Date): string {
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}

interface DiagCard {
  label: string
  value: string
  status: 'ok' | 'error' | 'loading' | 'pending'
  detail?: string
}

function DiagRow({ card }: { card: DiagCard }) {
  const dot =
    card.status === 'ok'      ? 'bg-wp-green' :
    card.status === 'error'   ? 'bg-wp-red' :
    card.status === 'loading' ? 'bg-wp-yellow animate-pulse' :
    'bg-border'

  const statusText =
    card.status === 'ok'      ? 'OK' :
    card.status === 'error'   ? 'Error' :
    card.status === 'loading' ? 'Checking…' :
    'Pending'

  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-border last:border-0">
      <div>
        <div className="text-[13px] font-medium text-text-base">{card.label}</div>
        {card.detail && <div className="text-[11px] text-wp-muted mt-0.5">{card.detail}</div>}
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="text-[13px] text-text-base font-medium">{card.value}</span>
        <div className="flex items-center gap-1.5">
          <span className={['w-2 h-2 rounded-full flex-shrink-0', dot].join(' ')} />
          <span className="text-[11px] text-wp-muted">{statusText}</span>
        </div>
      </div>
    </div>
  )
}

interface IntegrationStatus {
  status: 'ok' | 'error' | 'unconfigured'
  latencyMs: number | null
  productCount?: number | null
  lastModified?: string | null
  detail: string | null
}

interface DiagnosticsResponse {
  database: { status: string; detail: string | null }
  woocommerce: IntegrationStatus
  nextcloud: IntegrationStatus & { lastModified: string | null }
  checkedAt: string
}

export default function Diagnostics() {
  const { authFetch: ctxAuthFetch } = useAuth()
  const { success, error: notifyError } = useNotification()
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [diag, setDiag] = useState<DiagnosticsResponse | null>(null)
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
      setHealth(healthData)
      if (diagResp.ok) {
        setDiag(await diagResp.json() as DiagnosticsResponse)
      }
      setCheckedAt(new Date())
      success('Diagnostics refreshed')
    } catch (e) {
      const msg = e instanceof ApiError ? `HTTP ${e.status}` : 'Failed to reach backend'
      setErr(msg)
      notifyError(msg)
    } finally {
      setLoading(false)
    }
  }, [ctxAuthFetch, success, notifyError])

  useEffect(() => { void runCheck() }, [runCheck])

  const backendStatus = loading ? 'loading' : err ? 'error' : 'ok'

  function integrationCard(
    label: string,
    data: IntegrationStatus | undefined,
    extras?: { countLabel?: string },
  ): DiagCard {
    if (!data) return { label, value: '…', status: 'loading' }
    if (data.status === 'unconfigured') {
      return { label, value: 'Not configured', status: 'pending', detail: 'Configure in Settings' }
    }
    const latency = data.latencyMs != null ? `${data.latencyMs.toFixed(0)} ms` : null
    let value = data.status === 'ok' ? 'Connected' : 'Error'
    if (data.status === 'ok' && latency) value += ` — ${latency}`
    const detailParts: string[] = []
    if (data.detail) detailParts.push(data.detail)
    if (extras?.countLabel && data.productCount != null) {
      detailParts.push(`${data.productCount} ${extras.countLabel}`)
    }
    if (data.lastModified) {
      detailParts.push(`Last modified: ${data.lastModified}`)
    }
    return {
      label,
      value,
      status: data.status === 'ok' ? 'ok' : 'error',
      detail: detailParts.join(' · ') || undefined,
    }
  }

  const systemCards: DiagCard[] = [
    {
      label: 'Backend',
      value: health ? `v${health.version}` : loading ? '…' : 'Unavailable',
      status: backendStatus,
      detail: health ? `Environment: ${health.env}` : undefined,
    },
    {
      label: 'Database',
      value: !diag ? (loading ? '…' : 'Unavailable')
        : diag.database.status === 'ok' ? 'Connected' : 'Error',
      status: !diag ? backendStatus : diag.database.status === 'ok' ? 'ok' : 'error',
      detail: diag?.database.detail ?? 'PostgreSQL via beta schema',
    },
    {
      label: 'Authentication',
      value: backendStatus === 'ok' ? 'Active' : backendStatus === 'loading' ? '…' : 'Unavailable',
      status: backendStatus,
      detail: 'JWT (HS256) + opaque refresh tokens',
    },
  ]

  const integrationCards: DiagCard[] = [
    integrationCard('WooCommerce', diag?.woocommerce, { countLabel: 'products' }),
    integrationCard('Nextcloud', diag?.nextcloud),
  ]

  return (
    <div className="p-4 sm:p-7 flex flex-col gap-5 max-w-2xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold text-text-base">Diagnostics</h1>
          <p className="text-[13px] text-wp-muted mt-0.5">
            {checkedAt ? `Last checked ${relTime(checkedAt)}` : 'Checking…'}
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
          {loading ? 'Checking…' : 'Re-check'}
        </button>
      </div>

      {err && (
        <div className="bg-wp-red/10 border border-wp-red/30 rounded-card p-4 text-[13px] text-wp-red">
          {err}
        </div>
      )}

      <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px]">
        <p className="text-[11.5px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">System</p>
        {systemCards.map(card => <DiagRow key={card.label} card={card} />)}
      </div>

      <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px]">
        <p className="text-[11.5px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">Integrations</p>
        {loading && !diag ? (
          <div className="flex items-center gap-2 text-[13px] text-wp-muted py-2">
            <Spinner size="sm" />Checking integrations…
          </div>
        ) : (
          integrationCards.map(card => <DiagRow key={card.label} card={card} />)
        )}
      </div>

      <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px]">
        <p className="text-[11.5px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-2">About</p>
        <p className="text-[13px] text-text-base">
          <span className="text-wp-muted">Version: </span>
          <span className="font-mono">{health?.version ?? '—'}</span>
        </p>
        <p className="text-[13px] text-text-base mt-1">
          <span className="text-wp-muted">Environment: </span>
          <span className="font-medium capitalize">{health?.env ?? '—'}</span>
        </p>
        <p className="text-[13px] text-text-base mt-1">
          <span className="text-wp-muted">Health endpoint: </span>
          <span className="font-mono text-accent">GET /api/health</span>
        </p>
        {diag?.checkedAt && (
          <p className="text-[13px] text-text-base mt-1">
            <span className="text-wp-muted">Checked at: </span>
            <span className="font-mono text-[12px]">{diag.checkedAt}</span>
          </p>
        )}
      </div>
    </div>
  )
}
