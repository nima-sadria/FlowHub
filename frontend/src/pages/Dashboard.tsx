import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../api/client'
import type { HealthResponse } from '../api/types'
import { useAuth } from '../auth'
import Badge, { type BadgeVariant } from '../components/Badge'
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

function relTime(d: Date | null): string {
  if (!d) return translate('common:status.notRead')
  return formatRelativeTime(d)
}

function formatAction(action: string): string {
  return action.replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase())
}

const activityPresentation: Record<ActivityEvent['level'], {
  variant: BadgeVariant
  icon: IconName
  labelKey: string
}> = {
  info: { variant: 'info', icon: 'info', labelKey: 'activity:activity.info' },
  success: { variant: 'success', icon: 'success', labelKey: 'activity:activity.success' },
  warning: { variant: 'warning', icon: 'warning', labelKey: 'activity:activity.warning' },
  error: { variant: 'danger', icon: 'error', labelKey: 'activity:activity.error' },
}

export default function Dashboard() {
  const { authFetch } = useAuth()
  const { sources, products, activity, health: healthService } = useServices()
  const navigate = useNavigate()

  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [channelHealth, setChannelHealth] = useState<ChannelHealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthErr, setHealthErr] = useState(false)
  const [sourceList, setSourceList] = useState<Source[]>([])
  const [totalProducts, setTotalProducts] = useState<number | null>(null)
  const [recentEvents, setRecentEvents] = useState<ActivityEvent[]>([])
  const [dataLoading, setDataLoading] = useState(true)

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true)
    setHealthErr(false)
    try {
      const [data, channels] = await Promise.all([
        apiFetch<HealthResponse>('/api/health', authFetch),
        healthService.getChannelHealth(),
      ])
      setHealth(data)
      setChannelHealth(channels)
    } catch {
      setHealthErr(true)
    } finally {
      setHealthLoading(false)
    }
  }, [authFetch, healthService])

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

  const activeSources = sourceList.filter(source => source.status === 'active')
  const sourcesNeedingAttention = sourceList.length - activeSources.length
  const enabledChannels = (channelHealth?.items ?? []).filter(channel => channel.enabled)
  const readyChannels = enabledChannels.filter(channel => channel.status === 'Operational')
  const channelsNeedingAttention = enabledChannels.filter(channel => channel.status !== 'Operational')
  const hasChannelError = channelsNeedingAttention.some(channel => channel.status === 'Error')
  const firstChannelAttention = channelsNeedingAttention[0]

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
  const lastSync = activeSources.reduce<Date | null>((best, source) => {
    if (!source.lastSynced) return best
    return !best || source.lastSynced > best ? source.lastSynced : best
  }, null)

  const recommendationLabel = translate('dashboard:dashboard.recommendedAction')
  const loadingStatus = {
    label: translate('common:status.checking'),
    tone: 'info' as BusinessCardTone,
    icon: 'refresh' as IconName,
  }

  const productCard = dataLoading ? {
    value: translate('common:status.loading'),
    explanation: translate('dashboard:dashboard.loadingCatalogSummary'),
    status: loadingStatus,
    recommendation: translate('dashboard:dashboard.waitForDashboardData'),
  } : totalProducts && totalProducts > 0 ? {
    value: formatNumber(totalProducts),
    explanation: translate('dashboard:dashboard.productsAvailable', { count: totalProducts, value: formatNumber(totalProducts) }),
    status: { label: translate('common:status.ready'), tone: 'success' as BusinessCardTone, icon: 'success' as IconName },
    recommendation: translate('dashboard:dashboard.reviewManagedProducts'),
  } : {
    value: translate('dashboard:dashboard.noProducts'),
    explanation: translate('dashboard:dashboard.catalogIsEmpty'),
    status: { label: translate('dashboard:dashboard.needsSetup'), tone: 'warning' as BusinessCardTone, icon: 'warning' as IconName },
    recommendation: translate('dashboard:dashboard.addSourceToBuildCatalog'),
  }

  const sourceCard = dataLoading ? {
    value: translate('common:status.loading'),
    explanation: translate('dashboard:dashboard.loadingSourceSummary'),
    status: loadingStatus,
    recommendation: translate('dashboard:dashboard.waitForDashboardData'),
  } : sourceList.length === 0 ? {
    value: translate('dashboard:dashboard.noActiveSources'),
    explanation: translate('dashboard:dashboard.noSourceDataAvailable'),
    status: { label: translate('common:status.notConfigured'), tone: 'warning' as BusinessCardTone, icon: 'warning' as IconName },
    recommendation: translate('dashboard:dashboard.connectSourceForDailyWork'),
  } : sourcesNeedingAttention > 0 ? {
    value: translate('dashboard:dashboard.activeSourceValue', { count: activeSources.length, value: formatNumber(activeSources.length) }),
    explanation: translate('dashboard:dashboard.sourcesNeedAttention', { count: sourcesNeedingAttention, value: formatNumber(sourcesNeedingAttention) }),
    status: { label: translate('dashboard:dashboard.needsAttention'), tone: 'warning' as BusinessCardTone, icon: 'warning' as IconName },
    recommendation: translate('dashboard:dashboard.fixSourceConnections'),
  } : {
    value: translate('dashboard:dashboard.activeSourceValue', { count: activeSources.length, value: formatNumber(activeSources.length) }),
    explanation: translate('dashboard:dashboard.allSourcesReady'),
    status: { label: translate('common:status.healthy'), tone: 'success' as BusinessCardTone, icon: 'success' as IconName },
    recommendation: translate('dashboard:dashboard.noActionRequired'),
  }

  const channelCard = healthLoading ? {
    value: translate('common:status.checking'),
    explanation: translate('dashboard:dashboard.loadingChannelSummary'),
    status: loadingStatus,
    recommendation: translate('dashboard:dashboard.waitForHealthCheck'),
  } : enabledChannels.length === 0 ? {
    value: translate('dashboard:dashboard.noActiveChannels'),
    explanation: translate('dashboard:dashboard.noPublishingDestinations'),
    status: { label: translate('common:status.notConfigured'), tone: 'warning' as BusinessCardTone, icon: 'warning' as IconName },
    recommendation: translate('dashboard:dashboard.configureChannel'),
  } : channelsNeedingAttention.length > 0 ? {
    value: translate('dashboard:dashboard.readyChannelValue', { ready: formatNumber(readyChannels.length), total: formatNumber(enabledChannels.length) }),
    explanation: translate('dashboard:dashboard.channelsNeedAttention', { count: channelsNeedingAttention.length, value: formatNumber(channelsNeedingAttention.length) }),
    status: {
      label: hasChannelError ? translate('common:status.error') : translate('dashboard:dashboard.needsAttention'),
      tone: (hasChannelError ? 'danger' : 'warning') as BusinessCardTone,
      icon: (hasChannelError ? 'error' : 'warning') as IconName,
    },
    recommendation: formatDiagnosticMessage(firstChannelAttention?.nextRecommendedAction)
      || translate('dashboard:dashboard.reviewChannelHealth'),
  } : {
    value: translate('dashboard:dashboard.readyChannelValue', { ready: formatNumber(readyChannels.length), total: formatNumber(enabledChannels.length) }),
    explanation: translate('dashboard:dashboard.allChannelsReady'),
    status: { label: translate('common:status.healthy'), tone: 'success' as BusinessCardTone, icon: 'success' as IconName },
    recommendation: translate('dashboard:dashboard.noActionRequired'),
  }

  const freshnessCard = dataLoading ? {
    value: translate('common:status.loading'),
    explanation: translate('dashboard:dashboard.loadingFreshnessSummary'),
    status: loadingStatus,
    recommendation: translate('dashboard:dashboard.waitForDashboardData'),
  } : lastSync ? {
    value: relTime(lastSync),
    explanation: translate('dashboard:dashboard.latestSuccessfulSourceRead'),
    status: { label: translate('dashboard:dashboard.readRecorded'), tone: 'info' as BusinessCardTone, icon: 'success' as IconName },
    recommendation: translate('dashboard:dashboard.reviewLatestSourceRead'),
  } : {
    value: translate('dashboard:dashboard.notReadYet'),
    explanation: activeSources.length > 0
      ? translate('dashboard:dashboard.activeSourceHasNoRead')
      : translate('dashboard:dashboard.noActiveSourceAvailable'),
    status: { label: translate('dashboard:dashboard.needsAttention'), tone: 'warning' as BusinessCardTone, icon: 'warning' as IconName },
    recommendation: translate('dashboard:dashboard.readSourceBeforeReview'),
  }

  const systemCard = healthLoading ? {
    value: translate('dashboard:dashboard.checkingSystem'),
    explanation: translate('dashboard:dashboard.checkingDailyServices'),
    status: loadingStatus,
    recommendation: translate('dashboard:dashboard.waitForHealthCheck'),
  } : healthErr || !health ? {
    value: translate('dashboard:dashboard.systemUnavailable'),
    explanation: translate('dashboard:dashboard.dailyServicesNotConfirmed'),
    status: { label: translate('dashboard:dashboard.needsAttention'), tone: 'danger' as BusinessCardTone, icon: 'error' as IconName },
    recommendation: translate('dashboard:dashboard.openDiagnosticsToResolve'),
  } : {
    value: translate('dashboard:dashboard.dailyWorkReady'),
    explanation: translate('dashboard:dashboard.dailyServicesAvailable'),
    status: { label: translate('common:status.healthy'), tone: 'success' as BusinessCardTone, icon: 'success' as IconName },
    recommendation: translate('dashboard:dashboard.noActionRequired'),
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('dashboard:dashboard.dashboard')}</h1>
          <p className="fh-page-subtitle">{translate('dashboard:dashboard.controlCenterSummary')}</p>
        </div>
      </div>

      <section aria-labelledby="business-overview-heading">
        <div className="mb-3">
          <h2 id="business-overview-heading" className="fh-section-title">{translate('dashboard:dashboard.businessOverview')}</h2>
          <p className="fh-text-caption">{translate('dashboard:dashboard.businessOverviewDescription')}</p>
        </div>
        <div className="fh-business-card-grid">
          <BusinessCard
            testId="products"
            title={translate('dashboard:dashboard.managedProducts')}
            value={productCard.value}
            explanation={productCard.explanation}
            meaning={translate('dashboard:dashboard.productsMeaning')}
            icon="products"
            status={productCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={productCard.recommendation}
            action={{
              label: totalProducts && totalProducts > 0
                ? translate('dashboard:dashboard.viewProducts')
                : translate('dashboard:dashboard.addSource'),
              onClick: () => navigate(totalProducts && totalProducts > 0 ? '/products' : '/sources'),
            }}
          />
          <BusinessCard
            testId="sources"
            title={translate('dashboard:dashboard.sourceReadiness')}
            value={sourceCard.value}
            explanation={sourceCard.explanation}
            meaning={translate('dashboard:dashboard.sourcesMeaning')}
            icon="file"
            status={sourceCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={sourceCard.recommendation}
            action={{ label: translate('dashboard:dashboard.manageSources'), onClick: () => navigate('/sources') }}
          />
          <BusinessCard
            testId="channels"
            title={translate('dashboard:dashboard.channelReadiness')}
            value={channelCard.value}
            explanation={channelCard.explanation}
            meaning={translate('dashboard:dashboard.channelsMeaning')}
            icon="channel"
            status={channelCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={channelCard.recommendation}
            action={{ label: translate('dashboard:dashboard.openDiagnostics'), onClick: () => navigate('/diagnostics') }}
          />
          <BusinessCard
            testId="freshness"
            title={translate('dashboard:dashboard.dataFreshness')}
            value={freshnessCard.value}
            explanation={freshnessCard.explanation}
            meaning={translate('dashboard:dashboard.freshnessMeaning')}
            icon="sync"
            status={freshnessCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={freshnessCard.recommendation}
            action={{ label: translate('dashboard:dashboard.openSources'), onClick: () => navigate('/sources') }}
          />
          <BusinessCard
            testId="system"
            title={translate('dashboard:dashboard.systemStatus')}
            value={systemCard.value}
            explanation={systemCard.explanation}
            meaning={translate('dashboard:dashboard.systemMeaning')}
            icon="diagnostics"
            status={systemCard.status}
            recommendationLabel={recommendationLabel}
            recommendation={systemCard.recommendation}
            action={healthErr ? { label: translate('dashboard:dashboard.openDiagnostics'), onClick: () => navigate('/diagnostics') } : undefined}
          />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="fh-card">
          <div className="fh-panel-header">
            <div>
              <p className="fh-section-title">{translate('dashboard:dashboard.channels')}</p>
              <p className="fh-text-caption">{translate('dashboard:dashboard.channelListMeaning')}</p>
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
                      <div className="min-w-0">
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
              <p className="fh-text-caption">{translate('dashboard:dashboard.sourceListMeaning')}</p>
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
                      <div>
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
              <p className="fh-text-caption">{translate('dashboard:dashboard.activityListMeaning')}</p>
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
