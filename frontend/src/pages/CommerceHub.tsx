import { translate } from '../i18n'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import { useAuth } from '../auth'
import { ApiError, apiErrorMessage } from '../api/client'
import Badge from '../components/Badge'
import Alert from '../components/Alert'
import { useServices } from '../services/ServiceContext'
import type { CommerceChannel, CommerceRelationshipMap, CommerceSource, CommerceTypeField, CommerceTypeOption } from '../services/types'
import type { ChannelCacheRefreshResult, CommerceSourceConfiguration, CommerceVendor, ConnectionCheckResult, NextcloudBrowseItem, NextcloudBrowseResult } from '../services/commerce/CommerceService'
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
  prepareResourceCollection,
  preferredResourceId,
  type ResourceBadge,
} from '../features/resourceOrdering/resourceOrdering'

type Tab = 'sources' | 'channels'
type FormKind = 'source' | 'channel'
export type ReadPolicyDraft = { enabled: boolean; max_reads_per_24h: number; manual_read_allowed: boolean }

export const DEFAULT_READ_POLICY: ReadPolicyDraft = {
  enabled: true,
  max_reads_per_24h: 10,
  manual_read_allowed: true,
}

const CHANNEL_VISIBLE_FIELDS: Record<string, ReadonlySet<string>> = {
  snappshop: new Set(['token', 'agent_identifier']),
  tapsishop: new Set(['token', 'webhook_token']),
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
  const canUseNextcloudActions = canManage && source.provider === 'nextcloud' && !source.placeholder
  const canOpenDataSheet = source.configuration_state === 'configured'
  const canTestSavedConnection = source.connection_configured === true
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
        <Badge variant="neutral">{formatStatus(source.health?.status ?? "unknown")}</Badge>
        <span className="fh-text-caption">{translate('commerce:commerceHub.lastRead')} {readStatus?.last_read_at ? formatDateTime(readStatus.last_read_at) : translate('commerce:commerceHub.notRead')}</span>
      </div>

      <details className="rounded-lg border border-border bg-bg-subtle p-3">
        <summary className="cursor-pointer font-medium text-text-base">{translate('commerce:commerceHub.details')}</summary>
        <div className="fh-form-grid mt-3 sm:grid-cols-2 fh-text-caption">
          <p><span className="text-wp-muted">{translate('commerce:commerceHub.credentialStatus')} </span><span className="font-medium text-text-base">{formatStatus(source.credential_status)}</span></p>
          <p><span className="text-wp-muted">{translate('commerce:commerceHub.lastHealthCheck')} </span><span className="font-medium text-text-base">{source.last_health_check ? formatDateTime(source.last_health_check) : translate('commerce:commerceHub.notChecked')}</span></p>
          <p><span className="text-wp-muted">{translate('commerce:commerceHub.dataRole')} </span><span className="font-medium text-text-base">{formatDataRole(source.data_role)}</span></p>
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
  const isWooCommerce = channel.provider === 'woocommerce' && !channel.placeholder
  const supportsProductCache = ['woocommerce', 'snappshop', 'tapsishop'].includes(channel.provider) && !channel.placeholder
  const isConfigurable = channel.implemented && !channel.placeholder && ['woocommerce', 'snappshop', 'tapsishop'].includes(channel.provider)
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
  | 'timeout'
  | 'authentication'
  | 'permission_denied'
  | 'invalid_url'
  | 'invalid_webdav_path'
  | 'not_configured'
  | 'spreadsheet_unsupported'
  | 'unreachable'
  | 'unsafe_destination'
  | 'resource_not_found'
  | null {
  const identity = [result.code, result.error_class, result.status].filter(Boolean).join(' ').toLowerCase()
  const message = String(result.message || '').toLowerCase()
  const evidence = `${identity} ${message}`
  if (/unsafe_destination|ssrf|private.network|trusted.network|blocked.*destination/.test(evidence)) return 'unsafe_destination'
  if (/timeout|timed.out|deadline.exceeded|did not respond in time/.test(evidence)) return 'timeout'
  if (/permission.denied|authorization.failed|forbidden|access.denied/.test(evidence)) return 'permission_denied'
  if (/authentication|unauthorized|invalid.credential/.test(evidence)) return 'authentication'
  if (/not.configured|required.settings.missing/.test(evidence)) return 'not_configured'
  if (/spreadsheet.unsupported|unsupported.*xlsx|supported.*xlsx/.test(evidence)) return 'spreadsheet_unsupported'
  if (/invalid.url|malformed.url/.test(evidence)) return 'invalid_url'
  if (/invalid.webdav|webdav.path|malformed.*path|invalid.*path/.test(evidence)) return 'invalid_webdav_path'
  if (/file.not.found|spreadsheet.not.found|resource.not.found|missing.resource|\b404\b/.test(evidence)) return 'resource_not_found'
  if (/connection.failed|unreachable|dns|name resolution|connection refused|failed to fetch|networkerror|network|tls|certificate|502|503/.test(evidence)) return 'unreachable'
  return null
}

function nextcloudConnectionFailureMessage(
  result: Pick<ConnectionCheckResult, 'status' | 'message' | 'code' | 'error_class'>,
): string {
  const category = nextcloudFailureCategory(result)
  if (category === 'unsafe_destination') return translate('errors:codes.unsafe_destination')
  if (category === 'timeout') return translate('commerce:commerceHub.connectionError.timeout')
  if (category === 'authentication') return translate('commerce:commerceHub.connectionError.authenticationRejected')
  if (category === 'permission_denied') return translate('commerce:commerceHub.connectionError.permissionDenied')
  if (category === 'invalid_url') return translate('commerce:commerceHub.connectionError.invalidUrl')
  if (category === 'invalid_webdav_path') return translate('commerce:commerceHub.connectionError.invalidWebdavPath')
  if (category === 'not_configured') return translate('commerce:commerceHub.connectionError.notConfigured')
  if (category === 'spreadsheet_unsupported') return translate('commerce:commerceHub.connectionError.spreadsheetUnsupported')
  if (category === 'resource_not_found') return translate('commerce:commerceHub.connectionError.resourceNotFound')
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
  onClose,
  onOpenDirectory,
  onSelectFile,
}: {
  data: NextcloudBrowseResult | null
  loading: boolean
  error: string | null
  onClose: () => void
  onOpenDirectory: (path: string) => void
  onSelectFile: (file: NextcloudBrowseItem) => void
}) {
  const currentPath = data?.path ?? '/'
  const parentPath = currentPath === '/' ? null : `/${currentPath.split('/').filter(Boolean).slice(0, -1).join('/')}`
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
      <div className="fh-card w-full max-w-3xl max-h-[80vh] overflow-hidden flex flex-col">
        <div className="fh-panel-header !min-h-0 !items-start">
          <div>
            <h3 className="fh-section-title">{translate('commerce:commerceHub.browseNextcloud')}</h3>
            <p className="fh-section-subtitle mt-1">{currentPath}</p>
          </div>
          <button type="button" onClick={onClose} className="fh-button-secondary">
            <Icon name="close" />
            {translate('commerce:commerceHub.close')}
          </button>
        </div>
        <div className="overflow-auto p-4">
          {error && <div className="fh-error-alert mb-3">{error}</div>}
          {loading ? (
            <div className="flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />{translate('commerce:commerceHub.loadingFiles')}</div>
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
              {data?.files.map(file => (
                <button
                  key={file.path}
                  type="button"
                  disabled={!file.supported}
                  onClick={() => onSelectFile(file)}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-bg-base px-3 py-3 text-left fh-text-body disabled:opacity-60"
                >
                  <span className="inline-flex min-w-0 items-center gap-2 font-medium text-text-base">
                    <Icon name="file" />
                    <span className="truncate">{file.name}</span>
                  </span>
                  <span className="fh-text-caption">{file.supported ? translate('commerce:commerceHub.spreadsheet') : translate('commerce:commerceHub.unsupported')}</span>
                </button>
              ))}
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
  const [selectedId, setSelectedId] = useState(
    () => preferredResourceId(initialResourceId, typeResources) ?? '',
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
  const [savedNextcloudConnection, setSavedNextcloudConnection] = useState<SavedNextcloudConnection | null>(null)
  const [savedNextcloudSpreadsheetPath, setSavedNextcloudSpreadsheetPath] = useState('')
  const [lastTestEvidence, setLastTestEvidence] = useState<CommerceSourceConfiguration['last_test']>(undefined)
  const [vendors, setVendors] = useState<CommerceVendor[]>([])
  const [vendorInformation, setVendorInformation] = useState<CommerceVendor | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerLoading, setPickerLoading] = useState(false)
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
    setSavedNextcloudConnection(null)
    setSavedNextcloudSpreadsheetPath('')
    setLastTestEvidence(undefined)
    setVendors([])
    setVendorInformation(null)
    setPickerOpen(false)
    setPickerData(null)
    setPickerError(null)
    setConnectionFeedback(null)
    setWorksheetMode('all')
    setWorksheetName('')
    setReadPolicy(DEFAULT_READ_POLICY)
  }, [selected?.id, initialResourceId, kind])

  useEffect(() => {
    if (!initialResourceId) return
    let active = true
    setLoadingConfiguration(true)
    setSelectedId(initialResourceId)
    const request = kind === 'source'
      ? commerce.getSourceConfiguration(initialResourceId)
      : commerce.getChannelConfiguration(initialResourceId)
    request
      .then(configuration => {
        if (!active) return
        setDisplayName(configuration.display_name)
        setEnabled(configuration.enabled)
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
        if (kind === 'source' && configuration.provider === 'nextcloud') {
          const sourceConfiguration = configuration as CommerceSourceConfiguration
          const passwordConfigured = configuration.secrets.password?.status === 'configured'
          setSavedNextcloudConnection(
            sourceConfiguration.connection_configured === false
              ? null
              : nextcloudConnectionSnapshot(editableSettings, passwordConfigured),
          )
          setLastTestEvidence(sourceConfiguration.last_test)
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
  }, [commerce, initialResourceId, kind, notifyError])

  if (!selected) return null
  const selectedType = selected
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
  const nextcloudTestTargetSaved = nextcloudConnectionMatchesDraft
    && savedNextcloudSpreadsheetPath === String(settings.spreadsheet_path ?? '').trim()
  const nextcloudConnectionUsable = persistedNextcloudConnectionConfigured
    && lastTestEvidence?.status.trim().toLowerCase() === 'healthy'
  const worksheetSelected = spreadsheetSelected
    && (worksheetMode === 'all' || Boolean(worksheetName.trim()))
  const worksheetPolicyDraftValid = worksheetMode === 'all' || Boolean(worksheetName.trim())
  // Connection health unlocks connection-independent declarations. Workbook
  // selection remains a separate prerequisite only for the Data Sheet.
  const completedSourceSetup = isNextcloudSource && configurationWasConfigured
  const worksheetStepAvailable = !isNextcloudSource
    || nextcloudConnectionUsable
  const dataSheetStepAvailable = !isNextcloudSource
    || (nextcloudConnectionUsable && worksheetSelected)
  const monetaryStepAvailable = !isNextcloudSource
    || nextcloudConnectionUsable
  const hasLastTestEvidence = Boolean(
    lastTestEvidence
      && (lastTestEvidence.checked_at
        || !['', 'unknown', 'not_checked', 'not_tested'].includes(lastTestEvidence.status.trim().toLowerCase())),
  )
  const canTest = selected.provider === 'nextcloud'
    ? Boolean(settings.url?.trim()) && hasNextcloudUsername(settings) && hasSecret('password')
    : selected.provider === 'snappshop'
      ? Boolean(settings.agent_identifier?.trim()) && hasSecret('token')
      : selected.provider === 'tapsishop'
        ? hasSecret('token')
        : selected.provider === 'technolife'
          ? hasSecret('api_key') && hasSecret('encryption_secret')
          : selected.provider === 'woocommerce'
            ? Boolean(settings.url?.trim()) && hasSecret('key') && hasSecret('secret')
            : true
  const vendorSelectionRequired = selected.provider === 'snappshop' && vendors.length > 0
  const canSaveConnection = isNextcloudSource
    && nextcloudConnectionReady
    && !nextcloudUrlError
  const canSave = Boolean(currency) && Boolean(currencyUnit)
    && (!isNextcloudSource || (
      nextcloudConnectionUsable
      && nextcloudConnectionReady
      && !nextcloudUrlError
      && worksheetPolicyDraftValid
    ))
    && (!vendorSelectionRequired || Boolean(settings.vendor_id?.trim()))

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
        ? await commerce.saveSource(selectedType.id, payload)
        : null
      if (kind === 'channel') await commerce.saveChannel(selectedType.id, payload)

      if (sourceResult?.configuration_state && sourceResult.configuration_state !== 'configured') {
        const nextSecretStatus = { ...secretStatus, ...sourceResult.secrets }
        setSecretStatus(nextSecretStatus)
        setSecrets({})
        setConfigurationWasConfigured(current => current || Boolean(sourceResult.configured))
        if (isNextcloudSource) {
          const passwordConfigured = nextSecretStatus.password?.status === 'configured'
          setSavedNextcloudConnection(
            sourceResult.connection_configured === false
              ? null
              : nextcloudConnectionSnapshot(settings, passwordConfigured),
          )
          setSavedNextcloudSpreadsheetPath(String(settings.spreadsheet_path ?? '').trim())
          if (!nextcloudTestTargetSaved) setLastTestEvidence(undefined)
        }
        success({
          title: translate('commerce:commerceHub.sourceSettingsUpdatedSuccessfully'),
          description: translate('commerce:commerceHub.yourChangesHaveBeenSaved'),
        })
        return
      }
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
        externalId: selectedType.id,
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
      const result = await commerce.saveSource(
        selectedType.id,
        configurationPayload({ includeCurrency: false, connectionOnly: true }),
      )
      const nextSecretStatus = { ...secretStatus, ...result.secrets }
      const passwordConfigured = nextSecretStatus.password?.status === 'configured'
      const snapshot = result.connection_configured === false
        ? null
        : nextcloudConnectionSnapshot(settings, passwordConfigured)
      setSecretStatus(nextSecretStatus)
      setSavedNextcloudConnection(snapshot)
      if (!nextcloudConnectionMatchesDraft) setLastTestEvidence(undefined)
      setSecrets({})
      setConfigurationWasConfigured(current => current || Boolean(result.configured))
      const feedback = {
        variant: 'success' as const,
        title: translate('commerce:commerceHub.connectionSettingsSaved'),
        message: translate('commerce:commerceHub.connectionSettingsSavedDescription'),
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
    if (
      completedSourceSetup
      && (!nextcloudConnectionReady || Boolean(nextcloudUrlError) || !worksheetSelected)
    ) {
      onConfigureData?.(selectedType.id)
      return
    }
    if (
      !isNextcloudSource
      || !nextcloudConnectionUsable
      || !nextcloudConnectionReady
      || nextcloudUrlError
      || !worksheetSelected
    ) return
    setSaving(true)
    try {
      const result = await commerce.saveSource(selectedType.id, configurationPayload())
      setSecretStatus(current => ({ ...current, ...result.secrets }))
      setConfigurationWasConfigured(current => current || (result.configured ?? true))
      setSavedNextcloudSpreadsheetPath(String(settings.spreadsheet_path ?? '').trim())
      if (!nextcloudTestTargetSaved) setLastTestEvidence(undefined)
      setSecrets({})
      success({
        title: translate('commerce:commerceHub.sourceSettingsUpdatedSuccessfully'),
        description: translate('commerce:commerceHub.openingDataSheet'),
      })
      await onSaved({
        kind: 'source',
        externalId: selectedType.id,
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
        ? await commerce.testSource(selectedType.id, configurationPayload())
        : await commerce.testChannel(selectedType.id, configurationPayload())
      if (kind === 'source') {
        if (nextcloudTestTargetSaved) {
          setLastTestEvidence({
            status: result.ok ? 'healthy' : 'unhealthy',
            message: result.message,
            error_code: result.error_class ?? result.code ?? null,
            latency_ms: result.latency_ms ?? null,
            checked_at: result.checked_at ?? null,
          })
        }
        try {
          const refreshed = await commerce.getSourceConfiguration(selectedType.id)
          const refreshedStatus = refreshed.last_test?.status.trim().toLowerCase()
          if (refreshedStatus === 'healthy' || refreshedStatus === 'unhealthy') {
            setLastTestEvidence(refreshed.last_test)
          }
        } catch {
          // Connection feedback below still reports this test. Persisted evidence
          // remains unchanged when the follow-up metadata read is unavailable.
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
          setConnectionFeedback({
            variant: 'success',
            title: translate('commerce:commerceHub.connectionDetailsVerified'),
            message: translate('commerce:commerceHub.connectionDetailsVerifiedDescription'),
          })
        }
        success(kind === 'source'
          ? {
              title: translate('commerce:commerceHub.sourceConnectedSuccessfully'),
              description: translate('commerce:commerceHub.isReadyToUse', { value1: selectedType.name }),
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
            : translate('commerce:commerceHub.pleaseVerifyYourCredentialsAndTryAgain'),
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
          : translate('commerce:commerceHub.pleaseVerifyYourCredentialsAndTryAgain'),
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
    if (!nextcloudConnectionUsable || !savedNextcloudConnection) {
      const message = translate('commerce:commerceHub.validation.saveConnectionBeforeBrowsing')
      setPickerError(message)
      notifyError(message)
      return
    }
    setPickerOpen(true)
    setPickerLoading(true)
    setPickerError(null)
    try {
      // When connection fields have unsaved edits, browse the persisted target.
      // This keeps completed setup editable without forwarding a stored secret
      // to a draft URL that the Owner has not saved yet.
      const browseSettings = nextcloudConnectionMatchesDraft
        ? settings
        : {
            ...settings,
            url: savedNextcloudConnection.url,
            username: savedNextcloudConnection.username,
          }
      const result = await commerce.browseNextcloud(selectedType.id, {
        path,
        settings: browseSettings,
        secrets: nextcloudConnectionMatchesDraft ? secrets : {},
      })
      setPickerData(result)
    } catch (error) {
      setPickerError(apiErrorMessage(error, 'Unable to browse Nextcloud'))
    } finally {
      setPickerLoading(false)
    }
  }

  function selectNextcloudFile(file: NextcloudBrowseItem) {
    if (!file.supported) return
    setSettings(current => ({ ...current, spreadsheet_path: file.path }))
    setConnectionFeedback(null)
    setPickerOpen(false)
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

  const HeadingTag = headingLevel === 2 ? 'h2' : 'h3'

  return (
    <form onSubmit={event => void submit(event)} className="fh-card overflow-hidden">
      <div className="fh-panel-header">
        <div>
          <HeadingTag className="fh-section-title">
            {initialResourceId ? translate('commerce:commerceHub.configure2', { value1: localizedChannelName(selected.id, selected.name) }) : kind === "source" ? translate('commerce:commerceHub.addSource') : translate('commerce:commerceHub.addChannel')}
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
          {isNextcloudSource && <p className="fh-text-caption font-semibold">{translate('commerce:commerceHub.setupStep', { step: 1 })}</p>}
          <p className="fh-form-section-title">{translate('commerce:commerceHub.general')}</p>
          <p className="fh-form-section-description">{translate('commerce:commerceHub.defineTheConnectorTypeDisplayNameAnd')}</p>
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
            onChange={event => setEnabled(event.target.checked)}
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
            {isNextcloudSource && <p className="fh-text-caption font-semibold">{translate('commerce:commerceHub.setupStep', { step: 2 })}</p>}
            <p className="fh-form-section-title">{translate('commerce:commerceHub.connectionSettings')}</p>
            <p className="fh-form-section-description">{translate('commerce:commerceHub.enterTheCredentialsRequiredToVerifyThis')}</p>
          </div>
          {isNextcloudSource && (
            <Badge variant={nextcloudConnectionMatchesDraft ? 'success' : 'neutral'}>
              {nextcloudConnectionMatchesDraft
                ? translate('commerce:commerceHub.connectionConfigured')
                : savedNextcloudConnection
                  ? translate('commerce:commerceHub.connectionHasUnsavedChanges')
                  : translate('commerce:commerceHub.connectionNotConfigured')}
            </Badge>
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
            <button type="button" onClick={() => void testConnection()} disabled={testing || saving || !canTest} className="fh-button-secondary px-4">
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

      {hasSpreadsheetResource && (
        <div className="fh-stack">
          <div
            className={["fh-form-section", isNextcloudSource && !nextcloudConnectionUsable ? "opacity-70" : ''].join(' ')}
            aria-disabled={isNextcloudSource && !nextcloudConnectionUsable}
            data-setup-step="spreadsheet"
          >
            {selected.provider === "nextcloud" ? (
              <div>
                <p className="fh-text-caption font-semibold">{translate('commerce:commerceHub.setupStep', { step: 3 })}</p>
                <p className="fh-form-section-title">{translate('commerce:commerceHub.nextcloudSpreadsheetFile')}</p>
                <p className="fh-form-section-description">{translate('commerce:commerceHub.useWebdavWithYourAppPasswordPublic')}</p>
                <div
                  className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end"
                  data-testid="nextcloud-file-control-row"
                >
                  <div className="fh-field min-w-0">
                    <span className="fh-help-text">{translate('commerce:commerceHub.selectedFile')}</span>
                    <div className="min-h-10 rounded-md border border-border bg-bg-subtle px-3 py-2 fh-text-body">
                      {settings.spreadsheet_path || translate('commerce:commerceHub.noSpreadsheetFileSelected')}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void browseNextcloud('/')}
                    disabled={!nextcloudConnectionUsable}
                    className="fh-button-secondary w-full px-4 md:w-auto"
                  >
                    {translate('commerce:commerceHub.browseNextcloud')}
                  </button>
                </div>
                {!nextcloudConnectionUsable && (
                  <p className="mt-3 fh-text-caption" role="note">
                    <Icon name="info" /> {translate('commerce:commerceHub.lockedUntilConnectionSaved')}
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
              {isNextcloudSource && <p className="fh-text-caption font-semibold">{translate('commerce:commerceHub.setupStep', { step: 4 })}</p>}
              <p className="fh-form-section-title">{translate('commerce:commerceHub.worksheet')}</p>
              <p className="fh-form-section-description">{translate('commerce:commerceHub.chooseWhetherFlowhubShouldReadEveryWorksheet')}</p>
            </div>
            {!worksheetStepAvailable && (
              <p className="fh-text-caption" role="note"><Icon name="info" /> {translate('commerce:commerceHub.lockedUntilConnectionSaved')}</p>
            )}
            <fieldset
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
            </fieldset>
          </div>

          <div
            className={["fh-form-section", !dataSheetStepAvailable ? "opacity-70" : ''].join(' ')}
            aria-disabled={!dataSheetStepAvailable}
            data-setup-step="data-sheet"
          >
            <div>
              {isNextcloudSource && <p className="fh-text-caption font-semibold">{translate('commerce:commerceHub.setupStep', { step: 5 })}</p>}
              <p className="fh-form-section-title">{translate('sources:sourceConfiguration.channelMappings')}</p>
              <p className="fh-form-section-description">{translate('commerce:commerceHub.worksheetsMappingMovedToDataSheet')}</p>
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
                onClick={() => onConfigureData(selectedType.id)}
              >
                <Icon name="workspace" /> {translate('commerce:commerceHub.configureData')} <Icon name="next" />
              </button>
            ) : (
              <p className="fh-text-caption">{translate('commerce:commerceHub.saveConnectionBeforeConfiguringData')}</p>
            )}
            {isNextcloudSource && !dataSheetStepAvailable && (
              <p className="fh-text-caption" role="note"><Icon name="info" /> {translate(
                nextcloudConnectionUsable
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
                <p className="fh-text-caption font-semibold">{translate('commerce:commerceHub.setupStep', { step: 6 })}</p>
                <p className="fh-form-section-title">{translate('commerce:commerceHub.monetaryUnit')}</p>
                <p className="fh-form-section-description">{translate('commerce:commerceHub.monetaryUnitDescription')}</p>
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
          onClose={() => setPickerOpen(false)}
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
        description: translate('commerce:commerceHub.pleaseVerifyYourCredentialsAndTryAgain'),
      })
      await loadCommerce()
    } catch {
      notifyError({
        title: translate('commerce:commerceHub.unableToConnectToTheChannel'),
        description: translate('commerce:commerceHub.pleaseVerifyYourCredentialsAndTryAgain'),
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
    return sourceWorkspaceApi.createSource({
      name,
      source_kind: 'external',
      external_source_id: externalId,
      worksheet_mode: 'selected',
      worksheet_name: 'Sheet1',
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
      navigate(`/sources/${managed.id}`)
    }
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
          <button type="button" className="fh-button-secondary fh-button-sm mb-4" onClick={() => navigate('/sources')}>
            <Icon name="previous" /> {translate('sources:sourceConfiguration.backToSources')}
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
                onCancel={() => { setFormKind(null); setEditingSourceId(null); setSearchParams({ tab: 'sources' }) }}
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
