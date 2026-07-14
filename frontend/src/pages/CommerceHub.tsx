import { translate } from '../i18n'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth'
import { apiErrorMessage } from '../api/client'
import Badge from '../components/Badge'
import { useServices } from '../services/ServiceContext'
import type { CommerceChannel, CommerceRelationshipMap, CommerceSource, CommerceTypeField, CommerceTypeOption } from '../services/types'
import type { ChannelCacheRefreshResult, CommerceChannelConfiguration, CommerceVendor, NextcloudBrowseItem, NextcloudBrowseResult } from '../services/commerce/CommerceService'
import Spinner from '../components/loading/Spinner'
import { useNotification } from '../notifications/NotificationProvider'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import { formatDateTime } from '../i18n/format'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'

type Tab = 'sources' | 'channels'
type FormKind = 'source' | 'channel'
type SourceMappingField = { enabled: boolean; column: string }
type SourceMappingDraft = Record<'id' | 'price' | 'stock', SourceMappingField>
type ReadPolicyDraft = { enabled: boolean; max_reads_per_24h: number; manual_read_allowed: boolean }

const DEFAULT_SOURCE_MAPPING: SourceMappingDraft = {
  id: { enabled: true, column: 'B' },
  price: { enabled: true, column: 'C' },
  stock: { enabled: false, column: 'D' },
}

const DEFAULT_READ_POLICY: ReadPolicyDraft = {
  enabled: true,
  max_reads_per_24h: 10,
  manual_read_allowed: true,
}

function prettyStatus(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

const SNAPPSHOP_ESSENTIAL_FIELDS = new Set(['token', 'agent_identifier'])
const SNAPPSHOP_ADVANCED_FIELDS = new Set(['base_url', 'agent_header_name', 'request_timeout'])

function snappShopVendorActive(status: string | null | undefined): boolean {
  if (!status) return true
  return ['ACTIVE', 'ENABLED', 'TRUE', '1'].includes(status.trim().toUpperCase())
}

function channelDisplayName(provider: string, fallback: string): string {
  if (['woocommerce', 'snappshop', 'tapsishop', 'shopify'].includes(provider)) {
    return formatChannelDisplayName(`${provider}:primary`)
  }
  return fallback
}

function SafetyBadges({ readOnly, writeBlocked }: { readOnly: boolean; writeBlocked: boolean }) {
  return (
    <div className="flex flex-wrap gap-2">
      {readOnly && <Badge variant="neutral">{translate('commerce:commerceHub.readOnlyMode')}</Badge>}
      {writeBlocked && <Badge variant="danger">{translate('commerce:commerceHub.writesBlocked')}</Badge>}
    </div>
  )
}

function RelationshipMap({ map }: { map: CommerceRelationshipMap | null }) {
  const nodes = map?.nodes ?? [translate('commerce:commerceHub.source'), translate('commerce:commerceHub.flowhubDataLayer'), translate('commerce:commerceHub.channel')]
  const example = map?.example ?? ['Nextcloud', translate('commerce:commerceHub.dataLayer'), 'WooCommerce']
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

function SourceCard({ source, onTest, onRead, onConfigure, testing, reading, canManage }: {
  source: CommerceSource
  onTest: (sourceId: string) => void
  onRead: (sourceId: string) => void
  onConfigure: (sourceId: string) => void
  testing: boolean
  reading: boolean
  canManage: boolean
}) {
  const canUseNextcloudActions = canManage && source.provider === 'nextcloud' && !source.placeholder
  const readStatus = source.read_status
  return (
    <div className="fh-card fh-card-pad flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="fh-section-title">{source.name}</h3>
            <Badge variant={source.status === "degraded" ? "warning" : ["healthy", "configured", "current"].includes(source.status) ? "success" : ["planned", "future", "not_configured", "unknown"].includes(source.status) ? "neutral" : "danger"}>
              {prettyStatus(source.status)}
            </Badge>
            {source.placeholder && <Badge variant="neutral">{translate('commerce:commerceHub.plannedSource')}</Badge>}
          </div>
          <p className="fh-text-caption mt-1">{source.data_role}</p>
        </div>
        <span className="fh-text-caption font-medium text-text-base">{source.type}</span>
      </div>

      <div className="fh-form-grid sm:grid-cols-2 fh-text-caption">
        <p><span className="text-wp-muted">{translate('commerce:commerceHub.credentialStatus')} </span><span className="font-medium text-text-base">{prettyStatus(source.credential_status)}</span></p>
        <p><span className="text-wp-muted">{translate('commerce:commerceHub.lastHealthCheck')} </span><span className="font-medium text-text-base">{source.last_health_check ? formatDateTime(source.last_health_check) : translate('commerce:commerceHub.notChecked')}</span></p>
        <p><span className="text-wp-muted">{translate('commerce:commerceHub.health')} </span><span className="font-medium text-text-base">{prettyStatus(source.health?.status ?? "unknown")}</span></p>
        <p><span className="text-wp-muted">{translate('commerce:commerceHub.dataRole')} </span><span className="font-medium text-text-base">{source.data_role}</span></p>
        {readStatus && (
          <>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.lastRead')} </span><span className="font-medium text-text-base">{readStatus.last_read_at ? formatDateTime(readStatus.last_read_at) : translate('commerce:commerceHub.notRead')}</span></p>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.readsRemaining')} </span><span className="font-medium text-text-base">{readStatus.reads_remaining}</span></p>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.lastReadStatus')} </span><span className="font-medium text-text-base">{readStatus.last_read_status ? prettyStatus(readStatus.last_read_status) : translate('commerce:commerceHub.notRead')}</span></p>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.lastRowCount')} </span><span className="font-medium text-text-base">{readStatus.last_row_count ?? '-'}</span></p>
          </>
        )}
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <SafetyBadges readOnly={source.read_only} writeBlocked={source.runtime_write_blocked} />
        {canUseNextcloudActions && (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              aria-label={translate('commerce:commerceHub.sourceSettings')}
              onClick={() => onConfigure(source.id)}
              className="fh-button-secondary"
            >
              <Icon name="settings" />
              {translate('commerce:commerceHub.settings')}
            </button>
            <button
              onClick={() => onTest(source.id)}
              disabled={testing || reading}
              className="fh-button-secondary"
            >
              {testing && <Spinner size="sm" />}
              {!testing && <Icon name="testConnection" />}
              {testing ? translate('commerce:commerceHub.testing') : translate('commerce:commerceHub.testConnection')}
            </button>
            <button
              onClick={() => onRead(source.id)}
              disabled={testing || reading || source.read_policy?.manual_read_allowed === false}
              className="fh-button-secondary"
            >
              {reading && <Spinner size="sm" />}
              {!reading && <Icon name="sync" />}
              {reading ? translate('commerce:commerceHub.reading') : translate('commerce:commerceHub.readNow')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function ChannelCard({ channel, onTest, onRefresh, onConfigure, testing, refreshing, refreshResult, canManage }: {
  channel: CommerceChannel
  onTest: (channelId: string) => void
  onRefresh: (channelId: string) => void
  onConfigure: (channelId: string) => void
  testing: boolean
  refreshing: boolean
  refreshResult?: ChannelCacheRefreshResult
  canManage: boolean
}) {
  const isWooCommerce = channel.provider === 'woocommerce' && !channel.placeholder
  const supportsProductCache = ['woocommerce', 'snappshop'].includes(channel.provider) && !channel.placeholder
  const isConfigurable = channel.implemented && !channel.placeholder && ['woocommerce', 'snappshop', 'tapsishop'].includes(channel.provider)
  const isConfigured = channel.credential_status === 'configured'
  return (
    <div className="fh-card fh-card-pad flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="fh-section-title">{channel.name}</h3>
            <Badge variant={channel.status === "degraded" ? "warning" : ["healthy", "configured", "current"].includes(channel.status) ? "success" : ["planned", "future", "not_configured", "unknown"].includes(channel.status) ? "neutral" : "danger"}>
              {prettyStatus(channel.status)}
            </Badge>
            {channel.placeholder && <Badge variant="neutral">{translate('commerce:commerceHub.plannedChannel')}</Badge>}
          </div>
          <p className="fh-text-caption mt-1">{channel.capabilities_summary.join(', ')}</p>
        </div>
        <span className="fh-text-caption font-medium text-text-base">{channel.type}</span>
      </div>

      <div className="fh-form-grid sm:grid-cols-2 fh-text-caption">
        <p><span className="text-wp-muted">{translate('commerce:commerceHub.credentialStatus')} </span><span className="font-medium text-text-base">{prettyStatus(channel.credential_status)}</span></p>
        {channel.provider === "snappshop" && (
          <>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.setupState')} </span><span className="font-medium text-text-base">{prettyStatus(channel.configuration_state ?? "not_configured")}</span></p>
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.vendorSelected')} </span><span className="font-medium text-text-base">{channel.vendor_selected ? translate('commerce:commerceHub.yes') : translate('commerce:commerceHub.no')}</span></p>
          </>
        )}
        <p><span className="text-wp-muted">{translate('commerce:commerceHub.lastHealthCheck')} </span><span className="font-medium text-text-base">{channel.last_health_check ? formatDateTime(channel.last_health_check) : translate('commerce:commerceHub.notChecked')}</span></p>
        <p><span className="text-wp-muted">{translate('commerce:commerceHub.health')} </span><span className="font-medium text-text-base">{prettyStatus(channel.health?.status ?? "unknown")}</span></p>
        <p><span className="text-wp-muted">{translate('commerce:commerceHub.capabilities')} </span><span className="font-medium text-text-base">{channel.capabilities_summary.join(', ')}</span></p>
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
            <p><span className="text-wp-muted">{translate('commerce:commerceHub.refreshStatus')} </span><span className="font-medium text-text-base">{prettyStatus(channel.cache_refresh_status)}</span></p>
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
                {refreshing ? translate('commerce:commerceHub.refreshing') : translate('commerce:commerceHub.refreshProductCache')}
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

function ConfigPanel({
  kind,
  types,
  initialChannelId,
  onCancel,
  onSaved,
}: {
  kind: FormKind
  types: CommerceTypeOption[]
  initialChannelId?: string | null
  onCancel: () => void
  onSaved: () => Promise<void>
}) {
  const { commerce } = useServices()
  const { success, error: notifyError } = useNotification()
  const [selectedId, setSelectedId] = useState(initialChannelId ?? types[0]?.id ?? '')
  const selected = useMemo(
    () => types.find(item => item.id === selectedId) ?? types[0],
    [selectedId, types],
  )
  const [displayName, setDisplayName] = useState(selected?.name ?? '')
  const [enabled, setEnabled] = useState(false)
  const [accessMode, setAccessMode] = useState<'read_only' | 'write_enabled'>('read_only')
  const [description, setDescription] = useState('')
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [secrets, setSecrets] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [loadingConfiguration, setLoadingConfiguration] = useState(Boolean(initialChannelId))
  const [secretStatus, setSecretStatus] = useState<CommerceChannelConfiguration['secrets']>({})
  const [configurationWasConfigured, setConfigurationWasConfigured] = useState(false)
  const [vendors, setVendors] = useState<CommerceVendor[]>([])
  const [vendorInformation, setVendorInformation] = useState<CommerceVendor | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerLoading, setPickerLoading] = useState(false)
  const [pickerData, setPickerData] = useState<NextcloudBrowseResult | null>(null)
  const [pickerError, setPickerError] = useState<string | null>(null)
  const [sourceMapping, setSourceMapping] = useState<SourceMappingDraft>(DEFAULT_SOURCE_MAPPING)
  const [worksheetMode, setWorksheetMode] = useState<'all' | 'selected'>('all')
  const [worksheetName, setWorksheetName] = useState('')
  const [readPolicy, setReadPolicy] = useState<ReadPolicyDraft>(DEFAULT_READ_POLICY)
  const nextcloudUrlError = kind === 'source' && selected?.provider === 'nextcloud'
    ? nextcloudUrlErrorFor(settings)
    : null

  useEffect(() => {
    if (initialChannelId) return
    setDisplayName(selected?.name ?? '')
    setEnabled(false)
    setDescription('')
    setSettings(Object.fromEntries((selected?.settings_schema ?? [])
      .filter(field => !field.secret && field.default !== undefined && field.default !== null)
      .map(field => [field.key, String(field.default)])))
    setSecrets({})
    setAccessMode('read_only')
    setSecretStatus({})
    setConfigurationWasConfigured(false)
    setVendors([])
    setVendorInformation(null)
    setPickerOpen(false)
    setPickerData(null)
    setPickerError(null)
    setSourceMapping(DEFAULT_SOURCE_MAPPING)
    setWorksheetMode('all')
    setWorksheetName('')
    setReadPolicy(DEFAULT_READ_POLICY)
  }, [selected?.id, initialChannelId])

  useEffect(() => {
    if (kind !== 'channel' || !initialChannelId) return
    let active = true
    setLoadingConfiguration(true)
    setSelectedId(initialChannelId)
    commerce.getChannelConfiguration(initialChannelId)
      .then(configuration => {
        if (!active) return
        setDisplayName(configuration.display_name)
        setEnabled(configuration.enabled)
        setAccessMode(configuration.access_mode)
        setSettings(Object.fromEntries(Object.entries(configuration.settings).map(([key, value]) => [key, value == null ? '' : String(value)])))
        setSecrets({})
        setSecretStatus(configuration.secrets)
        setConfigurationWasConfigured(configuration.configured)
      })
      .catch(() => {
        if (active) notifyError({
          title: translate('commerce:commerceHub.unableToLoadChannelSettings'),
          description: translate('commerce:commerceHub.pleaseTryAgain'),
        })
      })
      .finally(() => {
        if (active) setLoadingConfiguration(false)
      })
    return () => { active = false }
  }, [commerce, initialChannelId, kind, notifyError])

  if (!selected) return null

  const configuredSecret = (key: string) => secretStatus[key]?.status === 'configured'
  const hasSecret = (key: string) => Boolean(secrets[key]?.trim()) || configuredSecret(key)
  const canTest = selected.provider === 'snappshop'
    ? Boolean(settings.agent_identifier?.trim()) && hasSecret('token')
    : selected.provider === 'tapsishop'
      ? hasSecret('token')
      : selected.provider === 'woocommerce'
        ? Boolean(settings.url?.trim()) && hasSecret('key') && hasSecret('secret')
        : true
  const canSave = selected.provider !== 'snappshop' || Boolean(settings.vendor_id?.trim())

  function configurationPayload() {
    return {
      display_name: displayName,
      enabled: selected.placeholder ? false : enabled,
      access_mode: accessMode,
      description,
      settings: kind === 'source' && selected.provider === 'nextcloud'
        ? {
            ...settings,
            source_mapping: sourceMapping,
            source_read_policy: readPolicy,
            worksheet_mode: worksheetMode,
            worksheet_name: worksheetName,
          }
        : settings,
      secrets,
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
      if (kind === 'source') await commerce.saveSource(selected.id, payload)
      else await commerce.saveChannel(selected.id, payload)
      success(kind === 'source'
        ? configurationWasConfigured
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
      await onSaved()
    } catch {
      notifyError({
        title: kind === 'source' ? translate('commerce:commerceHub.unableToSaveSourceSettings') : translate('commerce:commerceHub.unableToSaveChannelSettings'),
        description: translate('commerce:commerceHub.pleaseReviewYourChangesAndTryAgain'),
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
    setTesting(true)
    try {
      const result = kind === 'source'
        ? await commerce.testSource(selected.id)
        : await commerce.testChannel(selected.id, configurationPayload())
      if (result.ok) {
        const discoveredVendors = result.vendors ?? []
        setVendors(discoveredVendors)
        setVendorInformation(result.vendor_information ?? null)
        if (selected.provider === 'snappshop') {
          const suggested = result.suggested_vendor_id
            ?? (discoveredVendors.filter(vendor => snappShopVendorActive(vendor.status)).length === 1
              ? discoveredVendors.find(vendor => snappShopVendorActive(vendor.status))?.id
              : null)
          if (suggested) {
            setSettings(current => ({ ...current, vendor_id: current.vendor_id || suggested }))
          }
        }
        success(kind === 'source'
          ? {
              title: translate('commerce:commerceHub.sourceConnectedSuccessfully'),
              description: translate('commerce:commerceHub.isReadyToUse', { value1: selected.name }),
            }
          : {
              title: translate('commerce:commerceHub.channelConnectedSuccessfully'),
              description: translate('commerce:commerceHub.isReadyToUse', { value1: channelDisplayName(selected.provider, selected.name) }),
            })
      }
      else notifyError({
        title: kind === 'source' ? translate('commerce:commerceHub.unableToConnectToTheSource') : translate('commerce:commerceHub.unableToConnectToTheChannel'),
        description: translate('commerce:commerceHub.pleaseVerifyYourCredentialsAndTryAgain'),
      })
    } catch {
      notifyError({
        title: kind === 'source' ? translate('commerce:commerceHub.unableToConnectToTheSource') : translate('commerce:commerceHub.unableToConnectToTheChannel'),
        description: translate('commerce:commerceHub.pleaseVerifyYourCredentialsAndTryAgain'),
      })
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
    if (!settings.url || !hasNextcloudUsername(settings) || !secrets.password) {
      const message = translate('commerce:commerceHub.validation.nextcloudCredentialsRequired')
      setPickerError(message)
      notifyError(message)
      return
    }
    setPickerOpen(true)
    setPickerLoading(true)
    setPickerError(null)
    try {
      const result = await commerce.browseNextcloud(selected.id, {
        path,
        settings,
        secrets,
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
    setPickerOpen(false)
  }

  function updateMappingField(field: keyof SourceMappingDraft, patch: Partial<SourceMappingField>) {
    setSourceMapping(current => ({
      ...current,
      [field]: { ...current[field], ...patch },
    }))
  }

  function renderConnectionField(field: CommerceTypeField) {
    return (
      <label key={field.key} className="fh-field">
        <span className="fh-help-text">{fieldLabel(kind, selected.provider, field.key, field.label)}</span>
        {["token_refresh_enabled", "revoke_current_token"].includes(field.key) ? (
          <input
            type="checkbox"
            checked={settings[field.key] === "true"}
            onChange={event => setSettings(current => ({ ...current, [field.key]: String(event.target.checked) }))}
          />
        ) : (
          <input
            type={field.secret ? "password" : field.key === "request_timeout" ? "number" : "text"}
            min={field.key === "request_timeout" ? 1 : undefined}
            max={field.key === "request_timeout" ? 120 : undefined}
            step={field.key === "request_timeout" ? 1 : undefined}
            value={field.secret ? secrets[field.key] ?? '' : settings[field.key] ?? ''}
            onChange={event => {
              const value = event.target.value
              if (field.secret) setSecrets(current => ({ ...current, [field.key]: value }))
              else setSettings(current => {
                const next = { ...current, [field.key]: value }
                if (selected.provider === 'nextcloud' && field.key === 'url' && !next.username) {
                  const usernameFromUrl = webdavUsernameFromUrl(value)
                  if (usernameFromUrl) next.username = usernameFromUrl
                }
                return next
              })
            }}
            className="fh-input"
            autoComplete={field.secret ? "new-password" : undefined}
          />
        )}
        {field.secret && configuredSecret(field.key) && <span className="fh-help-text">{translate('commerce:commerceHub.configuredLeaveBlankToKeepUnchanged')}</span>}
        {selected.provider === "nextcloud" && field.key === "url" && nextcloudUrlError && (
          <span className="fh-field-error">{nextcloudUrlError}</span>
        )}
      </label>
    )
  }

  if (loadingConfiguration) {
    return <div className="fh-card fh-card-pad flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />{translate('commerce:commerceHub.loadingChannelConfiguration')}</div>
  }

  return (
    <form onSubmit={event => void submit(event)} className="fh-card overflow-hidden">
      <div className="fh-panel-header !items-start">
        <div>
          <h3 className="fh-section-title">
            {initialChannelId ? translate('commerce:commerceHub.configure2', { value1: selected.name }) : kind === "source" ? translate('commerce:commerceHub.addSource') : translate('commerce:commerceHub.addChannel')}
          </h3>
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
      <div className="fh-form-section">
        <div>
          <p className="fh-form-section-title">{translate('commerce:commerceHub.general')}</p>
          <p className="fh-form-section-description">{translate('commerce:commerceHub.defineTheConnectorTypeDisplayNameAnd')}</p>
        </div>
        <div className="fh-form-grid md:grid-cols-2">
        <label className="fh-field">
          <span className="fh-help-text">{kind === "source" ? translate('commerce:commerceHub.sourceType') : translate('commerce:commerceHub.channelType')}</span>
          <select
            value={selected.id}
            onChange={event => setSelectedId(event.target.value)}
            disabled={Boolean(initialChannelId)}
            className="fh-select"
          >
            {types.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <label className="fh-field">
          <span className="fh-help-text">{translate('commerce:commerceHub.displayName')}</span>
          <input value={displayName} onChange={event => setDisplayName(event.target.value)} className="fh-input" />
        </label>
        <label className="fh-field md:col-span-2">
          <span className="fh-help-text">{translate('commerce:commerceHub.descriptionOptional')}</span>
          <input value={description} onChange={event => setDescription(event.target.value)} className="fh-input" />
        </label>
        {kind === 'channel' && (
          <label className="fh-field">
            <span className="fh-help-text">{translate('commerce:commerceHub.accessMode')}</span>
            <select value={accessMode} onChange={event => setAccessMode(event.target.value as 'read_only' | 'write_enabled')} className="fh-select">
              <option value="read_only">{translate('commerce:commerceHub.readOnly2')}</option>
              {selected.provider === 'woocommerce' && <option value="write_enabled">{translate('commerce:commerceHub.writeEnabled2')}</option>}
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
        <SafetyBadges readOnly={selected.read_only} writeBlocked={selected.runtime_write_blocked} />
        {selected.placeholder && (
          <Badge variant="neutral">
            {kind === "source" ? translate('commerce:commerceHub.plannedSource') : translate('commerce:commerceHub.plannedChannel')}
          </Badge>
        )}
        {selected.placeholder && <Badge variant="neutral">{translate('commerce:commerceHub.notConfigured2')}</Badge>}
        </div>
      </div>

      <div className="fh-form-section">
        <div>
          <p className="fh-form-section-title">{translate('commerce:commerceHub.connectionSettings')}</p>
          <p className="fh-form-section-description">{translate('commerce:commerceHub.enterTheCredentialsRequiredToVerifyThis')}</p>
        </div>
      <div className="fh-form-grid md:grid-cols-2">
        {selected.settings_schema
          .filter(field => !(kind === "source" && selected.provider === "nextcloud" && field.key === "spreadsheet_path"))
          .filter(field => selected.provider !== "snappshop" || SNAPPSHOP_ESSENTIAL_FIELDS.has(field.key))
          .map(renderConnectionField)}
      </div>
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
              required
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

      {kind === "channel" && selected.provider === "snappshop" && (
        <details className="fh-form-section">
          <summary className="fh-form-section-title cursor-pointer">{translate('commerce:commerceHub.advancedSettings')}</summary>
          <p className="fh-form-section-description">{translate('commerce:commerceHub.defaultsAreSuitableForNormalSnappshopAccounts')}</p>
          <div className="fh-form-grid md:grid-cols-2 mt-3">
            {selected.settings_schema
              .filter(field => SNAPPSHOP_ADVANCED_FIELDS.has(field.key))
              .map(renderConnectionField)}
          </div>
        </details>
      )}

      {kind === "channel" && selected.provider === "tapsishop" && (
        <div className="fh-form-section">
          <div>
            <p className="fh-form-section-title">{translate('commerce:commerceHub.webhookRegistration')}</p>
            <p className="fh-form-section-description">{translate('commerce:commerceHub.registerThisUrlInTapsishopTheWebhook')}</p>
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

      {kind === "source" && selected.provider === "nextcloud" && (
        <div className="fh-stack">
          <div className="fh-form-section">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="fh-form-section-title">{translate('commerce:commerceHub.nextcloudSpreadsheetFile')}</p>
                <p className="fh-form-section-description">{translate('commerce:commerceHub.useWebdavWithYourAppPasswordPublic')}</p>
                <p className="mt-3 fh-help-text">{translate('commerce:commerceHub.selectedFile')}</p>
                <div className="mt-1 min-h-10 rounded-md border border-border bg-bg-subtle px-3 py-2 fh-text-body">
                  {settings.spreadsheet_path || "No spreadsheet file selected"}
                </div>
              </div>
              <button
                type="button"
                onClick={() => void browseNextcloud('/')}
                className="fh-button-secondary px-4"
              >
                {translate('commerce:commerceHub.browseNextcloud')}
              </button>
            </div>
          </div>

          <div className="fh-form-section">
            <div>
              <p className="fh-form-section-title">{translate('commerce:commerceHub.columnMapping')}</p>
              <p className="fh-form-section-description">{translate('commerce:commerceHub.enabledFieldsRequireASpreadsheetColumnLetter')}</p>
            </div>
            <div className="fh-form-grid md:grid-cols-3">
              {(["id", "price", "stock"] as const).map(field => (
                <div key={field} className="rounded-md border border-border bg-bg-subtle p-3">
                  <label className="fh-inline-check capitalize">
                    <input
                      type="checkbox"
                      checked={sourceMapping[field].enabled}
                      onChange={event => updateMappingField(field, { enabled: event.target.checked })}
                    />
                    {field === "id" ? translate('commerce:commerceHub.productId') : field}
                  </label>
                  <label className="fh-field mt-2">
                    <span className="fh-help-text">{translate('commerce:commerceHub.column')}</span>
                    <input
                      value={sourceMapping[field].column}
                      onChange={event => updateMappingField(field, { column: event.target.value })}
                      className="fh-input"
                      autoComplete="off"
                    />
                  </label>
                </div>
              ))}
            </div>
          </div>

          <div className="fh-form-grid md:grid-cols-2">
            <div className="fh-form-section">
              <div>
                <p className="fh-form-section-title">{translate('commerce:commerceHub.worksheet')}</p>
                <p className="fh-form-section-description">{translate('commerce:commerceHub.chooseWhetherFlowhubShouldReadEveryWorksheet')}</p>
              </div>
              <div className="flex flex-col gap-2 fh-text-body">
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
              </div>
            </div>

            <div className="fh-form-section">
              <div>
                <p className="fh-form-section-title">{translate('commerce:commerceHub.readPolicy')}</p>
                <p className="fh-form-section-description">{translate('commerce:commerceHub.theseControlsOnlyAffectSourceReadPolicy')}</p>
              </div>
              <div className="flex flex-col gap-3">
                <label className="fh-inline-check">
                  <input
                    type="checkbox"
                    checked={readPolicy.enabled}
                    onChange={event => setReadPolicy(current => ({ ...current, enabled: event.target.checked }))}
                  />
                  {translate('commerce:commerceHub.limitSourceReads')}
                </label>
                <label className="fh-inline-check">
                  <input
                    type="checkbox"
                    checked={readPolicy.manual_read_allowed}
                    onChange={event => setReadPolicy(current => ({ ...current, manual_read_allowed: event.target.checked }))}
                  />
                  {translate('commerce:commerceHub.manualReadNowAllowed')}
                </label>
                <label className="fh-field">
                  <span className="fh-help-text">{translate('commerce:commerceHub.maxReadsPer24Hours')}</span>
                  <input
                    type="number"
                    min={1}
                    max={1000}
                    value={readPolicy.max_reads_per_24h}
                    onChange={event => setReadPolicy(current => ({
                      ...current,
                      max_reads_per_24h: Number(event.target.value || DEFAULT_READ_POLICY.max_reads_per_24h),
                    }))}
                    className="fh-input"
                  />
                </label>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="fh-panel-footer">
        <button type="button" onClick={() => void testConnection()} disabled={testing || !canTest} className="fh-button-secondary px-4">
          {testing && <Spinner size="sm" />}
          {!testing && <Icon name="testConnection" />}
          {testing ? translate('commerce:commerceHub.testing') : translate('commerce:commerceHub.testConnection')}
        </button>
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

export default function CommerceHub() {
  const { commerce } = useServices()
  const { user } = useAuth()
  const { success, error: notifyError } = useNotification()
  const [searchParams, setSearchParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>(searchParams.get('tab') === 'sources' ? 'sources' : 'channels')
  const [sources, setSources] = useState<CommerceSource[]>([])
  const [channels, setChannels] = useState<CommerceChannel[]>([])
  const [sourceTypes, setSourceTypes] = useState<CommerceTypeOption[]>([])
  const [channelTypes, setChannelTypes] = useState<CommerceTypeOption[]>([])
  const [map, setMap] = useState<CommerceRelationshipMap | null>(null)
  const [loading, setLoading] = useState(true)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [readingId, setReadingId] = useState<string | null>(null)
  const [refreshingId, setRefreshingId] = useState<string | null>(null)
  const [refreshResults, setRefreshResults] = useState<Record<string, ChannelCacheRefreshResult>>({})
  const [formKind, setFormKind] = useState<FormKind | null>(null)
  const [editingChannelId, setEditingChannelId] = useState<string | null>(null)
  const canManageCommerce = user?.is_admin === true

  useEffect(() => {
    const queryTab = searchParams.get('tab')
    if (queryTab === 'sources' || queryTab === 'channels') setTab(queryTab)
  }, [searchParams])

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
        description: translate('commerce:commerceHub.pleaseVerifyYourCredentialsAndTryAgain'),
      })
      await loadCommerce()
    } catch {
      notifyError({
        title: translate('commerce:commerceHub.unableToConnectToTheSource'),
        description: translate('commerce:commerceHub.pleaseVerifyYourCredentialsAndTryAgain'),
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
          ? translate('commerce:commerceHub.isReadyToUse', { value1: channelDisplayName(channel.provider, channel.name) })
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

  async function handleSourceRead(sourceId: string) {
    if (!canManageCommerce) {
      notifyError(translate('commerce:commerceHub.adminPermissionRequired'))
      return
    }
    setReadingId(sourceId)
    try {
      const result = await commerce.readSource(sourceId)
      if (result.ok) {
        success({
          title: translate('commerce:commerceHub.sourceRefreshedSuccessfully'),
          description: translate('commerce:commerceHub.rowsLoaded', { count: result.rows_read }),
        })
      } else {
        notifyError({
          title: translate('commerce:commerceHub.unableToRefreshTheSource'),
          description: translate('commerce:commerceHub.pleaseTryAgain'),
        })
      }
      await loadCommerce()
    } catch {
      notifyError({
        title: translate('commerce:commerceHub.unableToRefreshTheSource'),
        description: translate('commerce:commerceHub.pleaseTryAgain'),
      })
    } finally {
      setReadingId(null)
    }
  }

  function handleSourceConfigure(_sourceId: string) {
    if (!canManageCommerce) {
      notifyError(translate('commerce:commerceHub.adminPermissionRequired'))
      return
    }
    setTab('sources')
    setSearchParams({ tab: 'sources' })
    setFormKind('source')
  }

  function handleChannelConfigure(channelId: string) {
    if (!canManageCommerce) {
      notifyError(translate('commerce:commerceHub.adminPermissionRequired'))
      return
    }
    setTab('channels')
    setSearchParams({ tab: 'channels' })
    setEditingChannelId(channelId)
    setFormKind('channel')
  }

  async function reloadAfterSave() {
    await loadCommerce()
    setFormKind(null)
    setEditingChannelId(null)
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('commerce:commerceHub.commerceHub')}</h1>
          <p className="fh-page-subtitle">{translate('commerce:commerceHub.readOnlySourceAndChannelOverview')}</p>
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
          <div className="fh-page-toolbar mb-4">
            <div>
              <h2 className="fh-section-title">{translate('commerce:commerceHub.sources2')}</h2>
              <p className="fh-section-subtitle mt-1">{translate('commerce:commerceHub.inputSystemsThatFeedFlowhubDataLayer')}</p>
            </div>
            {canManageCommerce ? (
              <button onClick={() => setFormKind("source")} className="fh-button-primary px-4">
                <Icon name="add" />
                {translate('commerce:commerceHub.addSource')}
              </button>
            ) : (
              <Badge variant="neutral">{translate('commerce:commerceHub.adminPermissionRequired')}</Badge>
            )}
          </div>
          {formKind === "source" && (
            <div className="mb-4">
              <ConfigPanel kind="source" types={sourceTypes} onCancel={() => setFormKind(null)} onSaved={reloadAfterSave} />
            </div>
          )}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {sources.map(source => (
              <SourceCard
                key={source.id}
                source={source}
                onTest={(id) => void handleSourceTest(id)}
                onRead={(id) => void handleSourceRead(id)}
                onConfigure={handleSourceConfigure}
                testing={testingId === source.id}
                reading={readingId === source.id}
                canManage={canManageCommerce}
              />
            ))}
          </div>
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
                types={channelTypes.filter(item => item.implemented)}
                initialChannelId={editingChannelId}
                onCancel={() => { setFormKind(null); setEditingChannelId(null) }}
                onSaved={reloadAfterSave}
              />
            </div>
          )}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {channels.map(channel => (
              <ChannelCard
                key={channel.id}
                channel={channel}
                onTest={(id) => void handleChannelTest(id)}
                onRefresh={(id) => void handleChannelCacheRefresh(id)}
                onConfigure={handleChannelConfigure}
                testing={testingId === channel.id}
                refreshing={refreshingId === channel.id}
                refreshResult={refreshResults[channel.id]}
                canManage={canManageCommerce}
              />
            ))}
          </div>
        </section>
      )}
    </PageShell>
  )
}
