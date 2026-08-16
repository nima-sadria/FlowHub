import { translate } from '../i18n'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import { useAuth } from '../auth'
import { ApiError, apiErrorMessage } from '../api/client'
import Badge from '../components/Badge'
import Alert from '../components/Alert'
import { useServices } from '../services/ServiceContext'
import type { CommerceChannel, CommerceRelationshipMap, CommerceSource, CommerceTypeField, CommerceTypeOption } from '../services/types'
import type { ChannelCacheRefreshResult, CommerceConfigPayload, CommerceSourceConfiguration, CommerceVendor, ConnectionCheckResult, NextcloudBrowseItem, NextcloudBrowseResult } from '../services/commerce/CommerceService'
import Spinner from '../components/loading/Spinner'
import SecretField from '../components/SecretField'
import BrandIcon from '../components/BrandIcon'
import { useNotification } from '../notifications/NotificationProvider'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import { formatDateTime } from '../i18n/format'
import { localizedChannelName } from '../features/unifiedWorkspace/channelDisplayName'
import { formatCapabilityList, formatCommerceType, formatDataRole, formatStatus } from '../i18n/display'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import { ResourceOptionGroups, ResourceSectionList, ResourceStateBadge } from '../components/ResourceOrdering'
import {
  commerceChannelSignals,
  commerceSourceSignals,
  commerceTypeSignals,
  isCommerceChannelComingSoon,
  isCommerceTypeComingSoon,
  prepareResourceCollection,
  preferredResourceId,
  type ResourceBadge,
} from '../features/resourceOrdering/resourceOrdering'
import { connectionExceptionMessage, connectionResultMessage } from '../features/diagnostics/connectionErrorPresentation'

type Tab = 'sources' | 'channels'
type FormKind = 'source' | 'channel'

function sourceConfigurationReturnPath(value: string | null): string | null {
  if (!value || !/^\/sources\/[^/?#]+$/.test(value)) return null
  return value
}
export type ReadPolicyDraft = { enabled: boolean; max_reads_per_24h: number; manual_read_allowed: boolean }

export const DEFAULT_READ_POLICY: ReadPolicyDraft = {
  enabled: true,
  max_reads_per_24h: 10,
  manual_read_allowed: true,
}

const CHANNEL_VISIBLE_FIELDS: Record<string, ReadonlySet<string>> = {
  snappshop: new Set(['token', 'agent_identifier']),
  tapsishop: new Set(['token', 'webhook_token']),
  digikala: new Set(['access_token', 'refresh_token']),
  technolife: new Set(['api_key', 'encryption_secret']),
}

function snappShopVendorActive(status: string | null | undefined): boolean {
  if (!status) return true
  return ['ACTIVE', 'ENABLED', 'TRUE', '1'].includes(status.trim().toUpperCase())
}

function SafetyBadges({
  readOnly,
  writeBlocked,
  writeEnabled = false,
}: {
  readOnly: boolean
  writeBlocked: boolean
  writeEnabled?: boolean
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {writeEnabled && <Badge variant="warning">{translate('commerce:commerceHub.writeEnabled2')}</Badge>}
      {readOnly && <Badge variant="neutral">{translate('commerce:commerceHub.readOnlyMode')}</Badge>}
      {writeBlocked && <Badge variant="danger">{translate('commerce:commerceHub.writesBlocked')}</Badge>}
    </div>
  )
}

function RelationshipMap({ map }: { map: CommerceRelationshipMap | null }) {
  const nodes = map?.nodes?.map(formatCommerceType) ?? [translate('commerce:commerceHub.source'), translate('commerce:commerceHub.flowhubDataLayer'), translate('commerce:commerceHub.channel')]
  const example = (map?.example ?? ['Nextcloud', translate('commerce:commerceHub.dataLayer'), 'WooCommerce']).map(formatCommerceType)
  return (
    <div className="fh-card fh-card-pad">
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr_auto_1fr] gap-3 items-center text-center">
        <div className="fh-stat-tile">
          <p className="fh-stat-tile-label">{nodes[0]}</p>
          <p className="fh-text-body font-semibold">{example[0]}</p>
        </div>
        <div className="text-xl text-wp-muted">/</div>
        <div className="fh-stat-tile">
          <p className="fh-stat-tile-label">{translate('commerce:commerceHub.flowhub')}</p>
          <p className="fh-text-body font-semibold">{example[1]}</p>
        </div>
        <div className="text-xl text-wp-muted">/</div>
        <div className="fh-stat-tile">
          <p className="fh-stat-tile-label">{nodes[2]}</p>
          <p className="fh-text-body font-semibold">{example[2]}</p>
        </div>
      </div>
    </div>
  )
}

function persistedSourceSetupState(source: CommerceSource): 'not_configured' | 'setup_required' | 'configured' {
  if (source.configuration_state === 'configured') return 'configured'
  if (source.configuration_state === 'setup_required') return 'setup_required'
  if (source.configuration_state === 'not_configured') return 'not_configured'
  return source.credential_status === 'configured' ? 'configured' : 'not_configured'
}

function SourceSetupBadge({ source, fallback }: { source: CommerceSource; fallback: ResourceBadge }) {
  if (source.placeholder || !source.implemented) return <ResourceStateBadge badge={fallback} />
  if (source.lifecycle_status === 'archived') {
    return <Badge variant="neutral">{translate('common:status.archived')}</Badge>
  }
  if (source.enabled === false) {
    return <Badge variant="neutral">{translate('commerce:commerceHub.sourceDisabled')}</Badge>
  }
  const state = persistedSourceSetupState(source)
  const presentation = state === 'configured'
    ? { label: translate('commerce:commerceHub.sourceStatus.configured'), variant: 'success' as const }
    : state === 'setup_required'
      ? { label: translate('commerce:commerceHub.sourceStatus.connectedSetupRequired'), variant: 'info' as const }
      : { label: translate('commerce:commerceHub.sourceStatus.addNow'), variant: 'warning' as const }
  return <Badge variant={presentation.variant}>{presentation.label}</Badge>
}

function SourceCard({ source, badge, onTest, onEdit, onConfigure, testing, canManage }: {
  source: CommerceSource
  badge: ResourceBadge
  onTest: (sourceId: string) => void
  onEdit: (sourceId: string) => void
  onConfigure: (sourceId: string) => void
  testing: boolean
  canManage: boolean
}) {
  const sourceArchived = source.lifecycle_status === 'archived'
  const canUseNextcloudActions = canManage && source.provider === 'nextcloud' && !source.placeholder && !sourceArchived
  const sourceDisabled = source.enabled === false
  const canOpenDataSheet = !sourceDisabled && source.configuration_state === 'configured'
  const canTestSavedConnection = !sourceDisabled && source.connection_configured === true
  const readStatus = source.read_status
  return (
    <div
      className="fh-card fh-card-pad flex flex-col gap-3"
      data-source-id={source.id}
      title={formatDataRole(source.data_role)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <BrandIcon identity={{ provider: source.provider, sourceType: source.type }} label={source.name} size={44} />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="fh-section-title">{source.name}</h3>
              <SourceSetupBadge source={source} fallback={badge} />
            </div>
          </div>
        </div>
        <span className="fh-text-caption font-medium text-text-base">{formatCommerceType(source.type)}</span>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="neutral">{sourceArchived ? translate('common:status.archived') : sourceDisabled ? translate('commerce:commerceHub.sourceDisabled') : formatStatus(source.health?.status ?? "unknown")}</Badge>
        <span className="fh-text-caption">{translate('commerce:commerceHub.lastRead')} {readStatus?.last_read_at ? formatDateTime(readStatus.last_read_at) : translate('commerce:commerceHub.notRead')}</span>
      </div>

      <details className="rounded-lg border border-border bg-bg-subtle p-3">
        <summary className="cursor-pointer font-medium text-text-base">{translate('commerce:commerceHub.details')}</summary>
        <div className="fh-form-grid mt-3 sm:grid-cols-2 fh-text-caption">
          <p><span className="text-wp-muted">{translate('commerce:commerceHub.credentialStatus')} </span><span className="font-medium text-text-base">{formatStatus(source.credential_status)}</span></p>
          <p><span className="text-wp-muted">{translate('commerce:commerceHub.lastHealthCheck')} </span><span className="font-medium text-text-base">{source.last_health_check ? formatDateTime(source.last_health_check) : translate('commerce:commerceHub.notChecked')}</span></p>
          <p><span className="text-wp-muted">{translate('commerce:commerceHub.dataRole')} </span><span className="font-medium text-text-base">{formatDataRole(source.data_role)}</span></p>
          {source.archived_at && <p><span className="text-wp-muted">{translate('sources:sourceCenter.archivedAt')} </span><span className="font-medium text-text-base">{formatDateTime(source.archived_at)}</span></p>}
          {readStatus && <>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.readsRemaining')} </span><span className="font-medium text-text-base">{readStatus.reads_remaining}</span></p>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.lastReadStatus')} </span><span className="font-medium text-text-base">{readStatus.last_read_status ? formatStatus(readStatus.last_read_status) : translate('commerce:commerceHub.notRead')}</span></p>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.lastRowCount')} </span><span className="font-medium text-text-base">{readStatus.last_row_count ?? '-'}</span></p>
          </>}
        </div>
      </details>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <SafetyBadges readOnly={source.read_only} writeBlocked={source.runtime_write_blocked} />
        {canUseNextcloudActions && (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              aria-label={translate('commerce:commerceHub.editConnection')}
              onClick={() => onEdit(source.id)}
              className="fh-button-secondary fh-button-sm"
            >
              <Icon name="settings" />
              {translate('commerce:commerceHub.editConnection')}
            </button>
            {canOpenDataSheet && (
              <button
                type="button"
                onClick={() => onConfigure(source.id)}
                className="fh-button-secondary fh-button-sm"
              >
                <Icon name="workspace" />
                {translate('commerce:commerceHub.configureData')}
              </button>
            )}
            {canTestSavedConnection && (
              <button
                onClick={() => onTest(source.id)}
                disabled={testing}
                className="fh-button-secondary fh-button-sm"
              >
                {testing && <Spinner size="sm" />}
                {!testing && <Icon name="testConnection" />}
                {testing ? translate('commerce:commerceHub.testing') : translate('commerce:commerceHub.testConnection')}
              </button>
            )}
          </div>
        )}
        {sourceArchived && source.source_profile_id && (
          <button type="button" className="fh-button-secondary fh-button-sm" onClick={() => onConfigure(source.id)}>
            <Icon name="preview" /> {translate('sources:sourceCenter.viewDataSheet')}
          </button>
        )}
      </div>
    </div>
  )
}

function ChannelCard({ channel, badge, onTest, onRefresh, onConfigure, testing, refreshing, refreshResult, canManage }: {
  channel: CommerceChannel
  badge: ResourceBadge
  onTest: (channelId: string) => void
  onRefresh: (channelId: string) => void
  onConfigure: (channelId: string) => void
  testing: boolean
  refreshing: boolean
  refreshResult?: ChannelCacheRefreshResult
  canManage: boolean
}) {
  const comingSoon = isCommerceChannelComingSoon(channel) || !channel.settings_available
  const isWooCommerce = channel.provider === 'woocommerce' && !comingSoon
  const supportsProductCache = ['woocommerce', 'snappshop', 'tapsishop'].includes(channel.provider) && !comingSoon
  const isConfigurable = !comingSoon && channel.implemented && ['woocommerce', 'snappshop', 'tapsishop', 'digikala'].includes(channel.provider)
  const isConfigured = channel.credential_status === 'configured'
  return (
    <div className="fh-card fh-card-pad flex flex-col gap-3" title={formatCapabilityList(channel.capabilities_summary)}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <BrandIcon identity={{ provider: channel.provider }} label={localizedChannelName(channel.id, channel.name, channel.display_name_custom)} size={44} />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="fh-section-title">{localizedChannelName(channel.id, channel.name, channel.display_name_custom)}</h3>
              <ResourceStateBadge badge={badge} />
            </div>
          </div>
        </div>
        <span className="fh-text-caption font-medium text-text-base">{formatCommerceType(channel.type)}</span>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="neutral">{formatStatus(channel.health?.status ?? "unknown")}</Badge>
        <span className="fh-text-caption">{translate('commerce:commerceHub.lastHealthCheck')} {channel.last_health_check ? formatDateTime(channel.last_health_check) : translate('commerce:commerceHub.notChecked')}</span>
      </div>

      <details className="rounded-lg border border-border bg-bg-subtle p-3">
        <summary className="cursor-pointer font-medium text-text-base">{translate('commerce:commerceHub.details')}</summary>
        <div className="fh-form-grid mt-3 sm:grid-cols-2 fh-text-caption">
        <p><span className="text-wp-muted">{translate('commerce:commerceHub.credentialStatus')} </span><span className="font-medium text-text-base">{formatStatus(channel.credential_status)}</span></p>
        {channel.provider === "snappshop" && (
          <>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.setupState')} </span><span className="font-medium text-text-base">{formatStatus(channel.configuration_state ?? "not_configured")}</span></p>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.vendorSelected')} </span><span className="font-medium text-text-base">{channel.vendor_selected ? translate('commerce:commerceHub.yes') : translate('commerce:commerceHub.no')}</span></p>
          </>
        )}
        <p><span className="text-wp-muted">{translate('commerce:commerceHub.lastHealthCheck')} </span><span className="font-medium text-text-base">{channel.last_health_check ? formatDateTime(channel.last_health_check) : translate('commerce:commerceHub.notChecked')}</span></p>
        <p><span className="text-wp-muted">{translate('commerce:commerceHub.health')} </span><span className="font-medium text-text-base">{formatStatus(channel.health?.status ?? "unknown")}</span></p>
        <p><span className="text-wp-muted">{translate('commerce:commerceHub.capabilities')} </span><span className="font-medium text-text-base">{formatCapabilityList(channel.capabilities_summary)}</span></p>
        {channel.provider === "tapsishop" && (
          <>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.apiCredentials')} </span><span className="font-medium text-text-base">{channel.token_configured ? translate('commerce:commerceHub.configured') : translate('commerce:commerceHub.notConfigured2')}</span></p>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.webhookCredentials')} </span><span className="font-medium text-text-base">{channel.webhook_token_configured ? translate('commerce:commerceHub.configured') : translate('commerce:commerceHub.notConfigured2')}</span></p>
          </>
        )}
        {supportsProductCache && (
          <>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.cachedProducts')} </span><span className="font-medium text-text-base">{channel.cached_products}</span></p>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.cachedVariations')} </span><span className="font-medium text-text-base">{channel.cached_variations}</span></p>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.lastCacheRefresh')} </span><span className="font-medium text-text-base">{channel.last_cache_refresh ? formatDateTime(channel.last_cache_refresh) : translate('commerce:commerceHub.notRefreshed')}</span></p>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.refreshStatus')} </span><span className="font-medium text-text-base">{formatStatus(channel.cache_refresh_status)}</span></p>
          </>
        )}
        {refreshResult && (
          <p className="sm:col-span-2" role="status">
            <span className="text-wp-muted">{translate('commerce:commerceHub.latestResult')} </span>
            <span className="font-medium text-text-base">
              {refreshResult.pages_read ?? 0} {translate('commerce:commerceHub.pageS')} {refreshResult.products_received ?? refreshResult.products_read} {translate('commerce:commerceHub.received')} {refreshResult.products_stored ?? refreshResult.cache_rows_upserted} {translate('commerce:commerceHub.cached')}
            </span>
          </p>
        )}
        </div>
      </details>

      <div className="flex items-center justify-between gap-3">
        <SafetyBadges readOnly={channel.read_only} writeBlocked={channel.write_blocked} />
        {canManage && (
          <div className="flex flex-wrap gap-2 justify-end">
            {isConfigurable && (
              <button
                type="button"
                onClick={() => onConfigure(channel.id)}
                disabled={testing || refreshing}
                className="fh-button-secondary"
              >
                <Icon name={isConfigured ? "settings" : "edit"} />
                {isConfigured ? translate('commerce:commerceHub.settings') : translate('commerce:commerceHub.configure')}
              </button>
            )}
            {isConfigurable && (
              <button
                onClick={() => onTest(channel.id)}
                disabled={testing || refreshing || !isConfigured}
                className="fh-button-secondary"
              >
                {testing && <Spinner size="sm" />}
                {!testing && <Icon name="testConnection" />}
                {testing ? translate('commerce:commerceHub.testing') : translate('commerce:commerceHub.testConnection')}
              </button>
            )}
            {supportsProductCache && (isWooCommerce || isConfigured) && (
              <button
                onClick={() => onRefresh(channel.id)}
                disabled={testing || refreshing}
                className="fh-button-secondary"
              >
                {refreshing && <Spinner size="sm" />}
                {!refreshing && <Icon name="refresh" />}
                {refreshing ? translate('commerce:commerceHub.refreshing') : translate('commerce:commerceHub.refreshCache')}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function fieldLabel(kind: FormKind, provider: string, key: string, fallback: string): string {
  if (kind === 'source' && provider === 'nextcloud' && key === 'url') return translate('commerce:commerceHub.fields.nextcloudServerUrl')
  if (kind === 'source' && provider === 'nextcloud' && key === 'password') return translate('commerce:commerceHub.fields.appPasswordToken')
  if (kind === 'channel' && provider === 'woocommerce' && key === 'url') return translate('commerce:commerceHub.fields.storeUrl')
  if (kind === 'channel' && provider === 'woocommerce' && key === 'key') return translate('commerce:commerceHub.fields.consumerKey')
  if (kind === 'channel' && provider === 'woocommerce' && key === 'secret') return translate('commerce:commerceHub.fields.consumerSecret')
  if (kind === 'channel' && provider === 'woocommerce' && key === 'webhook_secret') return translate('commerce:commerceHub.fields.webhookSecret')
  if (kind === 'channel' && provider === 'tapsishop') {
    const labels: Record<string, string> = {
      base_url: translate('commerce:commerceHub.fields.tapsishopBaseUrl'),
      request_timeout: translate('commerce:commerceHub.fields.requestTimeout'),
      selected_vendor_id: translate('commerce:commerceHub.fields.tapsishopVendorId'),
      token_refresh_enabled: translate('commerce:commerceHub.fields.tokenRefreshEnabled'),
      token_refresh_name: translate('commerce:commerceHub.fields.tokenRefreshName'),
      revoke_current_token: translate('commerce:commerceHub.fields.revokeCurrentToken'),
      token: translate('commerce:commerceHub.fields.tapsishopAuthorizationToken'),
      webhook_token: translate('commerce:commerceHub.fields.tapsishopWebhookToken'),
    }
    return labels[key] ?? fallback
  }
  if (kind === 'channel' && provider === 'technolife') {
    const labels: Record<string, string> = {
      api_key: translate('commerce:commerceHub.fields.technolifeApiKey'),
      encryption_secret: translate('commerce:commerceHub.fields.technolifeEncryptionSecret'),
    }
    return labels[key] ?? fallback
  }
  if (['seller_id', 'merchant_id'].includes(key)) return translate('commerce:commerceHub.fields.sellerStoreId')
  if (['api_key', 'api_token'].includes(key)) return translate('commerce:commerceHub.fields.apiKeyToken')
  return fallback
}

function validateNextcloudBaseUrl(value: string): string | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  try {
    const url = new URL(trimmed)
    const path = url.pathname.replace(/\/$/, '').toLowerCase()
    if (
      path.includes('/index.php/s/') ||
      path.endsWith('/index.php/s') ||
      path === '/s' ||
      path.endsWith('/s') ||
      path.startsWith('/s/') ||
      path.includes('/s/')
    ) {
      return translate('commerce:commerceHub.validation.publicShareUnsupported')
    }
    if (path.includes('/public.php/dav/files')) {
      return translate('commerce:commerceHub.validation.publicShareUnsupported')
    }
    const marker = '/remote.php/dav/files/'
    if (path.includes(marker) && !url.search && !url.hash) {
      const username = path.slice(path.indexOf(marker) + marker.length).split('/')[0]
      return username ? null : translate('commerce:commerceHub.validation.useNextcloudRootOrWebdav')
    }
    if (path.includes('/remote.php/dav/files') || path.includes('/remote.php/dav') || path.includes('/apps/files') || url.search || url.hash) {
      return translate('commerce:commerceHub.validation.useNextcloudRootOrWebdav')
    }
  } catch {
    return translate('commerce:commerceHub.validation.useNextcloudRootOrWebdav')
  }
  return null
}

function webdavUsernameFromUrl(value: string): string {
  try {
    const path = new URL(value.trim()).pathname.replace(/\/$/, '')
    const marker = '/remote.php/dav/files/'
    const index = path.toLowerCase().indexOf(marker)
    if (index < 0) {
      return ''
    }
    return decodeURIComponent(path.slice(index + marker.length).split('/')[0] || '').trim()
  } catch {
    return ''
  }
}

function webdavUrlUsernameMismatch(value: string, username: string): string | null {
  const usernameFromUrl = webdavUsernameFromUrl(value)
  if (usernameFromUrl && username.trim() && username.trim() !== usernameFromUrl) {
    return translate('commerce:commerceHub.validation.webdavUsernameMismatch')
  }
  return null
}

function hasNextcloudUsername(settings: Record<string, string>): boolean {
  return Boolean(settings.username || webdavUsernameFromUrl(String(settings.url ?? '')))
}

function nextcloudUrlErrorFor(settings: Record<string, string>): string | null {
  const urlError = validateNextcloudBaseUrl(String(settings.url ?? ''))
  if (urlError) {
    return urlError
  }
  return webdavUrlUsernameMismatch(String(settings.url ?? ''), String(settings.username ?? ''))
}

type SavedNextcloudConnection = {
  url: string
  username: string
  passwordConfigured: boolean
}

function nextcloudConnectionSnapshot(
  settings: Record<string, string>,
  passwordConfigured: boolean,
): SavedNextcloudConnection | null {
  const url = String(settings.url ?? '').trim()
  const username = String(settings.username || webdavUsernameFromUrl(url)).trim()
  return url && username && passwordConfigured ? { url, username, passwordConfigured: true } : null
}

function nextcloudFailureCategory(result: Pick<ConnectionCheckResult, 'status' | 'message' | 'code' | 'error_class'>):
  | 'disabled'
  | 'timeout'
  | 'authentication'
  | 'permission_denied'
  | 'invalid_url'
  | 'invalid_webdav_path'
  | 'not_configured'
  | 'spreadsheet_unsupported'
  | 'dns_failure'
  | 'tls_failure'
  | 'unreachable'
  | 'unsafe_destination'
  | 'resource_not_found'
  | null {
  const identity = [result.code, result.error_class, result.status].filter(Boolean).join(' ').toLowerCase()
  const message = String(result.message || '').toLowerCase()
  const evidence = `${identity} ${message}`
  if (/(^|[\s_.-])source_disabled($|[\s_.-])|(^|[\s_.-])disabled($|[\s_.-])/.test(identity)) return 'disabled'
  if (/unsafe_destination|ssrf|private.network|trusted.network|blocked.*destination/.test(evidence)) return 'unsafe_destination'
  if (/timeout|timed.out|deadline.exceeded|did not respond in time/.test(evidence)) return 'timeout'
  if (/permission.denied|authorization.failed|forbidden|access.denied/.test(evidence)) return 'permission_denied'
  if (/authentication|unauthorized|invalid.credential/.test(evidence)) return 'authentication'
  if (/not.configured|required.settings.missing/.test(evidence)) return 'not_configured'
  if (/spreadsheet.unsupported|unsupported.*xlsx|supported.*xlsx/.test(evidence)) return 'spreadsheet_unsupported'
  if (/invalid.url|malformed.url/.test(evidence)) return 'invalid_url'
  if (/invalid.webdav|webdav.path|malformed.*path|invalid.*path/.test(evidence)) return 'invalid_webdav_path'
  if (/file.not.found|spreadsheet.not.found|resource.not.found|missing.resource|\b404\b/.test(evidence)) return 'resource_not_found'
  if (/dns|name.resolution|host.not.found|nxdomain/.test(evidence)) return 'dns_failure'
  if (/tls|ssl|certificate/.test(evidence)) return 'tls_failure'
  if (/connection.failed|unreachable|dns|name resolution|connection refused|failed to fetch|networkerror|network|tls|certificate|502|503/.test(evidence)) return 'unreachable'
  return null
}

function nextcloudConnectionFailureMessage(
  result: Pick<ConnectionCheckResult, 'status' | 'message' | 'code' | 'error_class'>,
): string {
  const category = nextcloudFailureCategory(result)
  if (category === 'disabled') return translate('commerce:commerceHub.connectionError.disabled')
  if (category === 'unsafe_destination') return translate('errors:codes.unsafe_destination')
  if (category === 'timeout') return translate('commerce:commerceHub.connectionError.timeout')
  if (category === 'authentication') return translate('commerce:commerceHub.connectionError.authenticationRejected')
  if (category === 'permission_denied') return translate('commerce:commerceHub.connectionError.permissionDenied')
  if (category === 'invalid_url') return translate('commerce:commerceHub.connectionError.invalidUrl')
  if (category === 'invalid_webdav_path') return translate('commerce:commerceHub.connectionError.invalidWebdavPath')
  if (category === 'not_configured') return translate('commerce:commerceHub.connectionError.notConfigured')
  if (category === 'spreadsheet_unsupported') return translate('commerce:commerceHub.connectionError.spreadsheetUnsupported')
  if (category === 'resource_not_found') return translate('commerce:commerceHub.connectionError.resourceNotFound')
  if (category === 'dns_failure') return translate('commerce:commerceHub.connectionError.dnsFailure')
  if (category === 'tls_failure') return translate('commerce:commerceHub.connectionError.tlsFailure')
  if (category === 'unreachable') return translate('commerce:commerceHub.connectionError.unreachable')
  return translate('commerce:commerceHub.connectionError.unknown')
}

function nextcloudPersistedTestMessage(
  result: NonNullable<CommerceSourceConfiguration['last_test']>,
): string {
  if (['healthy', 'operational', 'connected'].includes(result.status.trim().toLowerCase())) {
    return translate(
      /spreadsheet found/i.test(result.message)
        ? 'commerce:commerceHub.connectionTestSuccessfulSpreadsheet'
        : 'commerce:commerceHub.connectionTestSuccessful',
    )
  }
  return nextcloudConnectionFailureMessage({
    status: result.status,
    message: result.message,
    code: result.error_code ?? undefined,
    error_class: result.error_code ?? undefined,
  })
}

function nextcloudConnectionExceptionMessage(error: unknown): string {
  const safeMessage = apiErrorMessage(error, translate('commerce:commerceHub.connectionError.unknown'))
  if (error instanceof ApiError
    && [401, 403].includes(error.status)
    && !['authentication_failed', 'permission_denied'].includes(String(error.code || '').toLowerCase())) {
    return safeMessage
  }
  const result = {
    status: error instanceof ApiError ? String(error.status) : '',
    code: error instanceof ApiError ? error.code : undefined,
    error_class: error instanceof Error ? error.name : undefined,
    message: safeMessage,
  }
  return nextcloudConnectionFailureMessage(result)
}

function NextcloudFilePicker({
  data,
  loading,
  error,
  requestedPath,
  selectedPath,
  onClose,
  onRetry,
  onOpenDirectory,
  onSelectFile,
}: {
  data: NextcloudBrowseResult | null
  loading: boolean
  error: string | null
  requestedPath: string
  selectedPath: string
  onClose: () => void
  onRetry: () => void
  onOpenDirectory: (path: string) => void
  onSelectFile: (file: NextcloudBrowseItem) => void
}) {
  const currentPath = data?.path ?? requestedPath
  const parentPath = currentPath === '/' ? null : `/${currentPath.split('/').filter(Boolean).slice(0, -1).join('/')}`
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4" role="presentation">
      <div className="fh-card w-full max-w-3xl max-h-[80vh] overflow-hidden flex flex-col" role="dialog" aria-modal="true" aria-labelledby="nextcloud-file-picker-title">
        <div className="fh-panel-header !min-h-0 !items-start">
          <div>
            <h3 className="fh-section-title" id="nextcloud-file-picker-title">{translate('commerce:commerceHub.browseNextcloud')}</h3>
            <p className="fh-section-subtitle mt-1" data-testid="nextcloud-current-folder">{currentPath}</p>
          </div>
          <button type="button" onClick={onClose} className="fh-button-secondary">
            <Icon name="close" />
            {translate('commerce:commerceHub.close')}
          </button>
        </div>
        <div className="overflow-auto p-4">
          {error && (
            <div className="fh-error-alert mb-3 flex flex-wrap items-center justify-between gap-3" role="alert">
              <span>{error}</span>
              <button type="button" onClick={onRetry} disabled={loading} className="fh-button-secondary fh-button-sm">
                {translate('common:action.retry')}
              </button>
            </div>
          )}
          {loading ? (
            <div className="flex items-center gap-2 fh-text-body-sm" role="status" aria-live="polite"><Spinner size="sm" />{translate('commerce:commerceHub.loadingFiles')}</div>
          ) : (
            <div className="flex flex-col gap-2">
              {parentPath !== null && (
                <button type="button" onClick={() => onOpenDirectory(parentPath || '/')} className="fh-button-secondary justify-start">
                  <Icon name="previous" mirrorRtl />
                  {translate('commerce:commerceHub.upOneFolder')}
                </button>
              )}
              {data?.directories.map(directory => (
                <button
                  key={directory.path}
                  type="button"
                  onClick={() => onOpenDirectory(directory.path)}
                  className="fh-button-secondary justify-start"
                >
                  <Icon name="folder" />
                  {directory.name}
                </button>
              ))}
              {data?.files.map(file => {
                const selected = file.path === selectedPath
                return (
                  <button
                    key={file.path}
                    type="button"
                    disabled={!file.supported}
                    onClick={() => onSelectFile(file)}
                    className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-3 text-left fh-text-body disabled:opacity-60 ${selected ? 'border-accent bg-accent/5' : 'border-border bg-bg-base'}`}
                    data-selected={selected}
                    aria-pressed={selected}
                  >
                    <span className="inline-flex min-w-0 items-center gap-2 font-medium text-text-base">
                      <Icon name="file" />
                      <span className="truncate">{file.name}</span>
                    </span>
                    <span className="inline-flex items-center gap-2 fh-text-caption">
                      {selected && <Badge variant="success">{translate('commerce:commerceHub.fileSelected')}</Badge>}
                      {file.supported ? translate('commerce:commerceHub.spreadsheet') : translate('commerce:commerceHub.unsupported')}
                    </span>
                  </button>
                )
              })}
              {!loading && data && data.directories.length === 0 && data.files.length === 0 && (
                <p className="fh-text-body-sm">{translate('commerce:commerceHub.noSpreadsheetFilesInThisFolder')}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function ConfigPanel({
  kind,
  types,
  initialResourceId,
  headingLevel = 3,
  onCancel,
  onSaved,
  onConfigureData,
}: {
  kind: FormKind
  types: CommerceTypeOption[]
  initialResourceId?: string | null
  headingLevel?: 2 | 3
  onCancel: () => void
  onSaved: (saved: { kind: FormKind; externalId: string; name: string; currency: string; currencyUnit: string }) => Promise<void>
  onConfigureData?: (externalId: string) => void
}) {
  const { commerce } = useServices()
  const { success, error: notifyError } = useNotification()
  const typeResources = useMemo(
    () => prepareResourceCollection(types, commerceTypeSignals),
    [types],
  )
  const initialTypeIsComingSoon = Boolean(initialResourceId && types.some(item => (
    item.id === initialResourceId && isCommerceTypeComingSoon(item)
  )))
  const [selectedId, setSelectedId] = useState(
    () => preferredResourceId(initialResourceId, typeResources) ?? '',
  )
  const [persistedResourceId, setPersistedResourceId] = useState<string | null>(
    initialResourceId ?? null,
  )
  const selected = useMemo(
    () => typeResources.ordered.find(item => item.id === selectedId)?.item,
    [selectedId, typeResources],
  )
  const [displayName, setDisplayName] = useState(selected?.name ?? '')
  const [enabled, setEnabled] = useState(false)
  const [accessMode, setAccessMode] = useState<'read_only' | 'write_enabled'>('read_only')
  const [description, setDescription] = useState('')
  const [currency, setCurrency] = useState('IRR')
  const [currencyUnit, setCurrencyUnit] = useState('')
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [secrets, setSecrets] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [loadingConfiguration, setLoadingConfiguration] = useState(Boolean(initialResourceId))
  const [secretStatus, setSecretStatus] = useState<CommerceSourceConfiguration['secrets']>({})
  const [configurationWasConfigured, setConfigurationWasConfigured] = useState(false)
  const [savedSourceEnabled, setSavedSourceEnabled] = useState<boolean | null>(null)
  const [sourceLifecycleStatus, setSourceLifecycleStatus] = useState<string | null>(null)
  const [sourceArchivedAt, setSourceArchivedAt] = useState<string | null>(null)
  const [savedNextcloudConnection, setSavedNextcloudConnection] = useState<SavedNextcloudConnection | null>(null)
  const [savedNextcloudSpreadsheetPath, setSavedNextcloudSpreadsheetPath] = useState('')
  const [lastTestEvidence, setLastTestEvidence] = useState<CommerceSourceConfiguration['last_test']>(undefined)
  const [vendors, setVendors] = useState<CommerceVendor[]>([])
  const [vendorInformation, setVendorInformation] = useState<CommerceVendor | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerLoading, setPickerLoading] = useState(false)
  const [pickerPath, setPickerPath] = useState('/')
  const [pickerData, setPickerData] = useState<NextcloudBrowseResult | null>(null)
  const [pickerError, setPickerError] = useState<string | null>(null)
  const [connectionFeedback, setConnectionFeedback] = useState<{
    variant: 'success' | 'error'
    title: string
    message: string
  } | null>(null)
  const [worksheetMode, setWorksheetMode] = useState<'all' | 'selected'>('all')
  const [worksheetName, setWorksheetName] = useState('')
  const [readPolicy, setReadPolicy] = useState<ReadPolicyDraft>(DEFAULT_READ_POLICY)
  const nextcloudUrlError = kind === 'source' && selected?.provider === 'nextcloud'
    ? nextcloudUrlErrorFor(settings)
    : null

  useEffect(() => {
    if (initialResourceId) return
    setDisplayName(selected?.name ?? '')
    setEnabled(false)
    setDescription('')
    setCurrency('IRR')
    setCurrencyUnit('')
    setSettings(Object.fromEntries((selected?.settings_schema ?? [])
      .filter(field => !field.secret && field.default !== undefined && field.default !== null)
      .map(field => [field.key, String(field.default)])))
    setSecrets({})
    setAccessMode('read_only')
    setSecretStatus({})
    setConfigurationWasConfigured(false)
    setSavedSourceEnabled(null)
    setSourceLifecycleStatus(null)
    setSourceArchivedAt(null)
    setSavedNextcloudConnection(null)
    setSavedNextcloudSpreadsheetPath('')
    setLastTestEvidence(undefined)
    setVendors([])
    setVendorInformation(null)
    setPickerOpen(false)
    setPickerPath('/')
    setPickerData(null)
    setPickerError(null)
    setConnectionFeedback(null)
    setWorksheetMode('all')
    setWorksheetName('')
    setReadPolicy(DEFAULT_READ_POLICY)
    setPersistedResourceId(null)
  }, [selected?.id, initialResourceId, kind])

  useEffect(() => {
    if (!initialResourceId) return
    if (types.length === 0) return
    if (initialTypeIsComingSoon) {
      setLoadingConfiguration(false)
      return
    }
    let active = true
    setLoadingConfiguration(true)
    const matchingType = types.find(item => item.id === initialResourceId)
    if (matchingType) setSelectedId(matchingType.id)
    const request = kind === 'source'
      ? commerce.getSourceConfiguration(initialResourceId)
      : commerce.getChannelConfiguration(initialResourceId)
    request
      .then(configuration => {
        if (!active) return
        setPersistedResourceId(initialResourceId)
        const providerType = types.find(item => item.provider === configuration.provider)
        if (providerType) setSelectedId(providerType.id)
        setDisplayName(configuration.display_name)
        // A bootstrap Source has no persisted operational state. Keep its edit
        // checkbox false without treating that absence as a disabled connection.
        setEnabled(configuration.enabled === true)
        setAccessMode(configuration.access_mode)
        const loadedSettings = configuration.settings
        const secretSettingKeys = new Set(configuration.settings_schema.filter(field => field.secret).map(field => field.key))
        setDescription(
          ('description' in configuration ? configuration.description : null)
            ?? (typeof loadedSettings.description === 'string' ? loadedSettings.description : ''),
        )
        if (kind === 'source' && configuration.provider === 'nextcloud') {
          const loadedReadPolicy = loadedSettings.source_read_policy
          if (loadedReadPolicy && typeof loadedReadPolicy === 'object' && !Array.isArray(loadedReadPolicy)) {
            const policy = loadedReadPolicy as Partial<ReadPolicyDraft>
            setReadPolicy({
              enabled: typeof policy.enabled === 'boolean' ? policy.enabled : DEFAULT_READ_POLICY.enabled,
              max_reads_per_24h: typeof policy.max_reads_per_24h === 'number'
                ? policy.max_reads_per_24h
                : DEFAULT_READ_POLICY.max_reads_per_24h,
              manual_read_allowed: typeof policy.manual_read_allowed === 'boolean'
                ? policy.manual_read_allowed
                : DEFAULT_READ_POLICY.manual_read_allowed,
            })
          }
          setWorksheetMode(loadedSettings.worksheet_mode === 'selected' ? 'selected' : 'all')
          setWorksheetName(typeof loadedSettings.worksheet_name === 'string' ? loadedSettings.worksheet_name : '')
        }
        const editableSettings = Object.fromEntries(Object.entries(loadedSettings)
          .filter(([key, value]) => !secretSettingKeys.has(key)
            && !['access_mode', 'description', 'source_read_policy', 'source_mapping', 'worksheet_mode', 'worksheet_name'].includes(key)
            && (value == null || ['string', 'number', 'boolean'].includes(typeof value)))
          .map(([key, value]) => [key, value == null ? '' : String(value)]))
        setSettings(editableSettings)
        setSecrets({})
        setSecretStatus(configuration.secrets)
        setConfigurationWasConfigured(configuration.configured)
        setSavedSourceEnabled(kind === 'source' ? configuration.enabled ?? null : null)
        const sourceConfiguration = kind === 'source'
          ? configuration as CommerceSourceConfiguration
          : null
        setSourceLifecycleStatus(sourceConfiguration?.lifecycle_status ?? null)
        setSourceArchivedAt(sourceConfiguration?.archived_at ?? null)
        if (kind === 'source' && configuration.provider === 'nextcloud') {
          const nextcloudSourceConfiguration = configuration as CommerceSourceConfiguration
          const passwordConfigured = configuration.secrets.password?.status === 'configured'
          setSavedNextcloudConnection(
            nextcloudSourceConfiguration.connection_configured === false
              ? null
              : nextcloudConnectionSnapshot(editableSettings, passwordConfigured),
          )
          setLastTestEvidence(nextcloudSourceConfiguration.last_test)
          setSavedNextcloudSpreadsheetPath(String(editableSettings.spreadsheet_path ?? '').trim())
        } else {
          setSavedNextcloudConnection(null)
          setSavedNextcloudSpreadsheetPath('')
          setLastTestEvidence(undefined)
        }
        setCurrency(configuration.currency_profile?.currency || 'IRR')
        setCurrencyUnit(
          configuration.currency_profile?.status === 'resolved'
            ? configuration.currency_profile.unit || ''
            : '',
        )
      })
      .catch(() => {
        if (active) notifyError({
          title: kind === 'source'
            ? translate('commerce:commerceHub.unableToLoadSourceSettings')
            : translate('commerce:commerceHub.unableToLoadChannelSettings'),
          description: translate('commerce:commerceHub.pleaseTryAgain'),
        })
      })
      .finally(() => {
        if (active) setLoadingConfiguration(false)
      })
    return () => { active = false }
  }, [commerce, initialResourceId, initialTypeIsComingSoon, kind, notifyError, types.length])

  if (!selected) return null
  const selectedType = selected
  const sourceTargetId = persistedResourceId ?? selectedType.id
  // Any source connector whose settings schema exposes a spreadsheet_path field gets the
  // same file-selection + worksheet + Configure Data treatment, not just Nextcloud —
  // this keeps Nextcloud, and any future spreadsheet-backed connector, on one shared UX.
  const hasSpreadsheetResource = kind === 'source' && selected.settings_schema.some(field => field.key === 'spreadsheet_path')

  const configuredSecret = (key: string) => secretStatus[key]?.status === 'configured'
  const hasSecret = (key: string) => Boolean(secrets[key]?.trim()) || configuredSecret(key)
  const isNextcloudSource = kind === 'source' && selected.provider === 'nextcloud'
  const nextcloudConnectionReady = Boolean(nextcloudConnectionSnapshot(settings, hasSecret('password')))
  const persistedNextcloudConnectionConfigured = Boolean(
    savedNextcloudConnection && configuredSecret('password')
  )
  const nextcloudConnectionMatchesDraft = Boolean(
    savedNextcloudConnection
      && savedNextcloudConnection.url === String(settings.url ?? '').trim()
      && savedNextcloudConnection.username === String(settings.username || webdavUsernameFromUrl(String(settings.url ?? ''))).trim()
      && configuredSecret('password')
      && !secrets.password?.trim(),
  )
  const spreadsheetSelected = Boolean(settings.spreadsheet_path?.trim())
  const spreadsheetSelectionSaved = spreadsheetSelected
    && savedNextcloudSpreadsheetPath === String(settings.spreadsheet_path ?? '').trim()
  // Connection-test evidence belongs to the persisted connection identity, not
  // to the selected workbook. A workbook can be saved later without making a
  // successful, matching connection test disappear.
  const nextcloudTestTargetSaved = nextcloudConnectionMatchesDraft
  // Health evidence belongs to the persisted connection identity. A healthy
  // result for URL/user/secret A must never unlock remote work for draft B.
  const nextcloudConnectionConfigured = persistedNextcloudConnectionConfigured
    && nextcloudConnectionMatchesDraft
  const hasLastTestEvidence = Boolean(
    lastTestEvidence
      && (lastTestEvidence.checked_at
        || !['', 'unknown', 'not_checked', 'not_tested'].includes(lastTestEvidence.status.trim().toLowerCase())),
  )
  // A predefined `nextcloud:primary` bootstrap or partially saved row can be
  // addressed by URL before source setup is complete. Its route identity—or a
  // saved connection alone—must not turn the remaining guided setup into an
  // edit screen.
  const isExistingNextcloudSource = isNextcloudSource
    && Boolean(initialResourceId)
    && configurationWasConfigured
  const showNextcloudSetupSteps = isNextcloudSource && !isExistingNextcloudSource
  // A new, unsaved Source can validate draft credentials. Once FlowHub has a
  // persisted Source record, its saved enabled state is authoritative for
  // external operations. This mirrors the API's SOURCE_DISABLED contract.
  const nextcloudSourceDisabled = isNextcloudSource
    && savedSourceEnabled === false
    && persistedNextcloudConnectionConfigured
  const nextcloudConnectionNeedsSave = isNextcloudSource
    && persistedNextcloudConnectionConfigured
    && !nextcloudConnectionMatchesDraft
    && !nextcloudSourceDisabled
  const nextcloudSpreadsheetNeedsSave = isNextcloudSource
    && nextcloudConnectionConfigured
    && spreadsheetSelected
    && !spreadsheetSelectionSaved
  const nextcloudRemoteActionsAvailable = nextcloudConnectionConfigured && !nextcloudSourceDisabled
  const nextcloudConnectionState = !persistedNextcloudConnectionConfigured
    ? 'not_configured'
    : nextcloudSourceDisabled
      ? 'disabled'
      : !nextcloudConnectionMatchesDraft
        ? 'unsaved_changes'
        : lastTestEvidence?.status.trim().toLowerCase() === 'healthy'
          ? 'healthy'
          : hasLastTestEvidence
            ? 'needs_attention'
            : 'configured_not_verified'
  // A workbook is a valid persisted partial-setup state. Worksheet participation
  // is chosen only after its real inventory can be discovered in the Data Sheet.
  const completedSourceSetup = isNextcloudSource && configurationWasConfigured
  const worksheetStepAvailable = !isNextcloudSource
    || (nextcloudConnectionConfigured && spreadsheetSelectionSaved)
  const dataSheetStepAvailable = !isNextcloudSource
    || (nextcloudConnectionConfigured && spreadsheetSelectionSaved)
  // Monetary representation is FlowHub-local. It follows the saved connection
  // identity, not optional health evidence from a separate Test operation.
  const monetaryStepAvailable = !isNextcloudSource
    || (nextcloudConnectionConfigured && !nextcloudSourceDisabled)
  const canTest = selected.provider === 'nextcloud'
    ? Boolean(settings.url?.trim()) && hasNextcloudUsername(settings) && hasSecret('password') && !nextcloudSourceDisabled
    : selected.provider === 'snappshop'
      ? Boolean(settings.agent_identifier?.trim()) && hasSecret('token')
      : selected.provider === 'tapsishop'
        ? hasSecret('token')
        : selected.provider === 'digikala'
          ? hasSecret('access_token')
        : selected.provider === 'technolife'
          ? hasSecret('api_key') && hasSecret('encryption_secret')
          : selected.provider === 'woocommerce'
            ? Boolean(settings.url?.trim()) && hasSecret('key') && hasSecret('secret')
            : true
  const vendorSelectionRequired = selected.provider === 'snappshop' && vendors.length > 0
  const canSaveConnection = isNextcloudSource
    && nextcloudConnectionReady
    && !nextcloudUrlError
  const canSave = (!isNextcloudSource || (
      nextcloudConnectionConfigured
      && nextcloudConnectionReady
      && !nextcloudUrlError
    ))
    && (isNextcloudSource || (Boolean(currency) && Boolean(currencyUnit)))
    && (!vendorSelectionRequired || Boolean(settings.vendor_id?.trim()))
  const nextcloudConnectionBadge = nextcloudConnectionState === 'healthy'
    ? { variant: 'success' as const, label: translate('commerce:commerceHub.sourceConnectionHealthy') }
    : nextcloudConnectionState === 'needs_attention'
      ? { variant: 'danger' as const, label: translate('commerce:commerceHub.sourceConnectionNeedsAttention') }
      : nextcloudConnectionState === 'configured_not_verified'
        ? { variant: 'warning' as const, label: translate('commerce:commerceHub.connectionConfiguredNotVerified') }
        : nextcloudConnectionState === 'disabled'
          ? { variant: 'neutral' as const, label: translate('commerce:commerceHub.sourceDisabled') }
          : nextcloudConnectionState === 'unsaved_changes'
            ? { variant: 'warning' as const, label: translate('commerce:commerceHub.connectionHasUnsavedChanges') }
            : { variant: 'neutral' as const, label: translate('commerce:commerceHub.connectionNotConfigured') }

  function configurationPayload({
    includeCurrency = true,
    connectionOnly = false,
  }: {
    includeCurrency?: boolean
    connectionOnly?: boolean
  } = {}) {
    const connectionSettings = connectionOnly
      ? Object.fromEntries(Object.entries(settings).filter(([key]) => key !== 'spreadsheet_path'))
      : settings
    const safeSettings = isNextcloudSource
      && completedSourceSetup
      && !String(connectionSettings.spreadsheet_path ?? '').trim()
      ? Object.fromEntries(Object.entries(connectionSettings).filter(([key]) => key !== 'spreadsheet_path'))
      : connectionSettings
    return {
      display_name: displayName,
      enabled: selectedType.placeholder ? false : enabled,
      access_mode: accessMode,
      description,
      settings: hasSpreadsheetResource && !connectionOnly
        ? {
            ...safeSettings,
            source_read_policy: readPolicy,
            worksheet_mode: worksheetMode,
            worksheet_name: worksheetName,
          }
        : safeSettings,
      secrets,
      ...(includeCurrency && currency && currencyUnit
        ? { currency, currency_unit: currencyUnit }
        : {}),
    }
  }

  async function saveSourceConfiguration(payload: CommerceConfigPayload) {
    if (persistedResourceId) {
      return commerce.saveSource(persistedResourceId, payload)
    }
    if (selectedType.provider !== 'nextcloud') {
      return commerce.saveSource(selectedType.id, payload)
    }
    const created = await commerce.createSource(selectedType.id, payload)
    if (!created.source_id) throw new Error('Created Source connector has no identity.')
    setPersistedResourceId(created.source_id)
    return created
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (nextcloudUrlError) {
      notifyError(nextcloudUrlError)
      return
    }
    setSaving(true)
    try {
      const payload = configurationPayload()
      const sourceResult = kind === 'source'
        ? await saveSourceConfiguration(payload)
        : null
      if (kind === 'channel') await commerce.saveChannel(selectedType.id, payload)

      if (sourceResult?.configuration_state && sourceResult.configuration_state !== 'configured') {
        const nextSecretStatus = { ...secretStatus, ...sourceResult.secrets }
        setSecretStatus(nextSecretStatus)
        setSecrets({})
        setConfigurationWasConfigured(current => current || Boolean(sourceResult.configured))
        setSavedSourceEnabled(enabled)
        if (isNextcloudSource) {
          const passwordConfigured = nextSecretStatus.password?.status === 'configured'
          setSavedNextcloudConnection(
            sourceResult.connection_configured === false
              ? null
              : nextcloudConnectionSnapshot(settings, passwordConfigured),
          )
          setSavedNextcloudSpreadsheetPath(String(settings.spreadsheet_path ?? '').trim())
          if (!nextcloudConnectionMatchesDraft) setLastTestEvidence(undefined)
        }
        success({
          title: translate('commerce:commerceHub.sourceSettingsUpdatedSuccessfully'),
          description: translate('commerce:commerceHub.yourChangesHaveBeenSaved'),
        })
        return
      }
      if (kind === 'source') setSavedSourceEnabled(enabled)
      const nextcloudNeedsSpreadsheet = hasSpreadsheetResource
        && !settings.spreadsheet_path?.trim()
      success(kind === 'source'
        ? nextcloudNeedsSpreadsheet
          ? {
              title: translate('commerce:commerceHub.sourceConnectionSaved'),
              description: translate('commerce:commerceHub.selectSpreadsheetToFinishSourceSetup'),
            }
          : configurationWasConfigured
          ? {
              title: translate('commerce:commerceHub.sourceSettingsUpdatedSuccessfully'),
              description: translate('commerce:commerceHub.yourChangesHaveBeenSaved'),
            }
          : {
              title: translate('commerce:commerceHub.sourceConfiguredSuccessfully'),
              description: translate('commerce:commerceHub.theSourceIsReadyToUse'),
            }
        : configurationWasConfigured
          ? {
              title: translate('commerce:commerceHub.channelSettingsUpdatedSuccessfully'),
              description: translate('commerce:commerceHub.yourChangesHaveBeenSaved'),
            }
          : {
              title: translate('commerce:commerceHub.channelConfiguredSuccessfully'),
              description: translate('commerce:commerceHub.theChannelIsReadyToUse'),
            })
      await onSaved({
        kind,
        externalId: sourceResult?.source_id ?? sourceTargetId,
        name: displayName || selectedType.name,
        currency,
        currencyUnit,
      })
    } catch {
      notifyError({
        title: kind === 'source' ? translate('commerce:commerceHub.unableToSaveSourceSettings') : translate('commerce:commerceHub.unableToSaveChannelSettings'),
        description: translate('commerce:commerceHub.pleaseReviewYourChangesAndTryAgain'),
      })
    } finally {
      setSaving(false)
    }
  }

  async function saveNextcloudConnection() {
    if (!isNextcloudSource || !canSaveConnection) return
    if (nextcloudUrlError) {
      notifyError(nextcloudUrlError)
      return
    }
    setSaving(true)
    setConnectionFeedback(null)
    try {
      // Step 2 deliberately omits a monetary declaration. Existing downstream
      // settings remain in the payload, so correcting a connection never erases them.
      const result = await saveSourceConfiguration(
        configurationPayload({ includeCurrency: false, connectionOnly: true }),
      )
      const nextSecretStatus = { ...secretStatus, ...result.secrets }
      const passwordConfigured = nextSecretStatus.password?.status === 'configured'
      const snapshot = result.connection_configured === false
        ? null
        : nextcloudConnectionSnapshot(settings, passwordConfigured)
      setSecretStatus(nextSecretStatus)
      setSavedNextcloudConnection(snapshot)
      setSavedSourceEnabled(enabled)
      if (!nextcloudConnectionMatchesDraft) setLastTestEvidence(undefined)
      setSecrets({})
      setConfigurationWasConfigured(current => current || Boolean(result.configured))
      const feedback = {
        variant: 'success' as const,
        title: translate('commerce:commerceHub.connectionSettingsSaved'),
        message: !enabled
          ? translate('commerce:commerceHub.sourceDisabledRemoteActions')
          : nextcloudConnectionMatchesDraft
            ? translate('commerce:commerceHub.connectionSettingsUnchangedDescription')
            : configurationWasConfigured
              ? translate('commerce:commerceHub.connectionSettingsSavedRetestDescription')
              : translate('commerce:commerceHub.connectionSettingsSavedDescription'),
      }
      setConnectionFeedback(feedback)
      success({ title: feedback.title, description: feedback.message })
    } catch (error) {
      const description = apiErrorMessage(
        error,
        translate('commerce:commerceHub.pleaseReviewYourChangesAndTryAgain'),
      )
      const failure = {
        title: translate('commerce:commerceHub.unableToSaveSourceSettings'),
        description,
      }
      setConnectionFeedback({ variant: 'error', title: failure.title, message: failure.description })
      notifyError(failure)
    } finally {
      setSaving(false)
    }
  }

  async function saveNextcloudSetupAndOpenDataSheet() {
    // An existing configured Source already has a persisted Data Sheet. Opening
    // it must not silently save unrelated connection or worksheet drafts.
    if (completedSourceSetup && nextcloudConnectionConfigured && spreadsheetSelectionSaved && onConfigureData) {
      onConfigureData?.(sourceTargetId)
      return
    }
    if (
      !isNextcloudSource
      || !nextcloudConnectionConfigured
      || !spreadsheetSelectionSaved
      || !nextcloudConnectionReady
      || nextcloudUrlError
    ) return
    setSaving(true)
    try {
      const result = await saveSourceConfiguration(configurationPayload())
      setSecretStatus(current => ({ ...current, ...result.secrets }))
      setConfigurationWasConfigured(current => current || (result.configured ?? true))
      setSavedSourceEnabled(enabled)
      setSavedNextcloudSpreadsheetPath(String(settings.spreadsheet_path ?? '').trim())
      if (!nextcloudConnectionMatchesDraft) setLastTestEvidence(undefined)
      setSecrets({})
      success({
        title: translate('commerce:commerceHub.sourceSettingsUpdatedSuccessfully'),
        description: translate('commerce:commerceHub.openingDataSheet'),
      })
      await onSaved({
        kind: 'source',
        externalId: result.source_id ?? sourceTargetId,
        name: displayName || selectedType.name,
        currency,
        currencyUnit,
      })
    } catch (error) {
      notifyError({
        title: translate('commerce:commerceHub.unableToSaveSourceSettings'),
        description: apiErrorMessage(
          error,
          translate('commerce:commerceHub.pleaseReviewYourChangesAndTryAgain'),
        ),
      })
    } finally {
      setSaving(false)
    }
  }

  async function testConnection() {
    if (nextcloudUrlError) {
      notifyError(nextcloudUrlError)
      return
    }
    setConnectionFeedback(null)
    setTesting(true)
    try {
      const result = kind === 'source'
        ? persistedResourceId
          ? await commerce.testSource(persistedResourceId, configurationPayload())
          : selectedType.provider === 'nextcloud'
            ? await commerce.testSourceType(selectedType.id, configurationPayload())
            : await commerce.testSource(selectedType.id, configurationPayload())
        : await commerce.testChannel(selectedType.id, configurationPayload())
      const sourceTestMatchesSaved = kind === 'source'
        && (result.configuration_matches_saved ?? nextcloudTestTargetSaved)
      const sourceTestDisabled = kind === 'source'
        && nextcloudFailureCategory(result) === 'disabled'
      if (kind === 'source') {
        if (sourceTestMatchesSaved && !sourceTestDisabled) {
          setLastTestEvidence({
            status: result.ok ? 'healthy' : 'unhealthy',
            message: result.message,
            error_code: result.error_class ?? result.code ?? null,
            latency_ms: result.latency_ms ?? null,
            checked_at: result.checked_at ?? null,
          })
        }
        if (!sourceTestDisabled) {
          try {
            const refreshed = await commerce.getSourceConfiguration(sourceTargetId)
            const refreshedStatus = refreshed.last_test?.status.trim().toLowerCase()
            if (refreshedStatus === 'healthy' || refreshedStatus === 'unhealthy') {
              setLastTestEvidence(refreshed.last_test)
            }
          } catch {
            // Connection feedback below still reports this test. Persisted evidence
            // remains unchanged when the follow-up metadata read is unavailable.
          }
        }
      }
      if (result.ok) {
        const discoveredVendors = result.vendors ?? []
        setVendors(discoveredVendors)
        setVendorInformation(result.vendor_information ?? null)
        if (selectedType.provider === 'snappshop') {
          const suggested = result.suggested_vendor_id
            ?? (discoveredVendors.filter(vendor => snappShopVendorActive(vendor.status)).length === 1
              ? discoveredVendors.find(vendor => snappShopVendorActive(vendor.status))?.id
              : null)
          if (suggested) {
            setSettings(current => ({ ...current, vendor_id: current.vendor_id || suggested }))
          }
        }
        if (kind === 'source') {
          const feedback = sourceTestMatchesSaved
            ? {
                variant: 'success' as const,
                title: translate('commerce:commerceHub.savedConnectionVerified'),
                message: translate(
                  configurationWasConfigured
                    ? 'commerce:commerceHub.savedConnectionHealthyDescription'
                    : 'commerce:commerceHub.savedConnectionVerifiedSetupDescription',
                ),
              }
            : {
                variant: 'success' as const,
                title: translate('commerce:commerceHub.connectionDetailsVerified'),
                message: translate('commerce:commerceHub.connectionDetailsVerifiedDescription'),
          }
          setConnectionFeedback(feedback)
          success({ title: feedback.title, description: feedback.message })
        }
        if (kind !== 'source') success(result.configuration_matches_saved !== true
            ? {
                title: translate('commerce:commerceHub.channelConnectionVerified'),
                description: translate('commerce:commerceHub.saveDraftBeforeChannelReady'),
              }
          : {
              title: translate('commerce:commerceHub.channelConnectedSuccessfully'),
              description: translate('commerce:commerceHub.isReadyToUse', { value1: localizedChannelName(selectedType.id, selectedType.name) }),
            })
      }
      else {
        const failure = {
          title: kind === 'source' ? translate('commerce:commerceHub.unableToConnectToTheSource') : translate('commerce:commerceHub.unableToConnectToTheChannel'),
          description: kind === 'source'
            ? nextcloudConnectionFailureMessage(result)
            : connectionResultMessage(result),
        }
        if (kind === 'source') {
          setConnectionFeedback({ variant: 'error', title: failure.title, message: failure.description })
        }
        notifyError(failure)
      }
    } catch (error) {
      const failure = {
        title: kind === 'source' ? translate('commerce:commerceHub.unableToConnectToTheSource') : translate('commerce:commerceHub.unableToConnectToTheChannel'),
        description: kind === 'source'
          ? nextcloudConnectionExceptionMessage(error)
          : connectionExceptionMessage(error),
      }
      if (kind === 'source') {
        setConnectionFeedback({ variant: 'error', title: failure.title, message: failure.description })
      }
      notifyError(failure)
    } finally {
      setTesting(false)
    }
  }

  async function browseNextcloud(path = '/') {
    if (nextcloudUrlError) {
      setPickerError(nextcloudUrlError)
      notifyError(nextcloudUrlError)
      return
    }
    if (!nextcloudRemoteActionsAvailable || !savedNextcloudConnection) {
      const message = nextcloudSourceDisabled
        ? translate('commerce:commerceHub.sourceDisabledRemoteActions')
        : nextcloudConnectionNeedsSave
          ? translate('commerce:commerceHub.connectionChangesRequireSave')
          : translate('commerce:commerceHub.validation.saveConnectionBeforeBrowsing')
      setPickerError(message)
      notifyError(message)
      return
    }
    setPickerOpen(true)
    setPickerPath(path)
    setPickerLoading(true)
    setPickerError(null)
    try {
      // Remote browsing uses only the saved connection identity. Test evidence
      // remains useful health information, but it is not a hidden prerequisite
      // for provider I/O that the backend permits for a configured connection.
      // Never browse a stale connection behind a changed URL, username, or
      // replacement secret.
      const result = await commerce.browseNextcloud(sourceTargetId, {
        path,
        settings,
        secrets,
      })
      setPickerData(result)
    } catch (error) {
      // Keep the previously loaded folder and selected file intact. The picker
      // reports only a safe, structured category rather than provider text.
      setPickerError(nextcloudConnectionExceptionMessage(error))
    } finally {
      setPickerLoading(false)
    }
  }

  function selectNextcloudFile(file: NextcloudBrowseItem) {
    if (!file.supported) return
    setSettings(current => ({ ...current, spreadsheet_path: file.path }))
    setConnectionFeedback(null)
          setPickerOpen(false)
          setPickerPath('/')
  }

  function renderConnectionField(field: CommerceTypeField) {
    const fieldName = `commerce.${kind}.${selectedType.provider}.${field.key}`
    if (field.secret) {
      return (
        <SecretField
          key={field.key}
          label={fieldLabel(kind, selectedType.provider, field.key, field.label)}
          value={secrets[field.key] ?? ''}
          configured={configuredSecret(field.key)}
          required={field.required && !configuredSecret(field.key)}
          onChange={value => {
            setSecrets(current => ({ ...current, [field.key]: value }))
            setConnectionFeedback(null)
          }}
          configuredHint={isNextcloudSource
            ? translate('commerce:commerceHub.savedCredentialLeaveUnchanged')
            : translate('commerce:commerceHub.configuredLeaveBlankToKeepUnchanged')}
          placeholder={translate('commerce:commerceHub.passwordPlaceholder')}
          configuredMask="••••••••••••"
          revealLabel={translate('commerce:commerceHub.showEnteredSecret', { defaultValue: 'Show entered secret' })}
          concealLabel={translate('commerce:commerceHub.hideEnteredSecret', { defaultValue: 'Hide entered secret' })}
          copyLabel={translate('commerce:commerceHub.copyEnteredSecret', { defaultValue: 'Copy entered secret' })}
          copiedLabel={translate('commerce:commerceHub.enteredSecretCopied', { defaultValue: 'Entered secret copied.' })}
          emptySecretHint={translate('commerce:commerceHub.savedSecretHiddenHint', { defaultValue: 'Saved secret is hidden for security — type a new one to reveal or copy it.' })}
        />
      )
    }
    return (
      <label key={field.key} className="fh-field">
        <span className="fh-help-text">{fieldLabel(kind, selectedType.provider, field.key, field.label)}</span>
        {["token_refresh_enabled", "revoke_current_token"].includes(field.key) ? (
          <input
            type="checkbox"
            name={fieldName}
            checked={settings[field.key] === "true"}
            onChange={event => {
              setSettings(current => ({ ...current, [field.key]: String(event.target.checked) }))
              setConnectionFeedback(null)
            }}
          />
        ) : (
          <input
            type={field.key === "request_timeout" ? "number" : "text"}
            name={fieldName}
            autoComplete={field.key === 'username' ? 'username' : field.key === 'url' ? 'url' : 'off'}
            min={field.key === "request_timeout" ? 1 : undefined}
            max={field.key === "request_timeout" ? 120 : undefined}
            step={field.key === "request_timeout" ? 1 : undefined}
            value={settings[field.key] ?? ''}
            required={field.required}
            onChange={event => {
              const value = event.target.value
              setConnectionFeedback(null)
              setSettings(current => {
                const next = { ...current, [field.key]: value }
                if (selectedType.provider === 'nextcloud' && field.key === 'url' && !next.username) {
                  const usernameFromUrl = webdavUsernameFromUrl(value)
                  if (usernameFromUrl) next.username = usernameFromUrl
                }
                return next
              })
            }}
            className="fh-input"
          />
        )}
        {selectedType.provider === "nextcloud" && field.key === "url" && nextcloudUrlError && (
          <span className="fh-field-error">{nextcloudUrlError}</span>
        )}
      </label>
    )
  }

  if (loadingConfiguration) {
    return <div className="fh-card fh-card-pad flex items-center gap-2 fh-text-body-sm" role="status" aria-live="polite" aria-busy="true"><Spinner size="sm" />{kind === 'source' ? translate('commerce:commerceHub.loadingSourceConfiguration') : translate('commerce:commerceHub.loadingChannelConfiguration')}</div>
  }

  if (kind === 'source' && sourceLifecycleStatus === 'archived') {
    return (
      <section className="fh-card fh-card-pad" data-testid="archived-source-configuration" role="status">
        <div className="flex items-center gap-3">
          <BrandIcon identity={{ provider: selected.provider, sourceType: selected.type }} label={selected.name} size={40} />
          <div>
            <h3 className="fh-section-title">{translate('common:status.archived')}</h3>
            <p className="fh-section-subtitle mt-1">{translate('sources:sourceCenter.archivedReadOnly')}</p>
            {sourceArchivedAt && <p className="fh-text-caption mt-1">{translate('sources:sourceCenter.archivedAt')} {formatDateTime(sourceArchivedAt)}</p>}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {onConfigureData && <button type="button" className="fh-button-secondary" onClick={() => onConfigureData(selected.id)}><Icon name="preview" /> {translate('sources:sourceCenter.viewDataSheet')}</button>}
          <button type="button" className="fh-button-secondary" onClick={onCancel}>{translate('commerce:commerceHub.close')}</button>
        </div>
      </section>
    )
  }

  if (isCommerceTypeComingSoon(selected)) {
    return (
      <section className="fh-card fh-card-pad" data-testid="configuration-coming-soon">
        <div className="flex items-center gap-3">
          <BrandIcon identity={{ provider: selected.provider, sourceType: selected.type }} label={selected.name} size={40} />
          <div>
            <h3 className="fh-section-title">{translate('common:resourceBadge.comingSoon')}</h3>
            <p className="fh-section-subtitle mt-1">{kind === 'source' ? translate('commerce:commerceHub.plannedSource') : translate('commerce:commerceHub.plannedChannel')}</p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" className="fh-button-secondary" onClick={onCancel}>{translate('commerce:commerceHub.close')}</button>
        </div>
      </section>
    )
  }

  const HeadingTag = headingLevel === 2 ? 'h2' : 'h3'

  return (
    <form onSubmit={event => void submit(event)} className="fh-card overflow-hidden">
      <div className="fh-panel-header">
        <div>
          <HeadingTag className="fh-section-title">
            {initialResourceId
              ? translate('commerce:commerceHub.configure2', { value1: localizedChannelName(selected.id, selected.name) })
              : kind === "source"
                ? translate('commerce:commerceHub.addSource')
                : translate('commerce:commerceHub.addChannel')}
          </HeadingTag>
          <p className="fh-section-subtitle mt-1">
            {translate('commerce:commerceHub.credentialsAreStoredServerSideAndNever')}
          </p>
        </div>
        <button type="button" onClick={onCancel} className="fh-button-secondary">
          <Icon name="close" />
          {translate('commerce:commerceHub.close')}
        </button>
      </div>

      <div className="fh-panel-body fh-stack">
      <div className="fh-form-section" data-setup-step={isNextcloudSource ? 'general' : undefined}>
        <div>
          {showNextcloudSetupSteps && <p className="fh-text-caption font-semibold">{translate('commerce:commerceHub.setupStep', { step: 1 })}</p>}
          <p className="fh-form-section-title">{translate('commerce:commerceHub.general')}</p>
          <p className="fh-form-section-description">{isExistingNextcloudSource
            ? translate('commerce:commerceHub.editSourceGeneralDescription')
            : translate('commerce:commerceHub.defineTheConnectorTypeDisplayNameAnd')}</p>
        </div>
        <div className="fh-form-grid md:grid-cols-2">
        <label className="fh-field">
          <span className="fh-help-text">{kind === "source" ? translate('commerce:commerceHub.sourceType') : translate('commerce:commerceHub.channelType')}</span>
          <select
            value={selected.id}
            onChange={event => setSelectedId(event.target.value)}
            disabled={Boolean(initialResourceId)}
            className="fh-select"
          >
            <ResourceOptionGroups
              resources={typeResources}
              isOptionDisabled={item => item.section === 'comingSoon'}
            />
          </select>
        </label>
        <label className="fh-field">
          <span className="fh-help-text">{translate('commerce:commerceHub.displayName')}</span>
          <input value={displayName} onChange={event => setDisplayName(event.target.value)} className="fh-input" />
        </label>
        {kind === 'source' && <label className="fh-field md:col-span-2">
          <span className="fh-help-text">{translate('commerce:commerceHub.descriptionOptional')}</span>
          <input value={description} onChange={event => setDescription(event.target.value)} className="fh-input" />
        </label>}
        {kind === 'channel' && (
          <label className="fh-field">
            <span className="fh-help-text">{translate('commerce:commerceHub.accessMode')}</span>
            <select value={accessMode} onChange={event => setAccessMode(event.target.value as 'read_only' | 'write_enabled')} className="fh-select">
              <option value="read_only">{translate('commerce:commerceHub.readOnly2')}</option>
              {['woocommerce', 'snappshop', 'tapsishop', 'technolife'].includes(selected.provider) && (
                <option value="write_enabled">{translate('commerce:commerceHub.writeEnabled2')}</option>
              )}
            </select>
          </label>
        )}
        </div>

        <div className="fh-actions">
        <label className="fh-inline-check">
          <input
            type="checkbox"
            checked={enabled && !selected.placeholder}
            disabled={selected.placeholder}
            onChange={event => {
              setEnabled(event.target.checked)
              setConnectionFeedback(null)
            }}
          />
          {translate('commerce:commerceHub.enabled')}
        </label>
        <SafetyBadges
          readOnly={kind === 'source' ? selected.read_only : accessMode === 'read_only'}
          writeBlocked={kind === 'source' ? selected.runtime_write_blocked : accessMode === 'read_only'}
          writeEnabled={kind === 'channel' && accessMode === 'write_enabled'}
        />
        {selected.placeholder && (
          <Badge variant="neutral">
            {kind === "source" ? translate('commerce:commerceHub.plannedSource') : translate('commerce:commerceHub.plannedChannel')}
          </Badge>
        )}
        {selected.placeholder && <Badge variant="neutral">{translate('commerce:commerceHub.notConfigured2')}</Badge>}
        </div>
        {isNextcloudSource && (
          <p className="fh-text-caption" data-testid="nextcloud-source-enabled-state" role="note">
            <Icon name="info" /> {nextcloudSourceDisabled
              ? translate('commerce:commerceHub.sourceDisabledRemoteActions')
              : savedSourceEnabled === null
                ? translate('commerce:commerceHub.lockedUntilConnectionSaved')
                : translate('commerce:commerceHub.sourceEnabledRemoteActions')}
          </p>
        )}
      </div>

      {!isNextcloudSource && <div className="fh-form-section">
        <div>
          <p className="fh-form-section-title">{translate('commerce:commerceHub.monetaryUnit')}</p>
          <p className="fh-form-section-description">{translate('commerce:commerceHub.monetaryUnitDescription')}</p>
        </div>
        <div className="fh-form-grid md:grid-cols-2">
          <label className="fh-field">
            <span className="fh-help-text">{translate('commerce:commerceHub.currency')}</span>
            <select
              value={currency}
              onChange={event => {
                const nextCurrency = event.target.value
                setCurrency(nextCurrency)
                setCurrencyUnit(nextCurrency === 'IRR' ? '' : nextCurrency)
              }}
              className="fh-select"
            >
              {['IRR', 'USD', 'EUR', 'AED', 'JPY'].map(code => (
                <option key={code} value={code}>{code}</option>
              ))}
            </select>
          </label>
          <label className="fh-field">
            <span className="fh-help-text">{translate('commerce:commerceHub.currencyUnit')}</span>
            {currency === 'IRR' ? (
              <select
                value={currencyUnit}
                onChange={event => setCurrencyUnit(event.target.value)}
                className="fh-select"
                required
              >
                <option value="">{translate('commerce:commerceHub.selectCurrencyUnit')}</option>
                <option value="RIAL">{translate('commerce:commerceHub.rial')}</option>
                <option value="TOMAN">{translate('commerce:commerceHub.toman')}</option>
              </select>
            ) : (
              <input value={currencyUnit} readOnly className="fh-input" />
            )}
          </label>
        </div>
      </div>}

      <div className="fh-form-section" data-setup-step={isNextcloudSource ? 'connection' : undefined}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            {showNextcloudSetupSteps && <p className="fh-text-caption font-semibold">{translate('commerce:commerceHub.setupStep', { step: 2 })}</p>}
            <p className="fh-form-section-title">{translate('commerce:commerceHub.connectionSettings')}</p>
            <p className="fh-form-section-description">{isExistingNextcloudSource
              ? translate('commerce:commerceHub.editConnectionSettingsDescription')
              : translate('commerce:commerceHub.enterTheCredentialsRequiredToVerifyThis')}</p>
          </div>
          {isNextcloudSource && (
            <span data-testid="nextcloud-connection-state">
              <Badge variant={nextcloudConnectionBadge.variant} className="nextcloud-connection-state">
                {nextcloudConnectionBadge.label}
              </Badge>
            </span>
          )}
        </div>
      <div className="fh-form-grid md:grid-cols-2">
        {selected.settings_schema
          .filter(field => !(hasSpreadsheetResource && field.key === "spreadsheet_path"))
          .filter(field => !CHANNEL_VISIBLE_FIELDS[selected.provider]
            || CHANNEL_VISIBLE_FIELDS[selected.provider].has(field.key))
          .map(renderConnectionField)}
      </div>
      {isNextcloudSource && (
        <>
          <p className="fh-help-text" dir="ltr">{translate('commerce:commerceHub.nextcloudWebdavExample')}</p>
          <div className="rounded-lg border border-border bg-bg-subtle p-3" data-testid="nextcloud-last-test">
            <p className="fh-help-text font-semibold">{translate('commerce:commerceHub.lastConnectionTest')}</p>
            {lastTestEvidence && hasLastTestEvidence && nextcloudTestTargetSaved ? (
              <div className="mt-1 fh-text-caption">
                <p>{formatStatus(lastTestEvidence.status)}</p>
                {lastTestEvidence.message && (
                  <p>{nextcloudPersistedTestMessage(lastTestEvidence)}</p>
                )}
                {lastTestEvidence.checked_at && (
                  <p>{translate('commerce:commerceHub.checkedPrefix')} {formatDateTime(lastTestEvidence.checked_at)}</p>
                )}
              </div>
            ) : (
              <p className="mt-1 fh-text-caption">{translate('commerce:commerceHub.notTested')}</p>
            )}
          </div>
          <div className="fh-actions">
            <button
              type="button"
              onClick={() => void testConnection()}
              disabled={testing || saving || !canTest}
              title={nextcloudSourceDisabled ? translate('commerce:commerceHub.sourceDisabledRemoteActions') : undefined}
              className="fh-button-secondary px-4"
            >
              {testing && <Spinner size="sm" />}
              {!testing && <Icon name="testConnection" />}
              {testing ? translate('commerce:commerceHub.testing') : translate('commerce:commerceHub.testConnection')}
            </button>
            <button type="button" onClick={() => void saveNextcloudConnection()} disabled={saving || testing || !canSaveConnection} className="fh-button-primary px-4">
              {saving && <Spinner size="sm" />}
              {!saving && <Icon name="save" />}
              {saving ? translate('commerce:commerceHub.saving') : translate('commerce:commerceHub.saveConnection')}
            </button>
          </div>
          {nextcloudSourceDisabled && (
            <p className="fh-text-caption" role="note"><Icon name="info" /> {translate('commerce:commerceHub.sourceDisabledRemoteActions')}</p>
          )}
          {connectionFeedback && (
            <Alert
              variant={connectionFeedback.variant}
              title={connectionFeedback.title}
              message={connectionFeedback.message}
            />
          )}
        </>
      )}
      </div>

      {kind === "channel" && selected.provider === "snappshop" && (
        <div className="fh-form-section">
          <div>
            <p className="fh-form-section-title">{translate('commerce:commerceHub.vendor')}</p>
            <p className="fh-form-section-description">{translate('commerce:commerceHub.testTheConnectionToLoadStoresAvailable')}</p>
          </div>
          <label className="fh-field">
            <span className="fh-help-text">{translate('commerce:commerceHub.vendorStore')}</span>
            <select
              value={settings.vendor_id ?? ''}
              onChange={event => setSettings(current => ({ ...current, vendor_id: event.target.value }))}
              className="fh-select"
              disabled={vendors.length === 0 && !settings.vendor_id}
              required={vendorSelectionRequired}
            >
              <option value="">{vendors.length ? translate('commerce:commerceHub.selectVendor') : translate('commerce:commerceHub.testConnectionToLoadVendors')}</option>
              {settings.vendor_id && !vendors.some(vendor => vendor.id === settings.vendor_id) && (
                <option value={settings.vendor_id}>{translate('commerce:commerceHub.savedVendor')}{settings.vendor_id})</option>
              )}
              {vendors.map(vendor => (
                <option
                  key={vendor.id ?? vendor.name}
                  value={vendor.id ?? ''}
                  disabled={!snappShopVendorActive(vendor.status)}
                >
                  {vendor.title || vendor.name}{vendor.title_en && vendor.title_en !== vendor.title ? translate('commerce:commerceHub.alternateTitle', { title: vendor.title_en }) : ''}{snappShopVendorActive(vendor.status) ? '' : translate('commerce:commerceHub.inactive')}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {kind === "channel" && selected.provider === "tapsishop" && (
        <div className="fh-form-section">
          <div>
            <p className="fh-form-section-title">{translate('commerce:commerceHub.webhookRegistration')}</p>
            <p className="fh-form-section-description">{translate('commerce:commerceHub.registerThisUrlInTapsishopTheWebhook')}</p>
            <p className="fh-form-section-description">{translate('commerce:commerceHub.tapsishopWriteSafety')}</p>
          </div>
          <label className="fh-field">
            <span className="fh-help-text">{translate('commerce:commerceHub.webhookUrl')}</span>
            <input readOnly value={`${window.location.origin}/api/v2/webhooks/tapsishop/${encodeURIComponent(selected.id)}`} className="fh-input" />
          </label>
          <p className="fh-help-text">{translate('commerce:commerceHub.webhookCredential')} {configuredSecret("webhook_token") ? translate('commerce:commerceHub.configured') : translate('commerce:commerceHub.notConfigured2')}</p>
          {vendorInformation && (
            <div className="rounded-md border border-border bg-bg-subtle p-3 fh-text-body-sm">
              <p className="font-medium text-text-base">{vendorInformation.name}</p>
              <p className="fh-text-caption">{translate('commerce:commerceHub.vendorId')} {vendorInformation.id ?? "Unavailable"}</p>
              {vendorInformation.reference_code && <p className="fh-text-caption">{translate('commerce:commerceHub.storeNumber')} {vendorInformation.reference_code}</p>}
            </div>
          )}
        </div>
      )}

      {kind === "channel" && selected.provider === "woocommerce" && (
        <div className="fh-form-section">
          <div>
            <p className="fh-form-section-title">{translate('commerce:commerceHub.webhookRegistration')}</p>
            <p className="fh-form-section-description">{translate('commerce:commerceHub.registerThisUrlInWoocommerceTheWebhook')}</p>
            <p className="fh-form-section-description">{translate('commerce:commerceHub.woocommerceProductWebhooksOnly')}</p>
          </div>
          <label className="fh-field">
            <span className="fh-help-text">{translate('commerce:commerceHub.webhookUrl')}</span>
            <input readOnly value={`${window.location.origin}/api/v2/webhooks/woocommerce/${encodeURIComponent(selected.id)}`} className="fh-input" />
          </label>
          <p className="fh-help-text">{translate('commerce:commerceHub.webhookCredential')} {configuredSecret("webhook_secret") ? translate('commerce:commerceHub.configured') : translate('commerce:commerceHub.notConfigured2')}</p>
        </div>
      )}

      {hasSpreadsheetResource && (
        <div className="fh-stack">
          <div
            className={["fh-form-section", isNextcloudSource && !nextcloudConnectionConfigured ? "opacity-70" : ''].join(' ')}
            aria-disabled={isNextcloudSource && !nextcloudConnectionConfigured}
            data-setup-step="spreadsheet"
          >
            {selected.provider === "nextcloud" ? (
              <div>
                {showNextcloudSetupSteps && <p className="fh-text-caption font-semibold">{translate('commerce:commerceHub.setupStep', { step: 3 })}</p>}
                <p className="fh-form-section-title">{translate('commerce:commerceHub.nextcloudSpreadsheetFile')}</p>
                <p className="fh-form-section-description">{isExistingNextcloudSource
                  ? translate('commerce:commerceHub.editSpreadsheetDescription')
                  : translate('commerce:commerceHub.useWebdavWithYourAppPasswordPublic')}</p>
                <div
                  className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end"
                  data-testid="nextcloud-file-control-row"
                >
                  <div className="fh-field min-w-0">
                    <span className="fh-help-text">{translate('commerce:commerceHub.selectedFile')}</span>
                    <div
                      className={`min-h-10 rounded-md border px-3 py-2 fh-text-body ${spreadsheetSelected ? 'border-accent bg-accent/5' : 'border-border bg-bg-subtle'}`}
                      data-testid="nextcloud-selected-file"
                      data-selected={spreadsheetSelected}
                    >
                      <span>{settings.spreadsheet_path || translate('commerce:commerceHub.noSpreadsheetFileSelected')}</span>
                      {spreadsheetSelected && <Badge variant={spreadsheetSelectionSaved ? 'success' : 'warning'}>{translate(
                        spreadsheetSelectionSaved
                          ? 'commerce:commerceHub.fileSelected'
                          : 'commerce:commerceHub.fileSelectionUnsaved',
                      )}</Badge>}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void browseNextcloud('/')}
                    disabled={!nextcloudRemoteActionsAvailable}
                    title={nextcloudSourceDisabled ? translate('commerce:commerceHub.sourceDisabledRemoteActions') : undefined}
                    className="fh-button-secondary w-full px-4 md:w-auto"
                  >
                    {translate('commerce:commerceHub.browseNextcloud')}
                  </button>
                </div>
                {!nextcloudRemoteActionsAvailable && (
                  <p className="mt-3 fh-text-caption" role="note">
                    <Icon name="info" /> {translate(nextcloudSourceDisabled
                      ? 'commerce:commerceHub.sourceDisabledRemoteActions'
                      : nextcloudConnectionNeedsSave
                        ? 'commerce:commerceHub.connectionChangesRequireSave'
                        : 'commerce:commerceHub.lockedUntilConnectionSaved')}
                  </p>
                )}
              </div>
            ) : (
              <div>
                <p className="fh-form-section-title">{translate('commerce:commerceHub.selectedFile')}</p>
                <p className="fh-form-section-description">{translate('commerce:commerceHub.spreadsheetResourceGenericHelp')}</p>
                <label className="fh-field mt-3">
                  <span className="fh-help-text">{translate('commerce:commerceHub.selectedFile')}</span>
                  <input
                    value={settings.spreadsheet_path ?? ''}
                    onChange={event => setSettings(current => ({ ...current, spreadsheet_path: event.target.value }))}
                    placeholder={translate('commerce:commerceHub.spreadsheetResourcePlaceholder')}
                    className="fh-input"
                  />
                </label>
              </div>
            )}
          </div>

          <div
            className={["fh-form-section", !worksheetStepAvailable ? "opacity-70" : ''].join(' ')}
            aria-disabled={!worksheetStepAvailable}
            data-setup-step="worksheet"
          >
            <div>
              {showNextcloudSetupSteps && <p className="fh-text-caption font-semibold">{translate('commerce:commerceHub.setupStep', { step: 4 })}</p>}
              <p className="fh-form-section-title">{translate('commerce:commerceHub.worksheet')}</p>
              <p className="fh-form-section-description">{translate(isExistingNextcloudSource
                ? 'commerce:commerceHub.editWorksheetDescription'
                : 'commerce:commerceHub.worksheetScopeAfterWorkbookSave')}</p>
            </div>
            {!worksheetStepAvailable && (
              <p className="fh-text-caption" role="note"><Icon name="info" /> {translate(
                nextcloudConnectionNeedsSave
                  ? 'commerce:commerceHub.connectionChangesRequireSave'
                  : spreadsheetSelected
                    ? 'commerce:commerceHub.spreadsheetChangesRequireSave'
                    : 'commerce:commerceHub.lockedUntilConnectionSaved',
              )}</p>
            )}
            {isNextcloudSource && !isExistingNextcloudSource ? (
              <p className="fh-text-caption" role="note"><Icon name="info" /> {translate(
                worksheetStepAvailable
                  ? 'commerce:commerceHub.worksheetScopeAfterWorkbookSave'
                  : 'commerce:commerceHub.saveWorkbookBeforeWorksheetScope',
              )}</p>
            ) : <fieldset
              className="flex flex-col gap-2 fh-text-body"
              disabled={!worksheetStepAvailable}
            >
              <label className="fh-inline-check">
                <input
                  type="radio"
                  name="worksheet_mode"
                  checked={worksheetMode === "all"}
                  onChange={() => setWorksheetMode("all")}
                />
                {translate('commerce:commerceHub.allWorksheets')}
              </label>
              <label className="fh-inline-check">
                <input
                  type="radio"
                  name="worksheet_mode"
                  checked={worksheetMode === "selected"}
                  onChange={() => setWorksheetMode("selected")}
                />
                {translate('commerce:commerceHub.selectedWorksheet')}
              </label>
              <label className="fh-field">
                <span className="fh-help-text">{translate('commerce:commerceHub.worksheetName')}</span>
                <input
                  value={worksheetName}
                  onChange={event => setWorksheetName(event.target.value)}
                  disabled={worksheetMode !== "selected"}
                  className="fh-input"
                />
              </label>
            </fieldset>}
          </div>

          <div
            className={["fh-form-section", !dataSheetStepAvailable ? "opacity-70" : ''].join(' ')}
            aria-disabled={!dataSheetStepAvailable}
            data-setup-step="data-sheet"
          >
            <div>
              {showNextcloudSetupSteps && <p className="fh-text-caption font-semibold">{translate('commerce:commerceHub.setupStep', { step: 5 })}</p>}
              <p className="fh-form-section-title">{translate('sources:sourceConfiguration.channelMappings')}</p>
              <p className="fh-form-section-description">{translate('commerce:commerceHub.dataSheetMappingScopeDescription')}</p>
            </div>
            {isNextcloudSource ? (
              <button
                type="button"
                className="fh-button-secondary px-4 w-fit"
                disabled={saving
                  || !dataSheetStepAvailable}
                onClick={() => void saveNextcloudSetupAndOpenDataSheet()}
              >
                <Icon name="workspace" /> {translate('commerce:commerceHub.saveAndOpenDataSheet')} <Icon name="next" />
              </button>
            ) : (initialResourceId && onConfigureData) ? (
              <button
                type="button"
                className="fh-button-secondary px-4 w-fit"
                onClick={() => onConfigureData(sourceTargetId)}
              >
                <Icon name="workspace" /> {translate('commerce:commerceHub.configureData')} <Icon name="next" />
              </button>
            ) : (
              <p className="fh-text-caption">{translate('commerce:commerceHub.saveConnectionBeforeConfiguringData')}</p>
            )}
            {isNextcloudSource && !dataSheetStepAvailable && (
              <p className="fh-text-caption" role="note"><Icon name="info" /> {translate(
                nextcloudConnectionNeedsSave
                  ? 'commerce:commerceHub.connectionChangesRequireSave'
                  : nextcloudSpreadsheetNeedsSave
                    ? 'commerce:commerceHub.spreadsheetChangesRequireSave'
                  : nextcloudConnectionConfigured
                    ? 'commerce:commerceHub.saveSourceSetupBeforeDataSheet'
                    : 'commerce:commerceHub.lockedUntilConnectionSaved',
              )}</p>
            )}
          </div>

          {isNextcloudSource && (
            <div
              className={["fh-form-section", !monetaryStepAvailable ? "opacity-70" : ''].join(' ')}
              aria-disabled={!monetaryStepAvailable}
              data-setup-step="monetary-unit"
            >
              <div>
                {showNextcloudSetupSteps && <p className="fh-text-caption font-semibold">{translate('commerce:commerceHub.setupStep', { step: 6 })}</p>}
                <p className="fh-form-section-title">{translate('commerce:commerceHub.monetaryUnit')}</p>
                <p className="fh-form-section-description">{translate(isExistingNextcloudSource
                  ? 'commerce:commerceHub.editMonetaryDescription'
                  : 'commerce:commerceHub.monetaryUnitDescription')}</p>
              </div>
              {!monetaryStepAvailable && (
                <p className="fh-text-caption" role="note"><Icon name="info" /> {translate('commerce:commerceHub.lockedUntilConnectionSaved')}</p>
              )}
              <fieldset className="fh-form-grid md:grid-cols-2" disabled={!monetaryStepAvailable}>
                <label className="fh-field">
                  <span className="fh-help-text">{translate('commerce:commerceHub.currency')}</span>
                  <select
                    value={currency}
                    onChange={event => {
                      const nextCurrency = event.target.value
                      setCurrency(nextCurrency)
                      setCurrencyUnit(nextCurrency === 'IRR' ? '' : nextCurrency)
                    }}
                    className="fh-select"
                  >
                    {['IRR', 'USD', 'EUR', 'AED', 'JPY'].map(code => (
                      <option key={code} value={code}>{code}</option>
                    ))}
                  </select>
                </label>
                <label className="fh-field">
                  <span className="fh-help-text">{translate('commerce:commerceHub.currencyUnit')}</span>
                  {currency === 'IRR' ? (
                    <select
                      value={currencyUnit}
                      onChange={event => setCurrencyUnit(event.target.value)}
                      className="fh-select"
                      required={!isNextcloudSource}
                    >
                      <option value="">{translate('commerce:commerceHub.selectCurrencyUnit')}</option>
                      <option value="RIAL">{translate('commerce:commerceHub.rial')}</option>
                      <option value="TOMAN">{translate('commerce:commerceHub.toman')}</option>
                    </select>
                  ) : (
                    <input value={currencyUnit} readOnly className="fh-input" />
                  )}
                </label>
              </fieldset>
            </div>
          )}
        </div>
      )}

      {!isNextcloudSource && connectionFeedback && (
        <Alert
          variant={connectionFeedback.variant}
          title={connectionFeedback.title}
          message={connectionFeedback.message}
        />
      )}

      <div className="fh-panel-footer">
        {!isNextcloudSource && (
          <button type="button" onClick={() => void testConnection()} disabled={testing || !canTest} className="fh-button-secondary px-4">
            {testing && <Spinner size="sm" />}
            {!testing && <Icon name="testConnection" />}
            {testing ? translate('commerce:commerceHub.testing') : translate('commerce:commerceHub.testConnection')}
          </button>
        )}
        <button type="submit" disabled={saving || !canSave} className="fh-button-primary px-4">
          {saving && <Spinner size="sm" />}
          {!saving && <Icon name="save" />}
          {saving ? translate('commerce:commerceHub.saving') : translate('commerce:commerceHub.saveConfiguration')}
        </button>
      </div>
      </div>
      {pickerOpen && (
        <NextcloudFilePicker
          data={pickerData}
          loading={pickerLoading}
          error={pickerError}
          requestedPath={pickerPath}
          selectedPath={String(settings.spreadsheet_path ?? '').trim()}
          onClose={() => setPickerOpen(false)}
          onRetry={() => void browseNextcloud(pickerPath)}
          onOpenDirectory={(path) => void browseNextcloud(path)}
          onSelectFile={selectNextcloudFile}
        />
      )}
    </form>
  )
}

export function CommerceHubContent({ initialTab }: { initialTab?: Tab } = {}) {
  const { commerce } = useServices()
  const { user } = useAuth()
  const { success, error: notifyError } = useNotification()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const returnToSource = sourceConfigurationReturnPath(searchParams.get('returnTo'))
  const [tab, setTab] = useState<Tab>(initialTab ?? (searchParams.get('tab') === 'sources' ? 'sources' : 'channels'))
  const [sources, setSources] = useState<CommerceSource[]>([])
  const [channels, setChannels] = useState<CommerceChannel[]>([])
  const [sourceTypes, setSourceTypes] = useState<CommerceTypeOption[]>([])
  const [channelTypes, setChannelTypes] = useState<CommerceTypeOption[]>([])
  const [map, setMap] = useState<CommerceRelationshipMap | null>(null)
  const [loading, setLoading] = useState(true)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [refreshingId, setRefreshingId] = useState<string | null>(null)
  const [refreshResults, setRefreshResults] = useState<Record<string, ChannelCacheRefreshResult>>({})
  const [formKind, setFormKind] = useState<FormKind | null>(null)
  const [editingSourceId, setEditingSourceId] = useState<string | null>(null)
  const [editingChannelId, setEditingChannelId] = useState<string | null>(null)
  const canManageCommerce = user?.is_admin === true
  const sourceResources = useMemo(
    () => prepareResourceCollection(sources, commerceSourceSignals),
    [sources],
  )
  const channelResources = useMemo(
    () => prepareResourceCollection(channels, commerceChannelSignals),
    [channels],
  )

  useEffect(() => {
    if (initialTab) return
    const queryTab = searchParams.get('tab')
    if (queryTab === 'sources' || queryTab === 'channels') setTab(queryTab)
  }, [searchParams, initialTab])

  useEffect(() => {
    if (loading || initialTab) return
    const resourceId = searchParams.get('resource')
    if (!resourceId) return
    const queryTab = searchParams.get('tab')
    if (queryTab === 'sources' && sourceTypes.some(item => item.id === resourceId)) {
      setEditingSourceId(resourceId)
      setEditingChannelId(null)
      setFormKind('source')
    }
    if (queryTab === 'channels' && channelTypes.some(item => item.id === resourceId)) {
      setEditingChannelId(resourceId)
      setEditingSourceId(null)
      setFormKind('channel')
    }
  }, [channelTypes, initialTab, loading, searchParams, sourceTypes])

  async function loadCommerce() {
    const [sourceData, channelData, sourceTypeData, channelTypeData] = await Promise.all([
      commerce.getSources(),
      commerce.getChannels(),
      commerce.getSourceTypes(),
      commerce.getChannelTypes(),
    ])
    setSources(sourceData.items)
    setMap(sourceData.relationship_map)
    setChannels(channelData.items)
    setSourceTypes(sourceTypeData.items)
    setChannelTypes(channelTypeData.items)
  }

  useEffect(() => {
    loadCommerce()
      .catch(() => notifyError({
        title: translate('commerce:commerceHub.unableToLoadCommerceHub'),
        description: translate('commerce:commerceHub.pleaseTryAgain'),
      }))
      .finally(() => setLoading(false))
  }, [commerce])

  function selectTab(nextTab: Tab) {
    setTab(nextTab)
    setSearchParams({ tab: nextTab })
    setFormKind(null)
    setEditingSourceId(null)
    setEditingChannelId(null)
  }

  async function handleSourceTest(sourceId: string) {
    if (!canManageCommerce) {
      notifyError(translate('commerce:commerceHub.adminPermissionRequired'))
      return
    }
    setTestingId(sourceId)
    try {
      const result = await commerce.testSource(sourceId)
      const source = sources.find(item => item.id === sourceId)
      if (result.ok) success({
        title: translate('commerce:commerceHub.sourceConnectedSuccessfully'),
        description: translate('commerce:commerceHub.isReadyToUse', { value1: source?.name ?? 'The source' }),
      })
      else notifyError({
        title: translate('commerce:commerceHub.unableToConnectToTheSource'),
        description: nextcloudConnectionFailureMessage(result),
      })
      await loadCommerce()
    } catch (error) {
      notifyError({
        title: translate('commerce:commerceHub.unableToConnectToTheSource'),
        description: nextcloudConnectionExceptionMessage(error),
      })
    } finally {
      setTestingId(null)
    }
  }

  async function handleChannelTest(channelId: string) {
    if (!canManageCommerce) {
      notifyError(translate('commerce:commerceHub.adminPermissionRequired'))
      return
    }
    setTestingId(channelId)
    try {
      const result = await commerce.testChannel(channelId)
      const channel = channels.find(item => item.id === channelId)
      if (result.ok) success({
        title: translate('commerce:commerceHub.channelConnectedSuccessfully'),
        description: channel
          ? translate('commerce:commerceHub.isReadyToUse', { value1: localizedChannelName(channel.id, channel.name, channel.display_name_custom) })
          : translate('commerce:commerceHub.theChannelIsReadyToUse'),
      })
      else notifyError({
        title: translate('commerce:commerceHub.unableToConnectToTheChannel'),
        description: connectionResultMessage(result),
      })
      await loadCommerce()
    } catch (error) {
      notifyError({
        title: translate('commerce:commerceHub.unableToConnectToTheChannel'),
        description: connectionExceptionMessage(error),
      })
    } finally {
      setTestingId(null)
    }
  }

  async function handleChannelCacheRefresh(channelId: string) {
    if (!canManageCommerce) {
      notifyError(translate('commerce:commerceHub.adminPermissionRequired'))
      return
    }
    setRefreshingId(channelId)
    try {
      const result = await commerce.refreshChannelCache(channelId)
      setRefreshResults(current => ({ ...current, [channelId]: result }))
      if (result.ok) {
        success({
          title: translate('commerce:commerceHub.productCacheRefreshedSuccessfully'),
          description: result.pages_read !== undefined
            ? translate('commerce:commerceHub.productsWereCachedFromPageS', { value1: result.products_stored ?? result.cache_rows_upserted, value2: result.pages_read })
            : translate('commerce:commerceHub.theLatestProductInformationHasBeenLoaded'),
        })
      } else {
        notifyError({
          title: translate('commerce:commerceHub.unableToRefreshTheProductCache'),
          description: translate('commerce:commerceHub.pleaseTryAgain'),
        })
      }
      await loadCommerce()
    } catch {
      notifyError({
        title: translate('commerce:commerceHub.unableToRefreshTheProductCache'),
        description: translate('commerce:commerceHub.pleaseTryAgain'),
      })
    } finally {
      setRefreshingId(null)
    }
  }

  async function managedSourceFor(
    externalId: string,
    name: string,
    currency?: string,
    currencyUnit?: string,
  ) {
    const existing = (await sourceWorkspaceApi.listSources()).items.find(
      item => item.sourceKind === 'external' && item.externalSourceId === externalId,
    )
    if (existing) return existing

    // The first Nextcloud Data Sheet profile is a projection of the persisted
    // Source policy. Never invent Sheet1: a partial selected-workbook setup
    // has no discovered worksheet yet, so the Data Sheet starts with neutral
    // all-worksheet participation until the user detects real inventory.
    let worksheetMode: 'all' | 'selected' = 'all'
    let worksheetName: string | null = null
    if (externalId.startsWith('nextcloud:')) {
      const configuration = await commerce.getSourceConfiguration(externalId)
      worksheetMode = configuration.settings.worksheet_mode === 'selected'
        ? 'selected'
        : 'all'
      const configuredName = typeof configuration.settings.worksheet_name === 'string'
        ? configuration.settings.worksheet_name.trim()
        : ''
      if (worksheetMode === 'selected' && configuredName) {
        worksheetName = configuredName
      } else if (worksheetMode === 'selected') {
        // The workbook is persisted but scope is intentionally incomplete.
        // SourceWorkspace accepts all/null as its safe provisional profile;
        // it does not imply that a particular worksheet will be read.
        worksheetMode = 'all'
      }
    }

    return sourceWorkspaceApi.createSource({
      name,
      source_kind: 'external',
      external_source_id: externalId,
      worksheet_mode: worksheetMode,
      worksheet_name: worksheetName,
      data_start_row: 2,
      currency,
      currency_unit: currencyUnit,
    })
  }

  function handleSourceEdit(sourceId: string) {
    if (!canManageCommerce) {
      notifyError(translate('commerce:commerceHub.adminPermissionRequired'))
      return
    }
    setTab('sources')
    setSearchParams({ tab: 'sources', resource: sourceId })
    setEditingSourceId(sourceId)
    setEditingChannelId(null)
    setFormKind('source')
  }

  async function handleSourceConfigure(sourceId: string) {
    if (!canManageCommerce) {
      notifyError(translate('commerce:commerceHub.adminPermissionRequired'))
      return
    }
    const source = sources.find(item => item.id === sourceId)
    if (!source || source.configuration_state !== 'configured') {
      handleSourceEdit(sourceId)
      return
    }
    try {
      const managed = await managedSourceFor(sourceId, source?.name || sourceId)
      navigate(`/sources/${managed.id}`)
    } catch {
      notifyError({
        title: translate('sources:sourceConfiguration.sourceConfigurationUnavailable'),
        description: translate('sources:sourceConfiguration.tryAgainAfterSavingConnection'),
      })
    }
  }

  function handleChannelConfigure(channelId: string) {
    if (!canManageCommerce) {
      notifyError(translate('commerce:commerceHub.adminPermissionRequired'))
      return
    }
    const channel = channels.find(item => item.id === channelId)
    if (!channel || isCommerceChannelComingSoon(channel) || !channel.settings_available) return
    setTab('channels')
    setSearchParams({ tab: 'channels', resource: channelId })
    setEditingChannelId(channelId)
    setFormKind('channel')
  }

  async function reloadAfterSave(saved: { kind: FormKind; externalId: string; name: string; currency: string; currencyUnit: string }) {
    await loadCommerce()
    setFormKind(null)
    setEditingChannelId(null)
    if (saved.kind === 'source') {
      const managed = await managedSourceFor(
        saved.externalId,
        saved.name,
        saved.currency || undefined,
        saved.currencyUnit || undefined,
      )
      navigate(returnToSource ?? `/sources/${managed.id}`)
    }
  }

  function closeSourceEditor() {
    if (returnToSource) {
      navigate(returnToSource)
      return
    }
    setFormKind(null)
    setEditingSourceId(null)
    setSearchParams({ tab: 'sources' })
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('commerce:commerceHub.commerceHub')}</h1>
        </div>
        <SafetyBadges readOnly writeBlocked />
      </div>

      <RelationshipMap map={map} />

      <div className="fh-segmented w-fit">
        {(["sources", "channels"] as const).map(item => (
          <button
            key={item}
            onClick={() => selectTab(item)}
            className={[
              "fh-segmented-button capitalize",
              tab === item ? "fh-segmented-button-active" : '',
            ].join(' ')}
          >
            {item === "sources" ? translate('commerce:commerceHub.sources2') : translate('commerce:commerceHub.channels2')}
          </button>
        ))}
      </div>

      {loading ? (
          <div className="fh-card fh-card-pad flex items-center gap-2 fh-text-body-sm">
            <Spinner size="sm" />{translate('commerce:commerceHub.loadingCommerceHub')}
          </div>
      ) : tab === "sources" ? (
        <section>
          <button type="button" className="fh-button-secondary fh-button-sm mb-4" onClick={() => navigate(returnToSource ?? '/sources')}>
            <Icon name="previous" /> {returnToSource
              ? translate('sources:sourceConfiguration.backToDataSheet')
              : translate('sources:sourceConfiguration.backToSources')}
          </button>
          <div className="fh-page-toolbar mb-4">
            <div>
              <h2 className="fh-section-title">{translate('commerce:commerceHub.sources2')}</h2>
              <p className="fh-section-subtitle mt-1">{translate('commerce:commerceHub.inputSystemsThatFeedFlowhubDataLayer')}</p>
            </div>
            {canManageCommerce ? (
              <button onClick={() => { setEditingSourceId(null); setFormKind("source") }} className="fh-button-primary px-4">
                <Icon name="add" />
                {translate('commerce:commerceHub.addSource')}
              </button>
            ) : (
              <Badge variant="neutral">{translate('commerce:commerceHub.adminPermissionRequired')}</Badge>
            )}
          </div>
          {formKind === "source" && (
            <div className="mb-4">
              <ConfigPanel
                kind="source"
                types={sourceTypes}
                initialResourceId={editingSourceId}
                onCancel={closeSourceEditor}
                onSaved={reloadAfterSave}
                onConfigureData={id => void handleSourceConfigure(id)}
              />
            </div>
          )}
          {!(formKind === 'source' && editingSourceId) && (
            <div className="grid gap-5">
              <ResourceSectionList
                resources={sourceResources}
                className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2"
                renderItem={resource => (
                <SourceCard
                  source={resource.item}
                  badge={resource.badge}
                  onTest={(id) => void handleSourceTest(id)}
                  onEdit={handleSourceEdit}
                  onConfigure={handleSourceConfigure}
                  testing={testingId === resource.id}
                  canManage={canManageCommerce}
                />
                )}
              />
            </div>
          )}
        </section>
      ) : (
        <section>
          <div className="fh-page-toolbar mb-4">
            <div>
              <h2 className="fh-section-title">{translate('commerce:commerceHub.channels2')}</h2>
              <p className="fh-section-subtitle mt-1">{translate('commerce:commerceHub.commerceSystemsThatReceiveCatalogVisibilityFrom')}</p>
            </div>
            {canManageCommerce ? (
              <button onClick={() => { setEditingChannelId(null); setFormKind('channel') }} className="fh-button-primary px-4">
                <Icon name="add" />
                {translate('commerce:commerceHub.addChannel')}
              </button>
            ) : (
              <Badge variant="neutral">{translate('commerce:commerceHub.adminPermissionRequired')}</Badge>
            )}
          </div>
          {formKind === "channel" && (
            <div className="mb-4">
              <ConfigPanel
                kind="channel"
                types={channelTypes}
                initialResourceId={editingChannelId}
                onCancel={() => { setFormKind(null); setEditingChannelId(null); setSearchParams({ tab: 'channels' }) }}
                onSaved={reloadAfterSave}
              />
            </div>
          )}
          <div className="grid gap-5">
            <ResourceSectionList
              resources={channelResources}
              className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2"
              renderItem={resource => (
              <ChannelCard
                channel={resource.item}
                badge={resource.badge}
                onTest={(id) => void handleChannelTest(id)}
                onRefresh={(id) => void handleChannelCacheRefresh(id)}
                onConfigure={handleChannelConfigure}
                testing={testingId === resource.id}
                refreshing={refreshingId === resource.id}
                refreshResult={refreshResults[resource.id]}
                canManage={canManageCommerce}
              />
              )}
            />
          </div>
        </section>
      )}
    </PageShell>
  )
}

export default function CommerceHub({ initialTab }: { initialTab?: Tab } = {}) {
  const [searchParams] = useSearchParams()
  const requestedTab = initialTab ?? (searchParams.get('tab') === 'sources' ? 'sources' : 'channels')

  if (requestedTab === 'channels') {
    const legacyResourceId = searchParams.get('resource') ?? searchParams.get('channel')
    const target = legacyResourceId
      ? `/channels?setup=${encodeURIComponent(legacyResourceId)}`
      : '/channels'
    return <Navigate to={target} replace />
  }

  return <CommerceHubContent initialTab={initialTab} />
}
