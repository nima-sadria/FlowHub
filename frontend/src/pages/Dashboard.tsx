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
import type { ActivityEvent, Source } from '../services/types'

type Indicator = 'ok' | 'error' | 'loading'

function relTime(d: Date | null): string {
  if (!d) return '-'
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function StatCard({ label, value, sub, indicator }: {
  label: string
  value: string
  sub?: string
  indicator?: Indicator
}) {
  const dot =
    indicator === 'ok' ? 'bg-wp-green' :
    indicator === 'error' ? 'bg-wp-red' :
    indicator === 'loading' ? 'bg-wp-yellow animate-pulse' :
    null

  return (
    <div className="fh-stat-card">
      <div className="flex items-center gap-3">
        <div className="fh-stat-card-icon">
          {dot ? (
            <span className={['h-2.5 w-2.5 rounded-full flex-shrink-0', dot].join(' ')} />
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
  const { sources, products, activity } = useServices()
  const navigate = useNavigate()

  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthErr, setHealthErr] = useState(false)

  const [sourceList, setSourceList] = useState<Source[]>([])
  const [totalProducts, setTotalProducts] = useState<number | null>(null)
  const [recentEvents, setRecentEvents] = useState<ActivityEvent[]>([])
  const [dataLoading, setDataLoading] = useState(true)

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true)
    try {
      const data = await apiFetch<HealthResponse>('/api/health', authFetch)
      setHealth(data)
    } catch {
      setHealthErr(true)
    } finally {
      setHealthLoading(false)
    }
  }, [authFetch])

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
          <h1 className="fh-page-title">Dashboard</h1>
          <p className="fh-page-subtitle">System overview</p>
        </div>
      </div>

      <div className="fh-card fh-card-pad">
        <p className="fh-section-label mb-3">Logged In</p>
        <div className="flex items-center gap-3">
          <div className="fh-user-avatar flex-shrink-0">{initial}</div>
          <div>
            <div className="fh-text-body font-medium">{user?.username ?? '-'}</div>
            <div className="fh-text-caption capitalize">{user?.role ?? '-'}</div>
          </div>
        </div>
      </div>

      <div className="fh-stat-grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label="Backend"
          value={health ? 'Online' : healthLoading ? 'Loading' : 'Unavailable'}
          indicator={backendInd}
        />
        <StatCard
          label="Database"
          value={backendInd === 'ok' ? 'Connected' : backendInd === 'loading' ? 'Loading' : 'Unavailable'}
          indicator={backendInd}
        />
        <StatCard
          label="Application"
          value={backendInd === 'ok' ? 'Running' : backendInd === 'loading' ? 'Loading' : 'Unavailable'}
          indicator={backendInd}
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
          <StatCard label="Total Products" value={totalProducts !== null ? String(totalProducts) : '-'} sub="across connected channels" />
          <StatCard label="Active Sources" value={String(activeSources.length)} sub={activeSources.length === 1 ? '1 connected' : `${activeSources.length} configured`} />
          <StatCard label="Last Preview" value={lastSync ? relTime(lastSync) : '-'} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="fh-card">
          <div className="fh-panel-header">
            <p className="fh-section-title">Sources</p>
            <button onClick={() => navigate('/sources/new')} className="fh-toolbar-link">
              Add Source
            </button>
          </div>
          <div className="fh-panel-body !py-3">
            {dataLoading ? (
              <SkeletonCard />
            ) : sourceList.length === 0 ? (
              <Empty
                title="No sources yet"
                action={{ label: 'Add your first source', onClick: () => navigate('/sources/new') }}
              />
            ) : (
              sourceList.map(source => (
                <div key={source.id} className="flex items-center justify-between border-b border-border py-2.5 last:border-0">
                  <div>
                    <p className="fh-text-body font-medium">{source.name}</p>
                    <p className="fh-text-caption">{`${relTime(source.lastSynced)} · ${source.productCount} products`}</p>
                  </div>
                  <Badge className="capitalize" variant={source.status === 'active' ? 'success' : 'error'}>{source.status}</Badge>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="fh-card">
          <div className="fh-panel-header">
            <p className="fh-section-title">Recent Activity</p>
            <button onClick={() => navigate('/activity')} className="fh-toolbar-link">
              View all
            </button>
          </div>
          <div className="fh-panel-body !pt-0">
            {dataLoading ? (
              <div className="py-3">
                <SkeletonCard />
              </div>
            ) : recentEvents.length === 0 ? (
              <Empty title="No events yet" />
            ) : (
              recentEvents.map(event => (
                <div key={event.id} className="flex items-center gap-3 border-b border-border py-2.5 last:border-0">
                  <span
                    className={[
                      'h-2 w-2 rounded-full flex-shrink-0',
                      event.level === 'success' ? 'bg-wp-green' :
                      event.level === 'error' ? 'bg-wp-red' :
                      event.level === 'warning' ? 'bg-wp-yellow' :
                      'bg-accent',
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
