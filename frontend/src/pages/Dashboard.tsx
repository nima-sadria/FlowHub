import { translate } from '../i18n'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../api/client'
import type { HealthResponse } from '../api/types'
import { useAuth } from '../auth'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import { SkeletonCard } from '../components/loading/Skeleton'
import PageShell from '../components/PageShell'
import { useServices } from '../services/ServiceContext'
import type { ActivityEvent, ChannelHealthResponse, Source } from '../services/types'
import { formatRelativeTime } from '../i18n/format'
import { formatDiagnosticMessage, formatRole, formatStatus } from '../i18n/display'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'

type Indicator = 'ok' | 'warning' | 'error' | 'loading'

function relTime(d: Date | null): string {
  if (!d) return '-'
  return formatRelativeTime(d)
}

function StatCard({ label, value, sub, indicator }: {
  label: string
  value: string
  sub?: string
  indicator?: Indicator
}) {
  const dot =
    indicator === 'ok' ? 'bg-wp-green' :
    indicator === 'warning' ? 'bg-wp-yellow' :
    indicator === 'error' ? 'bg-wp-red' :
    indicator === 'loading' ? 'bg-wp-yellow animate-pulse' :
    null

  return (
    <div className="fh-stat-card">
      <div className="flex items-center gap-3">
        <div className="fh-stat-card-icon">
          {dot ? (
            <span className={["h-2.5 w-2.5 rounded-full flex-shrink-0", dot].join(' ')} />
          ) : (
            <span className="h-2.5 w-2.5 rounded-full bg-border" />
          )}
        </div>
        <div className="min-w-0">
          <p className="fh-stat-card-label">{label}</p>
          <div className="fh-stat-card-value">{value}</div>
        </div>
      </div>
      {sub && <div className="fh-text-caption">{sub}</div>}
    </div>
  )
}

function formatAction(action: string): string {
  return action.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export default function Dashboard() {
  const { user, authFetch } = useAuth()
  const { sources, products, activity, health: healthService } = useServices()
  const navigate = useNavigate()

  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [channelHealth, setChannelHealth] = useState<ChannelHealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthErr, setHealthErr] = useState(false)

  const [sourceList, setSourceList] = useState<Source[]>([])
  const [totalProducts, setTotalProducts] = useState<number | null>(null)
  const [recentEvents, setRecentEvents] = useState<ActivityEvent[]>([])
  const [dataLoading, setDataLoading] = useState(true)

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true)
    setHealthErr(false)
    try {
      const [data, channels] = await Promise.all([
        apiFetch<HealthResponse>('/api/health', authFetch),
        healthService.getChannelHealth(),
      ])
      setHealth(data)
      setChannelHealth(channels)
    } catch {
      setHealthErr(true)
    } finally {
      setHealthLoading(false)
    }
  }, [authFetch, healthService])

  useEffect(() => { void fetchHealth() }, [fetchHealth])

  useEffect(() => {
    Promise.all([
      sources.getSources(),
      products.getProducts({ search: '', status: 'all', page: 1, pageSize: 1 }),
      activity.getEvents({ page: 1, pageSize: 5 }),
    ]).then(([srcs, prods, evts]) => {
      setSourceList(srcs)
      setTotalProducts(prods.total)
      setRecentEvents(evts.items)
    }).finally(() => setDataLoading(false))
  }, [sources, products, activity])

  const backendInd: Indicator = healthLoading ? 'loading' : healthErr ? 'error' : 'ok'
  const channelOverall = channelHealth?.summary.overall
  const channelInd: Indicator =
    healthLoading ? 'loading' :
    channelOverall === 'Operational' ? 'ok' :
    channelOverall === 'Warning' || channelOverall === 'Unable to check' ? 'warning' :
    channelOverall === 'Disabled' ? 'warning' :
    channelOverall === 'Error' ? 'error' :
    healthErr ? 'error' : 'warning'
  const activeSources = sourceList.filter(s => s.status === 'active')
  const lastSync = activeSources.reduce<Date | null>((best, s) => {
    if (!s.lastSynced) return best
    return !best || s.lastSynced > best ? s.lastSynced : best
  }, null)

  const initial = user?.username?.slice(0, 2).toUpperCase() ?? '?'

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('dashboard:dashboard.dashboard')}</h1>
          <p className="fh-page-subtitle">{translate('dashboard:dashboard.systemOverview')}</p>
        </div>
      </div>

      <div className="fh-card fh-card-pad">
        <p className="fh-section-label mb-3">{translate('dashboard:dashboard.loggedIn')}</p>
        <div className="flex items-center gap-3">
          <div className="fh-user-avatar flex-shrink-0">{initial}</div>
          <div>
            <div className="fh-text-body font-medium">{user?.username ?? '-'}</div>
            <div className="fh-text-caption">{formatRole(user?.role)}</div>
          </div>
        </div>
      </div>

      <div className="fh-stat-grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label={translate('dashboard:dashboard.backend')}
          value={formatStatus(health ? 'online' : healthLoading ? 'loading' : 'unavailable')}
          indicator={backendInd}
        />
        <StatCard
          label={translate('dashboard:dashboard.database')}
          value={formatStatus(backendInd === 'ok' ? 'connected' : backendInd === 'loading' ? 'loading' : 'unavailable')}
          indicator={backendInd}
        />
        <StatCard
          label={translate('dashboard:dashboard.application')}
          value={formatStatus(backendInd === 'ok' ? 'running' : backendInd === 'loading' ? 'loading' : 'unavailable')}
          indicator={backendInd}
        />
        <StatCard
          label={translate('dashboard:dashboard.channels')}
          value={formatStatus(channelOverall ?? (healthLoading ? 'loading' : 'unable_to_check'))}
          sub={channelHealth ? translate('dashboard:dashboard.monitoredDestinations', { count: channelHealth.items.length }) : undefined}
          indicator={channelInd}
        />
      </div>

      {dataLoading ? (
        <div className="fh-stat-grid grid-cols-1 sm:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <div className="fh-stat-grid grid-cols-1 sm:grid-cols-3">
          <StatCard label={translate('dashboard:dashboard.totalProducts')} value={totalProducts !== null ? String(totalProducts) : '-'} sub={translate('dashboard:dashboard.totalProductsAcrossChannels')} />
          <StatCard label={translate('dashboard:dashboard.activeSources')} value={String(activeSources.length)} sub={translate(activeSources.length === 1 ? 'dashboard:dashboard.connectedSources' : 'dashboard:dashboard.configuredSources', { count: activeSources.length })} />
          <StatCard label={translate('dashboard:dashboard.lastPreview')} value={lastSync ? relTime(lastSync) : '-'} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="fh-card">
          <div className="fh-panel-header">
            <p className="fh-section-title">{translate('dashboard:dashboard.channels')}</p>
            <button onClick={() => navigate("/diagnostics")} className="fh-toolbar-link">
              {translate('dashboard:dashboard.diagnostics2')}
            </button>
          </div>
          <div className="fh-panel-body !py-3">
            {healthLoading && !channelHealth ? (
              <SkeletonCard />
            ) : !channelHealth || channelHealth.items.length === 0 ? (
              <Empty title={translate('dashboard:dashboard.noChannelsMonitored')} />
            ) : (
              channelHealth.items.map(channel => (
                <div key={channel.channelId} className="flex items-center justify-between gap-3 border-b border-border py-2.5 last:border-0">
                  <div className="min-w-0">
                    {/* i18n-ignore -- fallback is a technical Channel identity, not interface copy */}
                    <p className="fh-text-body font-medium truncate">{formatChannelDisplayName(channel.channelId || `${channel.channelType}:primary`)}</p>
                    <p className="fh-text-caption truncate">{formatDiagnosticMessage(channel.summary)}</p>
                  </div>
                  <Badge
                    className="capitalize flex-shrink-0"
                    variant={channel.status === "Operational" ? "success" : channel.status === "Error" ? "error" : "warning"}
                  >
                    {formatStatus(channel.status)}
                  </Badge>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="fh-card">
          <div className="fh-panel-header">
            <p className="fh-section-title">{translate('dashboard:dashboard.sources')}</p>
            <button onClick={() => navigate("/sources/new")} className="fh-toolbar-link">
              {translate('dashboard:dashboard.addSource')}
            </button>
          </div>
          <div className="fh-panel-body !py-3">
            {dataLoading ? (
              <SkeletonCard />
            ) : sourceList.length === 0 ? (
              <Empty
                title={translate('dashboard:dashboard.noSourcesYet')}
                action={{ label: translate('dashboard:dashboard.addYourFirstSource'), onClick: () => navigate("/sources/new") }}
              />
            ) : (
              sourceList.map(source => (
                <div key={source.id} className="flex items-center justify-between border-b border-border py-2.5 last:border-0">
                  <div>
                    <p className="fh-text-body font-medium">{source.name}</p>
                    <p className="fh-text-caption">{translate('dashboard:dashboard.products', { value1: relTime(source.lastSynced), value2: source.productCount })}</p>
                  </div>
                  <Badge className="capitalize" variant={source.status === "active" ? "success" : "error"}>{formatStatus(source.status)}</Badge>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="fh-card">
          <div className="fh-panel-header">
            <p className="fh-section-title">{translate('dashboard:dashboard.recentActivity')}</p>
            <button onClick={() => navigate("/activity")} className="fh-toolbar-link">
              {translate('dashboard:dashboard.viewAll')}
            </button>
          </div>
          <div className="fh-panel-body !pt-0">
            {dataLoading ? (
              <div className="py-3">
                <SkeletonCard />
              </div>
            ) : recentEvents.length === 0 ? (
              <Empty title={translate('dashboard:dashboard.noEventsYet')} />
            ) : (
              recentEvents.map(event => (
                <div key={event.id} className="flex items-center gap-3 border-b border-border py-2.5 last:border-0">
                  <span
                    className={[
                      "h-2 w-2 rounded-full flex-shrink-0",
                      event.level === "success" ? "bg-wp-green" :
                      event.level === "error" ? "bg-wp-red" :
                      event.level === "warning" ? "bg-wp-yellow" :
                      "bg-accent",
                    ].join(' ')}
                  />
                  <p className="fh-text-caption flex-1 truncate text-text-base">{formatAction(event.action)}</p>
                  <span className="fh-text-caption flex-shrink-0">{relTime(event.timestamp)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </PageShell>
  )
}
