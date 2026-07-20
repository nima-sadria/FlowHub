import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../api/client'
import { useAuth } from '../auth'
import Badge from '../components/Badge'
import BrandIcon from '../components/BrandIcon'
import BusinessCard, { type BusinessCardTone } from '../components/BusinessCard'
import Empty from '../components/Empty'
import Icon, { type IconName } from '../components/Icon'
import KpiCard from '../components/KpiCard'
import LocalizedText from '../components/LocalizedText'
import { SkeletonCard } from '../components/loading/Skeleton'
import PageShell from '../components/PageShell'
import { ResourceSectionList, ResourceStateBadge } from '../components/ResourceOrdering'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import {
  diagnosticChannelSignals,
  legacySourceSignals,
  prepareResourceCollection,
} from '../features/resourceOrdering/resourceOrdering'
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

interface DashboardCardModel {
  value: string
  explanation: string
  status: {
    label: string
    tone: BusinessCardTone
    icon: IconName
  }
  recommendation: string
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
          {translate('dashboard:dashboard.loadedOrders')}
        </span>
      </div>
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center">
        {children}
      </div>
    </div>
  )
}

interface RevenueSeries {
  currency: string
  points: Array<{ day: string; total: number }>
}

const REVENUE_SERIES_COLORS = [
  'var(--color-accent)',
  'var(--fh-warning-500)',
  'var(--fh-success-500)',
  'var(--fh-error-500)',
]

function RevenueLineChart({ series }: { series: RevenueSeries[] }) {
  const width = 440
  const height = 150
  const max = Math.max(...series.flatMap(item => item.points.map(point => point.total)), 1)
  return (
    <div className="flex w-full flex-col items-center gap-2">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="h-[130px] w-full max-w-[440px]"
        role="img"
        aria-label={translate('dashboard:dashboard.revenueTrend')}
      >
        <line x1="0" y1="12" x2={width} y2="12" stroke="var(--fh-ui-border)" strokeWidth="3" />
        {series.map((item, seriesIndex) => {
          const step = item.points.length > 1 ? width / (item.points.length - 1) : width
          const path = item.points.map((point, pointIndex) => {
            const x = item.points.length > 1 ? pointIndex * step : width / 2
            const y = height - 10 - (point.total / max) * (height - 30)
            return `${pointIndex === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
          }).join(' ')
          return (
            <path
              key={item.currency}
              data-revenue-currency={item.currency}
              d={path}
              fill="none"
              stroke={REVENUE_SERIES_COLORS[seriesIndex % REVENUE_SERIES_COLORS.length]}
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )
        })}
      </svg>
      <div className="flex flex-wrap justify-center gap-3 text-[11px] text-[color:var(--fh-text-secondary)]">
        {series.map((item, index) => (
          <span key={item.currency} className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full" style={{ background: REVENUE_SERIES_COLORS[index % REVENUE_SERIES_COLORS.length] }} />
            {item.currency}
          </span>
        ))}
      </div>
    </div>
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
          title={`${formatChannelDisplayName(bar.channel)}: ${formatNumber(bar.count)}`}
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
      Promise.resolve().then(() => {
        if (!products?.getProducts) throw new Error('products service unavailable')
        return products.getProducts({ search: '', status: 'all', page: 1, pageSize: 1 })
      }),
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

  const orderedSources = useMemo(
    () => prepareResourceCollection(sourceList, legacySourceSignals),
    [sourceList],
  )
  const orderedChannels = useMemo(
    () => prepareResourceCollection(channelHealth?.items ?? [], channel => ({
      ...diagnosticChannelSignals(channel),
      // i18n-ignore -- technical connector identity passed to the display-name formatter.
      displayName: formatChannelDisplayName(channel.channelId || `${channel.channelType}:primary`),
    })),
    [channelHealth],
  )
  const activeSources = sourceList.filter(source => source.status === 'active')
  const lastSync = activeSources.reduce<Date | null>((best, source) => {
    if (!source.lastSynced) return best
    return !best || source.lastSynced > best ? source.lastSynced : best
  }, null)

  const counts = channelHealth?.summary.counts
  const operationalChannels = counts?.Operational ?? 0
  const totalChannels = channelHealth?.items.length ?? 0
  const channelWarnings = counts?.Warning ?? 0
  // i18n-ignore -- backend diagnostic status identifier.
  const channelBlocking = (counts?.Error ?? 0) + (counts?.['Unable to check'] ?? 0)
  const metrics = businessSummary?.metrics
  const recommendationLabel = translate('dashboard:dashboard.recommendedAction')
  const loadingCard: DashboardCardModel = {
    value: translate('common:status.loading'),
    explanation: translate('dashboard:dashboard.loadingBusinessMetrics'),
    status: {
      label: translate('common:status.checking'),
      tone: 'info',
      icon: 'refresh',
    },
    recommendation: translate('dashboard:dashboard.waitForDashboardData'),
  }
  const unavailableCard: DashboardCardModel = {
    value: translate('dashboard:dashboard.businessDataUnavailable'),
    explanation: translate('dashboard:dashboard.businessDataUnavailableExplanation'),
    status: {
      label: translate('dashboard:dashboard.needsAttention'),
      tone: 'warning',
      icon: 'warning',
    },
    recommendation: translate('dashboard:dashboard.retryBusinessSummary'),
  }
  const pendingCard = businessLoading ? loadingCard : businessError || !metrics ? unavailableCard : null
  const countValue = (value: number, emptyKey: string, valueKey: string): string => (
    value > 0
      ? translate(valueKey, { count: value, value: formatNumber(value) })
      : translate(emptyKey)
  )
  const healthyStatus = {
    label: translate('common:status.healthy'),
    tone: 'success' as BusinessCardTone,
    icon: 'success' as IconName,
  }
  const readyStatus = {
    label: translate('common:status.ready'),
    tone: 'success' as BusinessCardTone,
    icon: 'success' as IconName,
  }
  const infoStatus = {
    label: translate('common:status.info'),
    tone: 'info' as BusinessCardTone,
    icon: 'info' as IconName,
  }
  const changesCard: DashboardCardModel = pendingCard ?? {
    value: countValue(metrics!.productsWithChanges, 'dashboard:dashboard.noPriceChanges', 'dashboard:dashboard.productChangesValue'),
    explanation: metrics!.productsWithChanges > 0
      ? translate('dashboard:dashboard.productChangesExplanation', { count: metrics!.productsWithChanges, value: formatNumber(metrics!.productsWithChanges) })
      : translate('dashboard:dashboard.productChangesEmptyExplanation'),
    status: metrics!.productsWithChanges > 0 ? infoStatus : healthyStatus,
    recommendation: metrics!.productsWithChanges > 0
      ? translate('dashboard:dashboard.reviewTodaysPriceChanges')
      : translate('dashboard:dashboard.noActionRequired'),
  }
  const reviewCard: DashboardCardModel = pendingCard ?? {
    value: countValue(metrics!.readyForReview, 'dashboard:dashboard.nothingReadyForReview', 'dashboard:dashboard.productsReadyValue'),
    explanation: metrics!.readyForReview > 0
      ? translate('dashboard:dashboard.readyForReviewExplanation', { count: metrics!.readyForReview, value: formatNumber(metrics!.readyForReview) })
      : translate('dashboard:dashboard.readyForReviewEmptyExplanation'),
    status: metrics!.readyForReview > 0 ? readyStatus : infoStatus,
    recommendation: metrics!.readyForReview > 0
      ? translate('dashboard:dashboard.reviewPendingChanges')
      : translate('dashboard:dashboard.noActionRequired'),
  }
  const applyCard: DashboardCardModel = pendingCard ?? {
    value: countValue(metrics!.readyForApply, 'dashboard:dashboard.nothingReadyForApply', 'dashboard:dashboard.productsReadyValue'),
    explanation: metrics!.readyForApply > 0
      ? translate('dashboard:dashboard.readyForApplyExplanation', { count: metrics!.readyForApply, value: formatNumber(metrics!.readyForApply) })
      : translate('dashboard:dashboard.readyForApplyEmptyExplanation'),
    status: metrics!.readyForApply > 0 ? readyStatus : infoStatus,
    recommendation: metrics!.readyForApply > 0
      ? translate('dashboard:dashboard.applyApprovedChanges')
      : translate('dashboard:dashboard.noActionRequired'),
  }
  const blockingCard: DashboardCardModel = pendingCard ?? {
    value: countValue(metrics!.blockingIssues, 'dashboard:dashboard.noBlockingIssues', 'dashboard:dashboard.issueCountValue'),
    explanation: metrics!.blockingIssues > 0
      ? translate('dashboard:dashboard.blockingIssuesExplanation', {
        count: metrics!.affectedProducts,
        issues: formatNumber(metrics!.blockingIssues),
        products: formatNumber(metrics!.affectedProducts),
      })
      : translate('dashboard:dashboard.blockingIssuesEmptyExplanation'),
    status: metrics!.blockingIssues > 0
      ? { label: translate('common:status.blocked'), tone: 'danger', icon: 'error' }
      : healthyStatus,
    recommendation: metrics!.blockingIssues > 0
      ? translate('dashboard:dashboard.fixBlockingProducts')
      : translate('dashboard:dashboard.noActionRequired'),
  }
  const warningCard: DashboardCardModel = pendingCard ?? {
    value: countValue(metrics!.warnings, 'dashboard:dashboard.noWarnings', 'dashboard:dashboard.issueCountValue'),
    explanation: metrics!.warnings > 0
      ? translate('dashboard:dashboard.warningsExplanation', { count: metrics!.warnings, value: formatNumber(metrics!.warnings) })
      : translate('dashboard:dashboard.warningsEmptyExplanation'),
    status: metrics!.warnings > 0
      ? { label: translate('dashboard:dashboard.needsAttention'), tone: 'warning', icon: 'warning' }
      : healthyStatus,
    recommendation: metrics!.warnings > 0
      ? translate('dashboard:dashboard.reviewWarnings')
      : translate('dashboard:dashboard.noActionRequired'),
  }
  const businessRevenueText = metrics?.revenueToday.map(item => (
    formatMoney(item.amount, { currency: item.currency })
  )).join(' · ') ?? ''
  const ordersCard: DashboardCardModel = pendingCard ?? {
    value: countValue(metrics!.ordersToday, 'dashboard:dashboard.noOrdersToday', 'dashboard:dashboard.ordersValue'),
    explanation: metrics!.ordersToday > 0
      ? translate('dashboard:dashboard.ordersTodayExplanation', {
        revenue: businessRevenueText || translate('dashboard:dashboard.revenueUnavailable'),
        trend: comparisonWithYesterday(metrics!.ordersToday, metrics!.ordersYesterday),
      })
      : translate('dashboard:dashboard.ordersTodayEmptyExplanation'),
    status: metrics!.ordersToday > 0 ? infoStatus : healthyStatus,
    recommendation: metrics!.ordersToday > 0
      ? translate('dashboard:dashboard.reviewTodaysOrders')
      : translate('dashboard:dashboard.noActionRequired'),
  }
  const stockCard: DashboardCardModel = pendingCard ?? {
    value: countValue(metrics!.outOfStockProducts, 'dashboard:dashboard.noInventoryAlerts', 'dashboard:dashboard.productsAffectedValue'),
    explanation: metrics!.outOfStockProducts > 0
      ? translate('dashboard:dashboard.outOfStockExplanation', { count: metrics!.outOfStockProducts, value: formatNumber(metrics!.outOfStockProducts) })
      : translate('dashboard:dashboard.outOfStockEmptyExplanation'),
    status: metrics!.outOfStockProducts > 0
      ? { label: translate('dashboard:dashboard.needsAttention'), tone: 'warning', icon: 'warning' }
      : healthyStatus,
    recommendation: metrics!.outOfStockProducts > 0
      ? translate('dashboard:dashboard.reviewInventoryAlerts')
      : translate('dashboard:dashboard.noActionRequired'),
  }
  const updatesCard: DashboardCardModel = pendingCard ?? {
    value: metrics!.failedUpdates > 0
      ? translate('dashboard:dashboard.failedUpdatesValue', { count: metrics!.failedUpdates, value: formatNumber(metrics!.failedUpdates) })
      : metrics!.pendingUpdates > 0
        ? translate('dashboard:dashboard.pendingUpdatesValue', { count: metrics!.pendingUpdates, value: formatNumber(metrics!.pendingUpdates) })
        : translate('dashboard:dashboard.everythingSynchronized'),
    explanation: metrics!.failedUpdates > 0
      ? translate('dashboard:dashboard.failedUpdatesExplanation', {
        failed: formatNumber(metrics!.failedUpdates),
        pending: formatNumber(metrics!.pendingUpdates),
      })
      : metrics!.pendingUpdates > 0
        ? translate('dashboard:dashboard.pendingUpdatesExplanation', { count: metrics!.pendingUpdates, value: formatNumber(metrics!.pendingUpdates) })
        : translate('dashboard:dashboard.updatesCompleteExplanation', {
          trend: comparisonWithYesterday(metrics!.updatesAppliedToday, metrics!.updatesAppliedYesterday),
        }),
    status: metrics!.failedUpdates > 0
      ? { label: translate('common:status.error'), tone: 'danger', icon: 'error' }
      : metrics!.pendingUpdates > 0
        ? { label: translate('common:status.pending'), tone: 'warning', icon: 'warning' }
        : healthyStatus,
    recommendation: metrics!.failedUpdates > 0
      ? translate('dashboard:dashboard.reviewFailedUpdates')
      : metrics!.pendingUpdates > 0
        ? translate('dashboard:dashboard.monitorPendingUpdates')
        : translate('dashboard:dashboard.noActionRequired'),
  }

  const countedOrders = useMemo(
    () => (orderWindow ?? []).filter(order => !EXCLUDED_ORDER_STATUSES.has(order.normalizedStatus.toLowerCase())),
    [orderWindow],
  )
  const synchronizedOrdersToday = countedOrders.filter(order => isToday(order.createdAtProvider))
  const ordersToday = metrics?.ordersToday ?? synchronizedOrdersToday.length
  const blockingCount = metrics?.blockingIssues ?? channelBlocking
  const warningCount = metrics?.warnings ?? channelWarnings

  const fallbackRevenueByCurrency = synchronizedOrdersToday.reduce((totals, order) => {
    if (!order.currency || order.finalAmount === null) return totals
    totals.set(order.currency, (totals.get(order.currency) ?? 0) + order.finalAmount)
    return totals
  }, new Map<string, number>())
  const fallbackRevenueText = Array.from(fallbackRevenueByCurrency.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([currency, amount]) => formatMoney(amount, { currency }))
    .join(' · ')
  const revenueText = metrics
    ? metrics.revenueToday.map(item => formatMoney(item.amount, { currency: item.currency })).join(' · ')
    : orderWindow === null
      ? translate('common:status.loading')
      : fallbackRevenueText || '-'

  const revenueSeries = useMemo(() => {
    const currencies = new Map<string, Map<string, number>>()
    for (const order of countedOrders) {
      if (!order.createdAtProvider || order.finalAmount === null || !order.currency) continue
      const day = order.createdAtProvider.slice(0, 10)
      const days = currencies.get(order.currency) ?? new Map<string, number>()
      days.set(day, (days.get(day) ?? 0) + order.finalAmount)
      currencies.set(order.currency, days)
    }
    return Array.from(currencies.entries())
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([currency, days]) => ({
        currency,
        points: Array.from(days.entries())
          .sort(([left], [right]) => left.localeCompare(right))
          .slice(-30)
          .map(([day, total]) => ({ day, total })),
      }))
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

      <section aria-labelledby="business-overview-heading">
        <div className="mb-2">
          <h2 id="business-overview-heading" className="fh-section-title">
            {translate('dashboard:dashboard.businessOverview')}
          </h2>
        </div>
        <div className="fh-business-card-grid">
          <BusinessCard
            testId="price-changes"
            title={translate('dashboard:dashboard.productsWithPriceChanges')}
            value={changesCard.value}
            explanation={changesCard.explanation}
            meaning={translate('dashboard:dashboard.productChangesMeaning')}
            icon="edit"
            status={changesCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={changesCard.recommendation}
            action={businessError
              ? { label: translate('common:action.retry'), onClick: () => void fetchBusinessSummary() }
              : { label: translate('dashboard:dashboard.viewProducts'), onClick: () => navigate('/products') }}
          />
          <BusinessCard
            testId="ready-review"
            title={translate('dashboard:dashboard.readyForReview')}
            value={reviewCard.value}
            explanation={reviewCard.explanation}
            meaning={translate('dashboard:dashboard.readyForReviewMeaning')}
            icon="preview"
            status={reviewCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={reviewCard.recommendation}
            action={{ label: translate('dashboard:dashboard.openProducts'), onClick: () => navigate('/products') }}
          />
          <BusinessCard
            testId="ready-apply"
            title={translate('dashboard:dashboard.readyForApply')}
            value={applyCard.value}
            explanation={applyCard.explanation}
            meaning={translate('dashboard:dashboard.readyForApplyMeaning')}
            icon="apply"
            status={applyCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={applyCard.recommendation}
            action={{ label: translate('dashboard:dashboard.openWorkspace'), onClick: () => navigate('/workspace') }}
          />
          <BusinessCard
            testId="blocking"
            title={translate('dashboard:dashboard.blockingIssues')}
            value={blockingCard.value}
            explanation={blockingCard.explanation}
            meaning={translate('dashboard:dashboard.blockingIssuesMeaning')}
            icon="error"
            status={blockingCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={blockingCard.recommendation}
            action={{ label: translate('dashboard:dashboard.openDataQuality'), onClick: () => navigate('/data-quality') }}
          />
          <BusinessCard
            testId="warnings"
            title={translate('dashboard:dashboard.warnings')}
            value={warningCard.value}
            explanation={warningCard.explanation}
            meaning={translate('dashboard:dashboard.warningsMeaning')}
            icon="warning"
            status={warningCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={warningCard.recommendation}
            action={{ label: translate('dashboard:dashboard.openDataQuality'), onClick: () => navigate('/data-quality') }}
          />
          <BusinessCard
            testId="orders"
            title={translate('dashboard:dashboard.ordersAndRevenueToday')}
            value={ordersCard.value}
            explanation={ordersCard.explanation}
            meaning={translate('dashboard:dashboard.ordersMeaning')}
            icon="orders"
            status={ordersCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={ordersCard.recommendation}
            action={{ label: translate('dashboard:dashboard.openOrders'), onClick: () => navigate('/orders') }}
          />
          <BusinessCard
            testId="inventory"
            title={translate('dashboard:dashboard.inventoryAlerts')}
            value={stockCard.value}
            explanation={stockCard.explanation}
            meaning={translate('dashboard:dashboard.inventoryMeaning')}
            icon="products"
            status={stockCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={stockCard.recommendation}
            action={{ label: translate('dashboard:dashboard.viewProducts'), onClick: () => navigate('/products') }}
          />
          <BusinessCard
            testId="updates"
            title={translate('dashboard:dashboard.publishingUpdates')}
            value={updatesCard.value}
            explanation={updatesCard.explanation}
            meaning={translate('dashboard:dashboard.updatesMeaning')}
            icon="sync"
            status={updatesCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={updatesCard.recommendation}
            action={{ label: translate('dashboard:dashboard.openActivity'), onClick: () => navigate('/activity') }}
          />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <ChartCard title={translate('dashboard:dashboard.revenueTrend')}>
          {orderWindow === null ? (
            <SkeletonCard />
          ) : revenueSeries.some(item => item.points.length > 1) ? (
            <RevenueLineChart series={revenueSeries} />
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
        <div className={[CARD, 'flex flex-col gap-3 p-3.5'].join(' ')}>
          <div className="flex items-center">
            <p className="text-sm font-semibold leading-[22px] text-text-base">
              {translate('dashboard:dashboard.channels')}
            </p>
            <button
              type="button"
              onClick={() => navigate('/diagnostics')}
              className="ms-auto text-xs font-medium leading-4 text-accent hover:text-accent-hover"
            >
              {translate('dashboard:dashboard.openDiagnostics')}
            </button>
          </div>
          {!channelHealth ? (
            loading
              ? <SkeletonCard />
              : <Empty title={translate('dashboard:dashboard.channelHealthUnavailable')} />
          ) : channelHealth.items.length === 0 ? (
            <Empty title={translate('dashboard:dashboard.noChannelsMonitored')} />
          ) : (
            <ResourceSectionList
              resources={orderedChannels}
              className="divide-y divide-border"
              renderItem={resource => {
                const channel = resource.item
                return (
                  <button
                    type="button"
                    onClick={() => navigate('/diagnostics')}
                    className="flex w-full items-center gap-2.5 py-2.5 text-start"
                  >
                    <BrandIcon identity={channel.channelId} label={resource.displayName} size={36} />
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="truncate text-[13px] font-medium leading-[18px] text-text-base">
                        {resource.displayName}
                      </span>
                      <span className="truncate text-xs leading-4 text-[color:var(--fh-text-secondary)]">
                        {formatDiagnosticMessage(channel.summary)}
                      </span>
                    </span>
                    <ResourceStateBadge badge={resource.badge} />
                  </button>
                )
              }}
            />
          )}
        </div>

        <div className={[CARD, 'flex flex-col gap-3 p-3.5'].join(' ')}>
          <div className="flex items-center">
            <p className="text-sm font-semibold leading-[22px] text-text-base">
              {translate('dashboard:dashboard.sources')}
            </p>
            <button
              type="button"
              onClick={() => navigate('/sources')}
              className="ms-auto text-xs font-medium leading-4 text-accent hover:text-accent-hover"
            >
              {translate('dashboard:dashboard.manageSources')}
            </button>
          </div>
          {loading ? (
            <SkeletonCard />
          ) : sourceList.length === 0 ? (
            <Empty
              title={translate('dashboard:dashboard.noSourcesYet')}
              description={translate('dashboard:dashboard.connectSourceForDailyWork')}
            />
          ) : (
            <ResourceSectionList
              resources={orderedSources}
              className="divide-y divide-border"
              renderItem={resource => {
                const source = resource.item
                return (
                  <button
                    type="button"
                    onClick={() => navigate('/sources')}
                    className="flex w-full items-center gap-2.5 py-2.5 text-start"
                  >
                    <BrandIcon identity={{ sourceType: source.type }} label={source.name} size={36} />
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="truncate text-[13px] font-medium leading-[18px] text-text-base">
                        {source.name}
                      </span>
                      <span className="truncate text-xs leading-4 text-[color:var(--fh-text-secondary)]">
                        {translate('dashboard:dashboard.products', {
                          value1: relTime(source.lastSynced),
                          value2: formatNumber(source.productCount),
                        })}
                      </span>
                    </span>
                    <ResourceStateBadge badge={resource.badge} />
                  </button>
                )
              }}
            />
          )}
        </div>
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
                    {/* i18n-ignore -- technical connector identity passed to the display-name formatter. */}
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
