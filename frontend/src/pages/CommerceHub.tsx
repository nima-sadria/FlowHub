import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth'
import { ApiError } from '../api/client'
import { useServices } from '../services/ServiceContext'
import type { CommerceChannel, CommerceRelationshipMap, CommerceSource, CommerceTypeOption } from '../services/types'
import type { NextcloudBrowseItem, NextcloudBrowseResult } from '../services/commerce/CommerceService'
import Spinner from '../components/loading/Spinner'
import { useNotification } from '../notifications/NotificationProvider'
import PageShell from '../components/PageShell'

type Tab = 'sources' | 'channels'
type FormKind = 'source' | 'channel'

function prettyStatus(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function statusClass(status: string): string {
  if (['healthy', 'configured', 'current'].includes(status)) return 'fh-badge-success'
  if (['planned', 'future', 'not_configured', 'unknown'].includes(status)) return 'fh-badge-neutral'
  if (['degraded'].includes(status)) return 'fh-badge-warning'
  return 'fh-badge-danger'
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
      {readOnly && <span className="fh-badge fh-badge-neutral">Read-only mode</span>}
      {writeBlocked && <span className="fh-badge fh-badge-danger">Writes blocked</span>}
    </div>
  )
}

function RelationshipMap({ map }: { map: CommerceRelationshipMap | null }) {
  const nodes = map?.nodes ?? ['Source', 'FlowHub / Data Layer', 'Channel']
  const example = map?.example ?? ['Nextcloud', 'Data Layer', 'WooCommerce']
  return (
    <div className="fh-card fh-card-pad">
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr_auto_1fr] gap-3 items-center text-center">
        <div className="rounded-lg border border-border bg-bg-base px-4 py-3">
          <p className="text-[11px] text-wp-muted">{nodes[0]}</p>
          <p className="text-[14px] font-semibold text-text-base">{example[0]}</p>
        </div>
        <div className="text-[20px] text-wp-muted">v</div>
        <div className="rounded-lg border border-border bg-bg-base px-4 py-3">
          <p className="text-[11px] text-wp-muted">FlowHub</p>
          <p className="text-[14px] font-semibold text-text-base">{example[1]}</p>
        </div>
        <div className="text-[20px] text-wp-muted">v</div>
        <div className="rounded-lg border border-border bg-bg-base px-4 py-3">
          <p className="text-[11px] text-wp-muted">{nodes[2]}</p>
          <p className="text-[14px] font-semibold text-text-base">{example[2]}</p>
        </div>
      </div>
    </div>
  )
}

function SourceCard({ source }: { source: CommerceSource }) {
  return (
    <div className="fh-card fh-card-pad flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-[15px] font-semibold text-text-base">{source.name}</h3>
            <span className={['fh-badge', statusClass(source.status)].join(' ')}>
              {prettyStatus(source.status)}
            </span>
            {source.placeholder && <span className="fh-badge fh-badge-neutral">Planned source</span>}
          </div>
          <p className="text-[12px] text-wp-muted mt-1">{source.data_role}</p>
        </div>
        <span className="text-[12px] font-medium text-text-base">{source.type}</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[12px]">
        <p><span className="text-wp-muted">Credential status: </span><span className="font-medium text-text-base">{prettyStatus(source.credential_status)}</span></p>
        <p><span className="text-wp-muted">Last health check: </span><span className="font-medium text-text-base">{source.last_health_check ? new Date(source.last_health_check).toLocaleString() : 'Not checked'}</span></p>
        <p><span className="text-wp-muted">Health: </span><span className="font-medium text-text-base">{prettyStatus(source.health?.status ?? 'unknown')}</span></p>
        <p><span className="text-wp-muted">Data role: </span><span className="font-medium text-text-base">{source.data_role}</span></p>
      </div>

      <SafetyBadges readOnly={source.read_only} writeBlocked={source.runtime_write_blocked} />
    </div>
  )
}

function ChannelCard({ channel, onTest, testing, canManage }: {
  channel: CommerceChannel
  onTest: (channelId: string) => void
  testing: boolean
  canManage: boolean
}) {
  return (
    <div className="fh-card fh-card-pad flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-[15px] font-semibold text-text-base">{channel.name}</h3>
            <span className={['fh-badge', statusClass(channel.status)].join(' ')}>
              {prettyStatus(channel.status)}
            </span>
            {channel.placeholder && <span className="fh-badge fh-badge-neutral">Planned channel</span>}
          </div>
          <p className="text-[12px] text-wp-muted mt-1">{channel.capabilities_summary.join(', ')}</p>
        </div>
        <span className="text-[12px] font-medium text-text-base">{channel.type}</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[12px]">
        <p><span className="text-wp-muted">Credential status: </span><span className="font-medium text-text-base">{prettyStatus(channel.credential_status)}</span></p>
        <p><span className="text-wp-muted">Last health check: </span><span className="font-medium text-text-base">{channel.last_health_check ? new Date(channel.last_health_check).toLocaleString() : 'Not checked'}</span></p>
        <p><span className="text-wp-muted">Health: </span><span className="font-medium text-text-base">{prettyStatus(channel.health?.status ?? 'unknown')}</span></p>
        <p><span className="text-wp-muted">Capabilities: </span><span className="font-medium text-text-base">{channel.capabilities_summary.join(', ')}</span></p>
      </div>

      <div className="flex items-center justify-between gap-3">
        <SafetyBadges readOnly={channel.read_only} writeBlocked={channel.write_blocked} />
        {canManage && (
          <button
            onClick={() => onTest(channel.id)}
            disabled={testing}
            className="fh-button-secondary px-3 py-1.5 text-[12px]"
          >
            {testing && <Spinner size="sm" />}
            {testing ? 'Testing' : 'Test connection'}
          </button>
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
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            <h3 className="text-[15px] font-semibold text-text-base">Browse Nextcloud</h3>
            <p className="text-[12px] text-wp-muted mt-1">{currentPath}</p>
          </div>
          <button type="button" onClick={onClose} className="fh-button-secondary px-3 py-1.5 text-[12px]">
            Close
          </button>
        </div>
        <div className="overflow-auto p-4">
          {error && <div className="fh-error-alert mb-3 rounded px-3 py-2 text-[12px]">{error}</div>}
          {loading ? (
            <div className="flex items-center gap-2 text-[13px] text-wp-muted"><Spinner size="sm" />Loading files</div>
          ) : (
            <div className="flex flex-col gap-2">
              {parentPath !== null && (
                <button type="button" onClick={() => onOpenDirectory(parentPath || '/')} className="fh-button-secondary justify-start px-3 py-2 text-[13px]">
                  Up one folder
                </button>
              )}
              {data?.directories.map(directory => (
                <button
                  key={directory.path}
                  type="button"
                  onClick={() => onOpenDirectory(directory.path)}
                  className="fh-button-secondary justify-start px-3 py-2 text-[13px]"
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
                  className="flex items-center justify-between gap-3 rounded border border-border bg-bg-base px-3 py-2 text-left text-[13px] disabled:opacity-60"
                >
                  <span className="font-medium text-text-base">{file.name}</span>
                  <span className="text-[12px] text-wp-muted">{file.supported ? 'Spreadsheet' : 'Unsupported'}</span>
                </button>
              ))}
              {!loading && data && data.directories.length === 0 && data.files.length === 0 && (
                <p className="text-[13px] text-wp-muted">No spreadsheet files in this folder.</p>
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
        settings,
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

  return (
    <form onSubmit={event => void submit(event)} className="fh-card fh-card-pad flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[16px] font-semibold text-text-base">
            {kind === 'source' ? 'Add Source' : 'Add Channel'}
          </h3>
          <p className="text-[12px] text-wp-muted mt-1">
            Configuration is local to FlowHub and remains read-only.
          </p>
        </div>
        <button type="button" onClick={onCancel} className="fh-button-secondary px-3 py-1.5 text-[12px]">
          Close
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <label className="flex flex-col gap-1 text-[12px] text-wp-muted">
          {kind === 'source' ? 'Source type' : 'Channel type'}
          <select
            value={selected.id}
            onChange={event => setSelectedId(event.target.value)}
            className="fh-input"
          >
            {types.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[12px] text-wp-muted">
          Display name
          <input value={displayName} onChange={event => setDisplayName(event.target.value)} className="fh-input" />
        </label>
        <label className="flex flex-col gap-1 text-[12px] text-wp-muted md:col-span-2">
          Description optional
          <input value={description} onChange={event => setDescription(event.target.value)} className="fh-input" />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="inline-flex items-center gap-2 text-[13px] text-text-base">
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
          <span className="fh-badge fh-badge-neutral">
            {kind === 'source' ? 'Planned source' : 'Planned channel'}
          </span>
        )}
        {selected.placeholder && <span className="fh-badge fh-badge-neutral">Not configured</span>}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {selected.settings_schema
          .filter(field => !(kind === 'source' && selected.provider === 'nextcloud' && field.key === 'spreadsheet_path'))
          .map(field => (
          <label key={field.key} className="flex flex-col gap-1 text-[12px] text-wp-muted">
            {fieldLabel(kind, selected.provider, field.key, field.label)}
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
              <span className="text-[12px] text-wp-red">{nextcloudUrlError}</span>
            )}
          </label>
        ))}
      </div>

      {kind === 'source' && selected.provider === 'nextcloud' && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-bg-base px-3 py-3">
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-medium text-text-base">Nextcloud spreadsheet file</p>
            <p className="text-[12px] text-wp-muted">Use WebDAV with your app password. Public share links are not required.</p>
            <p className="mt-2 text-[12px] text-wp-muted">Selected file</p>
            <div className="mt-1 min-h-10 rounded-md border border-border bg-bg-subtle px-3 py-2 text-[13px] text-text-base">
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
      )}

      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={() => void testConnection()} disabled={testing} className="fh-button-secondary px-4">
          {testing && <Spinner size="sm" />}
          {testing ? 'Testing' : 'Test connection'}
        </button>
        <button type="submit" disabled={saving} className="fh-button-primary px-4">
          {saving && <Spinner size="sm" />}
          {saving ? 'Saving' : 'Save configuration'}
        </button>
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

  async function handleTest(channelId: string) {
    if (!canManageCommerce) {
      notifyError('Admin permission required.')
      return
    }
    setTestingId(channelId)
    try {
      const result = await commerce.testChannel(channelId)
      if (result.ok) info(result.message)
      else notifyError(result.message)
    } catch (error) {
      notifyError(apiErrorMessage(error, 'Unable to test connection'))
    } finally {
      setTestingId(null)
    }
  }

  async function reloadAfterSave() {
    await loadCommerce()
    setFormKind(null)
  }

  return (
    <PageShell>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="fh-page-title">Commerce Hub</h1>
          <p className="fh-page-subtitle">Read-only source and channel overview</p>
        </div>
        <SafetyBadges readOnly writeBlocked />
      </div>

      <RelationshipMap map={map} />

      <div className="flex items-center gap-1 bg-bg-base rounded-lg p-1 border border-border w-fit">
        {(['sources', 'channels'] as const).map(item => (
          <button
            key={item}
            onClick={() => selectTab(item)}
            className={[
              'px-3 py-1.5 text-[13px] font-medium rounded capitalize transition-colors',
              tab === item ? 'bg-bg-card text-accent shadow-sm' : 'text-wp-muted hover:text-text-base',
            ].join(' ')}
          >
            {item === 'sources' ? 'Sources' : 'Channels'}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="fh-card fh-card-pad flex items-center gap-2 text-[13px] text-wp-muted">
          <Spinner size="sm" />Loading Commerce Hub
        </div>
      ) : tab === 'sources' ? (
        <section>
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-[16px] font-semibold text-text-base">Sources</h2>
              <p className="text-[12px] text-wp-muted mt-1">Input systems that feed FlowHub / Data Layer.</p>
            </div>
            {canManageCommerce ? (
              <button onClick={() => setFormKind('source')} className="fh-button-primary px-4">
                Add Source
              </button>
            ) : (
              <span className="fh-badge fh-badge-neutral">Admin permission required</span>
            )}
          </div>
          {formKind === 'source' && (
            <div className="mb-4">
              <ConfigPanel kind="source" types={sourceTypes} onCancel={() => setFormKind(null)} onSaved={reloadAfterSave} />
            </div>
          )}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {sources.map(source => <SourceCard key={source.id} source={source} />)}
          </div>
        </section>
      ) : (
        <section>
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-[16px] font-semibold text-text-base">Channels</h2>
              <p className="text-[12px] text-wp-muted mt-1">Commerce systems that receive catalog visibility from FlowHub.</p>
            </div>
            {canManageCommerce ? (
              <button onClick={() => setFormKind('channel')} className="fh-button-primary px-4">
                Add Channel
              </button>
            ) : (
              <span className="fh-badge fh-badge-neutral">Admin permission required</span>
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
                onTest={(id) => void handleTest(id)}
                testing={testingId === channel.id}
                canManage={canManageCommerce}
              />
            ))}
          </div>
        </section>
      )}
    </PageShell>
  )
}
