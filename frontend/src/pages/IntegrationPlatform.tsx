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

interface ConnectorDefinition {
  connector: {
    identity: {
      id: string
      name: string
      type: string
      version: string
      enabled: boolean
      read_only: boolean
    }
    capabilities: ConnectorCapabilities
    status: HealthStatus
    runtime_write_blocked: boolean
    capability_authorizes_write: false
  }
  settings_schema: Array<{ key: string; label: string; required: boolean; secret: boolean }>
  diagnostics_contract: { checks: Array<{ name: string; category: string }> }
}

interface ConnectorInstance {
  connector: ConnectorDefinition['connector']
  settings: Array<{ key: string; value: unknown; secret: boolean; configured: boolean }>
  created_at: string | null
  updated_at: string | null
}

interface Telemetry {
  items: Array<{ id: number; connector_id: string; event_name: string; severity: string; message: string; created_at: string }>
  total: number
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

function badgeClass(enabled: boolean) {
  return [
    'inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium border',
    enabled
      ? 'bg-wp-green/10 text-wp-green border-wp-green/20'
      : 'bg-bg-base text-wp-muted border-border',
  ].join(' ')
}

function statusDot(status: string) {
  const map: Record<string, string> = {
    healthy: 'bg-wp-green',
    warning: 'bg-wp-yellow',
    degraded: 'bg-wp-yellow',
    error: 'bg-wp-red',
    authentication_failed: 'bg-wp-red',
    rate_limited: 'bg-wp-yellow',
    timeout: 'bg-wp-yellow',
    disabled: 'bg-border',
  }
  return map[status] ?? 'bg-border'
}

function Card({ children }: { children: ReactNode }) {
  return <div className="bg-bg-card border border-border rounded-card shadow-card p-[18px]">{children}</div>
}

function ConnectorCard({ definition, instance }: { definition: ConnectorDefinition; instance?: ConnectorInstance }) {
  const connector = instance?.connector ?? definition.connector
  const writeAdvertised = connector.capabilities.write_prices || connector.capabilities.write_inventory
  const configured = instance?.settings.filter(s => s.configured).length ?? 0

  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[16px] font-bold text-text-base">{connector.identity.name}</h2>
          <p className="text-[12px] text-wp-muted mt-0.5">{connector.identity.type} / v{connector.identity.version}</p>
        </div>
        <div className="flex items-center gap-1.5 text-[12px] text-text-base">
          <span className={['w-2 h-2 rounded-full', statusDot(connector.status)].join(' ')} />
          {connector.status}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {CAPABILITY_LABELS.map(([key, label]) => (
          <span key={key} className={badgeClass(connector.capabilities[key])}>{label}</span>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3 text-[12px]">
        <div className="rounded-lg bg-bg-base border border-border p-3">
          <div className="text-wp-muted">Instance</div>
          <div className="text-text-base font-semibold mt-1">{instance ? 'Configured' : 'Registry only'}</div>
        </div>
        <div className="rounded-lg bg-bg-base border border-border p-3">
          <div className="text-wp-muted">Settings</div>
          <div className="text-text-base font-semibold mt-1">{configured} configured</div>
        </div>
        <div className="rounded-lg bg-bg-base border border-border p-3">
          <div className="text-wp-muted">Writes</div>
          <div className="text-wp-green font-semibold mt-1">Blocked</div>
        </div>
      </div>

      {writeAdvertised && (
        <div className="mt-4 text-[12px] text-wp-muted bg-amber-50 border border-amber-200 rounded-lg p-3">
          Write capability is advertised as connector metadata only. FlowHub Beta runtime authorization blocks all writes.
        </div>
      )}
    </Card>
  )
}

export default function IntegrationPlatform() {
  const [registry, setRegistry] = useState<ConnectorDefinition[]>([])
  const [instances, setInstances] = useState<ConnectorInstance[]>([])
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [registryResp, connectorsResp, telemetryResp] = await Promise.all([
        authFetch('/api/v2/integrations/registry'),
        authFetch('/api/v2/integrations/connectors'),
        authFetch('/api/v2/integrations/telemetry'),
      ])
      if (!registryResp.ok) throw new Error(`Registry request failed (${registryResp.status})`)
      if (!connectorsResp.ok) throw new Error(`Connector request failed (${connectorsResp.status})`)
      if (!telemetryResp.ok) throw new Error(`Telemetry request failed (${telemetryResp.status})`)
      const registryData = await registryResp.json() as { items: ConnectorDefinition[] }
      const connectorData = await connectorsResp.json() as { items: ConnectorInstance[] }
      setRegistry(registryData.items)
      setInstances(connectorData.items)
      setTelemetry(await telemetryResp.json() as Telemetry)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Integration Platform')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const advertisedWrites = useMemo(
    () => registry.filter(d => d.connector.capabilities.write_prices || d.connector.capabilities.write_inventory).length,
    [registry],
  )
  const instanceByType = useMemo(
    () => Object.fromEntries(instances.map(item => [item.connector.identity.type, item])),
    [instances],
  )

  return (
    <div className="p-4 sm:p-7 flex flex-col gap-5 max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold text-text-base">Integration Platform</h1>
          <p className="text-[13px] text-wp-muted mt-0.5">Connector registry, local settings, health, and telemetry</p>
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
        <Card><p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-1">Runtime Writes</p><div className="text-[20px] font-bold text-wp-green">Blocked</div></Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {registry.map(definition => (
          <ConnectorCard
            key={definition.connector.identity.type}
            definition={definition}
            instance={instanceByType[definition.connector.identity.type]}
          />
        ))}
      </div>

      <Card>
        <p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">Telemetry</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[12px]">
          <div><div className="text-wp-muted">Events</div><div className="font-semibold text-text-base">{telemetry?.total ?? 0}</div></div>
          <div><div className="text-wp-muted">Requests</div><div className="font-semibold text-text-base">{telemetry?.aggregate.total_requests ?? 0}</div></div>
          <div><div className="text-wp-muted">Errors</div><div className="font-semibold text-text-base">{telemetry?.aggregate.total_errors ?? 0}</div></div>
          <div><div className="text-wp-muted">Products</div><div className="font-semibold text-text-base">{telemetry?.aggregate.total_products_fetched ?? 0}</div></div>
        </div>
        <div className="mt-4 divide-y divide-border">
          {(telemetry?.items ?? []).slice(0, 5).map(item => (
            <div key={item.id} className="py-3 text-[12px]">
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium text-text-base">{item.event_name}</span>
                <span className="text-wp-muted">{item.connector_id}</span>
              </div>
              <div className="text-wp-muted mt-0.5">{item.message}</div>
            </div>
          ))}
          {!loading && (telemetry?.items.length ?? 0) === 0 && (
            <div className="py-4 text-center text-[12px] text-wp-muted">No telemetry events yet</div>
          )}
        </div>
      </Card>
    </div>
  )
}
