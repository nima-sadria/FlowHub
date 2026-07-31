import { useCallback, useEffect, useMemo, useState } from 'react'
import { translate } from '../i18n'
import { useAuth } from '../auth'
import { apiFetch, ApiError } from '../api/client'
import { useNotification } from '../notifications/NotificationProvider'
import Spinner from '../components/loading/Spinner'
import Empty from '../components/Empty'
import Icon, { type IconName } from '../components/Icon'
import PageShell from '../components/PageShell'
import Badge from '../components/Badge'
import DiagnosticStateBadge from '../components/DiagnosticStateBadge'
import type { ChannelHealthItem, ChannelHealthResponse } from '../services/types'
import { formatDateTime, formatNumber, formatRelativeTime } from '../i18n/format'
import { formatDiagnosticDimension, formatDiagnosticMessage, formatStatus } from '../i18n/display'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import {
  deriveOverallDiagnosticState,
  diagnosticEvidenceCheckedAt,
  diagnosticEvidenceDescription,
  diagnosticRecommendedAction,
  diagnosticStatePresentation,
  resolveDiagnosticState,
  type DiagnosticEvidenceLike,
  type DiagnosticState,
} from '../features/diagnostics/diagnosticPresentation'
import {
  diagnosticChannelSignals,
  diagnosticSourceSignals,
  prepareResourceCollection,
} from '../features/resourceOrdering/resourceOrdering'

const REQUEST_TIMEOUT_MS = 10_000
const SOURCE_CONNECTOR_TYPES = new Set(['nextcloud', 'csv', 'gsheets', 'erp'])
const SEVERITY_RANK: Record<DiagnosticState, number> = {
  ERROR: 0, WARNING: 1, NOT_CHECKED: 2, INFO: 3, HEALTHY: 4, DISABLED: 5, NOT_APPLICABLE: 6,
}
const RECENT_CHECKS_LIMIT = 8

type SummaryStatus = DiagnosticState | 'LOADING'

interface ConnectorStatus {
  id?: string
  name?: string
  connector_type?: string
  enabled?: boolean
  status?: string
  health?: string | {
    healthy?: boolean
    status?: string
    message?: string
    checked_at?: string | null
    last_checked_at?: string | null
  } | null
  last_checked_at?: string | null
  last_successful_operation?: string | null
}

interface DiagnosticCheck {
  check_name?: string
  category?: string
  target?: string
  status?: string
  severity?: string
}

interface RunnerState {
  lastHeartbeat?: string | null
  state?: string | null
}

interface DiagnosticsStatusResponse {
  overall_status?: string
  checkedAt?: string
  checks?: DiagnosticCheck[]
  connectors?: ConnectorStatus[]
  channelHealth?: ChannelHealthResponse & { orderSyncRunner?: RunnerState }
  rateLimiter?: {
    settings?: {
      read_requests_per_minute?: number
      write_requests_per_minute?: number
      read_delay_ms?: number
      write_delay_ms?: number
    }
    queue_length?: number
    average_request_duration_ms?: number | null
    average_latency_ms?: number | null
    throttle_count?: number
    last_throttle?: string | null
    last_connector_delay_ms?: number | null
    last_limiter_delay_ms?: number | null
    requests_completed?: number
    requests_delayed?: number
    estimated_completion_seconds?: number | null
  }
  external_call_performed?: boolean
}

interface SummaryCardProps {
  label: string
  value: string
  detail?: string
  status: SummaryStatus
  icon: IconName
}

function summaryStatusLabel(status: SummaryStatus): string {
  return status === 'LOADING'
    ? translate('common:status.loading')
    : diagnosticStatePresentation(status).label
}

function SummaryStatusBadge({ status }: { status: SummaryStatus }) {
  if (status !== 'LOADING') return <DiagnosticStateBadge state={status} />
  return (
    <Badge variant="info">
      <span role="status" className="inline-flex items-center gap-1.5">
        <Icon name="refresh" aria-hidden="true" />
        {translate('common:status.loading')}
      </span>
    </Badge>
  )
}

function SummaryCard({ label, value, detail, status, icon }: SummaryCardProps) {
  return (
    <article className="rounded-lg border border-border bg-[var(--fh-ui-card)] p-4" data-testid="diagnostics-summary-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="fh-text-caption font-medium text-wp-muted">{label}</p>
          <p className="mt-1 fh-text-body font-semibold text-text-base">{value}</p>
          {detail && <p className="mt-1 fh-text-caption">{detail}</p>}
        </div>
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-bg-subtle text-wp-muted" aria-hidden="true">
          <Icon name={icon} />
        </span>
      </div>
      <div className="mt-3"><SummaryStatusBadge status={status} /></div>
    </article>
  )
}

function channelLabel(channel: ChannelHealthItem): string {
  return formatChannelDisplayName(channel.channelId || `${channel.channelType}:primary`)
}

function connectorHealth(connector: ConnectorStatus): string | undefined {
  if (typeof connector.health === 'string') return connector.health
  return connector.health?.status ?? connector.status
}

function connectorHealthMessage(connector: ConnectorStatus): string | undefined {
  return typeof connector.health === 'object' && connector.health
    ? connector.health.message
    : undefined
}

function connectorLastChecked(connector: ConnectorStatus): string | null {
  if (connector.last_checked_at) return connector.last_checked_at
  if (typeof connector.health === 'object' && connector.health) {
    return connector.health.last_checked_at ?? connector.health.checked_at ?? null
  }
  return null
}

function isDatabaseCheck(check: DiagnosticCheck): boolean {
  const identities = [check.category, check.target, check.check_name]
    .filter((value): value is string => Boolean(value))
    .map(value => value.trim().toLowerCase().replace(/[\s-]+/g, '_'))
  return identities.some(value => value === 'database' || value.startsWith('database_'))
}

/**
 * Database presentation is intentionally fail-closed and evidence-based:
 * no check means not checked, every pass means healthy, any failure means
 * error, and skipped/unknown/mixed evidence means needs attention.
 */
function databaseDiagnosticStatus(checks: DiagnosticCheck[]): DiagnosticState {
  const databaseChecks = checks.filter(isDatabaseCheck)
  if (databaseChecks.length === 0) return 'NOT_CHECKED'

  const statuses = databaseChecks.map(check => check.status?.trim().toLowerCase() ?? '')
  if (statuses.some(status => status === 'fail' || status === 'failed' || status === 'error')) return 'ERROR'
  if (statuses.some(status => status === 'warning' || status === 'degraded')) return 'WARNING'
  if (statuses.every(status => status === 'pass' || status === 'passed' || status === 'ok')) return 'HEALTHY'
  return 'NOT_CHECKED'
}

interface SourcePresentation {
  status: DiagnosticState
  label: string
  description: string
}

function sourcePresentation(connector: ConnectorStatus): SourcePresentation {
  if (connector.enabled === false) {
    return {
      status: 'DISABLED',
      label: translate('common:status.disabled'),
      description: translate('diagnostics:diagnostics.sourceDisabledDescription', {
        defaultValue: 'This Source is disabled. Enable it before running a connection check.',
      }),
    }
  }

  const normalized = resolveDiagnosticState(connectorHealth(connector))
  const healthMessage = connectorHealthMessage(connector)
  if (normalized === 'ERROR') {
    return {
      status: 'ERROR',
      label: formatStatus(connectorHealth(connector)),
      description: healthMessage
        ? formatDiagnosticMessage(healthMessage)
        : translate('diagnostics:diagnostics.sourceConnectionError', {
          defaultValue: 'The latest Source connection check failed.',
        }),
    }
  }

  if (!connectorLastChecked(connector)) {
    return {
      status: 'NOT_CHECKED',
      label: translate('diagnostics:diagnostics.notCheckedYet', { defaultValue: 'Not checked yet' }),
      description: translate('diagnostics:diagnostics.sourceNotCheckedDescription', {
        defaultValue: 'No connection check has been recorded for this Source.',
      }),
    }
  }

  if (normalized === 'WARNING') {
    return {
      status: 'WARNING',
      label: formatStatus(connectorHealth(connector)),
      description: healthMessage
        ? formatDiagnosticMessage(healthMessage)
        : translate('diagnostics:diagnostics.sourceNeedsAttention', {
          defaultValue: 'The latest Source connection check needs attention.',
        }),
    }
  }

  if (normalized === 'HEALTHY') {
    return {
      status: 'HEALTHY',
      label: formatStatus(connectorHealth(connector)),
      description: translate('diagnostics:diagnostics.sourceConnectionReady', {
        defaultValue: 'Source connection is ready.',
      }),
    }
  }

  return {
    status: 'NOT_CHECKED',
    label: translate('diagnostics:diagnostics.notCheckedYet', { defaultValue: 'Not checked yet' }),
    description: translate('diagnostics:diagnostics.sourceResultPendingDescription', {
      defaultValue: 'A conclusive Source connection result is not available yet.',
    }),
  }
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="fh-text-caption text-wp-muted">{label}</dt>
      <dd className="mt-0.5 break-words fh-text-body-sm text-text-base">{value}</dd>
    </div>
  )
}

const DIAGNOSTIC_GROUPS = [
  {
    key: 'connection',
    dimensions: ['configuration', 'credentials', 'externalApi', 'vendorSelection'],
  },
  {
    key: 'capabilities',
    dimensions: ['readCapability', 'writeCapability'],
  },
  {
    key: 'synchronization',
    dimensions: ['lastProductSync', 'lastOrderSync', 'productCache'],
  },
  {
    key: 'backgroundProcessing',
    dimensions: ['webhookReceipt', 'webhookProcessing', 'tokenRefresh', 'polling'],
  },
  {
    key: 'recoveryQueues',
    dimensions: ['queueDeadLetter'],
  },
] as const

function metricValue(value: number | null | undefined, unit?: 'milliseconds' | 'seconds'): string {
  if (value === null || value === undefined) return translate('common:status.unavailable')
  const formatted = formatNumber(value)
  if (unit === 'milliseconds') return translate('diagnostics:units.milliseconds', { value: formatted })
  if (unit === 'seconds') return translate('diagnostics:units.seconds', { value: formatted })
  return formatted
}

function IntegrationDetails({ channel }: { channel: ChannelHealthItem }) {
  const knownDimensions = new Set<string>(DIAGNOSTIC_GROUPS.flatMap(group => [...group.dimensions]))
  const groups = [
    ...DIAGNOSTIC_GROUPS.map(group => ({
      key: group.key,
      items: group.dimensions.flatMap(key => channel.dimensions[key] ? [[key, channel.dimensions[key]] as const] : []),
    })),
    {
      key: 'other',
      items: Object.entries(channel.dimensions).filter(([key]) => !knownDimensions.has(key)),
    },
  ].filter(group => group.items.length > 0)

  return (
    <details className="mt-3 border-t border-border pt-3" data-testid={`diagnostics-details-${channel.channelId}`}>
      <summary className="cursor-pointer select-none fh-text-body-sm font-medium text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
        {translate('diagnostics:diagnostics.expandDetails', { defaultValue: 'Expand details' })}
      </summary>
      <div className="mt-4 space-y-5">
        {groups.map(group => (
          <section key={group.key} aria-labelledby={`diagnostics-${channel.channelId}-${group.key}`}>
            <h4 id={`diagnostics-${channel.channelId}-${group.key}`} className="fh-text-body-sm font-semibold text-text-base">
              {translate(`diagnostics:diagnostics.checkGroups.${group.key}`)}
            </h4>
            <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
              {group.items.map(([key, dimension]) => {
                const checkedAt = diagnosticEvidenceCheckedAt(dimension)
                const action = diagnosticRecommendedAction(dimension)
                return (
                  <article
                    key={key}
                    className="rounded border border-border px-3 py-3"
                    data-testid={`diagnostics-check-${channel.channelId}-${key}`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="fh-text-caption font-medium text-text-base">{formatDiagnosticDimension(key)}</span>
                      <DiagnosticStateBadge evidence={dimension} />
                    </div>
                    <p className="mt-2 fh-text-caption">{diagnosticEvidenceDescription(dimension)}</p>
                    {dimension.is_actionable && <p className="mt-2 fh-text-caption font-medium text-text-base">{action}</p>}
                    {(checkedAt || dimension.evidence_source) && (
                      <dl className="mt-2 grid grid-cols-1 gap-2 border-t border-border pt-2 sm:grid-cols-2">
                        {checkedAt && <Field label={translate('diagnostics:diagnostics.evidenceRecorded')} value={formatDateTime(checkedAt)} />}
                        {dimension.evidence_source && <Field label={translate('diagnostics:diagnostics.evidenceSource')} value={dimension.evidence_source} />}
                      </dl>
                    )}
                  </article>
                )
              })}
            </div>
          </section>
        ))}
      </div>
      <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label={translate('diagnostics:diagnostics.latency')} value={metricValue(channel.latency, 'milliseconds')} />
        <Field label={translate('diagnostics:diagnostics.errorCategory')} value={channel.lastErrorCategory ? formatStatus(channel.lastErrorCategory) : translate('common:status.none')} />
        <Field label={translate('diagnostics:diagnostics.accessMode', { defaultValue: 'Access mode' })} value={formatStatus(channel.accessMode)} />
        <Field label={translate('diagnostics:diagnostics.nextAction')} value={diagnosticRecommendedAction({ ...channel, recommended_action: channel.recommended_action ?? channel.nextRecommendedAction })} />
      </dl>
    </details>
  )
}

function ChannelHealthRow({
  channel, displayName, canRefreshChannel, refreshingChannel, onRefresh,
}: {
  channel: ChannelHealthItem
  displayName: string
  canRefreshChannel: boolean
  refreshingChannel: string | null
  onRefresh: (channelId: string) => void
}) {
  const channelEvidence: DiagnosticEvidenceLike = {
    ...channel,
    message: channel.summary,
    recommended_action: channel.recommended_action ?? channel.nextRecommendedAction,
  }
  const lastSuccessfulVerification = channel.lastSuccessfulVerification
  const lastSuccessfulActivity = channel.lastSuccessfulSyncOrRead ?? channel.lastSuccessfulOperation
  const recommendedAction = diagnosticRecommendedAction(channelEvidence)
  const needsProductRefresh = [
    'product_sync_stale',
    'product_sync_not_checked',
    'product_cache_not_checked',
    'product_cache_refresh_failed',
  ].includes(channel.reason_code ?? '')
  return (
    <article id={`channel-${channel.channelId}`} className="rounded-lg border border-border p-4" data-testid={`diagnostics-channel-${channel.channelId}`} data-resource-id={channel.channelId}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-bg-subtle text-wp-muted" aria-hidden="true"><Icon name="channel" /></span>
            <h3 className="fh-text-body font-semibold text-text-base">{displayName}</h3>
            <DiagnosticStateBadge evidence={channelEvidence} testId={`diagnostics-channel-status-${channel.channelId}`} />
          </div>
          <p className="mt-2 fh-text-body-sm">{diagnosticEvidenceDescription(channelEvidence)}</p>
          <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <Field
              label={translate('diagnostics:diagnostics.lastSuccessfulVerification')}
              value={lastSuccessfulVerification ? formatDateTime(lastSuccessfulVerification) : translate('diagnostics:diagnostics.neverVerified')}
            />
            <Field
              label={translate('diagnostics:diagnostics.lastSuccessfulActivity', { defaultValue: 'Last successful sync or read' })}
              value={lastSuccessfulActivity ? formatDateTime(lastSuccessfulActivity) : translate('diagnostics:diagnostics.noSuccessfulActivity', { defaultValue: 'No successful activity recorded' })}
            />
            <Field label={translate('diagnostics:diagnostics.recommendedNextAction')} value={recommendedAction} />
          </dl>
        </div>
        {channel.enabled && needsProductRefresh ? (
          <a
            href={`/commerce?tab=channels&channel=${encodeURIComponent(channel.channelId)}`}
            className="fh-button-secondary self-start"
            data-testid={`diagnostics-channel-action-${channel.channelId}`}
          >
            <Icon name="refresh" />
            {recommendedAction}
          </a>
        ) : canRefreshChannel && channel.enabled ? (
          <button
            type="button"
            onClick={() => onRefresh(channel.channelId)}
            disabled={refreshingChannel !== null}
            className="fh-button-secondary self-start"
            data-testid={`diagnostics-channel-action-${channel.channelId}`}
          >
            {refreshingChannel === channel.channelId ? <Spinner size="sm" /> : <Icon name="testConnection" />}
            {translate('diagnostics:diagnostics.testConnection')}
          </button>
        ) : null}
      </div>
      <IntegrationDetails channel={channel} />
    </article>
  )
}

function SourceHealthRow({ connector, displayName }: { connector: ConnectorStatus; displayName: string }) {
  const presentation = sourcePresentation(connector)
  const lastChecked = connectorLastChecked(connector)
  return (
    <article id={`source-${connector.id}`} className="rounded-lg border border-border p-4" data-resource-id={connector.id}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-bg-subtle text-wp-muted" aria-hidden="true"><Icon name="file" /></span>
            <h3 className="fh-text-body font-semibold text-text-base">{displayName}</h3>
            <DiagnosticStateBadge state={presentation.status} testId={`diagnostics-source-status-${connector.id}`} />
          </div>
          <p className="mt-2 fh-text-caption">{presentation.description}</p>
          <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field
              label={translate('diagnostics:diagnostics.lastSuccessfulCheck', { defaultValue: 'Last successful check' })}
              value={lastChecked ? formatDateTime(lastChecked) : translate('diagnostics:diagnostics.notCheckedYet', { defaultValue: 'Not checked yet' })}
            />
            <Field
              label={translate('diagnostics:diagnostics.lastSuccessfulActivity', { defaultValue: 'Last successful sync or read' })}
              value={connector.last_successful_operation ? formatDateTime(connector.last_successful_operation) : translate('diagnostics:diagnostics.noSuccessfulActivity', { defaultValue: 'No successful activity recorded' })}
            />
          </dl>
        </div>
        <a href="/sources" className="fh-button-secondary self-start">
          {translate('diagnostics:diagnostics.openSources', { defaultValue: 'Open Sources' })}
        </a>
      </div>
      <details className="mt-3 border-t border-border pt-3">
        <summary className="cursor-pointer select-none fh-text-body-sm font-medium text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
          {translate('diagnostics:diagnostics.expandDetails', { defaultValue: 'Expand details' })}
        </summary>
        <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={translate('diagnostics:diagnostics.connector')} value={connector.connector_type ?? translate('common:status.unknown')} />
          <Field label={translate('diagnostics:diagnostics.status')} value={formatStatus(connectorHealth(connector))} />
        </dl>
      </details>
    </article>
  )
}

function BackgroundJobsRow({ runner, status }: { runner: RunnerState; status: DiagnosticState }) {
  return (
    <article className="rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-bg-subtle text-wp-muted" aria-hidden="true"><Icon name="activity" /></span>
        <h3 className="fh-text-body font-semibold text-text-base">{translate('diagnostics:diagnostics.backgroundJobs')}</h3>
        <DiagnosticStateBadge state={status} />
      </div>
      <p className="mt-2 fh-text-body-sm">{runner.state ? formatStatus(runner.state) : translate('diagnostics:diagnostics.notCheckedYet')}</p>
      <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field
          label={translate('diagnostics:diagnostics.lastSuccessfulActivity', { defaultValue: 'Last successful sync or read' })}
          value={runner.lastHeartbeat ? formatDateTime(runner.lastHeartbeat) : translate('diagnostics:diagnostics.noSuccessfulActivity', { defaultValue: 'No successful activity recorded' })}
        />
      </dl>
    </article>
  )
}

interface RecentCheckEntry {
  key: string
  icon: IconName
  title: string
  description: string
  status: DiagnosticState
  lastChecked: string | null
}

function RecentCheckRow({ entry }: { entry: RecentCheckEntry }) {
  return (
    <div className="flex items-center gap-3 border-b border-border py-3 last:border-0">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-bg-subtle text-wp-muted" aria-hidden="true"><Icon name={entry.icon} /></span>
      <div className="min-w-0 flex-1">
        <p className="fh-text-body-sm font-semibold text-text-base">{entry.title}</p>
        <p className="fh-text-caption truncate">{entry.description}</p>
      </div>
      <DiagnosticStateBadge state={entry.status} />
    </div>
  )
}

export default function Diagnostics() {
  const { user, authFetch } = useAuth()
  const { success, error: notifyError } = useNotification()
  const [diag, setDiag] = useState<DiagnosticsStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)
  const [refreshingChannel, setRefreshingChannel] = useState<string | null>(null)

  const canRefreshChannel = Boolean(user && ['owner', 'super_admin', 'admin'].includes(user.role))

  const runCheck = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const diagnosticsData = await apiFetch<DiagnosticsStatusResponse>(
        '/api/v2/diagnostics/status',
        authFetch,
        undefined,
        REQUEST_TIMEOUT_MS,
      )
      setDiag(diagnosticsData)
      setCheckedAt(diagnosticsData.checkedAt ? new Date(diagnosticsData.checkedAt) : null)
      success({
        title: translate('diagnostics:diagnostics.diagnosticsUpdated'),
        description: translate('diagnostics:diagnostics.latestSystemStatusHasBeenLoaded'),
      })
    } catch (error) {
      const message = error instanceof ApiError
        ? translate('diagnostics:diagnostics.unavailableHttp', { status: error.status })
        : error instanceof Error && error.message === 'request_timeout'
          ? translate('diagnostics:diagnostics.requestTimedOut')
          : translate('diagnostics:diagnostics.unavailableMessage')
      setErr(message)
      notifyError({
        title: translate('diagnostics:diagnostics.unableToUpdateDiagnostics'),
        description: translate('diagnostics:diagnostics.pleaseTryAgain'),
      })
    } finally {
      setLoading(false)
    }
  }, [authFetch, success, notifyError])

  const refreshChannel = useCallback(async (channelId: string) => {
    if (!canRefreshChannel) return
    setRefreshingChannel(channelId)
    try {
      const data = await apiFetch<ChannelHealthResponse>(
        '/api/v2/diagnostics/channels/health/refresh',
        authFetch,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ channelId }),
        },
        REQUEST_TIMEOUT_MS,
      )
      setDiag(current => current ? { ...current, channelHealth: data } : current)
      setCheckedAt(data.checkedAt ? new Date(data.checkedAt) : null)
      success({
        title: translate('diagnostics:diagnostics.diagnosticsUpdated'),
        description: translate('diagnostics:diagnostics.latestSystemStatusHasBeenLoaded'),
      })
    } catch {
      notifyError({
        title: translate('diagnostics:diagnostics.unableToUpdateDiagnostics'),
        description: translate('diagnostics:diagnostics.pleaseTryAgain'),
      })
    } finally {
      setRefreshingChannel(null)
    }
  }, [authFetch, canRefreshChannel, success, notifyError])

  useEffect(() => { void runCheck() }, [runCheck])

  const connectors = diag?.connectors ?? []
  const sourceConnectors = useMemo(
    () => connectors.filter(connector => SOURCE_CONNECTOR_TYPES.has(connector.connector_type ?? '')),
    [connectors],
  )
  const channelHealth = diag?.channelHealth
  const channels = channelHealth?.items ?? []
  const orderedSources = useMemo(
    () => prepareResourceCollection(sourceConnectors, connector => diagnosticSourceSignals({
      ...connector,
      health: connectorHealth(connector),
    })),
    [sourceConnectors],
  )
  const orderedChannels = useMemo(
    () => prepareResourceCollection(channels, channel => ({
      ...diagnosticChannelSignals(channel),
      displayName: channelLabel(channel),
    })),
    [channels],
  )
  const checkStates = (diag?.checks ?? []).map(check => resolveDiagnosticState(check.status))
  const failedChecks = checkStates.filter(state => state === 'ERROR').length
  const warningChecks = checkStates.filter(state => state === 'WARNING').length
  const enabledChannels = channels.filter(channel => channel.enabled)
  const channelStates = enabledChannels.map(channel => resolveDiagnosticState(channel))
  const channelErrors = channelStates.filter(state => state === 'ERROR').length
  const channelWarnings = channelStates.filter(state => state === 'WARNING').length
  const channelNotChecked = channelStates.filter(state => state === 'NOT_CHECKED').length
  const databaseState = databaseDiagnosticStatus(diag?.checks ?? [])
  const sourcePresentations = sourceConnectors.map(sourcePresentation)
  const activeSourcePresentations = sourceConnectors
    .map((connector, index) => ({ connector, presentation: sourcePresentations[index] }))
    .filter(item => item.connector.enabled !== false)
    .map(item => ({ state: item.presentation.status }))
  const sourceStatus: DiagnosticState = sourceConnectors.length === 0
    ? 'NOT_CHECKED'
    : activeSourcePresentations.length === 0
      ? 'DISABLED'
      : deriveOverallDiagnosticState(activeSourcePresentations)
  const channelStatus: DiagnosticState = channels.length === 0
    ? 'NOT_CHECKED'
    : enabledChannels.length === 0
      ? 'DISABLED'
      : deriveOverallDiagnosticState(enabledChannels)
  const reportedSystemState = resolveDiagnosticState(diag?.overall_status)
  const hasSourceEvidence = sourceConnectors.length > 0
  const overallStatus: SummaryStatus = loading
    ? 'LOADING'
    : err || failedChecks > 0 || channelErrors > 0 || databaseState === 'ERROR' || reportedSystemState === 'ERROR' || (hasSourceEvidence && sourceStatus === 'ERROR')
      ? 'ERROR'
      : warningChecks > 0 || channelWarnings > 0 || databaseState === 'WARNING' || reportedSystemState === 'WARNING' || (hasSourceEvidence && sourceStatus === 'WARNING')
        ? 'WARNING'
        : channelNotChecked > 0 || databaseState === 'NOT_CHECKED' || reportedSystemState === 'NOT_CHECKED' || (hasSourceEvidence && sourceStatus === 'NOT_CHECKED')
          ? 'NOT_CHECKED'
          : 'HEALTHY'
  const sourceReadyCount = sourcePresentations.filter(presentation => presentation.status === 'HEALTHY').length
  const channelReadyCount = channelStates.filter(state => state === 'HEALTHY').length
  const runner = channelHealth?.orderSyncRunner
  const runnerStatus = resolveDiagnosticState(runner?.state ?? undefined)

  const summaryCards: SummaryCardProps[] = [
    {
      label: translate('diagnostics:diagnostics.overallState'),
      value: summaryStatusLabel(overallStatus),
      detail: checkedAt ? translate('diagnostics:diagnostics.lastChecked2', { value1: formatRelativeTime(checkedAt) }) : undefined,
      status: overallStatus,
      icon: 'diagnostics',
    },
    {
      label: translate('diagnostics:diagnostics.healthyServices'),
      value: formatNumber(sourceReadyCount + channelReadyCount),
      status: loading ? 'LOADING' : overallStatus === 'LOADING' ? 'NOT_CHECKED' : 'HEALTHY',
      icon: 'success',
    },
    {
      label: translate('diagnostics:diagnostics.channelChecks'),
      value: translate('diagnostics:diagnostics.readyCountOfTotal', { ready: channelReadyCount, total: channels.length }),
      status: loading ? 'LOADING' : channelStatus,
      icon: 'channel',
    },
    {
      label: translate('diagnostics:diagnostics.sourceChecks'),
      value: translate('diagnostics:diagnostics.readyCountOfTotal', { ready: sourceReadyCount, total: sourceConnectors.length }),
      status: loading ? 'LOADING' : sourceStatus,
      icon: 'file',
    },
  ]

  type CombinedItem =
    | { kind: 'channel'; key: string; status: DiagnosticState; lastChecked: string | null; displayName: string; channel: ChannelHealthItem }
    | { kind: 'source'; key: string; status: DiagnosticState; lastChecked: string | null; displayName: string; connector: ConnectorStatus }
    | { kind: 'backgroundJobs'; key: string; status: DiagnosticState; lastChecked: string | null; runner: RunnerState }

  const combinedItems: CombinedItem[] = [
    ...orderedChannels.ordered.map((resource): CombinedItem => ({
      kind: 'channel', key: `channel:${resource.item.channelId}`,
      status: resolveDiagnosticState(resource.item), lastChecked: resource.item.lastChecked ?? null,
      displayName: resource.displayName, channel: resource.item,
    })),
    ...orderedSources.ordered.map((resource): CombinedItem => ({
      kind: 'source', key: `source:${resource.item.id ?? resource.id}`,
      status: sourcePresentation(resource.item).status, lastChecked: connectorLastChecked(resource.item),
      displayName: resource.displayName, connector: resource.item,
    })),
    ...(runner ? [{
      kind: 'backgroundJobs' as const, key: 'backgroundJobs',
      status: runnerStatus, lastChecked: runner.lastHeartbeat ?? null, runner,
    }] : []),
  ]

  const systemHealthOrder = [...combinedItems].sort((left, right) => SEVERITY_RANK[left.status] - SEVERITY_RANK[right.status])
  const urgentItem = systemHealthOrder.find(item => item.status === 'ERROR' || item.status === 'WARNING')
  const urgentDescription = urgentItem
    ? urgentItem.kind === 'channel'
      ? diagnosticEvidenceDescription({ ...urgentItem.channel, message: urgentItem.channel.summary, recommended_action: urgentItem.channel.recommended_action ?? urgentItem.channel.nextRecommendedAction })
      : urgentItem.kind === 'source'
        ? sourcePresentation(urgentItem.connector).description
        : urgentItem.runner.state ? formatStatus(urgentItem.runner.state) : translate('diagnostics:diagnostics.notCheckedYet')
    : null

  const recentChecksOrder = [...combinedItems]
    .sort((left, right) => {
      if (!left.lastChecked && !right.lastChecked) return 0
      if (!left.lastChecked) return 1
      if (!right.lastChecked) return -1
      return new Date(right.lastChecked).getTime() - new Date(left.lastChecked).getTime()
    })
    .slice(0, RECENT_CHECKS_LIMIT)
    .map((item): RecentCheckEntry => item.kind === 'channel'
      ? { key: item.key, icon: 'channel', title: item.displayName, description: diagnosticEvidenceDescription({ ...item.channel, message: item.channel.summary, recommended_action: item.channel.recommended_action ?? item.channel.nextRecommendedAction }), status: item.status, lastChecked: item.lastChecked }
      : item.kind === 'source'
        ? { key: item.key, icon: 'file', title: item.displayName, description: sourcePresentation(item.connector).description, status: item.status, lastChecked: item.lastChecked }
        : { key: item.key, icon: 'activity', title: translate('diagnostics:diagnostics.backgroundJobs'), description: item.runner.state ? formatStatus(item.runner.state) : translate('diagnostics:diagnostics.notCheckedYet'), status: item.status, lastChecked: item.lastChecked })

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('diagnostics:diagnostics.diagnostics')}</h1>
          <p className="fh-page-subtitle">
            {translate('diagnostics:diagnostics.systemHealthAndIntegrationChecks')}
          </p>
        </div>
        <button type="button" onClick={() => void runCheck()} disabled={loading} className="fh-button-secondary">
          {loading ? <Spinner size="sm" /> : <Icon name="refresh" />}
          {loading ? translate('diagnostics:diagnostics.loading') : translate('diagnostics:diagnostics.reCheck')}
        </button>
      </div>

      {err && <div className="fh-alert fh-alert-danger" role="alert">{err}</div>}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map(card => <SummaryCard key={card.label} {...card} />)}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <section className="fh-card fh-card-pad" aria-labelledby="diagnostics-system-health">
          <h2 id="diagnostics-system-health" className="fh-section-title mb-4">{translate('diagnostics:diagnostics.systemHealth')}</h2>
          {loading && combinedItems.length === 0 ? (
            <div className="flex items-center gap-2 py-2 fh-text-body-sm"><Spinner size="sm" />{translate('diagnostics:diagnostics.loadingChannelHealth')}</div>
          ) : combinedItems.length === 0 ? (
            <Empty title={translate('diagnostics:diagnostics.noChannelHealthData')} />
          ) : (
            <>
              {urgentItem && urgentDescription && (
                <div className="fh-alert fh-alert-warning mb-4" role="status">
                  <Icon name="warning" />
                  <span>{urgentDescription}</span>
                </div>
              )}
              <div className="space-y-3">
                {systemHealthOrder.map(item => item.kind === 'channel'
                  ? <ChannelHealthRow key={item.key} channel={item.channel} displayName={item.displayName} canRefreshChannel={canRefreshChannel} refreshingChannel={refreshingChannel} onRefresh={id => void refreshChannel(id)} />
                  : item.kind === 'source'
                    ? <SourceHealthRow key={item.key} connector={item.connector} displayName={item.displayName} />
                    : <BackgroundJobsRow key={item.key} runner={item.runner} status={item.status} />)}
              </div>
            </>
          )}
        </section>

        <section className="fh-card fh-card-pad" aria-labelledby="diagnostics-recent-checks">
          <h2 id="diagnostics-recent-checks" className="fh-section-title mb-2">{translate('diagnostics:diagnostics.recentChecks')}</h2>
          {recentChecksOrder.length === 0 ? (
            <p className="fh-text-caption">{translate('diagnostics:diagnostics.noChannelHealthData')}</p>
          ) : (
            <div>{recentChecksOrder.map(entry => <RecentCheckRow key={entry.key} entry={entry} />)}</div>
          )}
        </section>
      </div>
    </PageShell>
  )
}
