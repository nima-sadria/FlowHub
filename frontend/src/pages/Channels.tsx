import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import Badge, { type BadgeVariant } from '../components/Badge'
import BrandIcon from '../components/BrandIcon'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import {
  commerceChannelSignals,
  prepareResourceCollection,
  type ResourceBadge,
  type ResourceTier,
} from '../features/resourceOrdering/resourceOrdering'
import { localizedChannelBrandName } from '../features/unifiedWorkspace/channelDisplayName'
import { translate } from '../i18n'
import { formatNumber, formatRelativeTime } from '../i18n/format'
import { inputHint } from '../utils/inputHint'
import { useNotification } from '../notifications/NotificationProvider'
import { useServices } from '../services/ServiceContext'
import type { CommerceChannel } from '../services/types'

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
  if (badge === 'healthy' || badge === 'configured') return translate('commerce:commerceHub.channelHealthy')
  if (badge === 'warning') return translate('commerce:commerceHub.needsReview')
  if (badge === 'disabled') return translate('common:resourceBadge.disabled')
  return translate('common:resourceBadge.comingSoon')
}

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10)
}

export default function Channels() {
  const { commerce, orders } = useServices()
  const { user } = useAuth()
  const notify = useNotification()
  const navigate = useNavigate()
  const [channels, setChannels] = useState<CommerceChannel[]>([])
  const [ordersToday, setOrdersToday] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<ChannelFilter>('all')
  const [testingId, setTestingId] = useState<string | null>(null)
  const [refreshingId, setRefreshingId] = useState<string | null>(null)
  const canManageCommerce = user?.is_admin === true

  const channelResources = useMemo(
    () => prepareResourceCollection(channels, commerceChannelSignals),
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
    () => channelResources.ordered.filter(resource => resource.tier === 'attention').length,
    [channelResources],
  )
  const connectedChannelsCount = useMemo(
    () => channelResources.ordered.filter(resource => resource.tier !== 'comingSoon').length,
    [channelResources],
  )
  const healthyListingsTotal = useMemo(
    () => channels.reduce((sum, channel) => sum + (channel.cached_products || 0), 0),
    [channels],
  )

  async function load() {
    setLoading(true)
    setLoadError(false)
    try {
      const today = todayIsoDate()
      const [channelsResult, ordersResult] = await Promise.allSettled([
        commerce.getChannels(),
        orders ? orders.getOrders({ page: 1, pageSize: 1, dateFrom: today, dateTo: today }) : Promise.resolve(null),
      ])
      if (channelsResult.status === 'fulfilled') setChannels(channelsResult.value.items)
      else setLoadError(true)
      if (ordersResult.status === 'fulfilled' && ordersResult.value) setOrdersToday(ordersResult.value.total)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [commerce, orders])

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
          <p className="fh-page-subtitle">{translate('commerce:commerceHub.commerceSystemsThatReceiveCatalogVisibilityFrom')}</p>
        </div>
        {canManageCommerce && (
          <button className="fh-button-primary" type="button" onClick={() => navigate('/commerce?tab=channels')}>
            <Icon name="add" /> {translate('commerce:commerceHub.addChannel')}
          </button>
        )}
      </div>

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

      {loading ? <p className="fh-card fh-card-pad fh-text-caption">{translate('commerce:commerceHub.loadingCommerceHub')}</p> : loadError ? null : visibleChannels.length === 0 ? (
        <div className="fh-card fh-card-pad"><Empty title={translate('commerce:commerceHub.noChannelsFound')} description="" /></div>
      ) : (
        <div className="fh-channels-grid">
          {visibleChannels.map(resource => {
            const channel = resource.item
            const canOpen = resource.section === 'active'
            const supportsProductCache = ['woocommerce', 'snappshop'].includes(channel.provider) && !channel.placeholder
            const isConfigurable = canManageCommerce && channel.implemented && !channel.placeholder && ['woocommerce', 'snappshop', 'tapsishop'].includes(channel.provider)
            return (
              <article className="fh-channel-card" data-channel-card={channel.id} key={channel.id}>
                <div className="fh-channel-card-head">
                  <BrandIcon identity={{ provider: channel.provider }} label={localizedChannelBrandName(channel.provider, channel.name)} size={36} />
                  <h2 className="fh-channel-card-name">{localizedChannelBrandName(channel.provider, channel.name)}</h2>
                </div>

                <div className="fh-channel-card-row">
                  <Badge dot variant={channelBadgeTone(resource.badge)}>{channelBadgeLabel(resource.badge)}</Badge>
                  <span className="fh-text-caption">
                    {!canOpen
                      ? translate('common:resourceBadge.disabled')
                      : channel.last_health_check
                        ? `${translate('commerce:commerceHub.checkedPrefix')} ${formatRelativeTime(channel.last_health_check)}`
                        : translate('commerce:commerceHub.notChecked')}
                  </span>
                </div>

                <div className="fh-channel-card-row">
                  <span className="fh-text-caption">{translate('commerce:commerceHub.listingsCount', { count: channel.cached_products })}</span>
                  {!canOpen ? (
                    <span className="fh-text-caption">{translate('common:resourceBadge.disabled')}</span>
                  ) : isConfigurable ? (
                    <button type="button" className="fh-channel-card-configure" onClick={() => navigate('/commerce?tab=channels')}>
                      {translate('commerce:commerceHub.configure')}
                    </button>
                  ) : null}
                </div>

                {canManageCommerce && canOpen && (
                  <div className="fh-channel-card-actions">
                    <button type="button" className="fh-button-secondary fh-button-sm" disabled={testingId === channel.id} onClick={() => void handleTest(channel.id)}>
                      {testingId === channel.id ? translate('commerce:commerceHub.testing') : translate('commerce:commerceHub.testConnection')}
                    </button>
                    {supportsProductCache && (
                      <button type="button" className="fh-button-secondary fh-button-sm" disabled={refreshingId === channel.id} onClick={() => void handleRefresh(channel.id)}>
                        {refreshingId === channel.id ? translate('commerce:commerceHub.refreshing') : translate('commerce:commerceHub.refreshProductCache')}
                      </button>
                    )}
                  </div>
                )}
              </article>
            )
          })}
        </div>
      )}
    </PageShell>
  )
}
