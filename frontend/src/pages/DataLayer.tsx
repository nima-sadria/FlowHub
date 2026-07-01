import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth'
import { authFetch } from '../api/authFetch'
import Spinner from '../components/loading/Spinner'

// â”€â”€ Types â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

interface CacheStatus {
  initialized: boolean
  total: number
  fresh?: number
  stale?: number
  error?: number
  last_fetched_at: string | null
  last_snapshot_at?: string | null
}

interface ConnectorSummary {
  initialized: boolean
  total: number
  healthy?: number
  degraded?: number
  unhealthy?: number
  unknown?: number
  connectors_tracked?: number
  total_requests?: number
  total_errors?: number
  total_products_fetched?: number
  total_rows_parsed?: number
}

interface RefreshSummary {
  initialized: boolean
  total: number
  pending: number
  running: number
  completed: number
  failed: number
  cancelled: number
}

interface InvalidationSummary {
  initialized: boolean
  total: number
}

interface DataLayerStatus {
  data_layer_version: string
  initialized: boolean
  read_only: boolean
  apply_blocked: boolean
  product_cache: CacheStatus
  source_snapshots: CacheStatus
  destination_snapshots: CacheStatus
  connector_health: ConnectorSummary
  connector_telemetry: ConnectorSummary
  refresh_jobs: RefreshSummary
  invalidation_events: InvalidationSummary
}

interface RefreshJob {
  id: number
  job_type: string
  entity_type: string
  connector_id: string | null
  status: string
  triggered_by: string | null
  duration_ms: number | null
  error_message: string | null
  created_at: string | null
  started_at: string | null
  completed_at: string | null
  failed_at: string | null
}

interface ConnectorHealth {
  id: number
  connector_id: string
  connector_type: string
  status: string
  latency_ms: number | null
  detail: string | null
  consecutive_failures: number
  checked_at: string | null
}

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function relTime(iso: string | null): string {
  if (!iso) return 'â€”'
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}

function statusDot(status: string) {
  const map: Record<string, string> = {
    healthy: 'bg-wp-green',
    ok: 'bg-wp-green',
    completed: 'bg-wp-green',
    degraded: 'bg-wp-yellow',
    pending: 'bg-border',
    running: 'bg-accent animate-pulse',
    unhealthy: 'bg-wp-red',
    failed: 'bg-wp-red',
    error: 'bg-wp-red',
    unknown: 'bg-border',
    cancelled: 'bg-border',
  }
  return map[status] ?? 'bg-border'
}

// â”€â”€ Section components â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function SectionHeader({ title }: { title: string }) {
  return (
    <p className="text-[11.5px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">
      {title}
    </p>
  )
}

function Row({ label, value, sub, dot }: { label: string; value: string; sub?: string; dot?: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-border last:border-0">
      <div>
        <div className="text-[13px] font-medium text-text-base">{label}</div>
        {sub && <div className="text-[11px] text-wp-muted mt-0.5">{sub}</div>}
      </div>
      <div className="flex items-center gap-1.5 flex-shrink-0">
        {dot && <span className={['w-2 h-2 rounded-full', dot].join(' ')} />}
        <span className="text-[13px] text-text-base">{value}</span>
      </div>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="py-4 text-center text-[12px] text-wp-muted">{message}</div>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px]">
      {children}
    </div>
  )
}

// â”€â”€ Main page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export default function DataLayer() {
  const { authFetch: ctxAuthFetch } = useAuth()
  const [status, setStatus] = useState<DataLayerStatus | null>(null)
  const [jobs, setJobs] = useState<RefreshJob[]>([])
  const [connectorHealth, setConnectorHealth] = useState<ConnectorHealth[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const [statusResp, jobsResp, connResp] = await Promise.all([
        authFetch('/api/v2/data-layer/status'),
        authFetch('/api/v2/data-layer/refresh-jobs?limit=10'),
        authFetch('/api/v2/data-layer/connectors/status'),
      ])

      if (statusResp.ok) setStatus(await statusResp.json() as DataLayerStatus)
      if (jobsResp.ok) {
        const j = await jobsResp.json() as { items: RefreshJob[] }
        setJobs(j.items ?? [])
      }
      if (connResp.ok) {
        const c = await connResp.json() as { health: { connectors: ConnectorHealth[] } }
        setConnectorHealth(c.health?.connectors ?? [])
      }
      setCheckedAt(new Date())
    } catch {
      setErr('Failed to reach Data Layer API')
    } finally {
      setLoading(false)
    }
  }, [ctxAuthFetch])

  useEffect(() => { void load() }, [load])

  // â”€â”€ Render â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

  const initialized = status?.initialized ?? false

  return (
    <div className="p-4 sm:p-7 flex flex-col gap-5 max-w-3xl">

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold text-text-base">Data Layer</h1>
          <p className="text-[13px] text-wp-muted mt-0.5">
            {checkedAt ? `Last checked ${relTime(checkedAt.toISOString())}` : 'Loadingâ€¦'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-wp-green/10 border border-wp-green/20 text-[11px] font-semibold text-wp-green">
            <span className="w-1.5 h-1.5 rounded-full bg-wp-green" />
            Read-only
          </span>
          <button
            onClick={() => void load()}
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
            {loading ? 'Loadingâ€¦' : 'Refresh'}
          </button>
        </div>
      </div>

      {err && (
        <div className="bg-wp-red/10 border border-wp-red/30 rounded-card p-4 text-[13px] text-wp-red">
          {err}
        </div>
      )}

      {/* Initialization banner */}
      {!loading && !err && !initialized && (
        <div className="bg-amber-50 border border-amber-200 rounded-card p-4">
          <p className="text-[13px] font-medium text-amber-800">Data Layer not yet initialized</p>
          <p className="text-[12px] text-amber-700 mt-0.5">
            All stores are empty. Data populates when products are browsed or previewed.
            Background refresh will be added in a future phase.
          </p>
        </div>
      )}

      {/* Safety Model */}
      <Card>
        <SectionHeader title="Safety" />
        <Row label="Mode" value="Read-only" dot="bg-wp-green" sub="FlowHub does not write to external connectors from this release" />
        <Row label="Apply" value="Blocked" dot="bg-border" sub="Price changes cannot be applied from this release" />
        <Row label="Scheduler" value="Not implemented" dot="bg-border" sub="Automatic background refresh is a future phase" />
        <Row label="Data Layer version" value={status?.data_layer_version ?? 'â€”'} />
      </Card>

      {/* Product Cache */}
      <Card>
        <SectionHeader title="Product Cache" />
        {loading && !status ? (
          <div className="flex items-center gap-2 py-2 text-[13px] text-wp-muted"><Spinner size="sm" />Loadingâ€¦</div>
        ) : status?.product_cache.initialized ? (
          <>
            <Row label="Total products" value={String(status.product_cache.total)} />
            <Row label="Fresh" value={String(status.product_cache.fresh ?? 0)} dot="bg-wp-green" />
            <Row label="Stale" value={String(status.product_cache.stale ?? 0)} dot="bg-wp-yellow" />
            <Row label="Error" value={String(status.product_cache.error ?? 0)} dot="bg-wp-red" />
            <Row label="Last fetched" value={relTime(status.product_cache.last_fetched_at)} />
          </>
        ) : (
          <EmptyState message="Not initialized â€” browse Products to populate" />
        )}
      </Card>

      {/* Source Snapshots */}
      <Card>
        <SectionHeader title="Source Snapshots" />
        {loading && !status ? (
          <div className="flex items-center gap-2 py-2 text-[13px] text-wp-muted"><Spinner size="sm" />Loadingâ€¦</div>
        ) : status?.source_snapshots.initialized ? (
          <>
            <Row label="Snapshots" value={String(status.source_snapshots.total)} />
            <Row label="Last snapshot" value={relTime(status.source_snapshots.last_snapshot_at ?? null)} />
          </>
        ) : (
          <EmptyState message="Not initialized â€” run a Workspace preview to populate" />
        )}
      </Card>

      {/* Destination Snapshots */}
      <Card>
        <SectionHeader title="Destination Snapshots" />
        {loading && !status ? (
          <div className="flex items-center gap-2 py-2 text-[13px] text-wp-muted"><Spinner size="sm" />Loadingâ€¦</div>
        ) : status?.destination_snapshots.initialized ? (
          <>
            <Row label="Snapshots" value={String(status.destination_snapshots.total)} />
            <Row label="Last snapshot" value={relTime(status.destination_snapshots.last_snapshot_at ?? null)} />
          </>
        ) : (
          <EmptyState message="Not initialized â€” destination snapshots populate with refresh jobs" />
        )}
      </Card>

      {/* Connector Health */}
      <Card>
        <SectionHeader title="Connector Health" />
        {loading && connectorHealth.length === 0 ? (
          <div className="flex items-center gap-2 py-2 text-[13px] text-wp-muted"><Spinner size="sm" />Loadingâ€¦</div>
        ) : connectorHealth.length > 0 ? (
          <>
            {status?.connector_health && (
              <div className="flex gap-4 mb-3 text-[12px]">
                <span className="text-wp-green font-medium">{status.connector_health.healthy ?? 0} healthy</span>
                <span className="text-wp-yellow font-medium">{status.connector_health.degraded ?? 0} degraded</span>
                <span className="text-wp-red font-medium">{status.connector_health.unhealthy ?? 0} unhealthy</span>
              </div>
            )}
            {connectorHealth.map(c => (
              <Row
                key={c.connector_id}
                label={c.connector_id}
                value={c.status}
                dot={statusDot(c.status)}
                sub={[
                  c.latency_ms != null ? `${c.latency_ms.toFixed(0)} ms` : null,
                  c.detail ?? null,
                  c.checked_at ? `Checked ${relTime(c.checked_at)}` : null,
                ].filter(Boolean).join(' آ· ') || undefined}
              />
            ))}
          </>
        ) : (
          <EmptyState message="Not initialized â€” connector health is recorded on first connection check" />
        )}
      </Card>

      {/* Connector Telemetry */}
      <Card>
        <SectionHeader title="Connector Telemetry" />
        {loading && !status ? (
          <div className="flex items-center gap-2 py-2 text-[13px] text-wp-muted"><Spinner size="sm" />Loadingâ€¦</div>
        ) : status?.connector_telemetry.initialized ? (
          <>
            <Row label="Connectors tracked" value={String(status.connector_telemetry.connectors_tracked ?? 0)} />
            <Row label="Total requests" value={String(status.connector_telemetry.total_requests ?? 0)} />
            <Row label="Total errors" value={String(status.connector_telemetry.total_errors ?? 0)} />
            <Row label="Products fetched" value={String(status.connector_telemetry.total_products_fetched ?? 0)} />
            <Row label="Rows parsed" value={String(status.connector_telemetry.total_rows_parsed ?? 0)} />
          </>
        ) : (
          <EmptyState message="Not initialized â€” telemetry accumulates as connectors are used" />
        )}
      </Card>

      {/* Refresh Jobs */}
      <Card>
        <SectionHeader title="Refresh Queue" />
        {loading && jobs.length === 0 ? (
          <div className="flex items-center gap-2 py-2 text-[13px] text-wp-muted"><Spinner size="sm" />Loadingâ€¦</div>
        ) : jobs.length > 0 ? (
          <>
            {status?.refresh_jobs && (
              <div className="flex flex-wrap gap-3 mb-3 text-[12px] text-wp-muted">
                <span>{status.refresh_jobs.total} total</span>
                {status.refresh_jobs.running > 0 && (
                  <span className="text-accent font-medium">{status.refresh_jobs.running} running</span>
                )}
                {status.refresh_jobs.failed > 0 && (
                  <span className="text-wp-red font-medium">{status.refresh_jobs.failed} failed</span>
                )}
              </div>
            )}
            <div className="space-y-0">
              {jobs.map(j => (
                <Row
                  key={j.id}
                  label={`${j.job_type} / ${j.entity_type}`}
                  value={j.status}
                  dot={statusDot(j.status)}
                  sub={[
                    j.connector_id ?? null,
                    j.triggered_by ? `by ${j.triggered_by}` : null,
                    j.created_at ? relTime(j.created_at) : null,
                    j.duration_ms != null ? `${j.duration_ms.toFixed(0)} ms` : null,
                    j.error_message ? `Error: ${j.error_message.slice(0, 60)}` : null,
                  ].filter(Boolean).join(' آ· ') || undefined}
                />
              ))}
            </div>
          </>
        ) : (
          <EmptyState message="No refresh jobs â€” refresh queue is empty" />
        )}
      </Card>

      {/* Invalidation Events */}
      <Card>
        <SectionHeader title="Invalidation Events" />
        {loading && !status ? (
          <div className="flex items-center gap-2 py-2 text-[13px] text-wp-muted"><Spinner size="sm" />Loadingâ€¦</div>
        ) : status?.invalidation_events.initialized ? (
          <Row
            label="Total events"
            value={String(status.invalidation_events.total)}
            sub="View full log in Activity"
          />
        ) : (
          <EmptyState message="No invalidation events recorded" />
        )}
      </Card>

      {/* TTL / Staleness */}
      <Card>
        <SectionHeader title="TTL Policy" />
        <Row label="Product cache TTL" value="Not enforced" sub="Background refresh not yet implemented (future phase)" dot="bg-border" />
        <Row label="Source snapshot TTL" value="Not enforced" sub="ETag-triggered refresh is a future phase" dot="bg-border" />
        <Row label="Connector health TTL" value="Not enforced" sub="Periodic health checks are a future phase" dot="bg-border" />
        <Row label="Stale data surfacing" value="Active" sub="Freshness field exposed on product cache entries" dot="bg-wp-green" />
      </Card>

      {/* Future multi-channel note */}
      <Card>
        <SectionHeader title="Multi-Channel Readiness" />
        <p className="text-[12px] text-wp-muted mb-3">
          The Data Layer schema supports multiple connector types. Adding a new connector does not
          require schema changes â€” it populates the same tables under a different connector_id.
        </p>
        {[
          ['WooCommerce', 'Destination connector', 'Current'],
          ['Nextcloud', 'Source connector', 'Current'],
          ['SnappShop', 'Destination connector', 'Planned'],
          ['Digikala', 'Destination connector', 'Planned'],
          ['Shopify', 'Destination connector', 'Planned'],
          ['Google Sheets', 'Source connector', 'Planned'],
          ['CSV', 'Source connector', 'Planned'],
          ['ERP', 'Source and destination connector', 'Planned'],
        ].map(([name, description, phase]) => (
          <Row
            key={name}
            label={name}
            value={phase}
            dot={phase === 'Current' ? 'bg-wp-green' : 'bg-border'}
            sub={description}
          />
        ))}
      </Card>

    </div>
  )
}
