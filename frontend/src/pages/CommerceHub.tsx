import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth'
import { ApiError } from '../api/client'
import Badge from '../components/Badge'
import { useServices } from '../services/ServiceContext'
import type { CommerceChannel, CommerceRelationshipMap, CommerceSource, CommerceTypeOption } from '../services/types'
import type { NextcloudBrowseItem, NextcloudBrowseResult } from '../services/commerce/CommerceService'
import Spinner from '../components/loading/Spinner'
import { useNotification } from '../notifications/NotificationProvider'
import PageShell from '../components/PageShell'

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

function redactSensitiveText(value: string): string {
  return value.replace(
    /((?:consumer_secret|consumer_key|access_token|refresh_token|authorization|password|api_key|apikey|secret|token|key)\s*["']?\s*[:=]\s*["']?)([^"',\s}]+)/gi,
    '$1[REDACTED]',
  )
}

function apiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    try {
      const parsed = JSON.parse(error.message) as { detail?: unknown }
      if (typeof parsed.detail === 'string' && parsed.detail.trim()) return redactSensitiveText(parsed.detail)
    } catch {
      if (error.message.trim()) return redactSensitiveText(error.message)
    }
  }
  return fallback
}

function SafetyBadges({ readOnly, writeBlocked }: { readOnly: boolean; writeBlocked: boolean }) {
  return (
    <div className="flex flex-wrap gap-2">
      {readOnly && <Badge variant="neutral">Read-only mode</Badge>}
      {writeBlocked && <Badge variant="danger">Writes blocked</Badge>}
    </div>
  )
}

function RelationshipMap({ map }: { map: CommerceRelationshipMap | null }) {
  const nodes = map?.nodes ?? ['Source', 'FlowHub / Data Layer', 'Channel']
  const example = map?.example ?? ['Nextcloud', 'Data Layer', 'WooCommerce']
  return (
    <div className="fh-card fh-card-pad">
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr_auto_1fr] gap-3 items-center text-center">
        <div className="fh-stat-tile">
          <p className="fh-stat-tile-label">{nodes[0]}</p>
          <p className="fh-text-body font-semibold">{example[0]}</p>
        </div>
        <div className="text-xl text-wp-muted">/</div>
        <div className="fh-stat-tile">
          <p className="fh-stat-tile-label">FlowHub</p>
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
            <Badge variant={source.status === 'degraded' ? 'warning' : ['healthy', 'configured', 'current'].includes(source.status) ? 'success' : ['planned', 'future', 'not_configured', 'unknown'].includes(source.status) ? 'neutral' : 'danger'}>
              {prettyStatus(source.status)}
            </Badge>
            {source.placeholder && <Badge variant="neutral">Planned source</Badge>}
          </div>
          <p className="fh-text-caption mt-1">{source.data_role}</p>
        </div>
        <span className="fh-text-caption font-medium text-text-base">{source.type}</span>
      </div>

      <div className="fh-form-grid sm:grid-cols-2 fh-text-caption">
        <p><span className="text-wp-muted">Credential status: </span><span className="font-medium text-text-base">{prettyStatus(source.credential_status)}</span></p>
        <p><span className="text-wp-muted">Last health check: </span><span className="font-medium text-text-base">{source.last_health_check ? new Date(source.last_health_check).toLocaleString() : 'Not checked'}</span></p>
        <p><span className="text-wp-muted">Health: </span><span className="font-medium text-text-base">{prettyStatus(source.health?.status ?? 'unknown')}</span></p>
        <p><span className="text-wp-muted">Data role: </span><span className="font-medium text-text-base">{source.data_role}</span></p>
        {readStatus && (
          <>
            <p><span className="text-wp-muted">Last read: </span><span className="font-medium text-text-base">{readStatus.last_read_at ? new Date(readStatus.last_read_at).toLocaleString() : 'Not read'}</span></p>
            <p><span className="text-wp-muted">Reads remaining: </span><span className="font-medium text-text-base">{readStatus.reads_remaining}</span></p>
            <p><span className="text-wp-muted">Last read status: </span><span className="font-medium text-text-base">{readStatus.last_read_status ? prettyStatus(readStatus.last_read_status) : 'Not read'}</span></p>
            <p><span className="text-wp-muted">Last row count: </span><span className="font-medium text-text-base">{readStatus.last_row_count ?? '-'}</span></p>
          </>
        )}
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <SafetyBadges readOnly={source.read_only} writeBlocked={source.runtime_write_blocked} />
        {canUseNextcloudActions && (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              aria-label="Source settings"
              onClick={() => onConfigure(source.id)}
              className="fh-button-secondary"
            >
              Settings
            </button>
            <button
              onClick={() => onTest(source.id)}
              disabled={testing || reading}
              className="fh-button-secondary"
            >
              {testing && <Spinner size="sm" />}
              {testing ? 'Testing' : 'Test connection'}
            </button>
            <button
              onClick={() => onRead(source.id)}
              disabled={testing || reading || source.read_policy?.manual_read_allowed === false}
              className="fh-button-secondary"
            >
              {reading && <Spinner size="sm" />}
              {reading ? 'Reading' : 'Read now'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function ChannelCard({ channel, onTest, onRefresh, onConfigure, testing, refreshing, canManage }: {
  channel: CommerceChannel
  onTest: (channelId: string) => void
  onRefresh: (channelId: string) => void
  onConfigure: (channelId: string) => void
  testing: boolean
  refreshing: boolean
  canManage: boolean
}) {
  const isWooCommerce = channel.provider === 'woocommerce' && !channel.placeholder
  return (
    <div className="fh-card fh-card-pad flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="fh-section-title">{channel.name}</h3>
            <Badge variant={channel.status === 'degraded' ? 'warning' : ['healthy', 'configured', 'current'].includes(channel.status) ? 'success' : ['planned', 'future', 'not_configured', 'unknown'].includes(channel.status) ? 'neutral' : 'danger'}>
              {prettyStatus(channel.status)}
            </Badge>
            {channel.placeholder && <Badge variant="neutral">Planned channel</Badge>}
          </div>
          <p className="fh-text-caption mt-1">{channel.capabilities_summary.join(', ')}</p>
        </div>
        <span className="fh-text-caption font-medium text-text-base">{channel.type}</span>
      </div>

      <div className="fh-form-grid sm:grid-cols-2 fh-text-caption">
        <p><span className="text-wp-muted">Credential status: </span><span className="font-medium text-text-base">{prettyStatus(channel.credential_status)}</span></p>
        <p><span className="text-wp-muted">Last health check: </span><span className="font-medium text-text-base">{channel.last_health_check ? new Date(channel.last_health_check).toLocaleString() : 'Not checked'}</span></p>
        <p><span className="text-wp-muted">Health: </span><span className="font-medium text-text-base">{prettyStatus(channel.health?.status ?? 'unknown')}</span></p>
        <p><span className="text-wp-muted">Capabilities: </span><span className="font-medium text-text-base">{channel.capabilities_summary.join(', ')}</span></p>
        {isWooCommerce && (
          <>
            <p><span className="text-wp-muted">Cached products: </span><span className="font-medium text-text-base">{channel.cached_products}</span></p>
            <p><span className="text-wp-muted">Cached variations: </span><span className="font-medium text-text-base">{channel.cached_variations}</span></p>
            <p><span className="text-wp-muted">Last cache refresh: </span><span className="font-medium text-text-base">{channel.last_cache_refresh ? new Date(channel.last_cache_refresh).toLocaleString() : 'Not refreshed'}</span></p>
            <p><span className="text-wp-muted">Refresh status: </span><span className="font-medium text-text-base">{prettyStatus(channel.cache_refresh_status)}</span></p>
          </>
        )}
      </div>

      <div className="flex items-center justify-between gap-3">
        <SafetyBadges readOnly={channel.read_only} writeBlocked={channel.write_blocked} />
        {canManage && (
          <div className="flex flex-wrap gap-2 justify-end">
            {isWooCommerce && (
              <button
                type="button"
                onClick={() => onConfigure(channel.id)}
                disabled={testing || refreshing}
                className="fh-button-secondary"
              >
                Settings
              </button>
            )}
            <button
              onClick={() => onTest(channel.id)}
              disabled={testing || refreshing}
              className="fh-button-secondary"
            >
              {testing && <Spinner size="sm" />}
              {testing ? 'Testing' : 'Test connection'}
            </button>
            {isWooCommerce && (
              <button
                onClick={() => onRefresh(channel.id)}
                disabled={testing || refreshing}
                className="fh-button-secondary"
              >
                {refreshing && <Spinner size="sm" />}
                {refreshing ? 'Refreshing' : 'Refresh product cache'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function fieldLabel(kind: FormKind, provider: string, key: string, fallback: string): string {
  if (kind === 'source' && provider === 'nextcloud' && key === 'url') return 'Nextcloud server URL'
  if (kind === 'source' && provider === 'nextcloud' && key === 'password') return 'App password / token'
  if (kind === 'channel' && provider === 'woocommerce' && key === 'url') return 'Store URL'
  if (kind === 'channel' && provider === 'woocommerce' && key === 'key') return 'Consumer Key'
  if (kind === 'channel' && provider === 'woocommerce' && key === 'secret') return 'Consumer Secret'
  if (['seller_id', 'merchant_id'].includes(key)) return 'Seller/store ID'
  if (['api_key', 'api_token'].includes(key)) return 'API key/token'
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
      return 'Public share links are not supported. Use the Nextcloud root URL or your personal WebDAV files URL.'
    }
    if (path.includes('/public.php/dav/files')) {
      return 'Public share links are not supported. Use the Nextcloud root URL or your personal WebDAV files URL.'
    }
    const marker = '/remote.php/dav/files/'
    if (path.includes(marker) && !url.search && !url.hash) {
      const username = path.slice(path.indexOf(marker) + marker.length).split('/')[0]
      return username ? null : 'Use the Nextcloud root URL or the WebDAV files URL shown in Nextcloud Files settings.'
    }
    if (path.includes('/remote.php/dav/files') || path.includes('/remote.php/dav') || path.includes('/apps/files') || url.search || url.hash) {
      return 'Use the Nextcloud root URL or the WebDAV files URL shown in Nextcloud Files settings.'
    }
  } catch {
    return 'Use the Nextcloud root URL or the WebDAV files URL shown in Nextcloud Files settings.'
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
    return 'WebDAV URL username does not match configured username.'
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
            <h3 className="fh-section-title">Browse Nextcloud</h3>
            <p className="fh-section-subtitle mt-1">{currentPath}</p>
          </div>
          <button type="button" onClick={onClose} className="fh-button-secondary">
            Close
          </button>
        </div>
        <div className="overflow-auto p-4">
          {error && <div className="fh-error-alert mb-3">{error}</div>}
          {loading ? (
            <div className="flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />Loading files</div>
          ) : (
            <div className="flex flex-col gap-2">
              {parentPath !== null && (
                <button type="button" onClick={() => onOpenDirectory(parentPath || '/')} className="fh-button-secondary justify-start">
                  Up one folder
                </button>
              )}
              {data?.directories.map(directory => (
                <button
                  key={directory.path}
                  type="button"
                  onClick={() => onOpenDirectory(directory.path)}
                  className="fh-button-secondary justify-start"
                >
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
                  <span className="font-medium text-text-base">{file.name}</span>
                  <span className="fh-text-caption">{file.supported ? 'Spreadsheet' : 'Unsupported'}</span>
                </button>
              ))}
              {!loading && data && data.directories.length === 0 && data.files.length === 0 && (
                <p className="fh-text-body-sm">No spreadsheet files in this folder.</p>
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
  onCancel,
  onSaved,
}: {
  kind: FormKind
  types: CommerceTypeOption[]
  onCancel: () => void
  onSaved: () => Promise<void>
}) {
  const { commerce } = useServices()
  const { info, error: notifyError } = useNotification()
  const [selectedId, setSelectedId] = useState(types[0]?.id ?? '')
  const selected = useMemo(
    () => types.find(item => item.id === selectedId) ?? types[0],
    [selectedId, types],
  )
  const [displayName, setDisplayName] = useState(selected?.name ?? '')
  const [enabled, setEnabled] = useState(false)
  const [description, setDescription] = useState('')
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [secrets, setSecrets] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
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
    setDisplayName(selected?.name ?? '')
    setEnabled(false)
    setDescription('')
    setSettings({})
    setSecrets({})
    setPickerOpen(false)
    setPickerData(null)
    setPickerError(null)
    setSourceMapping(DEFAULT_SOURCE_MAPPING)
    setWorksheetMode('all')
    setWorksheetName('')
    setReadPolicy(DEFAULT_READ_POLICY)
  }, [selected?.id])

  if (!selected) return null

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (nextcloudUrlError) {
      notifyError(nextcloudUrlError)
      return
    }
    setSaving(true)
    try {
      const payload = {
        display_name: displayName,
        enabled: selected.placeholder ? false : enabled,
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
      if (kind === 'source') await commerce.saveSource(selected.id, payload)
      else await commerce.saveChannel(selected.id, payload)
      info(`${selected.name} configuration saved. Secrets remain write-only.`)
      await onSaved()
    } catch (error) {
      notifyError(apiErrorMessage(error, `Unable to save ${kind} configuration`))
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
        : await commerce.testChannel(selected.id)
      if (result.ok) info(result.message)
      else notifyError(result.message)
    } catch (error) {
      notifyError(apiErrorMessage(error, 'Unable to test connection'))
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
      const message = 'Enter Nextcloud server URL, Username, and App password / token before browsing Nextcloud.'
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

  return (
    <form onSubmit={event => void submit(event)} className="fh-card overflow-hidden">
      <div className="fh-panel-header !items-start">
        <div>
          <h3 className="fh-section-title">
            {kind === 'source' ? 'Add Source' : 'Add Channel'}
          </h3>
          <p className="fh-section-subtitle mt-1">
            Configuration is local to FlowHub and remains read-only.
          </p>
        </div>
        <button type="button" onClick={onCancel} className="fh-button-secondary">
          Close
        </button>
      </div>

      <div className="fh-panel-body fh-stack">
      <div className="fh-form-section">
        <div>
          <p className="fh-form-section-title">General</p>
          <p className="fh-form-section-description">Define the connector type, display name, and local FlowHub state.</p>
        </div>
        <div className="fh-form-grid md:grid-cols-2">
        <label className="fh-field">
          <span className="fh-help-text">{kind === 'source' ? 'Source type' : 'Channel type'}</span>
          <select
            value={selected.id}
            onChange={event => setSelectedId(event.target.value)}
            className="fh-select"
          >
            {types.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <label className="fh-field">
          <span className="fh-help-text">Display name</span>
          <input value={displayName} onChange={event => setDisplayName(event.target.value)} className="fh-input" />
        </label>
        <label className="fh-field md:col-span-2">
          <span className="fh-help-text">Description optional</span>
          <input value={description} onChange={event => setDescription(event.target.value)} className="fh-input" />
        </label>
        </div>

        <div className="fh-actions">
        <label className="fh-inline-check">
          <input
            type="checkbox"
            checked={enabled && !selected.placeholder}
            disabled={selected.placeholder}
            onChange={event => setEnabled(event.target.checked)}
          />
          Enabled
        </label>
        <SafetyBadges readOnly={selected.read_only} writeBlocked={selected.runtime_write_blocked} />
        {selected.placeholder && (
          <Badge variant="neutral">
            {kind === 'source' ? 'Planned source' : 'Planned channel'}
          </Badge>
        )}
        {selected.placeholder && <Badge variant="neutral">Not configured</Badge>}
        </div>
      </div>

      <div className="fh-form-section">
        <div>
          <p className="fh-form-section-title">Connection Settings</p>
          <p className="fh-form-section-description">Labels, help text, and validation states are normalized here without changing the underlying validation rules.</p>
        </div>
      <div className="fh-form-grid md:grid-cols-2">
        {selected.settings_schema
          .filter(field => !(kind === 'source' && selected.provider === 'nextcloud' && field.key === 'spreadsheet_path'))
          .map(field => (
          <label key={field.key} className="fh-field">
            <span className="fh-help-text">{fieldLabel(kind, selected.provider, field.key, field.label)}</span>
            <input
              type={field.secret ? 'password' : 'text'}
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
              autoComplete="off"
            />
            {selected.provider === 'nextcloud' && field.key === 'url' && nextcloudUrlError && (
              <span className="fh-field-error">{nextcloudUrlError}</span>
            )}
          </label>
        ))}
      </div>
      </div>

      {kind === 'source' && selected.provider === 'nextcloud' && (
        <div className="fh-stack">
          <div className="fh-form-section">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="fh-form-section-title">Nextcloud spreadsheet file</p>
                <p className="fh-form-section-description">Use WebDAV with your app password. Public share links are not required.</p>
                <p className="mt-3 fh-help-text">Selected file</p>
                <div className="mt-1 min-h-10 rounded-md border border-border bg-bg-subtle px-3 py-2 fh-text-body">
                  {settings.spreadsheet_path || 'No spreadsheet file selected'}
                </div>
              </div>
              <button
                type="button"
                onClick={() => void browseNextcloud('/')}
                className="fh-button-secondary px-4"
              >
                Browse Nextcloud
              </button>
            </div>
          </div>

          <div className="fh-form-section">
            <div>
              <p className="fh-form-section-title">Column Mapping</p>
              <p className="fh-form-section-description">Enabled fields require a spreadsheet column letter or header name.</p>
            </div>
            <div className="fh-form-grid md:grid-cols-3">
              {(['id', 'price', 'stock'] as const).map(field => (
                <div key={field} className="rounded-md border border-border bg-bg-subtle p-3">
                  <label className="fh-inline-check capitalize">
                    <input
                      type="checkbox"
                      checked={sourceMapping[field].enabled}
                      onChange={event => updateMappingField(field, { enabled: event.target.checked })}
                    />
                    {field === 'id' ? 'Product ID' : field}
                  </label>
                  <label className="fh-field mt-2">
                    <span className="fh-help-text">Column</span>
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
                <p className="fh-form-section-title">Worksheet</p>
                <p className="fh-form-section-description">Choose whether FlowHub should read every worksheet or a single named worksheet.</p>
              </div>
              <div className="flex flex-col gap-2 fh-text-body">
                <label className="fh-inline-check">
                  <input
                    type="radio"
                    name="worksheet_mode"
                    checked={worksheetMode === 'all'}
                    onChange={() => setWorksheetMode('all')}
                  />
                  All worksheets
                </label>
                <label className="fh-inline-check">
                  <input
                    type="radio"
                    name="worksheet_mode"
                    checked={worksheetMode === 'selected'}
                    onChange={() => setWorksheetMode('selected')}
                  />
                  Selected worksheet
                </label>
                <label className="fh-field">
                  <span className="fh-help-text">Worksheet name</span>
                  <input
                    value={worksheetName}
                    onChange={event => setWorksheetName(event.target.value)}
                    disabled={worksheetMode !== 'selected'}
                    className="fh-input"
                  />
                </label>
              </div>
            </div>

            <div className="fh-form-section">
              <div>
                <p className="fh-form-section-title">Read Policy</p>
                <p className="fh-form-section-description">These controls only affect source read policy presentation and action placement.</p>
              </div>
              <div className="flex flex-col gap-3">
                <label className="fh-inline-check">
                  <input
                    type="checkbox"
                    checked={readPolicy.enabled}
                    onChange={event => setReadPolicy(current => ({ ...current, enabled: event.target.checked }))}
                  />
                  Limit source reads
                </label>
                <label className="fh-inline-check">
                  <input
                    type="checkbox"
                    checked={readPolicy.manual_read_allowed}
                    onChange={event => setReadPolicy(current => ({ ...current, manual_read_allowed: event.target.checked }))}
                  />
                  Manual Read now allowed
                </label>
                <label className="fh-field">
                  <span className="fh-help-text">Max reads per 24 hours</span>
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
        <button type="button" onClick={() => void testConnection()} disabled={testing} className="fh-button-secondary px-4">
          {testing && <Spinner size="sm" />}
          {testing ? 'Testing' : 'Test connection'}
        </button>
        <button type="submit" disabled={saving} className="fh-button-primary px-4">
          {saving && <Spinner size="sm" />}
          {saving ? 'Saving' : 'Save configuration'}
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
  const { info, error: notifyError } = useNotification()
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
  const [formKind, setFormKind] = useState<FormKind | null>(null)
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
      .catch(() => notifyError('Unable to load Commerce Hub'))
      .finally(() => setLoading(false))
  }, [commerce])

  function selectTab(nextTab: Tab) {
    setTab(nextTab)
    setSearchParams({ tab: nextTab })
    setFormKind(null)
  }

  async function handleSourceTest(sourceId: string) {
    if (!canManageCommerce) {
      notifyError('Admin permission required.')
      return
    }
    setTestingId(sourceId)
    try {
      const result = await commerce.testSource(sourceId)
      if (result.ok) info(result.message)
      else notifyError(result.message)
      await loadCommerce()
    } catch (error) {
      notifyError(apiErrorMessage(error, 'Unable to test connection'))
    } finally {
      setTestingId(null)
    }
  }

  async function handleChannelTest(channelId: string) {
    if (!canManageCommerce) {
      notifyError('Admin permission required.')
      return
    }
    setTestingId(channelId)
    try {
      const result = await commerce.testChannel(channelId)
      if (result.ok) info(result.message)
      else notifyError(result.message)
      await loadCommerce()
    } catch (error) {
      notifyError(apiErrorMessage(error, 'Unable to test connection'))
    } finally {
      setTestingId(null)
    }
  }

  async function handleChannelCacheRefresh(channelId: string) {
    if (!canManageCommerce) {
      notifyError('Admin permission required.')
      return
    }
    setRefreshingId(channelId)
    try {
      const result = await commerce.refreshChannelCache(channelId)
      if (result.ok) {
        info('WooCommerce product cache updated. Workspace Preview is now available.')
      } else {
        notifyError(result.errors[0] || 'Unable to refresh WooCommerce product cache')
      }
      await loadCommerce()
    } catch (error) {
      notifyError(apiErrorMessage(error, 'Unable to refresh WooCommerce product cache'))
    } finally {
      setRefreshingId(null)
    }
  }

  async function handleSourceRead(sourceId: string) {
    if (!canManageCommerce) {
      notifyError('Admin permission required.')
      return
    }
    setReadingId(sourceId)
    try {
      const result = await commerce.readSource(sourceId)
      if (result.ok) {
        info(`Read complete - ${result.rows_read} row${result.rows_read !== 1 ? 's' : ''} read; ${result.reads_remaining} read${result.reads_remaining !== 1 ? 's' : ''} remaining today.`)
      } else {
        notifyError('Source read failed.')
      }
      await loadCommerce()
    } catch (error) {
      notifyError(apiErrorMessage(error, 'Unable to read source'))
    } finally {
      setReadingId(null)
    }
  }

  function handleSourceConfigure(_sourceId: string) {
    if (!canManageCommerce) {
      notifyError('Admin permission required.')
      return
    }
    setTab('sources')
    setSearchParams({ tab: 'sources' })
    setFormKind('source')
  }

  function handleChannelConfigure(_channelId: string) {
    if (!canManageCommerce) {
      notifyError('Admin permission required.')
      return
    }
    setTab('channels')
    setSearchParams({ tab: 'channels' })
    setFormKind('channel')
  }

  async function reloadAfterSave() {
    await loadCommerce()
    setFormKind(null)
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">Commerce Hub</h1>
          <p className="fh-page-subtitle">Read-only source and channel overview</p>
        </div>
        <SafetyBadges readOnly writeBlocked />
      </div>

      <RelationshipMap map={map} />

      <div className="fh-segmented w-fit">
        {(['sources', 'channels'] as const).map(item => (
          <button
            key={item}
            onClick={() => selectTab(item)}
            className={[
              'fh-segmented-button capitalize',
              tab === item ? 'fh-segmented-button-active' : '',
            ].join(' ')}
          >
            {item === 'sources' ? 'Sources' : 'Channels'}
          </button>
        ))}
      </div>

      {loading ? (
          <div className="fh-card fh-card-pad flex items-center gap-2 fh-text-body-sm">
            <Spinner size="sm" />Loading Commerce Hub
          </div>
      ) : tab === 'sources' ? (
        <section>
          <div className="fh-page-toolbar mb-4">
            <div>
              <h2 className="fh-section-title">Sources</h2>
              <p className="fh-section-subtitle mt-1">Input systems that feed FlowHub / Data Layer.</p>
            </div>
            {canManageCommerce ? (
              <button onClick={() => setFormKind('source')} className="fh-button-primary px-4">
                Add Source
              </button>
            ) : (
              <Badge variant="neutral">Admin permission required</Badge>
            )}
          </div>
          {formKind === 'source' && (
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
              <h2 className="fh-section-title">Channels</h2>
              <p className="fh-section-subtitle mt-1">Commerce systems that receive catalog visibility from FlowHub.</p>
            </div>
            {canManageCommerce ? (
              <button onClick={() => setFormKind('channel')} className="fh-button-primary px-4">
                Add Channel
              </button>
            ) : (
              <Badge variant="neutral">Admin permission required</Badge>
            )}
          </div>
          {formKind === 'channel' && (
            <div className="mb-4">
              <ConfigPanel kind="channel" types={channelTypes} onCancel={() => setFormKind(null)} onSaved={reloadAfterSave} />
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
                canManage={canManageCommerce}
              />
            ))}
          </div>
        </section>
      )}
    </PageShell>
  )
}
