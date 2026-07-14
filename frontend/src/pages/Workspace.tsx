import { translate } from '../i18n'
import { useCallback, useEffect, useRef, useState } from 'react'
import Badge from '../components/Badge'
import { useServices } from '../services/ServiceContext'
import type { WorkspacePreview, PriceChange, WorkspacePreviewRow, WritePipelineBatch, WritePipelineItem } from '../services/types'
import { useNotification } from '../notifications/NotificationProvider'
import Spinner from '../components/loading/Spinner'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import LocalizedText from '../components/LocalizedText'
import PageShell from '../components/PageShell'
import { ApiError } from '../api/client'
import { formatMoney } from '../utils/price'
import { formatDateTime, formatNumber, formatPercent } from '../i18n/format'
import { localizedApiError } from '../i18n/errors'

const workspaceErrorMessage = localizedApiError

function previewErrorContent(error: unknown): { title: string; description: string } {
  if (error instanceof ApiError && error.status === 429 && error.code === 'SOURCE_READ_LIMIT_REACHED') {
    const usage = error.details.usage
    const limit = error.details.limit
    const reset = error.details.resetAt ? new Date(error.details.resetAt) : null
    const allowance = usage !== undefined && limit !== undefined ? translate('workspace:workspace.sourceReadsUsed', { usage: formatNumber(Number(usage)), limit: formatNumber(Number(limit)) }) : ''
    const recovery = reset && !Number.isNaN(reset.getTime())
      ? translate('workspace:workspace.tryAgainAfter', { date: formatDateTime(reset) })
      : error.details.retryAfterSeconds !== undefined
        ? translate('workspace:workspace.tryAgainInMinutes', { count: Math.ceil(error.details.retryAfterSeconds / 60) })
        : translate('workspace:workspace.tryAgainAfterAllowanceReset')
    return { title: translate('workspace:workspace.sourceReadLimitReached'), description: translate('workspace:workspace.sourceReadRecovery', { allowance, recovery }) }
  }
  return { title: translate('workspace:workspace.unableToStartPreview'), description: workspaceErrorMessage(error, 'errors:codes.UNKNOWN') }
}

function fmtPrice(p: number, currency: string): string {
  return formatMoney(p, { currency, position: 'prefix' })
}

function ChangePct({ pct }: { pct: number }) {
  const positive = pct >= 0
  return (
    <span className={["fh-text-caption font-semibold", positive ? "text-wp-orange" : "text-wp-green"].join(' ')}>
      {formatPercent(pct / 100, { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: positive ? 'always' : 'auto' })}
    </span>
  )
}

function PriceChangeRow({ change }: { change: PriceChange }) {
  return (
    <tr className="border-b border-border hover:bg-bg-base/60 transition-colors">
      <td className="px-4 py-3 min-w-0 max-w-[200px]">
        <div className="fh-text-body font-medium truncate">
          <LocalizedText text={change.productName} />
        </div>
        <div className="fh-text-caption fh-text-mono mt-0.5">{change.sku}</div>
      </td>
      <td className="px-4 py-3 fh-text-caption font-mono">
        {fmtPrice(change.currentPrice, change.currency)}
      </td>
      <td className="px-4 py-3 fh-text-body font-medium font-mono">
        {fmtPrice(change.proposedPrice, change.currency)}
      </td>
      <td className="px-4 py-3">
        <ChangePct pct={change.changePct} />
      </td>
      <td className="px-4 py-3 fh-text-caption">
        {change.warning ?? '-'}
      </td>
    </tr>
  )
}

type Phase = 'idle' | 'previewing' | 'preview_ready' | 'dry_running' | 'dry_run_ready' | 'approving' | 'approved' | 'applying' | 'result' | 'error'

function StepPill({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  return (
    <span className={[
      "fh-badge",
      active ? "fh-badge-warning" : done ? "fh-badge-success" : "fh-badge-neutral",
    ].join(' ')}>
      {label}
    </span>
  )
}

function statusLabel(status: WorkspacePreviewRow['status']): string {
  if (status === 'valid_change') return translate('workspace:workspace.status.valid')
  if (status === 'warning') return translate('common:status.warning')
  if (status === 'unchanged') return translate('common:status.unchanged')
  if (status === 'stock_changed') return translate('workspace:workspace.status.stockOnly')
  if (status === 'price_and_stock_changed') return translate('workspace:workspace.status.priceAndStock')
  return translate('common:status.error')
}

function messages(row: WorkspacePreviewRow): string {
  const items = [...row.errors, ...row.warnings]
  return items.length ? items.join(', ') : '-'
}

function attributeText(attributes?: Array<Record<string, string>>): string {
  if (!attributes?.length) return ''
  return attributes
    .map(item => [item.name, item.value].filter(Boolean).join(': '))
    .filter(Boolean)
    .join(', ')
}

function PreviewRow({ row, selected, onToggle }: {
  row: WorkspacePreviewRow
  selected: boolean
  onToggle: (rowId: string, selected: boolean) => void
}) {
  const name = row.matchedProduct?.name ?? row.source.productName ?? translate('workspace:workspace.unmatchedProduct')
  const sku = row.matchedProduct?.sku || row.source.sku || '-'
  const isVariation = row.matchedProduct?.itemType === 'variation' || row.matchedProduct?.productType === 'variation'
  const attrs = attributeText(row.matchedProduct?.variationAttributes)
  const currency = 'EUR'
  const stockDiff = row.stockDifference
  return (
    <tr className="border-b border-border hover:bg-bg-base/60 transition-colors">
      <td className="px-4 py-3 text-center">
        <input
          type="checkbox"
          aria-label={translate('workspace:workspace.selectProduct', { product: name })}
          checked={selected}
          disabled={!row.eligible_for_dry_run}
          onChange={event => onToggle(row.id, event.target.checked)}
        />
      </td>
      <td className="px-4 py-3 min-w-0 max-w-[220px]">
        <div className="flex items-center gap-2 fh-text-body font-medium text-text-base">
          <LocalizedText className="truncate" text={name} />
          {isVariation && <Badge className="shrink-0" variant="neutral">{translate('workspace:workspace.variation')}</Badge>}
        </div>
        <div className="fh-text-caption fh-text-mono mt-0.5">
          {row.source.worksheet}:{row.source.rowNumber} · {sku}
        </div>
        {isVariation && (
          <div className="fh-text-caption mt-0.5 truncate">
            {translate('workspace:workspace.parent')} {row.matchedProduct?.parentProductId ?? row.matchedProduct?.parentId ?? '-'}
            {row.matchedProduct?.parentProductName && (
              <>
                {' · '}
                <LocalizedText text={row.matchedProduct.parentProductName} />
              </>
            )}
            {attrs && (
              <>
                {' · '}
                <LocalizedText text={attrs} />
              </>
            )}
          </div>
        )}
      </td>
      <td className="px-4 py-3 fh-text-caption font-mono">
        {row.currentPrice == null ? '-' : fmtPrice(row.currentPrice, currency)}
      </td>
      <td className="px-4 py-3 fh-text-body font-medium font-mono">
        {row.proposedPrice == null ? row.source.rawPrice || '-' : fmtPrice(row.proposedPrice, currency)}
      </td>
      <td className="px-4 py-3">
        {row.changePct == null ? '-' : <ChangePct pct={row.changePct} />}
      </td>
      <td className="px-4 py-3 fh-text-caption font-mono">
        {row.currentStock == null ? '-' : row.currentStock}
      </td>
      <td className="px-4 py-3 fh-text-body font-mono">
        {row.sourceStock == null ? row.source.rawStock || '-' : row.sourceStock}
      </td>
      <td className="px-4 py-3 fh-text-caption font-mono">
        {stockDiff == null ? '-' : formatNumber(stockDiff, { signDisplay: 'always' })}
      </td>
      <td className="px-4 py-3">
        <Badge variant={
          row.status === "valid_change" ? "success" :
          row.status === "warning" || row.status === "price_and_stock_changed" ? "warning" :
          row.status === "unchanged" || row.status === "stock_changed" ? "neutral" :
          "danger"
        }>{statusLabel(row.status)}</Badge>
      </td>
      <td className="px-4 py-3 fh-text-caption max-w-[280px]">
        <span className="line-clamp-2">{messages(row)}</span>
      </td>
    </tr>
  )
}

function WorkflowSteps({ phase }: { phase: Phase }) {
  const order = ['preview_ready', 'dry_run_ready', 'approved', 'result']
  const idx = phase === 'dry_running' ? 1 : phase === 'approving' ? 2 : phase === 'applying' ? 3 : order.indexOf(phase)
  const steps = [
    translate('workspace:workspace.steps.preview'),
    translate('workspace:workspace.steps.dryRun'),
    translate('workspace:workspace.steps.approve'),
    translate('workspace:workspace.steps.result'),
  ]
  return (
    <div className="flex flex-wrap gap-2">
      {steps.map((label, index) => (
        <StepPill key={label} label={label} active={idx === index} done={idx > index} />
      ))}
    </div>
  )
}

function batchMetric(batch: WritePipelineBatch, key: string, fallback = 0): number {
  const value = batch.resultSummary?.[key as keyof NonNullable<WritePipelineBatch['resultSummary']>]
  return typeof value === 'number' ? value : fallback
}

function safetyMetric(batch: WritePipelineBatch, key: string, fallback = 0): number {
  const value = batch.safetySummary[key]
  return typeof value === 'number' ? value : fallback
}

function ResultItemRow({ item }: { item: WritePipelineItem }) {
  const verification = item.verification
  const verified = verification?.verified === true
  const isVariation = item.itemType === 'variation'
  const attrs = attributeText(item.variationAttributes)
  return (
    <tr className="border-b border-border last:border-0">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2 fh-text-body font-medium text-text-base">
          <LocalizedText text={item.productName || item.productId} />
          {isVariation && <Badge variant="neutral">{translate('workspace:workspace.variation')}</Badge>}
        </div>
        <div className="fh-text-caption font-mono">{item.source?.worksheet ?? '-'}:{item.source?.rowNumber ?? '-'} · {item.sku || '-'}</div>
        {isVariation && (
          <div className="fh-text-caption mt-0.5">
            {translate('workspace:workspace.parent')} {item.parentProductId ?? '-'}
            {attrs && (
              <>
                {' · '}
                <LocalizedText text={attrs} />
              </>
            )}
          </div>
        )}
      </td>
      <td className="px-4 py-3 fh-text-caption font-mono">{fmtPrice(item.currentPrice, item.currency)}</td>
      <td className="px-4 py-3 fh-text-body-sm font-mono text-text-base">{fmtPrice(item.proposedPrice, item.currency)}</td>
      <td className="px-4 py-3"><Badge variant={item.status === "failed" ? "error" : "valid"}>{item.status}</Badge></td>
      <td className="px-4 py-3 fh-text-body-sm">
        {item.status === "failed"
          ? (item.errorMessage ?? item.errorCode ?? "Failed")
          : verified
            ? translate('workspace:workspace.verifiedAt', { value1: fmtPrice(Number(verification?.observed_price ?? item.proposedPrice), item.currency) })
            : (verification?.verification_error ?? "Not verified")}
      </td>
    </tr>
  )
}

export default function Workspace() {
  const { workspace, settings, writePipeline } = useServices()
  const { info, success } = useNotification()

  const [phase, setPhase] = useState<Phase>('idle')
  const [preview, setPreview] = useState<WorkspacePreview | null>(null)
  const [batch, setBatch] = useState<WritePipelineBatch | null>(null)
  const [errorTitle, setErrorTitle] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [cacheEmptyError, setCacheEmptyError] = useState(false)
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set())

  // Check if both product and source connectors are configured.
  const [wcConfigured, setWcConfigured] = useState<boolean | null>(null)
  const [ncConfigured, setNcConfigured] = useState<boolean | null>(null)
  const [configLoading, setConfigLoading] = useState(true)
  const previewRequestInFlight = useRef(false)

  useEffect(() => {
    settings.getSettings()
      .then(s => {
        setWcConfigured(s.wcConfigured ?? false)
        setNcConfigured(s.ncConfigured ?? false)
      })
      .catch(() => {
        setWcConfigured(false)
        setNcConfigured(false)
      })
      .finally(() => setConfigLoading(false))
  }, [settings])

  const startPreview = useCallback(async () => {
    if (previewRequestInFlight.current) return
    previewRequestInFlight.current = true
    setPhase('previewing')
    setErrorTitle(null)
    setErrorMsg(null)
    setCacheEmptyError(false)
    try {
      const p = await workspace.startPreview('')
      setPreview(p)
      setSelectedRowIds(new Set(p.rows.filter(row => row.eligible_for_dry_run).map(row => row.id)))
      setBatch(null)
      setPhase('preview_ready')
      info({
        title: translate('workspace:workspace.previewPreparedSuccessfully'),
        description: translate('workspace:workspace.productReadyForReview', { count: p.totalChanges }),
      })
    } catch (e) {
      const error = previewErrorContent(e)
      setErrorTitle(error.title)
      setErrorMsg(error.description)
      setCacheEmptyError(e instanceof ApiError && (
        e.code === 'CACHE_EMPTY'
        // i18n-ignore -- legacy diagnostic fallback until this endpoint emits CACHE_EMPTY.
        || e.message.includes('WooCommerce product cache is empty')
      ))
      setPhase('error')
    } finally {
      previewRequestInFlight.current = false
    }
  }, [workspace, info])

  const createDryRun = useCallback(async () => {
    if (!preview) return
    const selected = [...selectedRowIds]
    if (selected.length === 0) return
    setPhase('dry_running')
    setErrorMsg(null)
    try {
      const b = await writePipeline.createDryRun(preview.id, selected)
      setBatch(b)
      setPhase('dry_run_ready')
      success({
        title: translate('workspace:workspace.dryRunCompletedSuccessfully'),
        description: translate('workspace:workspace.noChangesHaveBeenApplied'),
      })
    } catch (e) {
      setErrorMsg(workspaceErrorMessage(e, 'workspace:workspace.failedToCreateDryRun'))
      setPhase('error')
    }
  }, [preview, selectedRowIds, writePipeline, info])

  const approveDryRun = useCallback(async () => {
    if (!batch) return
    setPhase('approving')
    setErrorMsg(null)
    try {
      const b = await writePipeline.approve(batch.id,
        /* i18n-ignore -- stable API audit reason, never displayed as interface copy */ 'Approved from Workspace')
      setBatch(b)
      setPhase('approved')
      info({
        title: translate('workspace:workspace.changesApprovedSuccessfully'),
        description: translate('workspace:workspace.applyIsStillRequiredBeforeChangesAre'),
      })
    } catch (e) {
      setErrorMsg(workspaceErrorMessage(e, 'workspace:workspace.failedToApprove'))
      setPhase('error')
    }
  }, [batch, writePipeline, info])

  const applyToWooCommerce = useCallback(async () => {
    if (!batch) return
    setPhase('applying')
    setErrorMsg(null)
    try {
      const b = await writePipeline.applyToWooCommerce(batch.id)
      setBatch(b)
      setPhase('result')
      success({
        title: translate('workspace:workspace.changesAppliedSuccessfully'),
        description: translate('workspace:workspace.allApprovedUpdatesHaveBeenCompleted'),
      })
    } catch (e) {
      setErrorMsg(workspaceErrorMessage(e, 'workspace:workspace.failedToApplyToWooCommerce'))
      setPhase('error')
    }
  }, [batch, writePipeline, success])

  const cancelPreview = useCallback(async () => {
    if (preview) await workspace.cancelPreview(preview.id)
    setPreview(null)
    setBatch(null)
    setSelectedRowIds(new Set())
    setPhase('idle')
  }, [workspace, preview])

  const bothConfigured = wcConfigured === true && ncConfigured === true
  const eligibleRows = preview?.rows.filter(row => row.eligible_for_dry_run) ?? []
  const blockedRows = preview?.rows.filter(row => row.errors.length > 0).length ?? 0
  const stockOnlyRows = preview?.rows.filter(row => row.status === 'stock_changed').length ?? 0
  const toggleRow = useCallback((rowId: string, selected: boolean) => {
    setSelectedRowIds(current => {
      const next = new Set(current)
      if (selected) next.add(rowId)
      else next.delete(rowId)
      return next
    })
  }, [])

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
        <h1 className="fh-page-title">{translate('workspace:workspace.workspace')}</h1>
        <p className="fh-page-subtitle">{translate('workspace:workspace.previewPriceChangesFromYourSources')}</p>
        </div>
      </div>

      {/* Config loading */}
      {configLoading && (
        <div className="fh-card fh-card-pad flex items-center gap-2 fh-text-body-sm">
          <Spinner size="sm" />
          {translate('workspace:workspace.loadingConfiguration')}
        </div>
      )}

      {/* Not configured */}
      {!configLoading && !bothConfigured && phase === "idle" && (
        <div className="fh-card">
          {!wcConfigured && (
            <Empty
              title={translate('workspace:workspace.productConnectorRequired')}
              description={translate('workspace:workspace.connectAProductSourceFromSourcesTo')}
              action={{ label: translate('workspace:workspace.openSources'), onClick: () => { window.location.href = '/sources' } }}
            />
          )}
          {wcConfigured && !ncConfigured && (
            <Empty
              title={translate('workspace:workspace.sourceConnectorRequired')}
              description={translate('workspace:workspace.reviewConnectorSettingsBeforeUsingWorkspace')}
              action={{ label: translate('workspace:workspace.openSettings'), onClick: () => { window.location.href = '/settings' } }}
            />
          )}
        </div>
      )}

      {/* Idle - start button */}
      {!configLoading && bothConfigured && phase === "idle" && (
        <div className="fh-card fh-card-pad flex flex-col gap-5">
          <div>
            <p className="fh-section-title">{translate('workspace:statusDisplay.ready')}</p>
            <p className="fh-section-subtitle mt-1">
              {translate('workspace:workspace.flowhubWillFetchProductsFromTheConnected')}
            </p>
          </div>
          <button
            onClick={() => void startPreview()}
            className="fh-button-primary w-full"
          >
            <Icon name="preview" />
            {translate('workspace:workspace.startPreview')}
          </button>
        </div>
      )}

      {/* Previewing - loading state */}
      {(phase === "previewing" || phase === "dry_running" || phase === "approving" || phase === "applying") && (
        <div className="fh-card fh-card-pad flex flex-col items-center gap-4 py-12">
          <Spinner size="lg" />
          <p className="fh-text-body font-medium">
            {phase === "previewing" && "Fetching products and source data..."}
            {phase === "dry_running" && "Running safety checks..."}
            {phase === "approving" && "Recording approval..."}
            {phase === "applying" && "Applying approved prices to WooCommerce..."}
          </p>
          <p className="fh-text-caption">
            {phase === "applying" ? translate('workspace:workspace.thisIsTheOnlyStepThatWrites') : translate('workspace:workspace.noMarketplaceChangeIsAppliedInThis')}
          </p>
        </div>
      )}

      {/* Preview ready */}
      {(["preview_ready", "dry_run_ready", "approved", "result"] as Phase[]).includes(phase) && preview && (
        <>
          <WorkflowSteps phase={phase} />

          <div className="fh-form-section">
            <div>
              <p className="fh-section-label">{translate('workspace:workspace.workflowGuardrails')}</p>
              <p className="fh-form-section-description">{translate('workspace:workspace.theUnderlyingWorkflowIsUnchangedTheseSurfaces')}</p>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4 fh-text-caption">
              <p>{translate('workspace:workspace.stockWillNotBeChanged')}</p>
              <p>{translate('workspace:workspace.automaticApplyIsDisabled')}</p>
              <p>{translate('workspace:workspace.onlyApprovedBatchesCanBeApplied')}</p>
              <p>{translate('workspace:workspace.otherChannelsAreReadOnlyUnavailableFor')}</p>
            </div>
            <div className="grid gap-2 border-t border-border pt-4 sm:grid-cols-2 xl:grid-cols-4 fh-text-caption">
              <p>{translate('workspace:workspace.simpleAndVariationWoocommercePriceUpdatesAre')}</p>
              <p>{translate('workspace:workspace.variationRowsRequireCachedParentProductMetadata')}</p>
              <p>{translate('workspace:workspace.stockUpdatesAreNotSupported')}</p>
              <p>{translate('workspace:workspace.csvAndGoogleSheetsAreNotAvailable')}</p>
            </div>
          </div>

          <div className="fh-alert fh-alert-warning">
            <Icon name="alert" className="mt-0.5 h-5 w-5 text-wp-yellow" />
            <div>
              <p className="fh-text-body font-medium text-wp-yellow">
                {preview.summary.valid_changes + preview.summary.warning_rows} {translate('workspace:workspace.eligibleRow')}{preview.summary.valid_changes + preview.summary.warning_rows !== 1 ? 's' : ''}; {preview.summary.error_rows} {translate('workspace:workspace.blockingError')}{preview.summary.error_rows !== 1 ? 's' : ''}
              </p>
              <p className="fh-text-caption mt-0.5">
                {translate('workspace:workspace.previewFirstThenRunSafetyChecksBefore')}
              </p>
            </div>
          </div>

          <div className="fh-stat-grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8">
            {[
              ["Rows", preview.summary.total_rows],
              ["Valid", preview.summary.valid_changes],
              ["Warnings", preview.summary.warning_rows],
              ["Unchanged", preview.summary.unchanged_rows],
              ["Errors", preview.summary.error_rows],
              ["Duplicates", preview.summary.duplicate_rows],
              ["Missing", preview.summary.missing_products],
              ["Large", preview.summary.large_changes],
            ].map(([label, value]) => (
              <div key={label} className="fh-stat-tile">
                <p className="fh-stat-tile-label">{label}</p>
                <p className="fh-stat-tile-value">{value}</p>
              </div>
            ))}
          </div>

          {batch && (
            <div className="fh-card fh-card-pad flex flex-col gap-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="fh-section-title">
                    {phase === "dry_run_ready" && "Dry Run ready"}
                    {phase === "approved" && "Approved"}
                    {phase === "result" && "Result"}
                  </p>
                  <p className="fh-text-caption mt-1">
                    {translate('workspace:workspace.reference')} {batch.id} - {batch.itemCount} {translate('workspace:workspace.priceChange')}{batch.itemCount !== 1 ? 's' : ''} {translate('workspace:workspace.forWoocommerce')}
                  </p>
                </div>
                <span className="fh-text-caption font-mono">{batch.status}</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 fh-text-caption">
                <div>
                  <p className="text-wp-muted">{translate('workspace:unifiedWorkspace.channel')}</p>
                  <p className="font-medium text-text-base">{translate('workspace:workspace.woocommerce')}</p>
                </div>
                <div>
                  <p className="text-wp-muted">{translate('workspace:workspace.stock')}</p>
                  <p className="font-medium text-text-base">{translate('workspace:unifiedWorkspace.blocked')}</p>
                </div>
                <div>
                  <p className="text-wp-muted">{translate('workspace:workspace.scheduler')}</p>
                  <p className="font-medium text-text-base">{translate('workspace:workspace.disabled')}</p>
                </div>
                <div>
                  <p className="text-wp-muted">{translate('workspace:workspace.automaticApply')}</p>
                  <p className="font-medium text-text-base">{translate('workspace:workspace.disabled')}</p>
                </div>
              </div>
              {batch.status === "dry_run_ready" && (
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 fh-text-caption">
                  {[
                    ["Eligible", safetyMetric(batch, "eligible_rows", batch.itemCount)],
                    ["Skipped", safetyMetric(batch, "skipped_rows")],
                    ["Blocked", safetyMetric(batch, "blocked_rows")],
                    ["Warnings", safetyMetric(batch, "warning_rows")],
                    ["Affected", safetyMetric(batch, "estimated_affected_products", batch.itemCount)],
                  ].map(([label, value]) => (
                    <div key={label} className="fh-stat-tile">
                      <p className="fh-stat-tile-label">{label}</p>
                      <p className="fh-stat-tile-value">{String(value)}</p>
                    </div>
                  ))}
                </div>
              )}
              {phase === "dry_run_ready" && (
                <button onClick={() => void approveDryRun()} className="fh-button-primary self-start">
                  <Icon name="apply" />
                  {translate('workspace:workspace.approve')}
                </button>
              )}
              {phase === "approved" && (
                <button onClick={() => void applyToWooCommerce()} className="fh-button-primary self-start">
                  <Icon name="apply" />
                  {translate('workspace:workspace.applyToWoocommerce')}
                </button>
              )}
              {phase === "result" && (
                <div className="flex flex-col gap-4">
                  <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 fh-text-caption">
                    {[
                      ["Attempted", batchMetric(batch, "total_attempted", batch.items.length)],
                      ["Success", batchMetric(batch, "success_count", batch.items.filter(item => item.status === "applied").length)],
                      ["Failed", batchMetric(batch, "failure_count", batch.items.filter(item => item.status === "failed").length)],
                      ["Skipped", batchMetric(batch, "skipped_count")],
                      ["Warnings", batchMetric(batch, "warning_count")],
                      ["Verified", batchMetric(batch, "verified_count")],
                      ["Unverified", batchMetric(batch, "unverified_count")],
                      ["Affected", batchMetric(batch, "estimated_affected_products", batch.itemCount)],
                    ].map(([label, value]) => (
                      <div key={label} className="fh-stat-tile">
                        <p className="fh-stat-tile-label">{label}</p>
                        <p className="fh-stat-tile-value">{String(value)}</p>
                      </div>
                    ))}
                  </div>
                  <div className="fh-table-wrapper">
                    <div className="overflow-x-auto">
                    <table className="fh-table fh-table-compact min-w-[720px]">
                      <thead>
                        <tr>
                          {["Product", "Old Price", "New Price", "Status", "Result"].map(h => (
                            <th key={h}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {batch.items.map(item => <ResultItemRow key={item.id ?? item.productId} item={item} />)}
                      </tbody>
                    </table>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Duplicate warnings */}
          {(preview.duplicateWarnings ?? []).length > 0 && (
            <div className="fh-card fh-card-pad">
              <p className="fh-section-label mb-3">
                {translate('workspace:workspace.spreadsheetWarnings')}{preview.duplicateWarnings!.length})
              </p>
              {preview.duplicateWarnings!.map((w, i) => (
                <p key={i} className="fh-text-caption py-1 border-b border-border last:border-0">{w}</p>
              ))}
            </div>
          )}

          <div className="fh-card overflow-hidden">
            <div className="fh-panel-header">
              <div>
                <span className="fh-section-title">
                {translate('workspace:workspace.preview2')} {preview.summary.total_rows} {translate('workspace:workspace.sourceRows')}
                </span>
                <p className="fh-text-caption mt-1">{translate('workspace:workspace.denseValidationRowsRemainScrollableButNow')}</p>
              </div>
              <div className="flex flex-wrap items-center gap-3 fh-text-caption">
                <span>
                  <span className="font-mono">{translate('workspace:workspace.source')} </span>
                  <LocalizedText text={preview.sourceName} />
                </span>
                <button type="button" onClick={() => setSelectedRowIds(new Set(eligibleRows.map(row => row.id)))} className="fh-button-secondary px-2 py-1">
                  <Icon name="apply" />
                  {translate('workspace:workspace.selectAllEligible')}
                </button>
                <button type="button" onClick={() => setSelectedRowIds(new Set())} className="fh-button-secondary px-2 py-1">
                  <Icon name="close" />
                  {translate('workspace:workspace.deselectAll')}
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 px-4 py-3 border-b border-border bg-bg-subtle fh-text-caption">
              <span>{translate('workspace:workspace.selected')} <strong>{selectedRowIds.size}</strong></span>
              <span>{translate('workspace:workspace.eligible')} <strong>{eligibleRows.length}</strong></span>
              <span>{translate('workspace:workspace.blocked')} <strong>{blockedRows}</strong></span>
              <span>{translate('workspace:workspace.stockOnly')} <strong>{stockOnlyRows}</strong></span>
              <span>{translate('workspace:workspace.estimatedWoocommerceCalls')} <strong>{selectedRowIds.size}</strong></span>
            </div>

            <div className="overflow-x-auto">
              <table className="fh-table fh-table-compact min-w-[1120px]">
                <thead>
                  <tr>
                    {["Select", "Product", "Current Price", "New Price", "Change", "Current Stock", "Source Stock", "Stock Change", "Status", "Validation"].map(h => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.length > 0
                    ? preview.rows.map(row => (
                        <PreviewRow key={row.id} row={row} selected={selectedRowIds.has(row.id)} onToggle={toggleRow} />
                      ))
                    : preview.changes.map(c => <PriceChangeRow key={c.productId} change={c} />)}
                </tbody>
              </table>
            </div>

            <div className="fh-panel-footer !justify-between">
              <div className="flex items-center gap-2 fh-text-caption">
                <Icon name="alert" />
                {translate('workspace:workspace.applyRequiresDryRunAndApprovalFirst')}
              </div>
              <div className="flex items-center gap-2">
                {phase === "preview_ready" && (
                  <button
                    onClick={() => void createDryRun()}
                    disabled={selectedRowIds.size === 0}
                    className="fh-button-primary disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Icon name="dryRun" />
                    {translate('workspace:workspace.dryRun')}
                  </button>
                )}
                <button
                  onClick={() => void cancelPreview()}
                  className="fh-button-secondary hover:text-wp-red hover:border-wp-red"
                >
                  <Icon name="preview" />
                  {translate('workspace:workspace.newPreview')}
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Error */}
      {phase === "error" && (
        <div className="fh-card fh-card-pad flex flex-col gap-4">
          <div className="fh-alert fh-alert-danger">
            <Icon name="disconnect" className="mt-0.5 h-5 w-5 text-wp-red" />
            <div>
              <p className="fh-text-body font-semibold text-wp-red">{errorTitle ?? "An error occurred"}</p>
              <p className="fh-text-body text-wp-red">{errorMsg ?? "Please try again."}</p>
            </div>
          </div>
          <button
            onClick={() => setPhase("idle")}
            className="fh-button-secondary self-start"
          >
            <Icon name="retry" />
            {translate('workspace:workspace.tryAgain')}
          </button>
          {cacheEmptyError && (
            <button
              type="button"
              onClick={() => { window.location.href = '/commerce?tab=channels' }}
              className="fh-button-secondary self-start"
            >
              <Icon name="next" mirrorRtl />
              {translate('workspace:workspace.goToCommerceHubChannelsAndRefresh')}
            </button>
          )}
        </div>
      )}
    </PageShell>
  )
}
