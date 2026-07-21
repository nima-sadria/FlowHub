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
import {
  diagnosticChannelSignals,
  legacySourceSignals,
  prepareResourceCollection,
  type ResourceTier,
} from '../features/resourceOrdering/resourceOrdering'
import i18n, { translate } from '../i18n'
import { formatDiagnosticMessage } from '../i18n/display'
import { formatNumber, formatPercent } from '../i18n/format'
import { useServices } from '../services/ServiceContext'
import type {
  ActivityEvent,
  ChannelHealthResponse,
  ChannelOrderListItem,
  Source,
} from '../services/types'
import { formatMoney } from '../utils/price'

// Figma: Screen/Dashboard (159:12911) — KPI row, action summary, revenue and
// orders charts, recent activity, and a unified channel/source health card.

const CARD = 'rounded-lg border border-border bg-bg-card'
const EXCLUDED_ORDER_STATUSES = new Set(['cancelled', 'canceled', 'refunded', 'failed'])
const TIER_RANK: Record<ResourceTier, number> = { configured: 0, attention: 1, disabled: 2, comingSoon: 3 }

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

interface HealthRow {
  id: string
  entityType: 'Channel' | 'Source'
  name: string
  detail: string
  tone: 'success' | 'warning'
  tier: ResourceTier
  onClick: () => void
}

function dashboardLocale(): string {
  return i18n.resolvedLanguage ?? i18n.language ?? 'en'
}

// Figma Dashboard shows compact relative times ("4 min"), not sentences.
function compactRelTime(date: Date | null): string {
  if (!date) return translate('common:status.notRead')
  const elapsedSeconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000))
  const unit: Intl.NumberFormatOptions =
    elapsedSeconds < 3_600
      ? { style: 'unit', unit: 'minute' }
      : elapsedSeconds < 86_400
        ? { style: 'unit', unit: 'hour' }
        : { style: 'unit', unit: 'day' }
  const value = elapsedSeconds < 3_600
    ? Math.max(1, Math.round(elapsedSeconds / 60))
    : elapsedSeconds < 86_400
      ? Math.round(elapsedSeconds / 3_600)
      : Math.round(elapsedSeconds / 86_400)
  return new Intl.NumberFormat(dashboardLocale(), { ...unit, unitDisplay: 'short' }).format(value)
}

// Figma Dashboard shows "$12,480" for USD; other currencies keep the shared format.
function dashboardMoney(amount: number, currency: string): string {
  if (currency === 'USD') {
    return new Intl.NumberFormat(dashboardLocale(), {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    }).format(amount)
  }
  return formatMoney(amount, { currency })
}

function formatAction(action: string): string {
  const sentence = action.replace(/_/g, ' ')
  return sentence.charAt(0).toUpperCase() + sentence.slice(1)
}

function isToday(iso: string | null): boolean {
  if (!iso) return false
  const date = new Date(iso)
  const now = new Date()
  return date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate()
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className={[CARD, 'flex h-[300px] flex-col gap-4 p-[18px]'].join(' ')}>
      <div className="flex items-center">
        <p className="text-[15px] font-semibold leading-5 text-text-base">{title}</p>
        <span className="ms-auto flex items-center text-xs text-[color:var(--fh-text-secondary)]">
          {translate('dashboard:dashboard.last30Days')}
          <Icon name="chevronDown" size="sm" style={{ width: 14, height: 14 }} />
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
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-[150px] w-full max-w-[440px]"
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
      activity.getEvents({ page: 1, pageSize: 2 }),
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
  // Freshness reflects the newest recorded read across all Sources; the
  // health list communicates each Source's current status separately.
  const lastSync = sourceList.reduce<Date | null>((best, source) => {
    if (!source.lastSynced) return best
    return !best || source.lastSynced > best ? source.lastSynced : best
  }, null)

  const counts = channelHealth?.summary.counts
  const channelWarnings = counts?.Warning ?? 0
  // i18n-ignore -- backend diagnostic status identifier.
  const channelBlocking = (counts?.Error ?? 0) + (counts?.['Unable to check'] ?? 0)
  const metrics = businessSummary?.metrics
  const metricsUnavailable = businessError || !metrics

  const todayLabel = useMemo(() => {
    const locale = i18n.resolvedLanguage ?? i18n.language ?? 'en'
    return new Intl.DateTimeFormat(locale, { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date())
  }, [])

  const countedOrders = useMemo(
    () => (orderWindow ?? []).filter(order => !EXCLUDED_ORDER_STATUSES.has(order.normalizedStatus.toLowerCase())),
    [orderWindow],
  )
  const synchronizedOrdersToday = countedOrders.filter(order => isToday(order.createdAtProvider))
  const blockingCount = metrics?.blockingIssues ?? channelBlocking
  const warningCount = metrics?.warnings ?? channelWarnings

  const fallbackRevenueByCurrency = synchronizedOrdersToday.reduce((totals, order) => {
    if (!order.currency || order.finalAmount === null) return totals
    totals.set(order.currency, (totals.get(order.currency) ?? 0) + order.finalAmount)
    return totals
  }, new Map<string, number>())
  const fallbackRevenueText = Array.from(fallbackRevenueByCurrency.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([currency, amount]) => dashboardMoney(amount, currency))
    .join(' · ')
  const revenueText = metrics
    ? metrics.revenueToday.map(item => dashboardMoney(item.amount, item.currency)).join(' · ')
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

  // -- Primary KPIs --------------------------------------------------------
  const kpiLoading = loading || businessLoading
  const outOfStock = metrics?.outOfStockProducts ?? 0
  const productsReadyValue = totalProducts !== null
    ? formatNumber(metrics ? Math.max(totalProducts - outOfStock, 0) : totalProducts)
    : '-'
  const productsReadyTrend = metrics
    ? outOfStock > 0
      ? translate('dashboard:dashboard.outOfStockCount', { count: outOfStock, value: formatNumber(outOfStock) })
      : translate('dashboard:dashboard.allInStock')
    : undefined
  const productsReadyTone = metrics && outOfStock > 0 ? 'warning' : 'up'

  const reviewRequiredCount = metrics?.readyForReview ?? 0
  const reviewRequiredValue = metricsUnavailable ? '-' : formatNumber(reviewRequiredCount)
  const reviewRequiredTrend = metricsUnavailable
    ? undefined
    : metrics!.blockingIssues > 0
      ? translate('dashboard:dashboard.blockingQualifier', { count: metrics!.blockingIssues, value: formatNumber(metrics!.blockingIssues) })
      : reviewRequiredCount > 0
        ? translate('dashboard:dashboard.awaitingReview')
        : translate('dashboard:dashboard.allClear')
  const reviewRequiredTone = !metricsUnavailable && metrics!.blockingIssues > 0 ? 'warning' : 'neutral'

  const applyReadyCount = metrics?.readyForApply ?? 0
  const applyReadyValue = metricsUnavailable ? '-' : formatNumber(applyReadyCount)
  const applyReadyTrend = metricsUnavailable
    ? undefined
    : applyReadyCount > 0
      ? translate('common:status.ready')
      : translate('dashboard:dashboard.allClear')

  const ordersTodayCount = metrics?.ordersToday ?? synchronizedOrdersToday.length
  const ordersYesterday = metrics?.ordersYesterday ?? 0
  const ordersTodayTrend = metrics && ordersYesterday > 0
    ? formatPercent((metrics.ordersToday - ordersYesterday) / ordersYesterday, { maximumFractionDigits: 1, signDisplay: 'exceptZero' })
    : undefined
  const ordersTodayTone = metrics && ordersYesterday > 0
    ? (metrics.ordersToday >= ordersYesterday ? 'up' : 'warning')
    : 'neutral'

  // -- Pricing workflow strip ----------------------------------------------
  const reviewStageCount = metrics?.readyForReview ?? 0
  const dryRunStageCount = metrics?.pendingUpdates ?? 0
  const applyStageCount = metrics?.readyForApply ?? 0

  // -- Unified channel + source health -------------------------------------
  const combinedHealthRows = useMemo<HealthRow[]>(() => {
    const channelRows: HealthRow[] = orderedChannels.ordered.map(resource => {
      const channel = resource.item
      const tone: HealthRow['tone'] = resource.badge === 'healthy' || resource.badge === 'configured' ? 'success' : 'warning'
      return {
        id: `channel:${channel.channelId}`,
        entityType: 'Channel',
        name: resource.displayName,
        detail: formatDiagnosticMessage(channel.summary),
        tone,
        tier: resource.tier,
        onClick: () => navigate('/diagnostics'),
      }
    })
    const sourceRows: HealthRow[] = orderedSources.ordered.map(resource => {
      const source = resource.item
      const tone: HealthRow['tone'] = resource.badge === 'healthy' || resource.badge === 'configured' ? 'success' : 'warning'
      return {
        id: `source:${source.id}`,
        entityType: 'Source',
        name: resource.displayName,
        detail: translate('dashboard:dashboard.products', {
          value1: compactRelTime(source.lastSynced),
          value2: formatNumber(source.productCount),
        }),
        tone,
        tier: resource.tier,
        onClick: () => navigate('/sources'),
      }
    })
    return [...channelRows, ...sourceRows].sort((left, right) => TIER_RANK[left.tier] - TIER_RANK[right.tier])
  }, [orderedChannels, orderedSources, navigate])

  const sourceWarnings = orderedSources.ordered.filter(resource => resource.tier === 'attention').length
  const combinedWarnings = channelWarnings + sourceWarnings
  const combinedBlocking = channelBlocking
  const healthBadge = combinedBlocking > 0
    ? { variant: 'error' as const, label: translate('dashboard:dashboard.blockingCountBadge', { count: combinedBlocking, value: formatNumber(combinedBlocking) }) }
    : combinedWarnings > 0
      ? { variant: 'warning' as const, label: translate('dashboard:dashboard.warningCountBadge', { count: combinedWarnings, value: formatNumber(combinedWarnings) }) }
      : { variant: 'success' as const, label: translate('common:status.operational') }

  return (
    <PageShell className="fh-dashboard-inter">
      <div className="fh-page-header h-12">
        <div className="flex flex-col gap-[2px]">
          <h1 className="fh-page-title">{translate('dashboard:dashboard.dashboard')}</h1>
          <p className="fh-page-subtitle">
            {todayLabel} · {translate('dashboard:dashboard.liveCommerceOverview')}
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/products')}
          className="fh-button-primary fh-button-sm"
        >
          {translate('dashboard:dashboard.reviewChangesButton', { count: reviewRequiredCount, value: formatNumber(reviewRequiredCount) })}
        </button>
      </div>

      {kpiLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label={translate('dashboard:dashboard.productsReady')}
            value={productsReadyValue}
            trend={productsReadyTrend}
            trendTone={productsReadyTone}
            icon="products"
          />
          <KpiCard
            label={translate('dashboard:dashboard.reviewRequired')}
            value={reviewRequiredValue}
            trend={reviewRequiredTrend}
            trendTone={reviewRequiredTone}
            icon="products"
          />
          <KpiCard
            label={translate('dashboard:dashboard.applyReady')}
            value={applyReadyValue}
            trend={applyReadyTrend}
            trendTone="neutral"
            icon="products"
          />
          <KpiCard
            label={translate('dashboard:dashboard.ordersTodayLabel')}
            value={formatNumber(ordersTodayCount)}
            trend={ordersTodayTrend}
            trendTone={ordersTodayTone}
            icon="products"
          />
        </div>
      )}

      <div className={[CARD, 'flex min-h-[52px] flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2'].join(' ')}>
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
          <span className="text-[11px] leading-4 text-wp-muted">{translate('dashboard:dashboard.blocking')}</span>
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
            {compactRelTime(lastSync)}
          </span>
        </span>
        <span className="ms-auto flex items-center gap-2">
          <span className="text-[11px] font-medium leading-4 text-[color:var(--fh-text-secondary)]">
            {translate('dashboard:dashboard.pricingWorkflow')}
          </span>
          <Badge dot variant="warning">
            {translate('dashboard:dashboard.reviewStageCount', { count: reviewStageCount, value: formatNumber(reviewStageCount) })}
          </Badge>
          <Badge dot variant="info">
            {translate('dashboard:dashboard.dryRunStageCount', { count: dryRunStageCount, value: formatNumber(dryRunStageCount) })}
          </Badge>
          <Badge dot variant="success">
            {translate('dashboard:dashboard.applyStageCount', { count: applyStageCount, value: formatNumber(applyStageCount) })}
          </Badge>
        </span>
      </div>

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
        <div className={[CARD, 'flex h-[176px] flex-col gap-2 overflow-hidden p-3.5'].join(' ')}>
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
            recentEvents.slice(0, 2).map(event => (
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
                  {compactRelTime(event.timestamp)}
                </span>
              </div>
            ))
          )}
        </div>

        <div className={[CARD, 'flex h-[176px] flex-col gap-2 overflow-hidden p-3.5'].join(' ')}>
          <div className="flex items-center">
            <p className="text-sm font-semibold leading-[22px] text-text-base">
              {translate('dashboard:dashboard.channelHealth')}
            </p>
            <span className="ms-auto">
              <Badge dot variant={healthBadge.variant}>{healthBadge.label}</Badge>
            </span>
          </div>
          {loading ? (
            <SkeletonCard />
          ) : combinedHealthRows.length === 0 ? (
            <Empty title={translate('dashboard:dashboard.channelHealthUnavailable')} />
          ) : (
            combinedHealthRows.slice(0, 2).map(row => (
              <button
                key={row.id}
                type="button"
                data-health-row={row.id}
                data-health-tone={row.tone}
                onClick={row.onClick}
                className="flex items-center gap-2.5 rounded-md px-3 py-2.5 text-start hover:bg-bg-subtle"
              >
                <span
                  className={[
                    'inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md',
                    row.tone === 'success'
                      ? 'bg-[color:var(--fh-success-surface)] text-wp-green'
                      : 'bg-[color:var(--fh-warning-surface)] text-wp-yellow',
                  ].join(' ')}
                >
                  <Icon name={row.entityType === 'Source' ? 'sources' : 'channels'} size="sm" />
                </span>
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="truncate text-[13px] font-medium leading-[18px] text-text-base">
                    {row.name}
                  </span>
                  <span className="truncate text-xs leading-4 text-[color:var(--fh-text-secondary)]">
                    {row.detail}
                  </span>
                </span>
                <Badge className="flex-shrink-0" variant={row.tone === 'success' ? 'success' : 'warning'}>
                  {row.tone === 'success' ? translate('common:status.healthy') : translate('common:status.warning')}
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
