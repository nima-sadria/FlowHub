import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useAuth } from '../auth'
import { apiFetch } from '../api/client'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import Icon, { type IconName } from '../components/Icon'
import { SkeletonCard } from '../components/loading/Skeleton'
import PageShell from '../components/PageShell'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { translate } from '../i18n'
import { formatRelativeTime } from '../i18n/format'
import { inputHint } from '../utils/inputHint'
import { useServices } from '../services/ServiceContext'
import type { ActivityEvent, ActivityLevel, BusinessEventLifecycleTransition } from '../services/types'
import type { BusinessEventLifecycleResult } from '../services/businessEvents/BusinessEventService'

const LEVEL_STYLES: Record<ActivityLevel, {
  variant: 'info' | 'success' | 'warning' | 'danger'
  icon: IconName
  labelKey: string
}> = {
  critical: { variant: 'danger', icon: 'error', labelKey: 'activity:activity.critical' },
  error: { variant: 'danger', icon: 'error', labelKey: 'activity:activity.error' },
  warning: { variant: 'warning', icon: 'warning', labelKey: 'activity:activity.warning' },
  success: { variant: 'success', icon: 'success', labelKey: 'activity:activity.success' },
  info: { variant: 'info', icon: 'info', labelKey: 'activity:activity.info' },
  debug: { variant: 'info', icon: 'diagnostics', labelKey: 'activity:activity.debug' },
}

const CATEGORY_ICON: Partial<Record<string, IconName>> = {
  products: 'products',
  orders: 'orders',
  sources: 'sources',
  channels: 'channels',
  users: 'user',
}

const CATEGORIES = [
  'authentication', 'users', 'sources', 'channels', 'products', 'workspace',
  'pricing', 'review', 'dry_run', 'apply', 'orders', 'diagnostics', 'security', 'system',
] as const

interface ActivityFilters {
  search: string
  username: string
  category: string
  severity: string
  dateFrom: string
  dateTo: string
  source: string
  channel: string
  includeDebug: boolean
}

interface ManagedUserSummary {
  username: string
}

interface UserListResponse {
  items: ManagedUserSummary[]
  total: number
}

interface TodayCategoryCounts {
  products: number | null
  orders: number | null
  sources: number | null
  users: number | null
}

function actionLabel(action: string): string {
  const fallback = action.replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase())
  return translate(`activity:event.${action}`, { defaultValue: fallback })
}

function categoryLabel(category: string | undefined): string {
  if (!category) return translate('activity:category.system')
  return translate(`activity:category.${category}`, {
    defaultValue: category.replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase()),
  })
}

function eventIcon(event: ActivityEvent): IconName {
  return CATEGORY_ICON[event.category ?? ''] ?? LEVEL_STYLES[event.level]?.icon ?? 'info'
}

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10)
}

function csvCell(value: string): string {
  return `"${value.replace(/"/g, '""')}"`
}

function groupRoutineEvents(events: ActivityEvent[]): ActivityEvent[] {
  const result: ActivityEvent[] = []
  const grouped = new Map<string, ActivityEvent>()
  for (const event of events) {
    if (event.action !== 'token_refreshed') {
      result.push(event)
      continue
    }
    const key = `${event.actor}:${event.action}`
    const existing = grouped.get(key)
    if (existing) {
      existing.repeatCount = (existing.repeatCount ?? 1) + 1
      continue
    }
    const groupedEvent = { ...event, repeatCount: 1 }
    grouped.set(key, groupedEvent)
    result.push(groupedEvent)
  }
  return result
}

const BUSINESS_EVENT_STATUS_VARIANT: Record<string, 'warning' | 'info' | 'success'> = {
  open: 'warning',
  acknowledged: 'info',
  resolved: 'success',
}

function statusLabel(status: string): string {
  return translate(`activity:activity.status${status.charAt(0).toUpperCase()}${status.slice(1)}`)
}

function BusinessEventLifecycle({ event, onLifecycleChange }: {
  event: ActivityEvent
  onLifecycleChange: (eventId: string, result: BusinessEventLifecycleResult) => void
}) {
  const { businessEvents } = useServices()
  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState<BusinessEventLifecycleTransition[] | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState(false)

  const eventId = event.businessEventId
  if (!eventId || !businessEvents) return null

  async function toggleHistory() {
    const next = !historyOpen
    setHistoryOpen(next)
    if (next && history === null) {
      setHistoryLoading(true)
      try {
        setHistory(await businessEvents!.getLifecycle(eventId!))
      } catch {
        setHistory([])
      } finally {
        setHistoryLoading(false)
      }
    }
  }

  async function runAction(action: (id: string, note?: string) => Promise<BusinessEventLifecycleResult>) {
    setActionLoading(true)
    setActionError(false)
    try {
      const result = await action(eventId!)
      onLifecycleChange(eventId!, result)
      setHistory(null)
      if (historyOpen) setHistoryOpen(false)
    } catch {
      setActionError(true)
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <div className="mt-2">
      <div className="flex flex-wrap items-center gap-2">
        {event.status === 'open' && (
          <button
            type="button"
            className="fh-button-secondary fh-button-sm"
            disabled={actionLoading}
            onClick={() => void runAction((id, note) => businessEvents!.acknowledge(id, note))}
          >
            {translate('activity:activity.acknowledge')}
          </button>
        )}
        {(event.status === 'open' || event.status === 'acknowledged') && (
          <button
            type="button"
            className="fh-button-secondary fh-button-sm"
            disabled={actionLoading}
            onClick={() => void runAction((id, note) => businessEvents!.resolve(id, note))}
          >
            {translate('activity:activity.resolve')}
          </button>
        )}
        <button type="button" className="fh-text-caption font-medium underline" onClick={() => void toggleHistory()}>
          {translate('activity:activity.viewHistory')}
        </button>
      </div>
      {actionError && <p className="fh-text-caption mt-1 text-(--fh-error-500)">{translate('activity:activity.lifecycleActionFailed')}</p>}
      {historyOpen && (
        <div className="mt-2 rounded bg-bg-subtle p-2">
          {historyLoading ? (
            <p className="fh-text-caption">{translate('activity:activity.loading')}</p>
          ) : !history || history.length === 0 ? (
            <p className="fh-text-caption">{translate('activity:activity.noLifecycleHistory')}</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {history.map(transition => (
                <li key={transition.id} className="fh-text-caption">
                  {statusLabel(transition.toStatus)} — {transition.actor} · {formatRelativeTime(transition.occurredAt)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function EventRow({ event, onLifecycleChange }: {
  event: ActivityEvent
  onLifecycleChange: (eventId: string, result: BusinessEventLifecycleResult) => void
}) {
  const isBusinessEvent = event.kind === 'business_event'
  return (
    <article className="flex items-start gap-3 border-b border-border py-3 last:border-0">
      <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-bg-subtle" aria-hidden="true">
        <Icon name={eventIcon(event)} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="fh-text-body font-medium text-text-base">
          {actionLabel(event.action)}
          {(event.repeatCount ?? 1) > 1 && ` — ${event.repeatCount}`}
        </p>
        <p className="fh-text-caption truncate">{event.actor}</p>
        {event.repeatCount && event.repeatCount > 1 && <p className="fh-text-caption mt-1">{translate('activity:activity.groupedRoutineSummary', { count: event.repeatCount })}</p>}
        {isBusinessEvent && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {event.status && (
              <Badge dot variant={BUSINESS_EVENT_STATUS_VARIANT[event.status] ?? 'neutral'}>
                {statusLabel(event.status)}
              </Badge>
            )}
            {event.actionUrl && (
              <a className="fh-text-caption font-medium text-primary underline" href={event.actionUrl}>
                {translate('activity:activity.openScreen')}
              </a>
            )}
          </div>
        )}
        {isBusinessEvent && event.recommendedAction && (
          <p className="fh-text-caption mt-1">
            <span className="font-medium">{translate('activity:activity.recommendedAction')}: </span>
            {event.recommendedAction}
          </p>
        )}
        {isBusinessEvent && <BusinessEventLifecycle event={event} onLifecycleChange={onLifecycleChange} />}
        {event.detail && <details className="mt-2"><summary className="cursor-pointer fh-text-caption">{translate('activity:activity.technicalDetails')}</summary><p className="mt-2 break-all rounded bg-bg-subtle p-2 text-xs" dir="ltr">{event.detail}</p></details>}
      </div>
      <time className="fh-text-caption shrink-0 whitespace-nowrap" dateTime={event.timestamp.toISOString()}>
        {formatRelativeTime(event.timestamp)}
      </time>
    </article>
  )
}

export default function Activity() {
  const { activity, commerce } = useServices()
  const { authFetch } = useAuth()
  const [searchParams] = useSearchParams()
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [channels, setChannels] = useState<Array<{ id: string; name: string }>>([])
  const [knownUsers, setKnownUsers] = useState<string[]>([])
  const [todayCounts, setTodayCounts] = useState<TodayCategoryCounts>({ products: null, orders: null, sources: null, users: null })
  const [filters, setFilters] = useState<ActivityFilters>({
    search: '',
    username: searchParams.get('user') ?? '',
    category: '',
    severity: '',
    dateFrom: '',
    dateTo: '',
    source: searchParams.get('source') ?? '',
    channel: searchParams.get('channel') ?? '',
    includeDebug: false,
  })
  const PAGE_SIZE = 30

  const loadPage = useCallback(async (requestedPage: number, append: boolean) => {
    if (requestedPage === 1) setLoading(true)
    else setLoadingMore(true)
    setLoadError(false)
    try {
      const result = await activity.getEvents({
        page: requestedPage,
        pageSize: PAGE_SIZE,
        search: filters.search.trim() || undefined,
        username: filters.username.trim() || undefined,
        category: filters.category || undefined,
        severity: filters.severity || undefined,
        dateFrom: filters.dateFrom || undefined,
        dateTo: filters.dateTo || undefined,
        source: filters.source.trim() || undefined,
        channel: filters.channel.trim() || undefined,
        includeDebug: filters.includeDebug,
      })
      setEvents(previous => append ? [...previous, ...result.items] : result.items)
      setTotal(result.total)
      setPage(requestedPage)
    } catch {
      setLoadError(true)
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }, [activity, filters])

  useEffect(() => {
    setPage(1)
    void loadPage(1, false)
  }, [loadPage])

  useEffect(() => {
    let active = true
    commerce.getChannels()
      .then(result => {
        if (active) setChannels(result.items.map(item => ({
          id: item.id,
          name: formatChannelDisplayName(item.id, {
            displayName: item.display_name_custom ? item.name : undefined,
            displayNameCustom: item.display_name_custom,
          }),
        })))
      })
      .catch(() => {})
    return () => { active = false }
  }, [commerce])

  useEffect(() => {
    let active = true
    apiFetch<UserListResponse>('/api/v2/users', authFetch)
      .then(result => { if (active) setKnownUsers(result.items.map(item => item.username)) })
      .catch(() => {})
    return () => { active = false }
  }, [authFetch])

  useEffect(() => {
    let active = true
    const today = todayIsoDate()
    const opts = (category: string) => ({ page: 1, pageSize: 1, dateFrom: today, dateTo: today, category })
    Promise.allSettled([
      activity.getEvents(opts('products')),
      activity.getEvents(opts('orders')),
      activity.getEvents(opts('sources')),
      activity.getEvents(opts('users')),
    ]).then(([products, orders, sources, users]) => {
      if (!active) return
      setTodayCounts({
        products: products.status === 'fulfilled' ? products.value.total : null,
        orders: orders.status === 'fulfilled' ? orders.value.total : null,
        sources: sources.status === 'fulfilled' ? sources.value.total : null,
        users: users.status === 'fulfilled' ? users.value.total : null,
      })
    })
    return () => { active = false }
  }, [activity])

  const displayedEvents = useMemo(() => groupRoutineEvents(events), [events])
  const importantEvents = displayedEvents.filter(event => event.action !== 'token_refreshed' && event.level !== 'debug')
  const routineEvents = displayedEvents.filter(event => event.action === 'token_refreshed' || event.level === 'debug')
  const hasMore = events.length < total

  function handleLifecycleChange(eventId: string, result: BusinessEventLifecycleResult) {
    setEvents(previous => previous.map(event => event.businessEventId === eventId
      ? { ...event, status: result.status }
      : event))
  }

  function updateFilter<Key extends keyof ActivityFilters>(key: Key, value: ActivityFilters[Key]) {
    setFilters(current => ({ ...current, [key]: value }))
  }

  function loadMore() {
    const next = page + 1
    void loadPage(next, true)
  }

  function exportCsv() {
    const header = ['Time', 'Status', 'Category', 'Actor', 'Action'].map(csvCell).join(',')
    const rows = displayedEvents.map(event => [
      event.timestamp.toISOString(),
      translate(LEVEL_STYLES[event.level]?.labelKey ?? 'activity:activity.info'),
      categoryLabel(event.category),
      event.actor,
      actionLabel(event.action),
    ].map(csvCell).join(','))
    const blob = new Blob([[header, ...rows].join('\r\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `activity-${todayIsoDate()}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  return <PageShell>
    <div className="fh-page-header">
      <div>
        <h1 className="fh-page-title">{translate('activity:activity.activity')}</h1>
        <p className="fh-page-subtitle">{translate('activity:activity.businessHistoryDescription')}</p>
      </div>
      <button className="fh-button-primary" type="button" disabled={displayedEvents.length === 0} onClick={exportCsv}>
        <Icon name="export" /> {translate('activity:activity.export')}
      </button>
    </div>

    <div className="fh-activity-toolbar">
      <form className="fh-activity-search" onSubmit={event => event.preventDefault()}>
        <Icon name="search" size="sm" className="fh-activity-search-icon" />
        <input
          className="fh-activity-search-input"
          type="search"
          value={filters.search}
          onChange={event => updateFilter('search', event.target.value)}
          {...inputHint(translate('activity:activity.search'))}
          aria-label={translate('activity:activity.search')}
        />
      </form>
      <label className="fh-chip-select">
        <span className="sr-only">{translate('activity:activity.allStatuses')}</span>
        <select value={filters.severity} onChange={event => updateFilter('severity', event.target.value)}>
          <option value="">{translate('activity:activity.allStatuses')}</option>
          {(['critical', 'error', 'warning', 'success', 'info', 'debug'] as const).map(level => <option key={level} value={level}>{translate(LEVEL_STYLES[level].labelKey)}</option>)}
        </select>
        <Icon name="chevronDown" size="sm" className="fh-chip-caret" />
      </label>
      <label className="fh-chip-select">
        <span className="sr-only">{translate('activity:activity.allChannels')}</span>
        <select value={filters.channel} onChange={event => updateFilter('channel', event.target.value)}>
          <option value="">{translate('activity:activity.allChannels')}</option>
          {channels.map(channel => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
        </select>
        <Icon name="chevronDown" size="sm" className="fh-chip-caret" />
      </label>
      <label className="fh-chip-select">
        <span className="sr-only">{translate('activity:activity.allUsers')}</span>
        <select value={filters.username} onChange={event => updateFilter('username', event.target.value)}>
          <option value="">{translate('activity:activity.allUsers')}</option>
          {knownUsers.map(username => <option key={username} value={username}>{username}</option>)}
        </select>
        <Icon name="chevronDown" size="sm" className="fh-chip-caret" />
      </label>
      <details className="fh-activity-filters ms-auto">
        <summary className="fh-button-secondary fh-button-sm cursor-pointer list-none"><Icon name="filter" size="sm" /> {translate('activity:activity.filters')}</summary>
        <div className="fh-activity-filters-panel">
          <label className="fh-field-label">{translate('activity:activity.category')}<select className="fh-input mt-1" value={filters.category} onChange={event => updateFilter('category', event.target.value)}><option value="">{translate('activity:activity.allCategories')}</option>{CATEGORIES.map(category => <option key={category} value={category}>{categoryLabel(category)}</option>)}</select></label>
          <label className="fh-field-label">{translate('activity:activity.fromDate')}<input className="fh-input mt-1" type="date" value={filters.dateFrom} onChange={event => updateFilter('dateFrom', event.target.value)} /></label>
          <label className="fh-field-label">{translate('activity:activity.toDate')}<input className="fh-input mt-1" type="date" value={filters.dateTo} onChange={event => updateFilter('dateTo', event.target.value)} /></label>
          <label className="fh-field-label">{translate('activity:activity.source')}<input className="fh-input mt-1" value={filters.source} onChange={event => updateFilter('source', event.target.value)} /></label>
          <label className="fh-inline-check"><input type="checkbox" checked={filters.includeDebug} onChange={event => updateFilter('includeDebug', event.target.checked)} />{translate('activity:activity.showRoutineSystemEvents')}</label>
        </div>
      </details>
    </div>

    {loadError && (
      <div className="fh-alert fh-alert-danger mb-4" role="alert">
        <Icon name="error" />
        <span className="flex-1">{translate('activity:activity.loadFailed')}</span>
        <button type="button" className="fh-button-secondary fh-button-sm" onClick={() => void loadPage(1, false)}>
          {translate('common:action.retry')}
        </button>
      </div>
    )}

    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div className="fh-card">
        <div className="fh-panel-header">
          <span className="fh-section-title">{translate('activity:activity.today')}</span>
          {loading ? <span className="fh-text-caption">{translate('activity:activity.loading')}</span> : <Badge dot variant="info">{translate('activity:activity.events', { value1: total })}</Badge>}
        </div>
        <div className="fh-panel-body !pt-0">
          {loading ? <div className="flex flex-col gap-3 py-4"><SkeletonCard /><SkeletonCard /></div>
            : displayedEvents.length === 0 ? <Empty title={translate('activity:activity.noActivityYet')} description={translate('activity:activity.eventsWillAppearHereAsTheSystem')} />
              : <>
                {importantEvents.length > 0 && <section>{importantEvents.map(event => <EventRow key={event.id} event={event} onLifecycleChange={handleLifecycleChange} />)}</section>}
                {routineEvents.length > 0 && <details className="mt-3"><summary className="cursor-pointer fh-section-title">{translate('activity:activity.routineSystemActivity')} ({routineEvents.length})</summary>{routineEvents.map(event => <EventRow key={event.id} event={event} onLifecycleChange={handleLifecycleChange} />)}</details>}
              </>}
        </div>
        {!loading && hasMore && <div className="fh-panel-footer !justify-start"><button onClick={loadMore} disabled={loadingMore} className="fh-button-secondary w-full"><Icon name="download" />{loadingMore ? translate('activity:activity.loading') : translate('activity:activity.loadMoreRemaining', { value1: total - events.length })}</button></div>}
      </div>

      <div className="fh-card fh-card-pad">
        <h2 className="fh-section-title mb-4">{translate('activity:activity.today')}</h2>
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3"><span className="text-text-base">{translate('activity:activity.productChanges')}</span><Badge dot variant="info">{todayCounts.products ?? '—'}</Badge></div>
          <div className="flex items-center justify-between gap-3"><span className="text-text-base">{translate('activity:activity.orderSyncs')}</span><Badge dot variant="success">{todayCounts.orders ?? '—'}</Badge></div>
          <div className="flex items-center justify-between gap-3"><span className="text-text-base">{translate('activity:activity.sourceRefreshes')}</span><Badge dot variant="success">{todayCounts.sources ?? '—'}</Badge></div>
          <div className="flex items-center justify-between gap-3"><span className="text-text-base">{translate('activity:activity.permissionChanges')}</span><Badge dot variant="warning">{todayCounts.users ?? '—'}</Badge></div>
        </div>
      </div>
    </div>
  </PageShell>
}
