import { useCallback, useEffect, useState } from 'react'
import { useServices } from '../services/ServiceContext'
import type { WorkspacePreview, PriceChange, WorkspacePreviewRow, WritePipelineBatch, WritePipelineItem } from '../services/types'
import { useNotification } from '../notifications/NotificationProvider'
import Spinner from '../components/loading/Spinner'
import Empty from '../components/Empty'
import PageShell from '../components/PageShell'
import { ApiError } from '../api/client'

function workspaceErrorMessage(error: unknown, fallback: string): string {
  const redact = (value: string) => value.replace(
    /((?:consumer_secret|consumer_key|access_token|refresh_token|authorization|password|api_key|apikey|secret|token|key)\s*["']?\s*[:=]\s*["']?)([^"',\s}]+)/gi,
    '$1[REDACTED]',
  )
  if (error instanceof ApiError) {
    try {
      const parsed = JSON.parse(error.message) as { detail?: unknown }
      if (typeof parsed.detail === 'string' && parsed.detail.trim()) return redact(parsed.detail)
    } catch {
      if (error.message.trim()) return redact(error.message)
    }
  }
  return error instanceof Error && error.message.trim() ? redact(error.message) : fallback
}

function fmtPrice(p: number, currency: string): string {
  return `${currency} ${p.toFixed(2)}`
}

function ChangePct({ pct }: { pct: number }) {
  const positive = pct >= 0
  return (
    <span className={['text-[12px] font-semibold', positive ? 'text-wp-orange' : 'text-wp-green'].join(' ')}>
      {positive ? '+' : ''}{pct.toFixed(2)}%
    </span>
  )
}

function PriceChangeRow({ change }: { change: PriceChange }) {
  return (
    <tr className="border-b border-border hover:bg-bg-base/60 transition-colors">
      <td className="px-4 py-3 min-w-0 max-w-[200px]">
        <div className="text-[13px] font-medium text-text-base truncate">{change.productName}</div>
        <div className="text-[11px] font-mono text-wp-muted mt-0.5">{change.sku}</div>
      </td>
      <td className="px-4 py-3 text-[13px] text-wp-muted font-mono">
        {fmtPrice(change.currentPrice, change.currency)}
      </td>
      <td className="px-4 py-3 text-[13px] font-medium text-text-base font-mono">
        {fmtPrice(change.proposedPrice, change.currency)}
      </td>
      <td className="px-4 py-3">
        <ChangePct pct={change.changePct} />
      </td>
      <td className="px-4 py-3 text-[11px] text-wp-muted">
        {change.warning ?? '-'}
      </td>
    </tr>
  )
}

type Phase = 'idle' | 'previewing' | 'preview_ready' | 'dry_running' | 'dry_run_ready' | 'approving' | 'approved' | 'applying' | 'result' | 'error'

function StepPill({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  return (
    <span className={[
      'px-2.5 py-1 rounded-md text-[11px] font-semibold border',
      active ? 'bg-wp-yellow/10 text-wp-yellow border-wp-yellow/30' : done ? 'bg-wp-green/10 text-wp-green border-wp-green/30' : 'text-wp-muted border-border',
    ].join(' ')}>
      {label}
    </span>
  )
}

function statusLabel(status: WorkspacePreviewRow['status']): string {
  if (status === 'valid_change') return 'Valid'
  if (status === 'warning') return 'Warning'
  if (status === 'unchanged') return 'Unchanged'
  if (status === 'stock_changed') return 'Stock only'
  if (status === 'price_and_stock_changed') return 'Price + Stock'
  return 'Error'
}

function statusClass(status: WorkspacePreviewRow['status']): string {
  if (status === 'valid_change') return 'fh-badge-success'
  if (status === 'warning') return 'fh-badge-warning'
  if (status === 'unchanged' || status === 'stock_changed') return 'fh-badge-neutral'
  if (status === 'price_and_stock_changed') return 'fh-badge-warning'
  return 'fh-badge-danger'
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
  const name = row.matchedProduct?.name ?? row.source.productName ?? 'Unmatched product'
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
          aria-label={`Select ${name}`}
          checked={selected}
          disabled={!row.eligible_for_dry_run}
          onChange={event => onToggle(row.id, event.target.checked)}
        />
      </td>
      <td className="px-4 py-3 min-w-0 max-w-[220px]">
        <div className="flex items-center gap-2 text-[13px] font-medium text-text-base">
          <span className="truncate">{name}</span>
          {isVariation && <span className="fh-badge fh-badge-neutral shrink-0">Variation</span>}
        </div>
        <div className="text-[11px] font-mono text-wp-muted mt-0.5">
          {row.source.worksheet}:{row.source.rowNumber} · {sku}
        </div>
        {isVariation && (
          <div className="text-[11px] text-wp-muted mt-0.5 truncate">
            Parent {row.matchedProduct?.parentProductId ?? row.matchedProduct?.parentId ?? '-'}
            {row.matchedProduct?.parentProductName ? ` آ· ${row.matchedProduct.parentProductName}` : ''}
            {attrs ? ` آ· ${attrs}` : ''}
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-[13px] text-wp-muted font-mono">
        {row.currentPrice == null ? '-' : fmtPrice(row.currentPrice, currency)}
      </td>
      <td className="px-4 py-3 text-[13px] font-medium text-text-base font-mono">
        {row.proposedPrice == null ? row.source.rawPrice || '-' : fmtPrice(row.proposedPrice, currency)}
      </td>
      <td className="px-4 py-3">
        {row.changePct == null ? '-' : <ChangePct pct={row.changePct} />}
      </td>
      <td className="px-4 py-3 text-[13px] text-wp-muted font-mono">
        {row.currentStock == null ? '-' : row.currentStock}
      </td>
      <td className="px-4 py-3 text-[13px] text-text-base font-mono">
        {row.sourceStock == null ? row.source.rawStock || '-' : row.sourceStock}
      </td>
      <td className="px-4 py-3 text-[12px] text-wp-muted font-mono">
        {stockDiff == null ? '-' : `${stockDiff > 0 ? '+' : ''}${stockDiff}`}
      </td>
      <td className="px-4 py-3">
        <span className={['fh-badge', statusClass(row.status)].join(' ')}>{statusLabel(row.status)}</span>
      </td>
      <td className="px-4 py-3 text-[11px] text-wp-muted max-w-[280px]">
        <span className="line-clamp-2">{messages(row)}</span>
      </td>
    </tr>
  )
}

function WorkflowSteps({ phase }: { phase: Phase }) {
  const order = ['preview_ready', 'dry_run_ready', 'approved', 'result']
  const idx = phase === 'dry_running' ? 1 : phase === 'approving' ? 2 : phase === 'applying' ? 3 : order.indexOf(phase)
  return (
    <div className="flex flex-wrap gap-2">
      {['Preview', 'Dry Run', 'Approve', 'Result'].map((label, index) => (
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
        <div className="flex items-center gap-2 text-[13px] font-medium text-text-base">
          <span>{item.productName || item.productId}</span>
          {isVariation && <span className="fh-badge fh-badge-neutral">Variation</span>}
        </div>
        <div className="text-[11px] font-mono text-wp-muted">{item.source?.worksheet ?? '-'}:{item.source?.rowNumber ?? '-'} · {item.sku || '-'}</div>
        {isVariation && (
          <div className="text-[11px] text-wp-muted mt-0.5">
            Parent {item.parentProductId ?? '-'}{attrs ? ` آ· ${attrs}` : ''}
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-[12px] font-mono text-wp-muted">{fmtPrice(item.currentPrice, item.currency)}</td>
      <td className="px-4 py-3 text-[12px] font-mono text-text-base">{fmtPrice(item.proposedPrice, item.currency)}</td>
      <td className="px-4 py-3"><span className={['fh-badge', item.status === 'failed' ? 'fh-badge-error' : 'fh-badge-valid'].join(' ')}>{item.status}</span></td>
      <td className="px-4 py-3 text-[12px] text-wp-muted">
        {item.status === 'failed'
          ? (item.errorMessage ?? item.errorCode ?? 'Failed')
          : verified
            ? `Verified at ${fmtPrice(Number(verification?.observed_price ?? item.proposedPrice), item.currency)}`
            : (verification?.verification_error ?? 'Not verified')}
      </td>
    </tr>
  )
}

export default function Workspace() {
  const { workspace, settings, writePipeline } = useServices()
  const { info } = useNotification()

  const [phase, setPhase] = useState<Phase>('idle')
  const [preview, setPreview] = useState<WorkspacePreview | null>(null)
  const [batch, setBatch] = useState<WritePipelineBatch | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set())

  // Check if both product and source connectors are configured.
  const [wcConfigured, setWcConfigured] = useState<boolean | null>(null)
  const [ncConfigured, setNcConfigured] = useState<boolean | null>(null)
  const [configLoading, setConfigLoading] = useState(true)

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
    setPhase('previewing')
    setErrorMsg(null)
    try {
      const p = await workspace.startPreview('')
      setPreview(p)
      setSelectedRowIds(new Set(p.rows.filter(row => row.eligible_for_dry_run).map(row => row.id)))
      setBatch(null)
      setPhase('preview_ready')
      info(`Preview ready - ${p.totalChanges} product${p.totalChanges !== 1 ? 's' : ''} with pending price changes`)
    } catch (e) {
      setErrorMsg(workspaceErrorMessage(e, 'Failed to start preview'))
      setPhase('error')
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
      info(`Dry Run ready - ${b.itemCount} price change${b.itemCount !== 1 ? 's' : ''} validated`)
    } catch (e) {
      setErrorMsg(workspaceErrorMessage(e, 'Failed to create Dry Run'))
      setPhase('error')
    }
  }, [preview, selectedRowIds, writePipeline, info])

  const approveDryRun = useCallback(async () => {
    if (!batch) return
    setPhase('approving')
    setErrorMsg(null)
    try {
      const b = await writePipeline.approve(batch.id, 'Approved from Workspace')
      setBatch(b)
      setPhase('approved')
      info('Approved. Apply to WooCommerce still requires a separate action.')
    } catch (e) {
      setErrorMsg(workspaceErrorMessage(e, 'Failed to approve'))
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
      info('WooCommerce apply finished')
    } catch (e) {
      setErrorMsg(workspaceErrorMessage(e, 'Failed to apply to WooCommerce'))
      setPhase('error')
    }
  }, [batch, writePipeline, info])

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
      <div>
        <h1 className="fh-page-title">Workspace</h1>
        <p className="fh-page-subtitle">Preview price changes from your sources</p>
      </div>

      {/* Config loading */}
      {configLoading && (
        <div className="fh-card fh-card-pad flex items-center gap-2 text-[13px] text-wp-muted">
          <Spinner size="sm" />
          Loading configuration...
        </div>
      )}

      {/* Not configured */}
      {!configLoading && !bothConfigured && phase === 'idle' && (
        <div className="fh-card">
          {!wcConfigured && (
            <Empty
              title="Product connector required"
              description="Connect a product source from Sources to use Workspace."
              action={{ label: 'Open Sources', onClick: () => { window.location.href = '/sources' } }}
            />
          )}
          {wcConfigured && !ncConfigured && (
            <Empty
              title="Source connector required"
              description="Review connector settings before using Workspace."
              action={{ label: 'Open Settings', onClick: () => { window.location.href = '/settings' } }}
            />
          )}
        </div>
      )}

      {/* Idle - start button */}
      {!configLoading && bothConfigured && phase === 'idle' && (
        <div className="fh-card fh-card-pad flex flex-col gap-5">
          <div>
            <p className="text-[13px] text-text-base font-medium mb-1">Ready</p>
            <p className="text-[12px] text-wp-muted">
              FlowHub will fetch products from the connected channel and compare them against the
              configured source data. No changes will be applied.
            </p>
          </div>
          <button
            onClick={() => void startPreview()}
            className="fh-button-primary w-full py-3 text-[14px]"
          >
            Start Preview
          </button>
        </div>
      )}

      {/* Previewing - loading state */}
      {(phase === 'previewing' || phase === 'dry_running' || phase === 'approving' || phase === 'applying') && (
        <div className="fh-card fh-card-pad flex flex-col items-center gap-4 py-12">
          <Spinner size="lg" />
          <p className="text-[14px] font-medium text-text-base">
            {phase === 'previewing' && 'Fetching products and source data...'}
            {phase === 'dry_running' && 'Running safety checks...'}
            {phase === 'approving' && 'Recording approval...'}
            {phase === 'applying' && 'Applying approved prices to WooCommerce...'}
          </p>
          <p className="text-[12px] text-wp-muted">
            {phase === 'applying' ? 'This is the only step that writes to WooCommerce.' : 'No marketplace change is applied in this step.'}
          </p>
        </div>
      )}

      {/* Preview ready */}
      {(['preview_ready', 'dry_run_ready', 'approved', 'result'] as Phase[]).includes(phase) && preview && (
        <>
          <WorkflowSteps phase={phase} />

          <div className="fh-card fh-card-pad">
            <p className="fh-section-label mb-3">Workflow guardrails</p>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4 text-[12px] text-wp-muted">
              <p>Stock will not be changed.</p>
              <p>Automatic apply is disabled.</p>
              <p>Only approved batches can be applied.</p>
              <p>Other channels are read-only/unavailable for this workflow.</p>
            </div>
            <div className="mt-3 pt-3 border-t border-border grid gap-2 sm:grid-cols-2 xl:grid-cols-4 text-[12px] text-wp-muted">
              <p>Simple and variation WooCommerce price updates are supported.</p>
              <p>Variation rows require cached parent product metadata.</p>
              <p>Stock updates are not supported.</p>
              <p>CSV and Google Sheets are not available in 1.0.0.</p>
            </div>
          </div>

          <div className="bg-wp-yellow/10 border border-wp-yellow/30 rounded-card p-4 flex items-start gap-3">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-wp-yellow flex-shrink-0 mt-0.5">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <div>
              <p className="text-[13px] font-medium text-wp-yellow">
                {preview.summary.valid_changes + preview.summary.warning_rows} eligible row{preview.summary.valid_changes + preview.summary.warning_rows !== 1 ? 's' : ''}; {preview.summary.error_rows} blocking error{preview.summary.error_rows !== 1 ? 's' : ''}
              </p>
              <p className="text-[12px] text-wp-muted mt-0.5">
                Preview first, then run safety checks before approval. Rows with errors cannot enter Dry Run.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
            {[
              ['Rows', preview.summary.total_rows],
              ['Valid', preview.summary.valid_changes],
              ['Warnings', preview.summary.warning_rows],
              ['Unchanged', preview.summary.unchanged_rows],
              ['Errors', preview.summary.error_rows],
              ['Duplicates', preview.summary.duplicate_rows],
              ['Missing', preview.summary.missing_products],
              ['Large', preview.summary.large_changes],
            ].map(([label, value]) => (
              <div key={label} className="fh-card fh-card-pad">
                <p className="text-[11px] text-wp-muted">{label}</p>
                <p className="text-[18px] font-semibold text-text-base mt-1">{value}</p>
              </div>
            ))}
          </div>

          {batch && (
            <div className="fh-card fh-card-pad flex flex-col gap-3">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[13px] font-semibold text-text-base">
                    {phase === 'dry_run_ready' && 'Dry Run ready'}
                    {phase === 'approved' && 'Approved'}
                    {phase === 'result' && 'Result'}
                  </p>
                  <p className="text-[12px] text-wp-muted mt-1">
                    Reference {batch.id} - {batch.itemCount} price change{batch.itemCount !== 1 ? 's' : ''} for WooCommerce.
                  </p>
                </div>
                <span className="text-[11px] font-mono text-wp-muted">{batch.status}</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[12px]">
                <div>
                  <p className="text-wp-muted">Channel</p>
                  <p className="font-medium text-text-base">WooCommerce</p>
                </div>
                <div>
                  <p className="text-wp-muted">Stock</p>
                  <p className="font-medium text-text-base">Blocked</p>
                </div>
                <div>
                  <p className="text-wp-muted">Scheduler</p>
                  <p className="font-medium text-text-base">Disabled</p>
                </div>
                <div>
                  <p className="text-wp-muted">Automatic apply</p>
                  <p className="font-medium text-text-base">Disabled</p>
                </div>
              </div>
              {batch.status === 'dry_run_ready' && (
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-[12px]">
                  {[
                    ['Eligible', safetyMetric(batch, 'eligible_rows', batch.itemCount)],
                    ['Skipped', safetyMetric(batch, 'skipped_rows')],
                    ['Blocked', safetyMetric(batch, 'blocked_rows')],
                    ['Warnings', safetyMetric(batch, 'warning_rows')],
                    ['Affected', safetyMetric(batch, 'estimated_affected_products', batch.itemCount)],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-card border border-border bg-bg-base p-3">
                      <p className="text-wp-muted">{label}</p>
                      <p className="text-text-base font-semibold mt-1">{String(value)}</p>
                    </div>
                  ))}
                </div>
              )}
              {phase === 'dry_run_ready' && (
                <button onClick={() => void approveDryRun()} className="fh-button-primary self-start">
                  Approve
                </button>
              )}
              {phase === 'approved' && (
                <button onClick={() => void applyToWooCommerce()} className="fh-button-primary self-start">
                  Apply to WooCommerce
                </button>
              )}
              {phase === 'result' && (
                <div className="flex flex-col gap-4">
                  <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 text-[12px]">
                    {[
                      ['Attempted', batchMetric(batch, 'total_attempted', batch.items.length)],
                      ['Success', batchMetric(batch, 'success_count', batch.items.filter(item => item.status === 'applied').length)],
                      ['Failed', batchMetric(batch, 'failure_count', batch.items.filter(item => item.status === 'failed').length)],
                      ['Skipped', batchMetric(batch, 'skipped_count')],
                      ['Warnings', batchMetric(batch, 'warning_count')],
                      ['Verified', batchMetric(batch, 'verified_count')],
                      ['Unverified', batchMetric(batch, 'unverified_count')],
                      ['Affected', batchMetric(batch, 'estimated_affected_products', batch.itemCount)],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-card border border-border bg-bg-base p-3">
                        <p className="text-wp-muted">{label}</p>
                        <p className="text-text-base font-semibold mt-1">{String(value)}</p>
                      </div>
                    ))}
                  </div>
                  <div className="overflow-x-auto border border-border rounded-card">
                    <table className="w-full text-[13px]">
                      <thead>
                        <tr className="border-b border-border bg-bg-base">
                          {['Product', 'Old Price', 'New Price', 'Status', 'Result'].map(h => (
                            <th key={h} className="px-4 py-2.5 text-start text-[11px] font-semibold text-wp-muted uppercase tracking-wide">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {batch.items.map(item => <ResultItemRow key={item.id ?? item.productId} item={item} />)}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Duplicate warnings */}
          {(preview.duplicateWarnings ?? []).length > 0 && (
            <div className="fh-card fh-card-pad">
              <p className="fh-section-label mb-3">
                Spreadsheet Warnings ({preview.duplicateWarnings!.length})
              </p>
              {preview.duplicateWarnings!.map((w, i) => (
                <p key={i} className="text-[12px] text-wp-muted py-1 border-b border-border last:border-0">{w}</p>
              ))}
            </div>
          )}

          <div className="fh-card overflow-hidden">
            <div className="fh-panel-header">
              <span className="text-[13px] font-semibold text-text-base">
                Preview - {preview.summary.total_rows} source rows
              </span>
              <div className="flex flex-wrap items-center gap-3 text-[11px] text-wp-muted">
                <span className="font-mono">Source: {preview.sourceName}</span>
                <button type="button" onClick={() => setSelectedRowIds(new Set(eligibleRows.map(row => row.id)))} className="fh-button-secondary px-2 py-1">
                  Select all eligible
                </button>
                <button type="button" onClick={() => setSelectedRowIds(new Set())} className="fh-button-secondary px-2 py-1">
                  Deselect all
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 px-4 py-3 border-b border-border text-[12px]">
              <span>Selected: <strong>{selectedRowIds.size}</strong></span>
              <span>Eligible: <strong>{eligibleRows.length}</strong></span>
              <span>Blocked: <strong>{blockedRows}</strong></span>
              <span>Stock-only: <strong>{stockOnlyRows}</strong></span>
              <span>Estimated WooCommerce calls: <strong>{selectedRowIds.size}</strong></span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-border bg-bg-base">
                    {['Select', 'Product', 'Current Price', 'New Price', 'Change', 'Current Stock', 'Source Stock', 'Stock Change', 'Status', 'Validation'].map(h => (
                      <th key={h} className="px-4 py-2.5 text-start text-[11px] font-semibold text-wp-muted uppercase tracking-wide">{h}</th>
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

            <div className="px-[22px] py-4 border-t border-border flex items-center justify-between">
              <div className="flex items-center gap-2 text-[12px] text-wp-muted">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
                  <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
                </svg>
                Apply requires Dry Run and Approval first
              </div>
              <div className="flex items-center gap-2">
                {phase === 'preview_ready' && (
                  <button
                    onClick={() => void createDryRun()}
                    disabled={selectedRowIds.size === 0}
                    className="fh-button-primary disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Dry Run
                  </button>
                )}
                <button
                  onClick={() => void cancelPreview()}
                  className="fh-button-secondary hover:text-wp-red hover:border-wp-red"
                >
                  New Preview
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Error */}
      {phase === 'error' && (
        <div className="fh-card fh-card-pad flex flex-col gap-4">
          <div className="flex items-start gap-3 p-4 bg-wp-red/10 border border-wp-red/30 rounded-lg">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-wp-red flex-shrink-0 mt-0.5">
              <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
            </svg>
            <p className="text-[13px] text-wp-red">{errorMsg ?? 'An error occurred.'}</p>
          </div>
          <button
            onClick={() => setPhase('idle')}
            className="fh-button-secondary self-start"
          >
            Try again
          </button>
        </div>
      )}
    </PageShell>
  )
}
