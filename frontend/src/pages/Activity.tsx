import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import Icon, { type IconName } from '../components/Icon'
import { SkeletonCard } from '../components/loading/Skeleton'
import PageShell from '../components/PageShell'
import { translate } from '../i18n'
import { formatRelativeTime } from '../i18n/format'
import { useServices } from '../services/ServiceContext'
import type { ActivityEvent, ActivityLevel } from '../services/types'

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

function EventRow({ event }: { event: ActivityEvent }) {
  const styles = LEVEL_STYLES[event.level] ?? LEVEL_STYLES.info
  return (
    <article className="border-b border-border py-3 last:border-0">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-bg-subtle" aria-hidden="true">
          <Icon name={styles.icon} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="fh-text-body font-medium text-text-base">
              {actionLabel(event.action)}
              {(event.repeatCount ?? 1) > 1 && ` — ${event.repeatCount}`}
            </span>
            <Badge variant={styles.variant}>{translate(styles.labelKey)}</Badge>
            <Badge variant="info">{categoryLabel(event.category)}</Badge>
            {event.kind === 'user_action' && <span className="fh-text-caption">{translate('activity:activity.by')} {event.actor}</span>}
          </div>
          {event.repeatCount && event.repeatCount > 1 && <p className="fh-text-caption mt-1">{translate('activity:activity.groupedRoutineSummary', { count: event.repeatCount })}</p>}
          {event.detail && <details className="mt-2"><summary className="cursor-pointer fh-text-caption">{translate('activity:activity.technicalDetails')}</summary><p className="mt-2 break-all rounded bg-bg-subtle p-2 text-xs" dir="ltr">{event.detail}</p></details>}
        </div>
        <time className="fh-text-caption shrink-0 whitespace-nowrap" dateTime={event.timestamp.toISOString()}>
          {formatRelativeTime(event.timestamp)}
        </time>
      </div>
    </article>
  )
}

export default function Activity() {
  const { activity } = useServices()
  const [searchParams] = useSearchParams()
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [filters, setFilters] = useState<ActivityFilters>({
    search: '',
    username: searchParams.get('user') ?? '',
    category: '',
    severity: '',
    dateFrom: '',
    dateTo: '',
    source: '',
    channel: '',
    includeDebug: false,
  })
  const PAGE_SIZE = 30

  const loadPage = useCallback(async (requestedPage: number, append: boolean) => {
    if (requestedPage === 1) setLoading(true)
    else setLoadingMore(true)
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
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }, [activity, filters])

  useEffect(() => {
    setPage(1)
    void loadPage(1, false)
  }, [loadPage])

  const displayedEvents = useMemo(() => groupRoutineEvents(events), [events])
  const importantEvents = displayedEvents.filter(event => event.action !== 'token_refreshed' && event.level !== 'debug')
  const routineEvents = displayedEvents.filter(event => event.action === 'token_refreshed' || event.level === 'debug')
  const hasMore = events.length < total

  function updateFilter<Key extends keyof ActivityFilters>(key: Key, value: ActivityFilters[Key]) {
    setFilters(current => ({ ...current, [key]: value }))
  }

  function loadMore() {
    const next = page + 1
    setPage(next)
    void loadPage(next, true)
  }

  return <PageShell>
    <div className="fh-page-header">
      <div>
        <h1 className="fh-page-title">{translate('activity:activity.activity')}</h1>
        <p className="fh-page-subtitle">{translate('activity:activity.businessHistoryDescription')}</p>
      </div>
    </div>

    <details className="fh-card fh-card-pad mb-4">
      <summary className="flex cursor-pointer items-center gap-2 font-medium text-text-base"><Icon name="filter" /> {translate('activity:activity.filters')}</summary>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="fh-field-label">{translate('activity:activity.search')}<input className="fh-input mt-1" type="search" value={filters.search} onChange={event => updateFilter('search', event.target.value)} /></label>
        <label className="fh-field-label">{translate('activity:activity.user')}<input className="fh-input mt-1" value={filters.username} onChange={event => updateFilter('username', event.target.value)} /></label>
        <label className="fh-field-label">{translate('activity:activity.category')}<select className="fh-input mt-1" value={filters.category} onChange={event => updateFilter('category', event.target.value)}><option value="">{translate('activity:activity.allCategories')}</option>{CATEGORIES.map(category => <option key={category} value={category}>{categoryLabel(category)}</option>)}</select></label>
        <label className="fh-field-label">{translate('activity:activity.severity')}<select className="fh-input mt-1" value={filters.severity} onChange={event => updateFilter('severity', event.target.value)}><option value="">{translate('activity:activity.allSeverities')}</option>{(['critical', 'error', 'warning', 'success', 'info', 'debug'] as const).map(level => <option key={level} value={level}>{translate(LEVEL_STYLES[level].labelKey)}</option>)}</select></label>
        <label className="fh-field-label">{translate('activity:activity.fromDate')}<input className="fh-input mt-1" type="date" value={filters.dateFrom} onChange={event => updateFilter('dateFrom', event.target.value)} /></label>
        <label className="fh-field-label">{translate('activity:activity.toDate')}<input className="fh-input mt-1" type="date" value={filters.dateTo} onChange={event => updateFilter('dateTo', event.target.value)} /></label>
        <label className="fh-field-label">{translate('activity:activity.source')}<input className="fh-input mt-1" value={filters.source} onChange={event => updateFilter('source', event.target.value)} /></label>
        <label className="fh-field-label">{translate('activity:activity.channel')}<input className="fh-input mt-1" value={filters.channel} onChange={event => updateFilter('channel', event.target.value)} /></label>
        <label className="fh-inline-check"><input type="checkbox" checked={filters.includeDebug} onChange={event => updateFilter('includeDebug', event.target.checked)} />{translate('activity:activity.showRoutineSystemEvents')}</label>
      </div>
    </details>

    <div className="fh-card">
      <div className="fh-panel-header"><span className="fh-section-title">{loading ? translate('activity:activity.loading') : translate('activity:activity.events', { value1: total })}</span></div>
      <div className="fh-panel-body !pt-0">
        {loading ? <div className="flex flex-col gap-3 py-4"><SkeletonCard /><SkeletonCard /></div>
          : displayedEvents.length === 0 ? <Empty title={translate('activity:activity.noActivityYet')} description={translate('activity:activity.eventsWillAppearHereAsTheSystem')} />
            : <>
              {importantEvents.length > 0 && <section aria-labelledby="important-activity"><h2 className="fh-section-title py-3" id="important-activity">{translate('activity:activity.importantActivity')}</h2>{importantEvents.map(event => <EventRow key={event.id} event={event} />)}</section>}
              {routineEvents.length > 0 && <details className="mt-3"><summary className="cursor-pointer fh-section-title">{translate('activity:activity.routineSystemActivity')} ({routineEvents.length})</summary>{routineEvents.map(event => <EventRow key={event.id} event={event} />)}</details>}
            </>}
      </div>
      {!loading && hasMore && <div className="fh-panel-footer !justify-start"><button onClick={loadMore} disabled={loadingMore} className="fh-button-secondary w-full"><Icon name="download" />{loadingMore ? translate('activity:activity.loading') : translate('activity:activity.loadMoreRemaining', { value1: total - events.length })}</button></div>}
    </div>
  </PageShell>
}
