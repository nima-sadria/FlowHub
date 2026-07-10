import { useCallback, useEffect, useState } from 'react'
import { useServices } from '../services/ServiceContext'
import type { ActivityEvent, ActivityLevel } from '../services/types'
import { SkeletonCard } from '../components/loading/Skeleton'
import Empty from '../components/Empty'
import PageShell from '../components/PageShell'

function relTime(d: Date): string {
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

const LEVEL_STYLES: Record<ActivityLevel, { dot: string; badge: string; label: string }> = {
  info:    { dot: 'bg-accent',        badge: 'fh-badge-info',    label: 'Info' },
  success: { dot: 'bg-wp-green',      badge: 'fh-badge-success', label: 'Success' },
  warning: { dot: 'bg-wp-yellow',     badge: 'fh-badge-warning', label: 'Warning' },
  error:   { dot: 'bg-wp-red',        badge: 'fh-badge-danger',  label: 'Error' },
}

function formatAction(action: string): string {
  return action.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function EventRow({ event }: { event: ActivityEvent }) {
  const styles = LEVEL_STYLES[event.level]
  return (
    <div className="flex items-start gap-3 py-3 border-b border-border last:border-0">
      <div className="flex-shrink-0 mt-1.5">
        <span className={['w-2 h-2 rounded-full block', styles.dot].join(' ')} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2 mb-0.5">
          <span className="text-[13px] font-medium text-text-base">{formatAction(event.action)}</span>
          <span className={['fh-badge', styles.badge].join(' ')}>
            {styles.label}
          </span>
          {event.kind === 'user_action' && (
            <span className="text-[11px] text-wp-muted">by {event.actor}</span>
          )}
        </div>
        {event.detail && (
          <p className="text-[12px] text-wp-muted truncate">{event.detail}</p>
        )}
      </div>
      <span className="flex-shrink-0 text-[11px] text-wp-muted whitespace-nowrap mt-0.5">
        {relTime(event.timestamp)}
      </span>
    </div>
  )
}

export default function Activity() {
  const { activity } = useServices()
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const PAGE_SIZE = 15

  const loadPage = useCallback(async (p: number, append: boolean) => {
    if (p === 1) setLoading(true); else setLoadingMore(true)
    try {
      const result = await activity.getEvents({ page: p, pageSize: PAGE_SIZE })
      setEvents(prev => append ? [...prev, ...result.items] : result.items)
      setTotal(result.total)
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }, [activity])

  useEffect(() => { void loadPage(1, false) }, [loadPage])

  function loadMore() {
    const next = page + 1
    setPage(next)
    void loadPage(next, true)
  }

  const hasMore = events.length < total

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
        <h1 className="fh-page-title">Activity</h1>
        <p className="fh-page-subtitle">System events and user actions</p>
        </div>
      </div>

      <div className="fh-card">
        <div className="fh-panel-header">
          <span className="text-[16px] font-semibold text-text-base">
            {loading ? 'Loading...' : `${total} events`}
          </span>
        </div>

        <div className="fh-panel-body !pt-0">
          {loading ? (
            <div className="py-4 flex flex-col gap-3">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : events.length === 0 ? (
            <Empty title="No activity yet" description="Events will appear here as the system runs." />
          ) : (
            events.map(e => <EventRow key={e.id} event={e} />)
          )}
        </div>

        {!loading && hasMore && (
          <div className="fh-panel-footer !justify-start">
            <button
              onClick={loadMore}
              disabled={loadingMore}
              className="fh-button-secondary w-full"
            >
              {loadingMore ? 'Loading...' : `Load more (${total - events.length} remaining)`}
            </button>
          </div>
        )}
      </div>
    </PageShell>
  )
}
