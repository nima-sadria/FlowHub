import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { useAuth } from '../auth'
import Badge from '../components/Badge'
import BrandIcon from '../components/BrandIcon'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import { translate } from '../i18n'
import { formatCapability, formatStatus } from '../i18n/display'
import { formatDateTime, formatNumber } from '../i18n/format'
import { useNotification } from '../notifications/NotificationProvider'
import { useServices } from '../services/ServiceContext'
import type { CommerceChannelConfiguration } from '../services/commerce/CommerceService'
import type { CommerceChannel } from '../services/types'
import { effectiveHasPerm } from '../utils/permissions'
import { WORKSPACE_PERMISSION } from '../utils/workspacePermissions'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { isCommerceChannelComingSoon } from '../features/resourceOrdering/resourceOrdering'
import { connectionExceptionMessage, connectionResultMessage } from '../features/diagnostics/connectionErrorPresentation'

const DETAIL_SECTIONS = [
  ['overview', 'commerce:commerceHub.channelDetails.overview'],
  ['credentials', 'commerce:commerceHub.channelDetails.credentials'],
  ['connection-test', 'commerce:commerceHub.channelDetails.connectionTest'],
  ['capabilities', 'commerce:commerceHub.channelDetails.capabilities'],
  ['access-mode', 'commerce:commerceHub.channelDetails.accessMode'],
  ['health', 'commerce:commerceHub.channelDetails.health'],
  ['activity', 'commerce:commerceHub.channelDetails.activity'],
  ['diagnostics', 'commerce:commerceHub.channelDetails.diagnostics'],
] as const

function DetailField({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="fh-text-caption">{label}</dt>
      <dd className="mt-1 font-medium text-text-base">{value}</dd>
    </div>
  )
}

export function channelConnectionEvidence(
  channel: Pick<CommerceChannel, 'enabled' | 'credential_status' | 'health'>,
): 'healthy' | 'warning' | 'configured' | 'setupRequired' | 'disabled' {
  if (!channel.enabled) return 'disabled'
  if (channel.credential_status !== 'configured') return 'setupRequired'
  if (channel.health.status === 'healthy') return 'healthy'
  if (['degraded', 'error', 'failed', 'partial_failed', 'unhealthy'].includes(channel.health.status)) {
    return 'warning'
  }
  return 'configured'
}

export default function ChannelDetail() {
  const { channelId = '' } = useParams()
  const navigate = useNavigate()
  const { commerce } = useServices()
  const { user } = useAuth()
  const notify = useNotification()
  const [channel, setChannel] = useState<CommerceChannel | null>(null)
  const [configuration, setConfiguration] = useState<CommerceChannelConfiguration | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [partialFailure, setPartialFailure] = useState(false)
  const [testing, setTesting] = useState(false)
  const canManageCommerce = user?.is_admin === true
  const canViewActivity = effectiveHasPerm(user, WORKSPACE_PERMISSION.readAudit)
  const canViewDiagnostics = effectiveHasPerm(user, 'can_view_settings')

  async function load() {
    setLoading(true)
    setLoadError(false)
    setPartialFailure(false)
    try {
      const channelsResult = await Promise.allSettled([commerce.getChannels()])
      const selected = channelsResult[0].status === 'fulfilled'
        ? channelsResult[0].value.items.find(item => item.id === channelId) ?? null
        : null
      setChannel(selected)
      if (!selected || isCommerceChannelComingSoon(selected)) {
        setConfiguration(null)
        setLoadError(!selected)
        return
      }
      const configurationResult = await Promise.allSettled([commerce.getChannelConfiguration(channelId)])
      setConfiguration(configurationResult[0].status === 'fulfilled' ? configurationResult[0].value : null)
      setLoadError(!selected)
      setPartialFailure(configurationResult[0].status === 'rejected')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [channelId, commerce])

  async function testConnection() {
    if (!channel || !canManageCommerce) return
    setTesting(true)
    try {
      const result = await commerce.testChannel(channel.id)
      if (result.ok) {
        notify.success({
          title: translate('commerce:commerceHub.channelConnectedSuccessfully'),
          description: translate('commerce:commerceHub.isReadyToUse', { value1: formatChannelDisplayName(channel.id, { displayName: channel.display_name_custom ? channel.name : undefined, displayNameCustom: channel.display_name_custom }) }),
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
      setTesting(false)
    }
  }

  const capabilities = useMemo(() => {
    if (!channel) return []
    if (channel.capabilities_summary.length > 0) return channel.capabilities_summary
    return Object.entries(channel.capabilities).filter(([, enabled]) => enabled).map(([name]) => name)
  }, [channel])

  if (loading) {
    return <PageShell><p className="fh-card fh-card-pad fh-text-caption" role="status" aria-live="polite" aria-busy="true">{translate('commerce:commerceHub.loadingChannelConfiguration')}</p></PageShell>
  }

  if (loadError || !channel) {
    return (
      <PageShell>
        <section className="fh-card fh-card-pad" role="alert" aria-busy="false">
          <h1 className="fh-page-title">{translate('commerce:commerceHub.channelDetails.loadFailedTitle')}</h1>
          <p className="fh-page-subtitle mt-2">{translate('commerce:commerceHub.channelDetails.loadFailed')}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button className="fh-button-primary" type="button" onClick={() => navigate('/channels')}>{translate('commerce:commerceHub.channelDetails.backToChannels')}</button>
            <button className="fh-button-secondary" type="button" onClick={() => void load()}>{translate('common:action.retry')}</button>
            {canViewDiagnostics && <button className="fh-button-secondary" type="button" onClick={() => navigate(`/diagnostics#channel-${encodeURIComponent(channelId)}`)}>{translate('common:action.diagnostics')}</button>}
          </div>
        </section>
      </PageShell>
    )
  }

  if (isCommerceChannelComingSoon(channel)) {
    const displayName = formatChannelDisplayName(channel.id, {
      displayName: channel.display_name_custom ? channel.name : undefined,
      displayNameCustom: channel.display_name_custom,
    })
    return (
      <PageShell>
        <div className="fh-page-header">
          <div className="flex min-w-0 items-center gap-3">
            <BrandIcon identity={{ provider: channel.provider }} label={displayName} size={44} />
            <div className="min-w-0">
              <button className="fh-text-caption mb-1" type="button" onClick={() => navigate('/channels')}>â†گ {translate('commerce:commerceHub.channels2')}</button>
              <h1 className="fh-page-title truncate">{displayName}</h1>
              <p className="fh-page-subtitle">{formatStatus(channel.provider)}</p>
            </div>
          </div>
          <Badge dot variant="neutral">{translate('common:resourceBadge.comingSoon')}</Badge>
        </div>
        <section className="fh-card fh-card-pad" data-testid="channel-coming-soon-detail">
          <h2 className="fh-section-title">{translate('common:resourceBadge.comingSoon')}</h2>
          <p className="fh-section-subtitle mt-1">{translate('commerce:commerceHub.plannedChannel')}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="fh-button-secondary" type="button" onClick={() => navigate('/channels')}>{translate('commerce:commerceHub.channelDetails.backToChannels')}</button>
            <button className="fh-button-secondary" type="button" onClick={() => navigate('/docs/channels')}><Icon name="file" /> {translate('commerce:commerceHub.channelDocumentation')}</button>
          </div>
        </section>
      </PageShell>
    )
  }

  const accessMode = configuration?.access_mode
    ?? (channel.read_only || channel.write_blocked ? 'read_only' : 'write_enabled')
  const accessModeLabel = accessMode === 'write_enabled'
    ? translate('commerce:commerceHub.writeEnabled2')
    : translate('commerce:commerceHub.readOnly2')
  const connectionEvidence = channelConnectionEvidence(channel)
  const connectionBadgeLabel = connectionEvidence === 'healthy'
    ? translate('common:status.healthy')
    : connectionEvidence === 'warning'
      ? translate('common:resourceBadge.warning')
      : connectionEvidence === 'configured'
        ? translate('common:status.configured')
        : connectionEvidence === 'disabled'
          ? translate('common:status.disabled')
          : translate('common:status.setupRequired')
  const healthWarning = ['degraded', 'error', 'failed', 'partial_failed', 'unhealthy'].includes(channel.health.status)
  const displayName = formatChannelDisplayName(channel.id, {
    displayName: channel.display_name_custom ? channel.name : undefined,
    displayNameCustom: channel.display_name_custom,
  })

  return (
    <PageShell>
      <div className="fh-page-header">
        <div className="flex min-w-0 items-center gap-3">
          <BrandIcon identity={{ provider: channel.provider }} label={displayName} size={44} />
          <div className="min-w-0">
            <button className="fh-text-caption mb-1" type="button" onClick={() => navigate('/channels')}>← {translate('commerce:commerceHub.channels2')}</button>
            <h1 className="fh-page-title truncate">{displayName}</h1>
            <p className="fh-page-subtitle">{formatStatus(channel.provider)}</p>
          </div>
        </div>
        {canManageCommerce && channel.settings_available && (
          <button className="fh-button-primary" type="button" onClick={() => navigate(`/channels?setup=${encodeURIComponent(channel.id)}`)}>
            <Icon name="settings" /> {translate('common:action.settings')}
          </button>
        )}
      </div>

      <nav className="mb-5 flex gap-2 overflow-x-auto pb-1" aria-label={translate('commerce:commerceHub.openChannel')}>
        {DETAIL_SECTIONS.map(([id, label]) => (
          <a className="fh-button-secondary fh-button-sm whitespace-nowrap" href={`#${id}`} key={id}>{translate(label)}</a>
        ))}
      </nav>

      {partialFailure && (
        <div className="fh-alert fh-alert-warning mb-5" role="status">
          <Icon name="warning" />
          <span className="flex-1">{translate('commerce:commerceHub.partialLoadDescription')}</span>
          <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => void load()}>{translate('common:action.retry')}</button>
        </div>
      )}

      <div className="grid gap-4">
        <section className="fh-card fh-card-pad" id="overview">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="fh-section-title">{translate('commerce:commerceHub.channelDetails.overview')}</h2>
            <Badge dot variant={connectionEvidence === 'healthy' ? 'success' : connectionEvidence === 'warning' || connectionEvidence === 'setupRequired' ? 'warning' : 'disabled'}>
              {connectionBadgeLabel}
            </Badge>
          </div>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <DetailField label={translate('commerce:commerceHub.accessMode')} value={accessModeLabel} />
            <DetailField label={translate('commerce:commerceHub.setupState')} value={formatStatus(channel.configuration_state ?? channel.credential_status)} />
            <DetailField label={translate('commerce:commerceHub.refreshStatus')} value={formatStatus(channel.cache_refresh_status)} />
            <DetailField label={translate('commerce:commerceHub.cachedProducts')} value={formatNumber(channel.cached_products)} />
            <DetailField label={translate('commerce:commerceHub.cachedVariations')} value={formatNumber(channel.cached_variations)} />
            <DetailField label={translate('commerce:commerceHub.lastCacheRefresh')} value={channel.last_cache_refresh ? formatDateTime(channel.last_cache_refresh) : translate('commerce:commerceHub.notRefreshed')} />
          </dl>
        </section>

        <section className="fh-card fh-card-pad" id="credentials">
          <h2 className="fh-section-title">{translate('commerce:commerceHub.channelDetails.credentials')}</h2>
          <p className="fh-text-caption mt-1">{translate('commerce:commerceHub.channelDetails.credentialsProtected')}</p>
          {configuration && Object.keys(configuration.secrets).length > 0 ? (
            <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(configuration.secrets).map(([name, metadata]) => (
                <DetailField label={name.replace(/_/g, ' ')} value={formatStatus(metadata.status)} key={name} />
              ))}
            </dl>
          ) : <p className="fh-text-caption mt-4">{translate('commerce:commerceHub.channelDetails.noCredentialMetadata')}</p>}
        </section>

        <section className="fh-card fh-card-pad" id="connection-test">
          <h2 className="fh-section-title">{translate('commerce:commerceHub.channelDetails.connectionTest')}</h2>
          <p className="fh-text-caption mt-1">{translate('commerce:commerceHub.channelDetails.connectionHelp')}</p>
          {canManageCommerce && channel.enabled && (
            <button className="fh-button-secondary mt-4" type="button" disabled={testing} onClick={() => void testConnection()}>
              <Icon name="testConnection" /> {testing ? translate('commerce:commerceHub.testing') : translate('commerce:commerceHub.testConnection')}
            </button>
          )}
        </section>

        <section className="fh-card fh-card-pad" id="capabilities">
          <h2 className="fh-section-title">{translate('commerce:commerceHub.channelDetails.capabilities')}</h2>
          <div className="mt-4 flex flex-wrap gap-2">
            {capabilities.length > 0
              ? capabilities.map(capability => <Badge variant="neutral" key={capability}>{formatCapability(capability)}</Badge>)
              : <span className="fh-text-caption">{translate('common:status.unavailable')}</span>}
          </div>
        </section>

        <section className="fh-card fh-card-pad" id="access-mode">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="fh-section-title">{translate('commerce:commerceHub.channelDetails.accessMode')}</h2>
            <Badge variant={accessMode === 'write_enabled' ? 'warning' : 'neutral'}>{accessModeLabel}</Badge>
          </div>
          <p className="fh-alert fh-alert-info mt-4">{translate('commerce:commerceHub.channelDetails.writeSafety')}</p>
        </section>

        <section className="fh-card fh-card-pad" id="health">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="fh-section-title">{translate('commerce:commerceHub.channelDetails.health')}</h2>
            <Badge dot variant={channel.health.status === 'healthy' ? 'success' : healthWarning ? 'warning' : 'neutral'}>{formatStatus(channel.health.status)}</Badge>
          </div>
          <dl className="mt-4 grid gap-4 sm:grid-cols-3">
            <DetailField label={translate('commerce:commerceHub.lastHealthCheck')} value={channel.last_health_check ? formatDateTime(channel.last_health_check) : translate('commerce:commerceHub.notChecked')} />
            <DetailField label={translate('commerce:commerceHub.latestResult')} value={channel.health.message || formatStatus(channel.health.status)} />
            <DetailField label={translate('commerce:commerceHub.channelDetails.latency')} value={channel.health.latency_ms !== null ? `${channel.health.latency_ms} ms` : translate('common:status.unavailable')} />
          </dl>
        </section>

        <section className="fh-card fh-card-pad" id="activity">
          <h2 className="fh-section-title">{translate('commerce:commerceHub.channelDetails.activity')}</h2>
          {canViewActivity && <button className="fh-button-secondary mt-4" type="button" onClick={() => navigate(`/activity?channel=${encodeURIComponent(channel.id)}`)}>{translate('common:action.viewActivity')}</button>}
        </section>

        <section className="fh-card fh-card-pad" id="diagnostics">
          <h2 className="fh-section-title">{translate('commerce:commerceHub.channelDetails.diagnostics')}</h2>
          {canViewDiagnostics && <button className="fh-button-secondary mt-4" type="button" onClick={() => navigate(`/diagnostics#channel-${channel.id}`)}>{translate('common:action.diagnostics')}</button>}
        </section>
      </div>
    </PageShell>
  )
}
