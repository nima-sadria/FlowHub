import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { useServices } from '../services/ServiceContext'
import type { Source, ActivityEvent } from '../services/types'
import { apiFetch } from '../api/client'
import type { HealthResponse } from '../api/types'
import { SkeletonCard } from '../components/loading/Skeleton'
import Empty from '../components/Empty'

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
  label: string; value: string; sub?: string; indicator?: Indicator
}) {
  const dot =
    indicator === 'ok'      ? 'bg-wp-green' :
    indicator === 'error'   ? 'bg-wp-red' :
    indicator === 'loading' ? 'bg-wp-yellow animate-pulse' :
    null

  return (
    <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px]">
      {dot && (
        <div className="flex items-center gap-2 mb-2">
          <span className={['w-2 h-2 rounded-full flex-shrink-0', dot].join(' ')} />
          <span className="text-[11.5px] uppercase tracking-[.7px] text-wp-muted font-semibold">{label}</span>
        </div>
      )}
      {!dot && (
        <p className="text-[11.5px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-2">{label}</p>
      )}
      <div className="text-[20px] font-bold text-text-base leading-tight">{value}</div>
      {sub && <div className="text-[11px] text-wp-muted mt-0.5">{sub}</div>}
    </div>
  )
}

function formatAction(action: string): string {
  return action.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export default function BetaDashboard() {
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

  const initial = user?.username?.[0]?.toUpperCase() ?? '?'

  return (
    <div className="p-4 sm:p-7 flex flex-col gap-6">
      {/* Header */}
      <div>
        <h1 className="text-[22px] font-bold text-text-base">Dashboard</h1>
        <p className="text-[13px] text-wp-muted mt-0.5">System overview</p>
      </div>

      {/* User card */}
      <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px]">
        <p className="text-[11.5px] uppercase tracking-[.7px] text-wp-muted mb-3 font-semibold">Logged In</p>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-accent/10 flex items-center justify-center flex-shrink-0">
            <span className="text-accent font-bold text-[14px]">{initial}</span>
          </div>
          <div>
            <div className="text-[15px] font-semibold text-text-base">{user?.username ?? '-'}</div>
            <div className="text-[12px] text-wp-muted capitalize">{user?.role ?? '-'}</div>
          </div>
        </div>
      </div>

      {/* System status - uses real /api/health */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
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

      {/* Summary stat row */}
      {dataLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard label="Total Products" value={totalProducts !== null ? String(totalProducts) : '-'} sub="across connected channels" />
          <StatCard label="Active Sources" value={String(activeSources.length)} sub={activeSources.length === 1 ? '1 connected' : `${activeSources.length} configured`} />
          <StatCard label="Last Preview" value={lastSync ? relTime(lastSync) : '-'} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Sources */}
        <div className="bg-bg-card border border-border rounded-card shadow-card">
          <div className="flex items-center justify-between px-[22px] py-4 border-b border-border">
            <p className="text-[13px] font-semibold text-text-base">Sources</p>
            <button
              onClick={() => navigate('/sources/new')}
              className="text-[12px] text-accent font-medium hover:underline"
            >
              + Add Source
            </button>
          </div>
          <div className="px-[22px] py-3">
            {dataLoading ? (
              <SkeletonCard />
            ) : sourceList.length === 0 ? (
              <Empty
                title="No sources yet"
                action={{ label: 'Add your first source', onClick: () => navigate('/sources/new') }}
              />
            ) : (
              sourceList.map(s => (
                <div key={s.id} className="flex items-center justify-between py-2.5 border-b border-border last:border-0">
                  <div>
                    <p className="text-[13px] font-medium text-text-base">{s.name}</p>
                    <p className="text-[11px] text-wp-muted">{relTime(s.lastSynced)} آ· {s.productCount} products</p>
                  </div>
                  <span className={[
                    'text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase',
                    s.status === 'active' ? 'bg-wp-green/10 text-wp-green' : 'bg-wp-red/10 text-wp-red',
                  ].join(' ')}>
                    {s.status}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Recent Activity */}
        <div className="bg-bg-card border border-border rounded-card shadow-card">
          <div className="flex items-center justify-between px-[22px] py-4 border-b border-border">
            <p className="text-[13px] font-semibold text-text-base">Recent Activity</p>
            <button
              onClick={() => navigate('/activity')}
              className="text-[12px] text-accent font-medium hover:underline"
            >
              View all
            </button>
          </div>
          <div className="px-[22px]">
            {dataLoading ? (
              <div className="py-3">
                <SkeletonCard />
              </div>
            ) : recentEvents.length === 0 ? (
              <Empty title="No events yet" />
            ) : (
              recentEvents.map(e => (
                <div key={e.id} className="flex items-center gap-3 py-2.5 border-b border-border last:border-0">
                  <span className={[
                    'w-2 h-2 rounded-full flex-shrink-0',
                    e.level === 'success' ? 'bg-wp-green' :
                    e.level === 'error'   ? 'bg-wp-red' :
                    e.level === 'warning' ? 'bg-wp-yellow' :
                    'bg-accent',
                  ].join(' ')} />
                  <p className="flex-1 text-[12px] text-text-base truncate">{formatAction(e.action)}</p>
                  <span className="text-[11px] text-wp-muted flex-shrink-0">{relTime(e.timestamp)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
