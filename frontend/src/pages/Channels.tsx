import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { useAuth } from '../auth'
import type { BadgeVariant } from '../components/Badge'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import { ManagementResourceSections } from '../components/ResourceOrdering'
import OperationalResourceCard, { type OperationalResourceAction, type OperationalResourceState } from '../components/OperationalResourceCard'
import {
  prepareResourceCollection,
  type ResourceBadge,
  type ResourceOrderingSignals,
  type ResourceTier,
} from '../features/resourceOrdering/resourceOrdering'
import { translate } from '../i18n'
import { formatCapabilityList, formatStatus } from '../i18n/display'
import { formatNumber, formatRelativeTime } from '../i18n/format'
import { inputHint } from '../utils/inputHint'
import { useNotification } from '../notifications/NotificationProvider'
import { useServices } from '../services/ServiceContext'
import type { CommerceChannel, CommerceTypeOption } from '../services/types'
import { effectiveHasPerm } from '../utils/permissions'
import { WORKSPACE_PERMISSION } from '../utils/workspacePermissions'
import { ConfigPanel } from './CommerceHub'
import { resourceQaFixtureState, withConnectedChannelFixture } from '../dev/resourceQaFixtures'

type ChannelFilter = 'all' | 'active' | 'attention' | 'disabled' | 'comingSoon'

function matchesFilter(tier: ResourceTier, filter: ChannelFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'active') return tier === 'configured' || tier === 'attention'
  return tier === filter
}

function channelBadgeTone(badge: ResourceBadge): BadgeVariant {
  if (badge === 'healthy' || badge === 'configured') return 'success'
  if (badge === 'warning') return 'warning'
  return 'neutral'
}

function channelBadgeLabel(badge: ResourceBadge): string {
  if (badge === 'healthy' || badge === 'configured') return translate('common:status.connected')
  if (badge === 'warning' || badge === 'disabled') return translate('common:status.setupRequired')
  return translate('common:resourceBadge.comingSoon')
}

function channelLifecycleSignals(channel: CommerceChannel): ResourceOrderingSignals {
  return {
    id: channel.id,
    displayName: channel.name,
    enabled: channel.status !== 'disabled' && channel.status !== 'inactive',
    configured: channel.credential_status === 'configured',
    implemented: channel.implemented,
    placeholder: channel.placeholder,
  }
}

function operationalState(tier: ResourceTier): OperationalResourceState {
  if (tier === 'configured') return 'connected'
  if (tier === 'comingSoon') return 'comingSoon'
  return 'setupRequired'
}

function channelNeedsOperationalAttention(channel: CommerceChannel): boolean {
  return ['degraded', 'error', 'failed', 'partial_failed', 'unhealthy'].includes(channel.health.status)
    || ['failed', 'partial_failed', 'completed_with_errors'].includes(channel.cache_refresh_status)
}

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10)
}

export default function Channels() {
  const { commerce, orders } = useServices()
  const { user } = useAuth()
  const notify = useNotification()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [channels, setChannels] = useState<CommerceChannel[]>([])
  const [channelTypes, setChannelTypes] = useState<CommerceTypeOption[]>([])
  const [setupLoading, setSetupLoading] = useState(false)
  const [setupError, setSetupError] = useState(false)
  const [ordersToday, setOrdersToday] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [partialLoadError, setPartialLoadError] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<ChannelFilter>('all')
  const [testingId, setTestingId] = useState<string | null>(null)
  const [refreshingId, setRefreshingId] = useState<string | null>(null)
  const setupDialogRef = useRef<HTMLDivElement | null>(null)
  const setupTriggerRef = useRef<HTMLElement | null>(null)
  const canManageCommerce = user?.is_admin === true
  const canViewActivity = effectiveHasPerm(user, WORKSPACE_PERMISSION.readAudit)
  const canViewDiagnostics = effectiveHasPerm(user, 'can_view_settings')
  const setupTarget = searchParams.get('setup')
  const setupResourceId = setupTarget && setupTarget !== 'new' ? setupTarget : null
  const qaFixture = resourceQaFixtureState(`?${searchParams.toString()}`)
  const setupResourceUnavailable = Boolean(setupResourceId && channelTypes.length > 0 && !channelTypes.some(item => item.id === setupResourceId))

  const channelResources = useMemo(
    () => prepareResourceCollection(channels, channelLifecycleSignals),
    [channels],
  )
  const visibleChannels = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    return channelResources.ordered
      .filter(resource => matchesFilter(resource.tier, filter))
      .filter(resource => !normalizedQuery
        || resource.displayName.toLocaleLowerCase().includes(normalizedQuery)
        || resource.item.provider.toLocaleLowerCase().includes(normalizedQuery))
  }, [channelResources, filter, query])
  const needsAttentionCount = useMemo(
    () => channelResources.ordered.filter(resource => resource.tier === 'attention' || resource.tier === 'disabled').length,
    [channelResources],
  )
  const connectedChannelsCount = useMemo(
    () => channelResources.ordered.filter(resource => resource.tier === 'configured').length,
    [channelResources],
  )
  const healthyListingsTotal = useMemo(
    () => channelResources.ordered
      .filter(resource => resource.tier === 'configured')
      .reduce((sum, resource) => sum + (resource.item.cached_products || 0), 0),
    [channelResources],
  )

  async function load() {
    setLoading(true)
    setLoadError(false)
    setPartialLoadError(false)
    try {
      const today = todayIsoDate()
      const [channelsResult, ordersResult] = await Promise.allSettled([
        commerce.getChannels(),
        orders ? orders.getOrders({ page: 1, pageSize: 1, dateFrom: today, dateTo: today }) : Promise.resolve(null),
      ])
      if (channelsResult.status === 'fulfilled') {
        setChannels(qaFixture === 'connected'
          ? withConnectedChannelFixture(channelsResult.value.items)
          : qaFixture === 'empty'
            ? []
            : channelsResult.value.items)
      }
      else setLoadError(true)
      if (ordersResult.status === 'fulfilled' && ordersResult.value) setOrdersToday(ordersResult.value.total)
      if (qaFixture === 'partial' || (channelsResult.status === 'fulfilled' && ordersResult.status === 'rejected')) setPartialLoadError(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [commerce, orders, qaFixture])

  useEffect(() => {
    if (!setupTarget || !canManageCommerce) return
    let active = true
    setSetupLoading(true)
    setSetupError(false)
    commerce.getChannelTypes()
      .then(result => {
        if (active) setChannelTypes(result.items)
      })
      .catch(() => {
        if (active) setSetupError(true)
      })
      .finally(() => {
        if (active) setSetupLoading(false)
      })
    return () => { active = false }
  }, [canManageCommerce, commerce, setupTarget])

  useEffect(() => {
    if (!setupTarget) return
    function handleDialogKeys(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        closeSetup()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = Array.from(setupDialogRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]') ?? [])
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', handleDialogKeys)
    return () => window.removeEventListener('keydown', handleDialogKeys)
  }, [setupTarget])

  useEffect(() => {
    if (!setupTarget) return
    const frame = window.requestAnimationFrame(() => {
      const dialog = setupDialogRef.current
      if (!dialog || dialog.contains(document.activeElement)) return
      dialog.querySelector<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled])')?.focus()
    })
    return () => window.cancelAnimationFrame(frame)
  }, [channelTypes.length, setupError, setupLoading, setupTarget])

  function openSetup(resourceId?: string) {
    setupTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const next = new URLSearchParams(searchParams)
    next.set('setup', resourceId ?? 'new')
    setSearchParams(next)
  }

  function closeSetup() {
    const next = new URLSearchParams(searchParams)
    next.delete('setup')
    setSearchParams(next, { replace: true })
    window.requestAnimationFrame(() => setupTriggerRef.current?.focus())
  }

  async function handleSetupSaved() {
    await load()
    closeSetup()
  }

  async function handleTest(channelId: string) {
    if (!canManageCommerce) {
      notify.error(translate('commerce:commerceHub.adminPermissionRequired'))
      return
    }
    setTestingId(channelId)
    try {
      const result = await commerce.testChannel(channelId)
      const channel = channels.find(item => item.id === channelId)
      if (result.ok) {
        notify.success({
          title: translate('commerce:commerceHub.channelConnectedSuccessfully'),
          description: channel
            ? translate('commerce:commerceHub.isReadyToUse', { value1: channel.name })
            : translate('commerce:commerceHub.theChannelIsReadyToUse'),
        })
      } else {
        notify.error({
          title: translate('commerce:commerceHub.unableToConnectToTheChannel'),
          description: translate('commerce:commerceHub.pleaseVerifyYourCredentialsAndTryAgain'),
        })
      }
      await load()
    } catch {
      notify.error({
        title: translate('commerce:commerceHub.unableToConnectToTheChannel'),
        description: translate('commerce:commerceHub.pleaseVerifyYourCredentialsAndTryAgain'),
      })
    } finally {
      setTestingId(null)
    }
  }

  async function handleRefresh(channelId: string) {
    if (!canManageCommerce) {
      notify.error(translate('commerce:commerceHub.adminPermissionRequired'))
      return
    }
    setRefreshingId(channelId)
    try {
      const result = await commerce.refreshChannelCache(channelId)
      if (result.ok) {
        notify.success({
          title: translate('commerce:commerceHub.productCacheRefreshedSuccessfully'),
          description: translate('commerce:commerceHub.theLatestProductInformationHasBeenLoaded'),
        })
      } else {
        notify.error({
          title: translate('commerce:commerceHub.unableToRefreshTheProductCache'),
          description: translate('commerce:commerceHub.pleaseTryAgain'),
        })
      }
      await load()
    } catch {
      notify.error({
        title: translate('commerce:commerceHub.unableToRefreshTheProductCache'),
        description: translate('commerce:commerceHub.pleaseTryAgain'),
      })
    } finally {
      setRefreshingId(null)
    }
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('commerce:commerceHub.channels2')}</h1>
          <p className="fh-page-subtitle">{translate('commerce:commerceHub.channelOperationalSubtitle')}</p>
        </div>
        {canManageCommerce && (
          <button className="fh-button-primary" type="button" onClick={() => openSetup()}>
            <Icon name="add" /> {translate('commerce:commerceHub.addChannel')}
          </button>
        )}
      </div>

      <section className="fh-card fh-card-pad mb-5" aria-label={translate('commerce:commerceHub.channelOperationalFlow')}>
        <p className="fh-text-body-sm font-semibold text-text-base" dir="ltr">{translate('commerce:commerceHub.channelOperationalFlow')}</p>
        <p className="fh-text-caption mt-1">{translate('commerce:commerceHub.channelOperationalFlowHelp')}</p>
      </section>

      <div className="fh-channels-kpi-row">
        <div className="fh-kpi-card">
          <div className="fh-kpi-card-head">
            <span className="fh-kpi-card-label">{translate('commerce:commerceHub.connectedChannels')}</span>
            <span className="fh-kpi-card-icon"><Icon name="channels" size="sm" /></span>
          </div>
          <div className="fh-kpi-card-value">{connectedChannelsCount}</div>
        </div>
        <div className="fh-kpi-card">
          <div className="fh-kpi-card-head">
            <span className="fh-kpi-card-label">{translate('commerce:commerceHub.healthyListings')}</span>
            <span className="fh-kpi-card-icon"><Icon name="channels" size="sm" /></span>
          </div>
          <div className="fh-kpi-card-value">{formatNumber(healthyListingsTotal)}</div>
        </div>
        <div className="fh-kpi-card">
          <div className="fh-kpi-card-head">
            <span className="fh-kpi-card-label">{translate('commerce:commerceHub.needsAttentionKpi')}</span>
            <span className="fh-kpi-card-icon"><Icon name="channels" size="sm" /></span>
          </div>
          <div className="fh-kpi-card-value">
            {needsAttentionCount}
            {needsAttentionCount > 0 && <span className="fh-kpi-card-trend fh-kpi-card-trend-danger">{translate('commerce:commerceHub.reviewCaption')}</span>}
          </div>
        </div>
        {orders && (
          <div className="fh-kpi-card">
            <div className="fh-kpi-card-head">
              <span className="fh-kpi-card-label">{translate('commerce:commerceHub.ordersToday')}</span>
              <span className="fh-kpi-card-icon"><Icon name="channels" size="sm" /></span>
            </div>
            <div className="fh-kpi-card-value">{ordersToday !== null ? formatNumber(ordersToday) : '—'}</div>
          </div>
        )}
      </div>

      <div className="fh-channels-toolbar">
        <form className="fh-channels-search" onSubmit={event => event.preventDefault()}>
          <Icon name="search" size="sm" className="fh-channels-search-icon" />
          <input
            className="fh-channels-search-input"
            type="search"
            value={query}
            onChange={event => setQuery(event.target.value)}
            {...inputHint(translate('commerce:commerceHub.searchChannels'))}
            aria-label={translate('commerce:commerceHub.searchChannels')}
          />
          {query && <button type="button" className="fh-channels-search-clear" aria-label={translate('commerce:commerceHub.clearSearch')} onClick={() => setQuery('')}><Icon name="close" size="sm" /></button>}
        </form>
        <label className="fh-chip-select">
          <span className="sr-only">{translate('commerce:commerceHub.allHealthStates')}</span>
          <select value={filter} onChange={event => setFilter(event.target.value as ChannelFilter)}>
            <option value="all">{translate('commerce:commerceHub.allHealthStates')}</option>
            <option value="active">{translate('common:resourceGroup.active')}</option>
            <option value="attention">{translate('commerce:commerceHub.needsReview')}</option>
            <option value="disabled">{translate('common:resourceGroup.disabled')}</option>
            <option value="comingSoon">{translate('common:resourceGroup.comingSoon')}</option>
          </select>
          <Icon name="chevronDown" size="sm" className="fh-chip-caret" />
        </label>
        <span className="fh-channels-count ms-auto">{translate('commerce:commerceHub.channelsCount', { count: channels.length })}</span>
      </div>

      {loadError && !loading ? (
        <div className="fh-alert fh-alert-danger mb-4" role="alert">
          <Icon name="error" />
          <span className="flex-1">{translate('commerce:commerceHub.unableToLoadCommerceHub')}</span>
          <button type="button" className="fh-button-secondary fh-button-sm" onClick={() => void load()}>
            {translate('common:action.retry')}
          </button>
        </div>
      ) : null}

      {partialLoadError && !loading ? (
        <div className="fh-alert fh-alert-warning mb-4" role="status">
          <Icon name="warning" />
          <span className="flex-1">
            <strong className="block">{translate('commerce:commerceHub.partialLoadTitle')}</strong>
            <span className="fh-text-caption">{translate('commerce:commerceHub.partialLoadDescription')}</span>
          </span>
          <button type="button" className="fh-button-secondary fh-button-sm" onClick={() => void load()}>{translate('common:action.retry')}</button>
          {canViewDiagnostics && <button type="button" className="fh-button-secondary fh-button-sm" onClick={() => navigate('/diagnostics')}>{translate('common:action.diagnostics')}</button>}
        </div>
      ) : null}

      {loading ? <p className="fh-card fh-card-pad fh-text-caption" role="status" aria-live="polite" aria-busy="true">{translate('commerce:commerceHub.loadingCommerceHub')}</p> : loadError ? null : visibleChannels.length === 0 ? (
        <div className="fh-card fh-card-pad"><Empty title={translate('commerce:commerceHub.noChannelsFound')} description={translate('commerce:commerceHub.channelOperationalSubtitle')} action={canManageCommerce ? { label: translate('commerce:commerceHub.addChannel'), onClick: () => openSetup() } : undefined} /></div>
      ) : (
        <ManagementResourceSections resources={prepareResourceCollection(visibleChannels.map(resource => resource.item), channelLifecycleSignals)} className="fh-sources-grid fh-channels-grid" renderItem={resource => {
          const channel = resource.item
          const state = operationalState(resource.tier)
          const supportsProductCache = ['woocommerce', 'snappshop', 'tapsishop'].includes(channel.provider) && !channel.placeholder
          const lastActivityAt = channel.last_cache_refresh ?? channel.last_health_check
          const accessMode = channel.read_only || channel.write_blocked
            ? translate('commerce:commerceHub.readOnly2')
            : translate('commerce:commerceHub.writeEnabled2')
          const capabilities = channel.capabilities_summary.length > 0
            ? formatCapabilityList(channel.capabilities_summary.slice(0, 3))
            : translate('common:status.unavailable')
          const setupReason = channel.status === 'disabled' || channel.status === 'inactive'
            ? translate('commerce:commerceHub.setupReasonDisabled')
            : translate('commerce:commerceHub.setupReasonCredentials')
          const facts = state === 'comingSoon' ? [] : state === 'setupRequired'
            ? [
              { label: translate('commerce:commerceHub.accessMode'), value: accessMode },
              { label: translate('commerce:commerceHub.setupState'), value: formatStatus(channel.configuration_state ?? channel.credential_status) },
            ]
            : [
              { label: translate('commerce:commerceHub.accessMode'), value: accessMode },
              { label: translate('commerce:commerceHub.channelHealthLabel'), value: formatStatus(channel.health.status) },
              { label: translate('commerce:commerceHub.channelLastActivity'), value: lastActivityAt ? formatRelativeTime(lastActivityAt) : translate('commerce:commerceHub.noRecentActivity') },
              { label: translate('commerce:commerceHub.cachedProducts'), value: formatNumber(channel.cached_products) },
              { label: translate('commerce:commerceHub.channelCapabilitiesLabel'), value: capabilities },
              ...(channel.cached_variations > 0 ? [{ label: translate('commerce:commerceHub.cachedVariations'), value: formatNumber(channel.cached_variations) }] : []),
            ]
          const actions: OperationalResourceAction[] = state === 'setupRequired'
            ? canManageCommerce ? [{ label: translate('common:action.setupNow'), primary: true, onClick: () => openSetup(channel.id) }] : []
            : state === 'comingSoon' ? [] : [
              { label: translate('common:action.open'), onClick: () => navigate(`/channels/${encodeURIComponent(channel.id)}`) },
              ...(canManageCommerce ? [{ label: testingId === channel.id ? translate('commerce:commerceHub.testing') : translate('commerce:commerceHub.testConnection'), disabled: testingId === channel.id, onClick: () => void handleTest(channel.id) }] : []),
              ...(canManageCommerce && supportsProductCache ? [{ label: refreshingId === channel.id ? translate('commerce:commerceHub.refreshing') : translate('commerce:commerceHub.refreshProductCache'), disabled: refreshingId === channel.id, onClick: () => void handleRefresh(channel.id) }] : []),
              ...(canViewActivity ? [{ label: translate('common:action.viewActivity'), onClick: () => navigate(`/activity?channel=${encodeURIComponent(channel.id)}`) }] : []),
              ...(canViewDiagnostics ? [{ label: translate('common:action.diagnostics'), onClick: () => navigate(`/diagnostics#channel-${channel.id}`) }] : []),
              ...(canManageCommerce ? [{ label: translate('common:action.settings'), onClick: () => openSetup(channel.id) }] : []),
            ]
          return (
            <OperationalResourceCard
              resourceId={channel.id}
              resourceType="channel"
              provider={channel.provider}
              name={channel.name}
              description={formatStatus(channel.provider)}
              state={state}
              statusLabel={channelBadgeLabel(resource.badge)}
              statusVariant={channelBadgeTone(resource.badge)}
              statusDetail={state === 'connected'
                ? lastActivityAt ? formatRelativeTime(lastActivityAt) : translate('commerce:commerceHub.noRecentActivity')
                : undefined}
              facts={facts}
              issue={state === 'setupRequired'
                ? setupReason
                : channelNeedsOperationalAttention(channel)
                  ? translate('commerce:commerceHub.channelOperationalIssue')
                  : undefined}
              actions={actions}
            />
          )
        }} />
      )}

      {setupTarget && canManageCommerce && (
        <div
          ref={setupDialogRef}
          className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-label={setupResourceId ? translate('common:action.settings') : translate('commerce:commerceHub.addChannel')}
          data-testid="channel-configuration-dialog"
        >
          <div className="max-h-[calc(100vh-2rem)] w-full max-w-4xl overflow-y-auto">
            {setupLoading ? (
              <div className="fh-card fh-card-pad flex items-center gap-2 fh-text-body-sm" role="status" aria-live="polite" aria-busy="true">
                {translate('commerce:commerceHub.loadingChannelConfiguration')}
              </div>
            ) : setupError || setupResourceUnavailable ? (
              <div className="fh-card fh-card-pad" role="alert">
                <h2 className="fh-section-title">{setupResourceUnavailable ? translate('commerce:commerceHub.channelDetails.loadFailed') : translate('commerce:commerceHub.unableToLoadCommerceHub')}</h2>
                <p className="fh-section-subtitle mt-1">{translate('commerce:commerceHub.pleaseTryAgain')}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button type="button" className="fh-button-secondary" onClick={closeSetup}>{translate('commerce:commerceHub.close')}</button>
                  {!setupResourceUnavailable && <button type="button" className="fh-button-primary" onClick={() => {
                    setSetupError(false)
                    setSetupLoading(true)
                    commerce.getChannelTypes()
                      .then(result => setChannelTypes(result.items))
                      .catch(() => setSetupError(true))
                      .finally(() => setSetupLoading(false))
                  }}>{translate('common:action.retry')}</button>}
                </div>
              </div>
            ) : (
              <ConfigPanel
                key={setupTarget}
                kind="channel"
                types={channelTypes}
                initialResourceId={setupResourceId}
                headingLevel={2}
                onCancel={closeSetup}
                onSaved={handleSetupSaved}
              />
            )}
          </div>
        </div>
      )}
    </PageShell>
  )
}
