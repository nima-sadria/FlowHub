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
  commerceChannelSignals,
  isCommerceChannelComingSoon,
  isCommerceTypeComingSoon,
  prepareResourceCollection,
  type ResourceBadge,
  type ResourceTier,
} from '../features/resourceOrdering/resourceOrdering'
import { connectionExceptionMessage, connectionResultMessage } from '../features/diagnostics/connectionErrorPresentation'
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
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { resourceQaFixtureState, withConnectedChannelFixture } from '../dev/resourceQaFixtures'

type ChannelFilter = 'all' | 'active' | 'connected' | 'healthy' | 'attention' | 'disabled' | 'comingSoon'

function channelDisplayName(channel: CommerceChannel): string {
  return formatChannelDisplayName(channel.id, {
    displayName: channel.display_name_custom ? channel.name : undefined,
    displayNameCustom: channel.display_name_custom,
  })
}

function matchesFilter(
  resource: { tier: ResourceTier; badge: ResourceBadge; item: CommerceChannel },
  filter: ChannelFilter,
): boolean {
  const state = channelCardState(resource.item, resource.tier)
  if (filter === 'all') return true
  if (filter === 'connected') return state === 'connected'
  if (filter === 'active') return state !== 'disabled' && state !== 'comingSoon'
  if (filter === 'healthy') return state === 'connected' && resource.badge === 'healthy'
  if (filter === 'attention') return state === 'needsAttention'
  if (filter === 'disabled') return state === 'disabled'
  return state === 'comingSoon'
}

function channelBadgeTone(badge: ResourceBadge): BadgeVariant {
  if (badge === 'healthy') return 'success'
  if (badge === 'warning') return 'warning'
  if (badge === 'disabled') return 'disabled'
  return 'neutral'
}

function normalizedChannelState(value: string | null | undefined): string {
  return String(value ?? '').trim().toLowerCase().replace(/[\s-]+/g, '_')
}

function channelRequiresSetup(channel: CommerceChannel): boolean {
  const configurationState = normalizedChannelState(channel.configuration_state)
  return channel.credential_status !== 'configured'
    || ['not_configured', 'setup_required'].includes(configurationState)
}

function channelCardState(channel: CommerceChannel, tier: ResourceTier): OperationalResourceState {
  if (isCommerceChannelComingSoon(channel) || tier === 'comingSoon') return 'comingSoon'
  if (tier === 'disabled') return 'disabled'
  if (channelRequiresSetup(channel)) return 'setupRequired'
  if (tier === 'attention') return 'needsAttention'
  return 'connected'
}

function channelStatusPresentation(
  state: OperationalResourceState,
  badge: ResourceBadge,
): { label: string; variant: BadgeVariant } {
  if (state === 'comingSoon') return { label: translate('common:resourceBadge.comingSoon'), variant: 'neutral' }
  if (state === 'disabled') return { label: translate('common:status.disabled'), variant: 'disabled' }
  if (state === 'setupRequired') return { label: translate('common:status.setupRequired'), variant: 'warning' }
  if (state === 'needsAttention') return { label: translate('commerce:commerceHub.needsAttentionKpi'), variant: 'warning' }
  if (badge === 'healthy') return { label: translate('common:status.healthy'), variant: 'success' }
  return { label: translate('common:status.configured'), variant: channelBadgeTone(badge) }
}

function channelNeedsOperationalAttention(channel: CommerceChannel): boolean {
  return ['degraded', 'error', 'failed', 'partial_failed', 'unhealthy'].includes(channel.health.status)
    || ['failed', 'partial_failed', 'completed_with_errors', 'completed_with_warnings', 'refresh_failed', 'stale'].includes(normalizedChannelState(channel.cache_refresh_status))
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

  const channelResources = useMemo(
    () => prepareResourceCollection(channels, commerceChannelSignals),
    [channels],
  )
  const setupResourceType = setupResourceId
    ? channelTypes.find(item => item.id === setupResourceId)
    : undefined
  const setupResourceUnavailable = Boolean(setupResourceId && channelTypes.length > 0 && !setupResourceType)
  const setupResourceComingSoon = Boolean(setupResourceId && (
    channelResources.ordered.find(item => item.id === setupResourceId)?.tier === 'comingSoon'
    || (setupResourceType && isCommerceTypeComingSoon(setupResourceType))
  ))
  const visibleChannels = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    return channelResources.ordered
      .filter(resource => matchesFilter(resource, filter))
      .filter(resource => !normalizedQuery
        || resource.displayName.toLocaleLowerCase().includes(normalizedQuery)
        || resource.item.provider.toLocaleLowerCase().includes(normalizedQuery))
  }, [channelResources, filter, query])
  const needsAttentionCount = useMemo(
    () => channelResources.ordered.filter(resource => channelCardState(resource.item, resource.tier) === 'needsAttention').length,
    [channelResources],
  )
  const connectedChannelsCount = useMemo(
    () => channelResources.ordered.filter(resource => channelCardState(resource.item, resource.tier) === 'connected').length,
    [channelResources],
  )
  const healthyListingsTotal = useMemo(
    () => channelResources.ordered
      .filter(resource => channelCardState(resource.item, resource.tier) === 'connected' && resource.badge === 'healthy')
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
    if (!setupTarget || !canManageCommerce) return
    const pageScroller = setupDialogRef.current?.closest('main') ?? document.querySelector('main')
    if (!(pageScroller instanceof HTMLElement)) return
    pageScroller.classList.add('fh-modal-scroll-lock')
    return () => { pageScroller.classList.remove('fh-modal-scroll-lock') }
  }, [canManageCommerce, setupTarget])

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
    const channel = resourceId ? channels.find(item => item.id === resourceId) : undefined
    if (channel && isCommerceChannelComingSoon(channel)) return
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
            ? translate('commerce:commerceHub.isReadyToUse', { value1: channelDisplayName(channel) })
            : translate('commerce:commerceHub.theChannelIsReadyToUse'),
        })
      } else {
        notify.error({
          title: translate('commerce:commerceHub.unableToConnectToTheChannel'),
          description: connectionResultMessage(result),
        })
      }
      await load()
    } catch (error) {
      notify.error({
        title: translate('commerce:commerceHub.unableToConnectToTheChannel'),
        description: connectionExceptionMessage(error),
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
        <div className="flex flex-wrap items-center gap-2">
          <button className="fh-button-secondary" type="button" onClick={() => navigate('/docs/channels')}>
            <Icon name="file" /> {translate('commerce:commerceHub.channelDocumentation')}
          </button>
          {canManageCommerce && (
            <button className="fh-button-primary" type="button" onClick={() => openSetup()}>
              <Icon name="add" /> {translate('commerce:commerceHub.addChannel')}
            </button>
          )}
        </div>
      </div>

      <section className="fh-card fh-card-pad mb-5" aria-label={translate('commerce:commerceHub.channelOperationalFlow')}>
        <p className="fh-text-body-sm font-semibold text-text-base" dir="ltr">{translate('commerce:commerceHub.channelOperationalFlow')}</p>
        <p className="fh-text-caption mt-1">{translate('commerce:commerceHub.channelOperationalFlowHelp')}</p>
      </section>

      <div className="fh-channels-kpi-row">
        <button
          type="button"
          className="fh-kpi-card fh-kpi-card-action"
          data-channel-kpi="connected"
          onClick={() => { setQuery(''); setFilter('connected') }}
        >
          <div className="fh-kpi-card-head">
            <span className="fh-kpi-card-label">{translate('commerce:commerceHub.connectedChannels')}</span>
            <span className="fh-kpi-card-icon"><Icon name="channels" size="sm" /></span>
          </div>
          <div className="fh-kpi-card-value">{connectedChannelsCount}</div>
        </button>
        <button
          type="button"
          className="fh-kpi-card fh-kpi-card-action"
          data-channel-kpi="healthy-listings"
          onClick={() => { setQuery(''); setFilter('healthy') }}
        >
          <div className="fh-kpi-card-head">
            <span className="fh-kpi-card-label">{translate('commerce:commerceHub.healthyListings')}</span>
            <span className="fh-kpi-card-icon"><Icon name="channels" size="sm" /></span>
          </div>
          <div className="fh-kpi-card-value">{formatNumber(healthyListingsTotal)}</div>
        </button>
        <button
          type="button"
          className="fh-kpi-card fh-kpi-card-action"
          data-channel-kpi="attention"
          onClick={() => { setQuery(''); setFilter('attention') }}
        >
          <div className="fh-kpi-card-head">
            <span className="fh-kpi-card-label">{translate('commerce:commerceHub.needsAttentionKpi')}</span>
            <span className="fh-kpi-card-icon"><Icon name="channels" size="sm" /></span>
          </div>
          <div className="fh-kpi-card-value">
            {needsAttentionCount}
              {needsAttentionCount > 0 && <span className="fh-kpi-card-trend fh-kpi-card-trend-danger">{translate('commerce:commerceHub.reviewCaption')}</span>}
          </div>
        </button>
        {orders && (
          <button
            type="button"
            className="fh-kpi-card fh-kpi-card-action"
            data-channel-kpi="orders-today"
            onClick={() => {
              const today = todayIsoDate()
              navigate(`/orders?dateFrom=${today}&dateTo=${today}`)
            }}
          >
            <div className="fh-kpi-card-head">
              <span className="fh-kpi-card-label">{translate('commerce:commerceHub.ordersToday')}</span>
              <span className="fh-kpi-card-icon"><Icon name="channels" size="sm" /></span>
            </div>
            <div className="fh-kpi-card-value">{ordersToday !== null ? formatNumber(ordersToday) : '—'}</div>
          </button>
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
            <option value="connected">{translate('commerce:commerceHub.connectedChannels')}</option>
            <option value="healthy">{translate('common:status.healthy')}</option>
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
        <ManagementResourceSections
          resources={prepareResourceCollection(visibleChannels.map(resource => resource.item), commerceChannelSignals)}
          className="fh-sources-grid fh-channels-grid"
          groupFor={resource => channelCardState(resource.item, resource.tier)}
          renderItem={resource => {
          const channel = resource.item
          const state = channelCardState(channel, resource.tier)
          const supportsProductCache = ['woocommerce', 'snappshop', 'tapsishop', 'technolife'].includes(channel.provider)
            && state !== 'comingSoon'
          const accessMode = channel.read_only || channel.write_blocked
            ? translate('commerce:commerceHub.readOnly2')
            : translate('commerce:commerceHub.writeEnabled2')
          const configurationState = channel.configuration_state
            ?? (channel.credential_status === 'configured' ? 'configured' : 'not_configured')
          const capabilities = channel.capabilities_summary.length > 0
            ? formatCapabilityList(channel.capabilities_summary.slice(0, 3))
            : translate('common:status.unavailable')
          const cachedProducts = `${formatNumber(channel.cached_products)} (${formatStatus(channel.cache_refresh_status)})`
          const facts = state === 'comingSoon' ? [] : state === 'setupRequired' || state === 'disabled'
            ? [
              { label: translate('commerce:commerceHub.accessMode'), value: accessMode },
              { label: translate('commerce:commerceHub.setupState'), value: formatStatus(configurationState) },
            ]
            : [
              { label: translate('commerce:commerceHub.accessMode'), value: accessMode },
              { label: translate('commerce:commerceHub.channelHealthLabel'), value: formatStatus(channel.health.status) },
              { label: translate('commerce:commerceHub.setupState'), value: formatStatus(configurationState) },
              { label: translate('commerce:commerceHub.refreshStatus'), value: formatStatus(channel.cache_refresh_status) },
              { label: translate('commerce:commerceHub.lastCacheRefresh'), value: channel.last_cache_refresh ? formatRelativeTime(channel.last_cache_refresh) : translate('commerce:commerceHub.notRefreshed') },
              { label: translate('commerce:commerceHub.cachedProducts'), value: cachedProducts },
              { label: translate('commerce:commerceHub.channelCapabilitiesLabel'), value: capabilities },
              ...(channel.cached_variations > 0 ? [{ label: translate('commerce:commerceHub.cachedVariations'), value: formatNumber(channel.cached_variations) }] : []),
            ]
          const actions: OperationalResourceAction[] = state === 'setupRequired'
            ? canManageCommerce ? [{ label: translate('common:action.setupNow'), icon: 'settings', primary: true, onClick: () => openSetup(channel.id) }] : []
            : state === 'comingSoon' ? [] : [
              { label: translate('common:action.open'), icon: 'preview', onClick: () => navigate(`/channels/${encodeURIComponent(channel.id)}`) },
              ...(canManageCommerce && state !== 'disabled' ? [{ label: testingId === channel.id ? translate('commerce:commerceHub.testing') : translate('commerce:commerceHub.testConnection'), icon: 'testConnection' as const, disabled: testingId === channel.id, onClick: () => void handleTest(channel.id) }] : []),
              ...(canManageCommerce && state !== 'disabled' && supportsProductCache ? [{ label: refreshingId === channel.id ? translate('commerce:commerceHub.refreshing') : translate('commerce:commerceHub.refreshCache'), icon: 'refresh' as const, disabled: refreshingId === channel.id, onClick: () => void handleRefresh(channel.id) }] : []),
              ...(canViewActivity ? [{ label: translate('common:action.viewActivity'), icon: 'preview' as const, onClick: () => navigate(`/activity?channel=${encodeURIComponent(channel.id)}`) }] : []),
              ...(canViewDiagnostics ? [{ label: translate('common:action.diagnostics'), icon: 'diagnostics' as const, onClick: () => navigate(`/diagnostics#channel-${channel.id}`) }] : []),
              ...(canManageCommerce && channel.settings_available ? [{ label: translate('common:action.settings'), icon: 'settings' as const, onClick: () => openSetup(channel.id) }] : []),
            ]
          const status = channelStatusPresentation(state, resource.badge)
          return (
            <OperationalResourceCard
              resourceId={channel.id}
              resourceType="channel"
              provider={channel.provider}
              name={channelDisplayName(channel)}
              description={formatStatus(channel.provider)}
              state={state}
              statusLabel={status.label}
              statusVariant={status.variant}
              facts={facts}
              issue={state === 'setupRequired'
                ? translate('commerce:commerceHub.setupReasonCredentials')
                : state === 'disabled'
                  ? translate('commerce:commerceHub.setupReasonDisabled')
                  : state === 'needsAttention' || channelNeedsOperationalAttention(channel)
                  ? translate('commerce:commerceHub.channelOperationalIssue')
                  : undefined}
              actions={actions}
            />
          )
          }}
        />
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
          <div className="max-h-[calc(100vh-2rem)] w-full max-w-[45rem] overflow-y-auto">
            {setupLoading ? (
              <div className="fh-card fh-card-pad flex items-center gap-2 fh-text-body-sm" role="status" aria-live="polite" aria-busy="true">
                {translate('commerce:commerceHub.loadingChannelConfiguration')}
              </div>
            ) : setupResourceComingSoon ? (
              <div className="fh-card fh-card-pad" role="status" data-testid="channel-coming-soon-notice">
                <h2 className="fh-section-title">{translate('common:resourceBadge.comingSoon')}</h2>
                <p className="fh-section-subtitle mt-1">{translate('commerce:commerceHub.plannedChannel')}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button type="button" className="fh-button-secondary" onClick={closeSetup}>{translate('commerce:commerceHub.close')}</button>
                  <button type="button" className="fh-button-secondary" onClick={() => navigate('/docs/channels')}>
                    <Icon name="file" /> {translate('commerce:commerceHub.channelDocumentation')}
                  </button>
                </div>
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
