import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth'
import { apiFetch, ApiError } from '../api/client'
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

export default function Diagnostics() {
  const { authFetch } = useAuth()
  const { success, error: notifyError } = useNotification()
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)

  const runCheck = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const data = await apiFetch<HealthResponse>('/api/health', authFetch)
      setHealth(data)
      setCheckedAt(new Date())
      success('Diagnostics refreshed')
    } catch (e) {
      const msg = e instanceof ApiError ? `HTTP ${e.status}` : 'Failed to reach backend'
      setErr(msg)
      notifyError(msg)
    } finally {
      setLoading(false)
    }
  }, [authFetch, success, notifyError])

  useEffect(() => { void runCheck() }, [runCheck])

  const backendStatus = loading ? 'loading' : err ? 'error' : 'ok'

  const cards: DiagCard[] = [
    {
      label: 'Backend',
      value: health ? `v${health.version}` : loading ? '…' : 'Unavailable',
      status: backendStatus,
      detail: health ? `Environment: ${health.env}` : undefined,
    },
    {
      label: 'Database',
      value: backendStatus === 'ok' ? 'Connected' : backendStatus === 'loading' ? '…' : 'Unavailable',
      status: backendStatus,
      detail: 'PostgreSQL via beta schema',
    },
    {
      label: 'Authentication',
      value: backendStatus === 'ok' ? 'Active' : backendStatus === 'loading' ? '…' : 'Unavailable',
      status: backendStatus,
      detail: 'JWT (HS256) + opaque refresh tokens',
    },
    {
      label: 'Control Plane',
      value: 'Running',
      status: 'ok',
      detail: 'CP1.3 — diagnostics, runtime config, CLI/API',
    },
    {
      label: 'WooCommerce Integration',
      value: 'Not configured',
      status: 'pending',
      detail: 'Available in BU4+',
    },
    {
      label: 'Nextcloud Integration',
      value: 'Not configured',
      status: 'pending',
      detail: 'Available in BU4+',
    },
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
        <p className="text-[11.5px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">System Components</p>
        {cards.map(card => <DiagRow key={card.label} card={card} />)}
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
      </div>
    </div>
  )
}
