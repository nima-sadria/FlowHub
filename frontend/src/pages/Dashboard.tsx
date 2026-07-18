import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../api/client'
import { useAuth } from '../auth'
import Badge, { type BadgeVariant } from '../components/Badge'
import BrandIcon from '../components/BrandIcon'
import BusinessCard, { type BusinessCardTone } from '../components/BusinessCard'
import Empty from '../components/Empty'
import Icon, { type IconName } from '../components/Icon'
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
import { formatDiagnosticMessage } from '../i18n/display'
import { formatNumber, formatRelativeTime } from '../i18n/format'
import { useServices } from '../services/ServiceContext'
import type { ActivityEvent, ChannelHealthResponse, Source } from '../services/types'
import { formatMoney } from '../utils/price'

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

function relTime(d: Date | null): string {
  if (!d) return translate('common:status.notRead')
  return formatRelativeTime(d)
}

function formatAction(action: string): string {
  return action.replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase())
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

function orderTrend(today: number, yesterday: number): string {
  return comparisonWithYesterday(today, yesterday)
}

function updateTrend(today: number, yesterday: number): string {
  return comparisonWithYesterday(today, yesterday)
}

const activityPresentation: Record<ActivityEvent['level'], {
  variant: BadgeVariant
  icon: IconName
  labelKey: string
}> = {
  critical: { variant: 'danger', icon: 'error', labelKey: 'activity:activity.critical' },
  debug: { variant: 'info', icon: 'diagnostics', labelKey: 'activity:activity.debug' },
  info: { variant: 'info', icon: 'info', labelKey: 'activity:activity.info' },
  success: { variant: 'success', icon: 'success', labelKey: 'activity:activity.success' },
  warning: { variant: 'warning', icon: 'warning', labelKey: 'activity:activity.warning' },
  error: { variant: 'danger', icon: 'error', labelKey: 'activity:activity.error' },
}

export default function Dashboard() {
  const { authFetch } = useAuth()
  const { sources, activity, health: healthService } = useServices()
  const navigate = useNavigate()

  const [channelHealth, setChannelHealth] = useState<ChannelHealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [sourceList, setSourceList] = useState<Source[]>([])
  const [recentEvents, setRecentEvents] = useState<ActivityEvent[]>([])
  const [dataLoading, setDataLoading] = useState(true)
  const [businessSummary, setBusinessSummary] = useState<DashboardBusinessSummary | null>(null)
  const [businessLoading, setBusinessLoading] = useState(true)
  const [businessError, setBusinessError] = useState(false)

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true)
    try {
      setChannelHealth(await healthService.getChannelHealth())
    } finally {
      setHealthLoading(false)
    }
  }, [healthService])

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

  useEffect(() => { void fetchHealth() }, [fetchHealth])
  useEffect(() => { void fetchBusinessSummary() }, [fetchBusinessSummary])

  useEffect(() => {
    Promise.all([
      sources.getSources(),
      activity.getEvents({ page: 1, pageSize: 5 }),
    ]).then(([srcs, evts]) => {
      setSourceList(srcs)
      setRecentEvents(evts.items)
    }).finally(() => setDataLoading(false))
  }, [sources, activity])

  const orderedSources = useMemo(
    () => prepareResourceCollection(sourceList, legacySourceSignals),
    [sourceList],
  )
  const orderedChannels = useMemo(
    () => prepareResourceCollection(channelHealth?.items ?? [], channel => ({
      ...diagnosticChannelSignals(channel),
      displayName: formatChannelDisplayName(channel.channelId || `${channel.channelType}:primary`),
    })),
    [channelHealth],
  )
  const recommendationLabel = translate('dashboard:dashboard.recommendedAction')
  const metrics = businessSummary?.metrics
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
  const revenueText = metrics?.revenueToday.map(item => (
    formatMoney(item.amount, { currency: item.currency })
  )).join(' · ') ?? ''
  const ordersCard: DashboardCardModel = pendingCard ?? {
    value: countValue(metrics!.ordersToday, 'dashboard:dashboard.noOrdersToday', 'dashboard:dashboard.ordersValue'),
    explanation: metrics!.ordersToday > 0
      ? translate('dashboard:dashboard.ordersTodayExplanation', {
        revenue: revenueText || translate('dashboard:dashboard.revenueUnavailable'),
        trend: orderTrend(metrics!.ordersToday, metrics!.ordersYesterday),
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
          trend: updateTrend(metrics!.updatesAppliedToday, metrics!.updatesAppliedYesterday),
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

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('dashboard:dashboard.dashboard')}</h1>
        </div>
      </div>

      <section aria-labelledby="business-overview-heading">
        <div className="mb-2">
          <h2 id="business-overview-heading" className="fh-section-title">{translate('dashboard:dashboard.businessOverview')}</h2>
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

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="fh-card">
          <div className="fh-panel-header">
            <div>
              <p className="fh-section-title">{translate('dashboard:dashboard.channels')}</p>
            </div>
            <button onClick={() => navigate('/diagnostics')} className="fh-toolbar-link">
              {translate('dashboard:dashboard.openDiagnostics')}
            </button>
          </div>
          <div className="fh-panel-body !py-3">
            {healthLoading && !channelHealth ? (
              <SkeletonCard />
            ) : !channelHealth || channelHealth.items.length === 0 ? (
              <Empty title={translate('dashboard:dashboard.noChannelsMonitored')} description={translate('dashboard:dashboard.configureChannel')} />
            ) : (
              <ResourceSectionList
                resources={orderedChannels}
                className="divide-y divide-border"
                renderItem={resource => {
                  const channel = resource.item
                  return (
                    <div className="flex items-center justify-between gap-3 py-2.5">
                      <BrandIcon identity={channel.channelId} label={resource.displayName} size={36} />
                      <div className="min-w-0 flex-1">
                        {/* i18n-ignore -- fallback is a technical Channel identity, not interface copy */}
                        <p className="fh-text-body font-medium truncate">{resource.displayName}</p>
                        <p className="fh-text-caption truncate">{formatDiagnosticMessage(channel.summary)}</p>
                      </div>
                      <ResourceStateBadge badge={resource.badge} />
                    </div>
                  )
                }}
              />
            )}
          </div>
        </div>

        <div className="fh-card">
          <div className="fh-panel-header">
            <div>
              <p className="fh-section-title">{translate('dashboard:dashboard.sources')}</p>
            </div>
            <button onClick={() => navigate('/sources')} className="fh-toolbar-link">
              {translate('dashboard:dashboard.manageSources')}
            </button>
          </div>
          <div className="fh-panel-body !py-3">
            {dataLoading ? (
              <SkeletonCard />
            ) : sourceList.length === 0 ? (
              <Empty
                title={translate('dashboard:dashboard.noSourcesYet')}
                description={translate('dashboard:dashboard.connectSourceForDailyWork')}
                action={{ label: translate('dashboard:dashboard.addYourFirstSource'), onClick: () => navigate('/sources') }}
              />
            ) : (
              <ResourceSectionList
                resources={orderedSources}
                className="divide-y divide-border"
                renderItem={resource => {
                  const source = resource.item
                  return (
                    <div className="flex items-center justify-between gap-3 py-2.5">
                      <BrandIcon identity={{ sourceType: source.type }} label={source.name} size={36} />
                      <div className="min-w-0 flex-1">
                        <p className="fh-text-body font-medium">{source.name}</p>
                        <p className="fh-text-caption">{translate('dashboard:dashboard.products', { value1: relTime(source.lastSynced), value2: formatNumber(source.productCount) })}</p>
                      </div>
                      <ResourceStateBadge badge={resource.badge} />
                    </div>
                  )
                }}
              />
            )}
          </div>
        </div>

        <div className="fh-card lg:col-span-2">
          <div className="fh-panel-header">
            <div>
              <p className="fh-section-title">{translate('dashboard:dashboard.recentActivity')}</p>
            </div>
            <button onClick={() => navigate('/activity')} className="fh-toolbar-link">
              {translate('dashboard:dashboard.viewAll')}
            </button>
          </div>
          <div className="fh-panel-body !pt-0">
            {dataLoading ? (
              <div className="py-3">
                <SkeletonCard />
              </div>
            ) : recentEvents.length === 0 ? (
              <Empty title={translate('dashboard:dashboard.noEventsYet')} description={translate('dashboard:dashboard.noActivityActionRequired')} />
            ) : (
              recentEvents.map(event => {
                const presentation = activityPresentation[event.level]
                return (
                  <div key={event.id} className="flex flex-wrap items-center gap-3 border-b border-border py-2.5 last:border-0">
                    <Badge variant={presentation.variant} icon={<Icon name={presentation.icon} />}>
                      {translate(presentation.labelKey)}
                    </Badge>
                    <p className="fh-text-caption min-w-0 flex-1 truncate text-text-base">{formatAction(event.action)}</p>
                    <span className="fh-text-caption flex-shrink-0">{relTime(event.timestamp)}</span>
                  </div>
                )
              })
            )}
          </div>
        </div>
      </div>
    </PageShell>
  )
}
