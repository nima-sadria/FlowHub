import { useCallback, useEffect, useMemo, useState } from 'react'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import { SkeletonCard } from '../components/loading/Skeleton'
import PageShell from '../components/PageShell'
import { useServices } from '../services/ServiceContext'
import type { ActivityEvent, ActivityLevel } from '../services/types'

function relTime(d: Date): string {
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 60) return `${Math.max(s, 0)}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

const LEVEL_STYLES: Record<ActivityLevel, { icon: 'info' | 'success' | 'warning' | 'error'; surface: string }> = {
  info: { icon: 'info', surface: 'bg-[color:var(--fh-info-surface)] text-accent' },
  success: { icon: 'success', surface: 'bg-[color:var(--fh-success-surface)] text-wp-green' },
  warning: { icon: 'warning', surface: 'bg-[color:var(--fh-warning-surface)] text-wp-yellow' },
  error: { icon: 'error', surface: 'bg-[color:var(--fh-danger-surface)] text-wp-red' },
}

function formatAction(action: string): string {
  return action.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function eventChannel(event: ActivityEvent): string {
  const value = `${event.action} ${event.detail ?? ''}`.toLowerCase()
  if (value.includes('woocommerce')) return 'WooCommerce'
  if (value.includes('snappshop')) return 'SnappShop'
  if (value.includes('tapsishop')) return 'TapsiShop'
  if (value.includes('nextcloud')) return 'Nextcloud'
  return 'System'
}

function csvCell(value: string): string {
  return `"${value.replace(/"/g, '""')}"`
}

function EventRow({ event }: { event: ActivityEvent }) {
  const styles = LEVEL_STYLES[event.level]
  return (
    <div className="flex items-start gap-3 border-b border-border px-5 py-4 last:border-0">
      <span className={['inline-flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-lg', styles.surface].join(' ')}>
        <Icon name={styles.icon} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-[13px] font-semibold leading-5 text-text-base">{formatAction(event.action)}</p>
          {event.level === 'error' && <span className="fh-status-dot fh-status-dot-danger" aria-label="Unresolved" />}
        </div>
        <p className="mt-0.5 truncate text-xs leading-[18px] text-wp-muted">
          {event.detail || (event.kind === 'user_action' ? `Action completed by ${event.actor}` : 'System activity recorded')}
        </p>
        <p className="mt-1 text-[11px] leading-4 text-wp-muted">
          {eventChannel(event)} · {event.actor || 'System'} · {relTime(event.timestamp)}
        </p>
      </div>
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
  const [search, setSearch] = useState('')
  const [level, setLevel] = useState<ActivityLevel | 'all'>('all')
  const [channel, setChannel] = useState('all')
  const [actor, setActor] = useState('all')
  const PAGE_SIZE = 100

  const loadPage = useCallback(async (p: number, append: boolean) => {
    if (p === 1) setLoading(true)
    else setLoadingMore(true)
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

  const actors = useMemo(
    () => [...new Set(events.map(event => event.actor).filter(Boolean))].sort(),
    [events],
  )
  const channels = useMemo(
    () => [...new Set(events.map(eventChannel))].sort(),
    [events],
  )
  const filteredEvents = useMemo(() => {
    const query = search.trim().toLowerCase()
    return events.filter(event => (
      (level === 'all' || event.level === level)
      && (channel === 'all' || eventChannel(event) === channel)
      && (actor === 'all' || event.actor === actor)
      && (!query || `${event.action} ${event.detail ?? ''} ${event.actor}`.toLowerCase().includes(query))
    ))
  }, [actor, channel, events, level, search])
  const todayEvents = useMemo(() => {
    const now = new Date()
    return events.filter(event => (
      event.timestamp.getFullYear() === now.getFullYear()
      && event.timestamp.getMonth() === now.getMonth()
      && event.timestamp.getDate() === now.getDate()
    ))
  }, [events])
  const todayCounts = {
    changes: todayEvents.filter(event => event.kind === 'user_action').length,
    syncs: todayEvents.filter(event => /sync/i.test(event.action)).length,
    warnings: todayEvents.filter(event => event.level === 'warning').length,
    failures: todayEvents.filter(event => event.level === 'error').length,
  }

  function loadMore() {
    const next = page + 1
    setPage(next)
    void loadPage(next, true)
  }

  function exportEvents() {
    const header = ['Timestamp', 'Action', 'Level', 'Actor', 'Channel', 'Detail']
    const rows = filteredEvents.map(event => [
      event.timestamp.toISOString(),
      formatAction(event.action),
      event.level,
      event.actor,
      eventChannel(event),
      event.detail ?? '',
    ])
    const csv = [header, ...rows].map(row => row.map(csvCell).join(',')).join('\n')
    const href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = href
    link.download = `flowhub-activity-${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(href)
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">Activity</h1>
          <p className="fh-page-subtitle">Business changes and synchronization history.</p>
        </div>
        <button type="button" onClick={exportEvents} disabled={filteredEvents.length === 0} className="fh-button-primary">
          <Icon name="export" />
          Export
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Icon name="search" className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-wp-muted" />
          <input
            type="search"
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder="Search activity..."
            aria-label="Search activity"
            className="fh-input !min-h-[40px] rounded-lg ps-9"
          />
        </div>
        <select value={level} onChange={event => setLevel(event.target.value as ActivityLevel | 'all')} aria-label="Filter by status" className="fh-select w-auto !min-h-[40px] rounded-lg">
          <option value="all">All statuses</option>
          <option value="success">Success</option>
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="error">Error</option>
        </select>
        <select value={channel} onChange={event => setChannel(event.target.value)} aria-label="Filter by channel" className="fh-select w-auto !min-h-[40px] rounded-lg">
          <option value="all">All channels</option>
          {channels.map(value => <option key={value} value={value}>{value}</option>)}
        </select>
        <select value={actor} onChange={event => setActor(event.target.value)} aria-label="Filter by user" className="fh-select w-auto !min-h-[40px] rounded-lg">
          <option value="all">All users</option>
          {actors.map(value => <option key={value} value={value}>{value}</option>)}
        </select>
        <button type="button" className="fh-button-secondary !min-h-[40px]" onClick={() => { setSearch(''); setLevel('all'); setChannel('all'); setActor('all') }}>
          <Icon name="filter" />
          Clear
        </button>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="fh-card overflow-hidden">
          <div className="fh-panel-header">
            <div>
              <p className="fh-section-title">Today</p>
              <p className="fh-text-caption mt-1">
                {loading ? 'Loading activity...' : `${filteredEvents.length} visible event${filteredEvents.length === 1 ? '' : 's'}${total > events.length ? ` of ${total}` : ''}`}
              </p>
            </div>
          </div>
          {loading ? (
            <div className="flex flex-col gap-3 p-5">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : filteredEvents.length === 0 ? (
            <Empty title="No activity found" description="Try adjusting the search or filters." />
          ) : (
            filteredEvents.map(event => <EventRow key={event.id} event={event} />)
          )}
          {!loading && events.length < total && (
            <div className="fh-panel-footer">
              <button type="button" onClick={loadMore} disabled={loadingMore} className="fh-button-secondary w-full">
                <Icon name="download" />
                {loadingMore ? 'Loading...' : `Load more (${total - events.length} remaining)`}
              </button>
            </div>
          )}
        </div>

        <aside className="fh-card h-fit">
          <div className="fh-panel-header">
            <div>
              <p className="fh-section-title">Today&apos;s summary</p>
              <p className="fh-text-caption mt-1">{todayEvents.length} recorded events</p>
            </div>
          </div>
          <div className="fh-panel-body space-y-4">
            {[
              ['Business changes', todayCounts.changes],
              ['Synchronizations', todayCounts.syncs],
              ['Warnings', todayCounts.warnings],
              ['Audit failures', todayCounts.failures],
            ].map(([label, value]) => (
              <div key={String(label)} className="flex items-center justify-between gap-3">
                <span className="fh-text-body text-wp-muted">{label}</span>
                <span className="fh-text-body font-semibold text-text-base">{value}</span>
              </div>
            ))}
            <div className={['fh-alert mt-2', todayCounts.failures > 0 ? 'fh-alert-danger' : 'fh-alert-success'].join(' ')}>
              <Icon name={todayCounts.failures > 0 ? 'error' : 'success'} />
              <span>{todayCounts.failures > 0 ? `${todayCounts.failures} unresolved audit failure${todayCounts.failures === 1 ? '' : 's'}` : 'No unresolved audit failures'}</span>
            </div>
          </div>
        </aside>
      </div>
    </PageShell>
  )
}
