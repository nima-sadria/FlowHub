import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { authFetch } from '../api/authFetch'
import Spinner from '../components/loading/Spinner'

type HealthStatus =
  | 'healthy'
  | 'warning'
  | 'error'
  | 'disabled'
  | 'degraded'
  | 'authentication_failed'
  | 'rate_limited'
  | 'timeout'

interface ConnectorCapabilities {
  read_products: boolean
  read_categories: boolean
  read_inventory: boolean
  read_orders: boolean
  write_prices: boolean
  write_inventory: boolean
  webhook: boolean
  polling: boolean
  oauth: boolean
  api_key: boolean
}

interface RegistryItem {
  connector_type: string
  name: string
  version: string
  description: string
  capabilities: ConnectorCapabilities
  authentication_types: string[]
  supported_operations: string[]
  supported_transports: string[]
  read_only_supported: boolean
  write_supported: boolean
  beta_write_blocked: boolean
  status: string
}

interface ConnectorInstance {
  id: string
  connector_type: string
  name: string
  enabled: boolean
  read_only: boolean
  status: HealthStatus
  health: { healthy: boolean; last_checked_at: string | null; message: string }
  capabilities: ConnectorCapabilities
  created_at: string | null
  updated_at: string | null
  last_checked_at: string | null
  runtime_write_blocked: boolean
  capability_authorizes_write: false
}

interface Telemetry {
  items: Array<{
    connector_id: string
    connector_type: string
    operation: string
    request_count: number
    error_count: number
    retry_count: number
    rate_limit_events: number
    records_fetched: number
  }>
  aggregate: Record<string, number>
}

const CAPABILITY_LABELS: Array<[keyof ConnectorCapabilities, string]> = [
  ['read_products', 'Products'],
  ['read_categories', 'Categories'],
  ['read_inventory', 'Inventory'],
  ['read_orders', 'Orders'],
  ['write_prices', 'Write prices'],
  ['write_inventory', 'Write inventory'],
  ['webhook', 'Webhook'],
  ['polling', 'Polling'],
  ['oauth', 'OAuth'],
  ['api_key', 'API key'],
]

function Card({ children }: { children: ReactNode }) {
  return <div className="bg-bg-card border border-border rounded-card shadow-card p-[18px]">{children}</div>
}

function statusClass(status: string) {
  const map: Record<string, string> = {
    healthy: 'bg-wp-green',
    warning: 'bg-wp-yellow',
    degraded: 'bg-wp-yellow',
    rate_limited: 'bg-wp-yellow',
    error: 'bg-wp-red',
    authentication_failed: 'bg-wp-red',
    timeout: 'bg-wp-red',
    disabled: 'bg-border',
  }
  return map[status] ?? 'bg-border'
}

function capabilityBadge(enabled: boolean) {
  return [
    'inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium border',
    enabled
      ? 'bg-wp-green/10 text-wp-green border-wp-green/20'
      : 'bg-bg-base text-wp-muted border-border',
  ].join(' ')
}

function ConnectorCard({ item, instance }: { item: RegistryItem; instance?: ConnectorInstance }) {
  const capabilities = instance?.capabilities ?? item.capabilities
  const status = instance?.status ?? 'disabled'
  const writesAdvertised = capabilities.write_prices || capabilities.write_inventory

  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[16px] font-bold text-text-base">{item.name}</h2>
          <p className="text-[12px] text-wp-muted mt-0.5">{item.connector_type} / v{item.version}</p>
        </div>
        <div className="flex items-center gap-1.5 text-[12px] text-text-base">
          <span className={['w-2 h-2 rounded-full', statusClass(status)].join(' ')} />
          {status}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {CAPABILITY_LABELS.map(([key, label]) => (
          <span key={key} className={capabilityBadge(capabilities[key])}>{label}</span>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3 text-[12px]">
        <div className="rounded-lg bg-bg-base border border-border p-3">
          <div className="text-wp-muted">Instance</div>
          <div className="text-text-base font-semibold mt-1">{instance ? 'Configured' : 'Registry only'}</div>
        </div>
        <div className="rounded-lg bg-bg-base border border-border p-3">
          <div className="text-wp-muted">Transports</div>
          <div className="text-text-base font-semibold mt-1">{item.supported_transports.join(', ') || 'None'}</div>
        </div>
        <div className="rounded-lg bg-bg-base border border-border p-3">
          <div className="text-wp-muted">Write access</div>
          <div className="text-wp-green font-semibold mt-1">Blocked</div>
        </div>
      </div>

      {writesAdvertised && (
        <div className="mt-4 text-[12px] text-wp-muted bg-wp-yellow/10 border border-wp-yellow/30 rounded-lg p-3">
          Write capability is connector metadata only. Write authorization and execution remain blocked.
        </div>
      )}
    </Card>
  )
}

export default function IntegrationPlatform() {
  const [registry, setRegistry] = useState<RegistryItem[]>([])
  const [instances, setInstances] = useState<ConnectorInstance[]>([])
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null)
  const [events, setEvents] = useState<Array<{ id: number; event_type: string; message: string; severity: string; connector_id: string }>>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [registryResp, connectorsResp, telemetryResp, eventsResp] = await Promise.all([
        authFetch('/api/v2/integration-platform/registry'),
        authFetch('/api/v2/integration-platform/connectors'),
        authFetch('/api/v2/integration-platform/telemetry'),
        authFetch('/api/v2/integration-platform/events'),
      ])
      if (!registryResp.ok) throw new Error(`Registry request failed (${registryResp.status})`)
      if (!connectorsResp.ok) throw new Error(`Connector request failed (${connectorsResp.status})`)
      if (!telemetryResp.ok) throw new Error(`Telemetry request failed (${telemetryResp.status})`)
      if (!eventsResp.ok) throw new Error(`Events request failed (${eventsResp.status})`)
      const registryData = await registryResp.json() as { items: RegistryItem[] }
      const connectorData = await connectorsResp.json() as { items: ConnectorInstance[] }
      const telemetryData = await telemetryResp.json() as Telemetry
      const eventsData = await eventsResp.json() as { items: Array<{ id: number; event_type: string; message: string; severity: string; connector_id: string }> }
      setRegistry(registryData.items)
      setInstances(connectorData.items)
      setTelemetry(telemetryData)
      setEvents(eventsData.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Integration Platform')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const instanceByType = useMemo(
    () => Object.fromEntries(instances.map(item => [item.connector_type, item])),
    [instances],
  )
  const advertisedWrites = useMemo(
    () => registry.filter(item => item.write_supported).length,
    [registry],
  )

  return (
    <div className="p-4 sm:p-7 flex flex-col gap-5 max-w-6xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold text-text-base">Integration Platform</h1>
          <p className="text-[13px] text-wp-muted mt-0.5">Connector registry, instances, settings status, diagnostics, telemetry, and events</p>
        </div>
        <button
          onClick={() => void load()}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-[13px] font-medium text-wp-muted hover:text-text-base hover:border-accent transition-colors disabled:opacity-50"
        >
          {loading ? <Spinner size="sm" /> : 'Refresh'}
        </button>
      </div>

      {error && <div className="bg-wp-red/10 border border-wp-red/30 rounded-card p-4 text-[13px] text-wp-red">{error}</div>}

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <Card><p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-1">Registry</p><div className="text-[20px] font-bold text-text-base">{registry.length}</div></Card>
        <Card><p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-1">Instances</p><div className="text-[20px] font-bold text-text-base">{instances.length}</div></Card>
        <Card><p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-1">Advertised Writes</p><div className="text-[20px] font-bold text-text-base">{advertisedWrites}</div></Card>
        <Card><p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-1">Write Access</p><div className="text-[20px] font-bold text-wp-green">Blocked</div></Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {registry.map(item => (
          <ConnectorCard key={item.connector_type} item={item} instance={instanceByType[item.connector_type]} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">Telemetry</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[12px]">
            <div><div className="text-wp-muted">Requests</div><div className="font-semibold text-text-base">{telemetry?.aggregate.total_requests ?? 0}</div></div>
            <div><div className="text-wp-muted">Errors</div><div className="font-semibold text-text-base">{telemetry?.aggregate.total_errors ?? 0}</div></div>
            <div><div className="text-wp-muted">Records</div><div className="font-semibold text-text-base">{telemetry?.items.reduce((sum, item) => sum + item.records_fetched, 0) ?? 0}</div></div>
            <div><div className="text-wp-muted">Rate limits</div><div className="font-semibold text-text-base">{telemetry?.items.reduce((sum, item) => sum + item.rate_limit_events, 0) ?? 0}</div></div>
          </div>
        </Card>

        <Card>
          <p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">Events</p>
          <div className="divide-y divide-border">
            {events.slice(0, 6).map(item => (
              <div key={item.id} className="py-3 text-[12px]">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium text-text-base">{item.event_type}</span>
                  <span className="text-wp-muted">{item.connector_id}</span>
                </div>
                <div className="text-wp-muted mt-0.5">{item.message}</div>
              </div>
            ))}
            {!loading && events.length === 0 && (
              <div className="py-4 text-center text-[12px] text-wp-muted">No connector events yet</div>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
