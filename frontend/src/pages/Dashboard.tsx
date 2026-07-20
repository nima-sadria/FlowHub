import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../api/client'
import { useAuth } from '../auth'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import KpiCard from '../components/KpiCard'
import LocalizedText from '../components/LocalizedText'
import { SkeletonCard } from '../components/loading/Skeleton'
import PageShell from '../components/PageShell'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { translate } from '../i18n'
import { formatDiagnosticMessage, formatStatus } from '../i18n/display'
import { formatNumber, formatRelativeTime } from '../i18n/format'
import { useServices } from '../services/ServiceContext'
import type {
  ActivityEvent,
  ChannelHealthResponse,
  ChannelOrderListItem,
  Source,
} from '../services/types'
import { formatMoney } from '../utils/price'

// Figma: Screen/Dashboard (159:12911) — seller-first overview built from
// live services plus the persisted business-summary endpoint.

const CARD = 'rounded-lg border border-border bg-bg-card'
const EXCLUDED_ORDER_STATUSES = new Set(['cancelled', 'canceled', 'refunded', 'failed'])

interface RevenueAmount {
  currency: string
  amount: number
}

interface DashboardBusinessMetrics {
  productsWithChanges: number
  readyForReview: number
  readyForApply: number
  blockingIssues: number
  warnings: number
  affectedProducts: number
  outOfStockProducts: number
  pendingUpdates: number
  failedUpdates: number
  ordersToday: number
  ordersYesterday: number
  updatesAppliedToday: number
  updatesAppliedYesterday: number
  revenueToday: RevenueAmount[]
}

interface DashboardBusinessSummary {
  generatedAt: string
  metrics: DashboardBusinessMetrics
}

function relTime(date: Date | null): string {
  return date ? formatRelativeTime(date) : translate('common:status.notRead')
}

function formatAction(action: string): string {
  return action.replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase())
}

function isToday(iso: string | null): boolean {
  if (!iso) return false
  const date = new Date(iso)
  const now = new Date()
  return date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate()
}

function comparisonWithYesterday(today: number, yesterday: number): string {
  const difference = today - yesterday
  if (difference === 0) return translate('dashboard:dashboard.noChangeSinceYesterday')
  if (difference > 0) {
    return translate('dashboard:dashboard.moreThanYesterday', {
      count: difference,
      value: formatNumber(difference),
    })
  }
  return translate('dashboard:dashboard.fewerThanYesterday', {
    count: Math.abs(difference),
    value: formatNumber(Math.abs(difference)),
  })
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className={[CARD, 'flex h-[300px] flex-col gap-4 p-[18px]'].join(' ')}>
      <div className="flex items-center">
        <p className="text-[15px] font-semibold leading-5 text-text-base">{title}</p>
        <span className="ms-auto text-xs text-[color:var(--fh-text-secondary)]">
          {translate('dashboard:dashboard.last30Days')}
        </span>
      </div>
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center">
        {children}
      </div>
    </div>
  )
}

function RevenueLineChart({ points }: { points: Array<{ day: string; total: number }> }) {
  const width = 440
  const height = 150
  const max = Math.max(...points.map(point => point.total), 1)
  const step = points.length > 1 ? width / (points.length - 1) : width
  const path = points
    .map((point, index) => {
      const x = points.length > 1 ? index * step : width / 2
      const y = height - 10 - (point.total / max) * (height - 30)
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-[150px] w-full max-w-[440px]"
      role="img"
      aria-label={translate('dashboard:dashboard.revenueTrend')}
    >
      <line x1="0" y1="12" x2={width} y2="12" stroke="var(--fh-ui-border)" strokeWidth="3" />
      <path d={path} fill="none" stroke="var(--color-accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function OrdersBarChart({ bars }: { bars: Array<{ channel: string; count: number }> }) {
  const max = Math.max(...bars.map(bar => bar.count), 1)
  return (
    <div
      className="flex h-[150px] w-full max-w-[420px] items-end justify-center gap-6"
      role="img"
      aria-label={translate('dashboard:dashboard.ordersByChannel')}
    >
      {bars.map(bar => (
        <div
          key={bar.channel}
          title={`${bar.channel}: ${formatNumber(bar.count)}`}
          className="w-7 rounded bg-accent"
          style={{ height: `${Math.max((bar.count / max) * 150, 6)}px` }}
        />
      ))}
    </div>
  )
}

export default function Dashboard() {
  const { authFetch } = useAuth()
  const { sources, products, activity, health: healthService, orders } = useServices()
  const navigate = useNavigate()

  const [channelHealth, setChannelHealth] = useState<ChannelHealthResponse | null>(null)
  const [sourceList, setSourceList] = useState<Source[]>([])
  const [totalProducts, setTotalProducts] = useState<number | null>(null)
  const [recentEvents, setRecentEvents] = useState<ActivityEvent[]>([])
  const [orderWindow, setOrderWindow] = useState<ChannelOrderListItem[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [businessSummary, setBusinessSummary] = useState<DashboardBusinessSummary | null>(null)
  const [businessLoading, setBusinessLoading] = useState(true)
  const [businessError, setBusinessError] = useState(false)

  const fetchBusinessSummary = useCallback(async () => {
    setBusinessLoading(true)
    setBusinessError(false)
    try {
      setBusinessSummary(await apiFetch<DashboardBusinessSummary>(
        '/api/v2/dashboard/business-summary',
        authFetch,
      ))
    } catch {
      setBusinessSummary(null)
      setBusinessError(true)
    } finally {
      setBusinessLoading(false)
    }
  }, [authFetch])

  useEffect(() => { void fetchBusinessSummary() }, [fetchBusinessSummary])

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([
      healthService.getChannelHealth(),
      sources.getSources(),
      products.getProducts({ search: '', status: 'all', page: 1, pageSize: 1 }),
      activity.getEvents({ page: 1, pageSize: 4 }),
      Promise.resolve().then(() => {
        if (!orders?.getOrders) throw new Error('orders service unavailable')
        return orders.getOrders({ page: 1, pageSize: 50 })
      }),
    ]).then(([healthResult, sourcesResult, productsResult, eventsResult, ordersResult]) => {
      if (cancelled) return
      if (healthResult.status === 'fulfilled') setChannelHealth(healthResult.value)
      if (sourcesResult.status === 'fulfilled') setSourceList(sourcesResult.value)
      if (productsResult.status === 'fulfilled') setTotalProducts(productsResult.value.total)
      if (eventsResult.status === 'fulfilled') setRecentEvents(eventsResult.value.items)
      setOrderWindow(ordersResult.status === 'fulfilled' ? ordersResult.value.items : [])
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [healthService, sources, products, activity, orders])

  const activeSources = sourceList.filter(source => source.status === 'active')
  const lastSync = activeSources.reduce<Date | null>((best, source) => {
    if (!source.lastSynced) return best
    return !best || source.lastSynced > best ? source.lastSynced : best
  }, null)

  const counts = channelHealth?.summary.counts
  const operationalChannels = counts?.Operational ?? 0
  const totalChannels = channelHealth?.items.length ?? 0
  const channelWarnings = counts?.Warning ?? 0
  const channelBlocking = (counts?.Error ?? 0) + (counts?.['Unable to check'] ?? 0)
  const metrics = businessSummary?.metrics

  const countedOrders = useMemo(
    () => (orderWindow ?? []).filter(order => !EXCLUDED_ORDER_STATUSES.has(order.normalizedStatus.toLowerCase())),
    [orderWindow],
  )
  const synchronizedOrdersToday = countedOrders.filter(order => isToday(order.createdAtProvider))
  const ordersToday = metrics?.ordersToday ?? synchronizedOrdersToday.length
  const blockingCount = metrics?.blockingIssues ?? channelBlocking
  const warningCount = metrics?.warnings ?? channelWarnings

  const fallbackRevenueCurrency =
    synchronizedOrdersToday.find(order => order.currency)?.currency
    ?? countedOrders.find(order => order.currency)?.currency
    ?? ''
  const fallbackRevenue = synchronizedOrdersToday.reduce(
    (sum, order) => sum + (order.finalAmount ?? 0),
    0,
  )
  const revenueText = metrics
    ? metrics.revenueToday.map(item => formatMoney(item.amount, { currency: item.currency })).join(' · ')
    : orderWindow === null
      ? translate('common:status.loading')
      : formatMoney(fallbackRevenue, { currency: fallbackRevenueCurrency, empty: '-' })

  const revenueByDay = useMemo(() => {
    const days = new Map<string, number>()
    for (const order of countedOrders) {
      if (!order.createdAtProvider || order.finalAmount === null) continue
      const day = order.createdAtProvider.slice(0, 10)
      days.set(day, (days.get(day) ?? 0) + order.finalAmount)
    }
    return Array.from(days.entries())
      .sort(([left], [right]) => left.localeCompare(right))
      .slice(-30)
      .map(([day, total]) => ({ day, total }))
  }, [countedOrders])

  const ordersByChannel = useMemo(() => {
    const channels = new Map<string, number>()
    for (const order of countedOrders) {
      channels.set(order.channelId, (channels.get(order.channelId) ?? 0) + 1)
    }
    return Array.from(channels.entries())
      .sort(([, left], [, right]) => right - left)
      .slice(0, 8)
      .map(([channel, count]) => ({ channel, count }))
  }, [countedOrders])

  const healthBadge =
    channelBlocking > 0
      ? { variant: 'error' as const, label: translate('dashboard:dashboard.blockingIssues') }
      : channelWarnings > 0
        ? { variant: 'warning' as const, label: translate('dashboard:dashboard.warnings') }
        : { variant: 'success' as const, label: translate('common:status.operational') }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('dashboard:dashboard.dashboard')}</h1>
          <p className="fh-page-subtitle">{translate('dashboard:dashboard.controlCenterSummary')}</p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/workspace')}
          className="fh-button-primary fh-button-sm"
        >
          {translate('dashboard:dashboard.openWorkspace')}
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label={translate('dashboard:dashboard.totalProducts')}
            value={totalProducts !== null ? formatNumber(totalProducts) : '-'}
            icon="products"
          />
          <KpiCard
            label={translate('dashboard:dashboard.ordersAndRevenueToday')}
            value={formatNumber(ordersToday)}
            trend={
              metrics
                ? comparisonWithYesterday(metrics.ordersToday, metrics.ordersYesterday)
                : countedOrders.length > 0
                  ? translate('dashboard:dashboard.ordersValue', {
                    count: countedOrders.length,
                    value: formatNumber(countedOrders.length),
                  })
                  : undefined
            }
            icon="orders"
          />
          <KpiCard
            label={translate('dashboard:dashboard.activeSources')}
            value={formatNumber(activeSources.length)}
            trend={
              sourceList.length > activeSources.length
                ? translate('dashboard:dashboard.configuredSources', { count: sourceList.length })
                : undefined
            }
            icon="sources"
          />
          <KpiCard
            label={translate('dashboard:dashboard.channels')}
            value={totalChannels > 0
              ? translate('dashboard:dashboard.readyChannelValue', {
                ready: formatNumber(operationalChannels),
                total: formatNumber(totalChannels),
              })
              : '-'}
            trend={
              channelBlocking > 0
                ? translate('dashboard:dashboard.channelsNeedAttention', {
                  count: channelBlocking,
                  value: formatNumber(channelBlocking),
                })
                : channelWarnings > 0
                  ? translate('dashboard:dashboard.channelsAwaitingVerification', {
                    count: channelWarnings,
                    value: formatNumber(channelWarnings),
                  })
                  : totalChannels > 0
                    ? translate('common:status.operational')
                    : undefined
            }
            trendTone={channelBlocking > 0 || channelWarnings > 0 ? 'warning' : 'up'}
            icon="channels"
          />
        </div>
      )}

      <div className={[CARD, 'flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2'].join(' ')}>
        <span className="flex items-center gap-1.5">
          <span className="text-[11px] leading-4 text-wp-muted">
            {translate('dashboard:dashboard.revenueToday')}
          </span>
          <span className="text-[13px] font-semibold leading-[22px] text-wp-green">
            {businessLoading
              ? translate('common:status.loading')
              : businessError && !orderWindow
                ? translate('dashboard:dashboard.revenueUnavailable')
                : revenueText || translate('dashboard:dashboard.revenueUnavailable')}
          </span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-[11px] leading-4 text-wp-muted">{translate('dashboard:dashboard.blockingIssues')}</span>
          <span className={['text-[13px] font-semibold leading-[22px]', blockingCount > 0 ? 'text-wp-red' : 'text-text-base'].join(' ')}>
            {formatNumber(blockingCount)}
          </span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-[11px] leading-4 text-wp-muted">{translate('dashboard:dashboard.warnings')}</span>
          <span className={['text-[13px] font-semibold leading-[22px]', warningCount > 0 ? 'text-wp-yellow' : 'text-text-base'].join(' ')}>
            {formatNumber(warningCount)}
          </span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-[11px] leading-4 text-wp-muted">{translate('dashboard:dashboard.sourceFreshness')}</span>
          <span className="text-[13px] font-semibold leading-[22px] text-wp-green">
            {relTime(lastSync)}
          </span>
        </span>
        <span className="ms-auto flex items-center gap-2">
          <span className="text-[11px] font-medium leading-4 text-[color:var(--fh-text-secondary)]">
            {translate('dashboard:dashboard.connections')}
          </span>
          <Badge dot variant="info">
            {translate('dashboard:dashboard.activeSourceValue', {
              count: activeSources.length,
              value: formatNumber(activeSources.length),
            })}
          </Badge>
          <Badge dot variant={healthBadge.variant}>
            {translate('dashboard:dashboard.monitoredDestinations', { count: totalChannels })}
          </Badge>
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <ChartCard title={translate('dashboard:dashboard.revenueTrend')}>
          {orderWindow === null ? (
            <SkeletonCard />
          ) : revenueByDay.length > 1 ? (
            <RevenueLineChart points={revenueByDay} />
          ) : (
            <Empty
              title={translate('dashboard:dashboard.notEnoughOrderData')}
              description={translate('dashboard:dashboard.revenueAppearsAfterSync')}
            />
          )}
        </ChartCard>
        <ChartCard title={translate('dashboard:dashboard.ordersByChannel')}>
          {orderWindow === null ? (
            <SkeletonCard />
          ) : ordersByChannel.length > 0 ? (
            <OrdersBarChart bars={ordersByChannel} />
          ) : (
            <Empty
              title={translate('dashboard:dashboard.noOrdersYet')}
              description={translate('dashboard:dashboard.ordersAppearAfterSync')}
            />
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className={[CARD, 'flex flex-col gap-2 p-3.5'].join(' ')}>
          <div className="flex items-center">
            <p className="text-sm font-semibold leading-[22px] text-text-base">
              {translate('dashboard:dashboard.recentActivity')}
            </p>
            <button
              type="button"
              onClick={() => navigate('/activity')}
              className="ms-auto text-xs font-medium leading-4 text-accent hover:text-accent-hover"
            >
              {translate('dashboard:dashboard.viewAll')}
            </button>
          </div>
          {loading ? (
            <SkeletonCard />
          ) : recentEvents.length === 0 ? (
            <Empty title={translate('dashboard:dashboard.noEventsYet')} />
          ) : (
            recentEvents.map(event => (
              <div key={event.id} className="flex items-center gap-3 rounded-md px-3 py-2.5">
                <span className="inline-flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-[7px] bg-bg-subtle text-[color:var(--fh-text-secondary)]">
                  <Icon name={/order/i.test(event.action) || /order/i.test(event.kind) ? 'orders' : 'products'} size="md" />
                </span>
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="truncate text-[13px] font-medium leading-[18px] text-text-base">
                    {formatAction(event.action)}
                  </span>
                  <span className="truncate text-xs leading-4 text-[color:var(--fh-text-secondary)]">
                    <LocalizedText text={event.detail ?? event.actor} />
                  </span>
                </span>
                <span className="flex-shrink-0 text-xs leading-4 text-wp-muted">
                  {relTime(event.timestamp)}
                </span>
              </div>
            ))
          )}
        </div>

        <div className={[CARD, 'flex flex-col gap-2 p-3.5'].join(' ')}>
          <div className="flex items-center">
            <p className="text-sm font-semibold leading-[22px] text-text-base">
              {translate('dashboard:dashboard.channelReadiness')}
            </p>
            <span className="ms-auto">
              <Badge dot variant={healthBadge.variant}>{healthBadge.label}</Badge>
            </span>
          </div>
          {!channelHealth ? (
            loading
              ? <SkeletonCard />
              : <Empty title={translate('dashboard:dashboard.channelHealthUnavailable')} />
          ) : channelHealth.items.length === 0 ? (
            <Empty title={translate('dashboard:dashboard.noChannelsMonitored')} />
          ) : (
            channelHealth.items.slice(0, 4).map(channel => (
              <button
                key={channel.channelId}
                type="button"
                onClick={() => navigate('/diagnostics')}
                className="flex items-center gap-2.5 rounded-md px-3 py-2.5 text-start hover:bg-bg-subtle"
              >
                <span
                  className={[
                    'inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md',
                    channel.status === 'Operational'
                      ? 'bg-[color:var(--fh-success-surface)] text-wp-green'
                      : channel.status === 'Error'
                        ? 'bg-[color:var(--fh-danger-surface)] text-wp-red'
                        : 'bg-[color:var(--fh-warning-surface)] text-wp-yellow',
                  ].join(' ')}
                >
                  <Icon name="channels" size="sm" />
                </span>
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="truncate text-[13px] font-medium leading-[18px] text-text-base">
                    {formatChannelDisplayName(channel.channelId || `${channel.channelType}:primary`)}
                  </span>
                  <span className="truncate text-xs leading-4 text-[color:var(--fh-text-secondary)]">
                    {formatDiagnosticMessage(channel.summary)}
                  </span>
                </span>
                <Badge
                  className="flex-shrink-0"
                  variant={channel.status === 'Operational' ? 'success' : channel.status === 'Error' ? 'error' : 'warning'}
                >
                  {formatStatus(channel.status)}
                </Badge>
                <Icon name="next" size="sm" mirrorRtl className="flex-shrink-0 text-wp-muted" />
              </button>
            ))
          )}
        </div>
      </div>
    </PageShell>
  )
}
