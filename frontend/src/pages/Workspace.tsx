import { translate } from '../i18n'
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Badge from '../components/Badge'
import Alert from '../components/Alert'
import { useServices } from '../services/ServiceContext'
import type { WorkspacePreview, PriceChange, WorkspacePreviewRow, WorkspaceSourceBinding, WritePipelineBatch, WritePipelineItem } from '../services/types'
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
  if (error instanceof ApiError) {
    const blockedMessages: Record<string, string> = {
      SOURCE_IDENTITY_VALIDATION_PENDING: 'workspace:workspace.sourceIdentityValidationPending',
      SOURCE_IDENTITY_VALIDATION_BLOCKED: 'workspace:workspace.sourceIdentityValidationBlocked',
      SOURCE_IDENTITY_AUTHORITY_REQUIRED: 'workspace:workspace.sourceIdentityAuthorityRequired',
      SOURCE_IDENTITY_POLICY_UPGRADE_REQUIRED: 'workspace:workspace.sourceIdentityPolicyUpgradeRequired',
      SOURCE_WORKSPACE_REBIND_REQUIRED: 'workspace:workspace.sourceWorkspaceRebindRequired',
      SOURCE_WORKSPACE_BINDING_INVALID: 'workspace:workspace.sourceWorkspaceBindingInvalid',
    }
    const messageKey = blockedMessages[error.code ?? '']
    if (messageKey) return { title: translate('workspace:workspace.previewUnavailable'), description: translate(messageKey) }
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
  return <Badge variant={active ? 'pending' : done ? 'success' : 'neutral'}>{label}</Badge>
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
  const currency = ''
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

const validationLabelKeys: Record<string, string> = {
  duplicate_sku: 'workspace:workspace.validation.duplicateSku', duplicate_product_id: 'workspace:workspace.validation.duplicateProductKey',
  missing_product: 'workspace:workspace.validation.missingProduct', invalid_product_id: 'workspace:workspace.validation.invalidProductKey',
  missing_product_identifier: 'workspace:workspace.validation.missingIdentifier', invalid_price: 'workspace:workspace.validation.invalidPrice',
  invalid_or_missing_price: 'workspace:workspace.validation.invalidOrMissingPrice', missing_price: 'workspace:workspace.validation.missingPrice',
  missing_current_price: 'workspace:workspace.validation.missingCurrentPrice',
  missing_variation_parent: 'workspace:workspace.validation.missingVariationParent', missing_variation_parent_id: 'workspace:workspace.validation.missingVariationParent',
  unsupported_product_type: 'workspace:workspace.validation.unsupportedProductType', suspiciously_high_price: 'workspace:workspace.validation.suspiciouslyHighPrice',
  active_sale_price_not_modified: 'workspace:workspace.validation.activeSalePrice', large_price_change: 'workspace:workspace.validation.largePriceChange',
  large_price_change_blocked: 'workspace:workspace.validation.largePriceChangeBlocked', zero_or_negative_price: 'workspace:workspace.validation.nonPositivePrice',
  stale_product_cache: 'workspace:workspace.validation.staleCache',
}

void PreviewRow
function validationLabel(code: string): string {
  const translationKey = validationLabelKeys[code]
  return translationKey ? translate(translationKey) : code.replace(/_/g, ' ').replace(/^./, (value: string) => value.toUpperCase())
}
function ownerAction(code: string): string | null {
  if (code === 'missing_product') return translate('workspace:workspace.actions.missingProduct')
  if (code === 'duplicate_sku') return translate('workspace:workspace.actions.duplicateSku')
  if (code === 'invalid_product_id' || code === 'missing_product_identifier') return translate('workspace:workspace.actions.missingIdentifier')
  if (code.includes('price')) return translate('workspace:workspace.actions.invalidPrice')
  return null
}

function OwnerPreviewRowReadable({ row, selected, onToggle, priceUnit }: { row: WorkspacePreviewRow; selected: boolean; onToggle: (rowId: string, selected: boolean) => void; priceUnit: string }) {
  const [expanded, setExpanded] = useState(false)
  const sourceName = row.source.sourceDisplayName || row.source.productName || translate('workspace:workspace.unmatchedProduct')
  const channelName = row.matchedProduct?.name || '-'
  const sourceSku = row.source.sku || '-'
  const channelSku = row.matchedProduct?.sku || '-'
  const sourceProductKey = row.source.sourceProductKey || row.source.productId || '-'
  const isVariation = row.matchedProduct?.itemType === 'variation' || row.matchedProduct?.productType === 'variation'
  const attrs = attributeText(row.matchedProduct?.variationAttributes)
  const parentName = row.matchedProduct?.parentProductName || '-'
  const parentId = row.matchedProduct?.parentProductId || row.matchedProduct?.parentId || '-'
  const issues = [...row.errors, ...row.warnings]
  const status = row.errors.length ? 'Blocked' : row.warnings.length ? 'Warning' : row.status === 'unchanged' ? 'Unchanged' : 'Ready'
  const evidence = (code: string) => <div className={['mt-1', 'text-text-muted'].join(' ')}><div>{translate('workspace:workspace.preview.source')}: {sourceName}</div>{(code === 'invalid_price' || code === 'invalid_or_missing_price' || code === 'missing_price') && <div>{translate('workspace:workspace.preview.sourceValue')}: {row.source.rawPrice || '-'}</div>}{ownerAction(code) && <div>{translate('workspace:workspace.preview.action')}: {ownerAction(code)}</div>}</div>
  return <Fragment>
    <tr className="border-b border-border hover:bg-bg-base/60 transition-colors align-top">
      <td className="w-16 px-4 py-3 text-center align-top"><input type="checkbox" aria-label={translate('workspace:workspace.selectProduct', { product: sourceName })} checked={selected} disabled={!row.eligible_for_dry_run} onChange={event => onToggle(row.id, event.target.checked)} /></td>
      <td className="min-w-[320px] px-4 py-3 align-top"><div className="flex items-start gap-3"><div className="h-11 w-11 shrink-0 overflow-hidden rounded bg-bg-subtle">{row.matchedProduct?.imageUrl ? <img loading="lazy" src={row.matchedProduct.imageUrl} alt="" className="h-full w-full object-cover" /> : <div aria-hidden="true" className="h-full w-full" />}</div><div className="min-w-0 space-y-1.5"><div className="fh-text-caption text-text-muted">{translate('workspace:workspace.preview.sourceLabel')}</div><LocalizedText className="block whitespace-normal break-words fh-text-body font-medium text-text-base" text={sourceName} /><div className="fh-text-caption fh-text-mono" dir="ltr">{translate('workspace:workspace.preview.sku')}: {sourceSku}</div><div className="fh-text-caption fh-text-mono" dir="ltr">{translate('workspace:workspace.preview.sourceProductKey')}: {sourceProductKey}</div><div className="fh-text-caption fh-text-mono" dir="ltr">{translate('workspace:workspace.preview.sourceRow')}: {row.source.worksheet}:{row.source.rowNumber}</div>{isVariation && <div className="space-y-1 pt-1"><div className="fh-text-caption font-semibold">{translate('workspace:workspace.preview.variation')}</div><LocalizedText className="block whitespace-normal break-words fh-text-caption" text={attrs || '-'} /><div className="fh-text-caption pt-1 font-semibold">{translate('workspace:workspace.preview.parent')}</div><LocalizedText className="block whitespace-normal break-words fh-text-caption" text={parentName} /><div className="fh-text-caption fh-text-mono" dir="ltr">{translate('workspace:workspace.preview.productId')}: {parentId}</div></div>}</div></div></td>
      <td className="min-w-[240px] px-4 py-3 align-top"><div className="fh-text-caption text-text-muted">{translate('workspace:workspace.preview.currentWooCommerce')}</div><LocalizedText className="block whitespace-normal break-words fh-text-body-sm font-medium" text={channelName} /><div className="mt-1 space-y-0.5 fh-text-caption fh-text-mono" dir="ltr"><div>{translate('workspace:workspace.preview.productId')}: {row.matchedProduct?.productId || '-'}</div><div>{translate('workspace:workspace.preview.sku')}: {channelSku}</div></div><div className="mt-2" dir="ltr">{row.currentPrice == null ? '-' : fmtPrice(row.currentPrice, priceUnit)}</div></td>
      <td className="min-w-[170px] px-4 py-3 align-top"><div className="fh-text-caption text-text-muted">{translate('workspace:workspace.preview.sourceChange')}</div><div dir="ltr">{row.proposedPrice == null ? row.source.rawPrice || '-' : fmtPrice(row.proposedPrice, priceUnit)}</div><div>{row.changePct == null ? '-' : <ChangePct pct={row.changePct} />}</div>{row.status === 'stock_changed' && <div className="mt-1 whitespace-normal fh-text-caption">{translate('workspace:workspace.preview.stockOnly')}: {row.currentStock ?? '-'} → {row.sourceStock ?? row.source.rawStock ?? '-'} ({row.stockDifference != null ? formatNumber(row.stockDifference, { signDisplay: 'always' }) : '-'})</div>}</td>
      <td className="w-36 min-w-[140px] px-4 py-3 align-top"><div className="fh-text-caption text-text-muted">{translate('workspace:workspace.preview.status')}</div><Badge variant={status === 'Ready' ? 'success' : status === 'Warning' ? 'warning' : status === 'Unchanged' ? 'neutral' : 'danger'}>{translate(`workspace:workspace.preview.statuses.${status.toLowerCase()}`)}{issues.length ? ` · ${translate('workspace:workspace.preview.issueCount', { count: issues.length })}` : ''}</Badge><button type="button" className="mt-2 block fh-text-caption underline" onClick={() => setExpanded(value => !value)} aria-expanded={expanded}>{expanded ? translate('workspace:workspace.preview.hideDetails') : translate('workspace:workspace.preview.viewDetails')}</button></td>
    </tr>
    {expanded && <tr className="border-b border-border bg-bg-subtle"><td colSpan={5} className="px-6 py-4"><div className="grid gap-4 md:grid-cols-3 fh-text-caption"><div><p className="font-semibold text-text-base">{translate('workspace:workspace.preview.blockingIssues')}</p>{row.errors.length ? row.errors.map(code => <div key={code} className="mt-2"><div>{validationLabel(code)}</div>{evidence(code)}</div>) : <p className="mt-1 text-text-muted">{translate('workspace:workspace.preview.none')}</p>}</div><div><p className="font-semibold text-text-base">{translate('workspace:workspace.preview.warnings')}</p>{row.warnings.length ? row.warnings.map(code => <div key={code} className="mt-2"><div>{validationLabel(code)}</div>{evidence(code)}</div>) : <p className="mt-1 text-text-muted">{translate('workspace:workspace.preview.none')}</p>}</div><details><summary className="font-semibold cursor-pointer text-text-base">{translate('workspace:workspace.preview.technicalDetails')}</summary><p className="mt-1 font-mono break-all">{translate('workspace:workspace.preview.codes')}: {issues.join(', ') || translate('workspace:workspace.preview.none')}<br />{translate('workspace:workspace.preview.sourceRow')}: {row.source.worksheet}:{row.source.rowNumber}<br />{translate('workspace:workspace.preview.snapshot')}: {row.source.sourceSnapshotId}</p></details></div></td></tr>}
  </Fragment>
}

export function OwnerPreviewRow({ row, selected, onToggle }: { row: WorkspacePreviewRow; selected: boolean; onToggle: (rowId: string, selected: boolean) => void }) {
  const [expanded, setExpanded] = useState(false)
  const sourceName = row.source.sourceDisplayName || row.source.productName || translate('workspace:workspace.unmatchedProduct')
  const channelName = row.matchedProduct?.name || '-'
  const sku = row.source.sku || row.matchedProduct?.sku || '-'
  const attrs = attributeText(row.matchedProduct?.variationAttributes)
  const currency = ''
  const issues = [...row.errors, ...row.warnings]
  const status = row.errors.length ? 'Blocked' : row.warnings.length ? 'Warning' : row.status === 'unchanged' ? 'Unchanged' : 'Ready'
  return <Fragment>
    <tr className="border-b border-border hover:bg-bg-base/60 transition-colors align-top">
      <td className="px-4 py-3 text-center"><input type="checkbox" aria-label={translate('workspace:workspace.selectProduct', { product: sourceName })} checked={selected} disabled={!row.eligible_for_dry_run} onChange={event => onToggle(row.id, event.target.checked)} /></td>
      <td className="px-4 py-3 min-w-0 max-w-[300px]"><div className="flex items-start gap-2">{row.matchedProduct?.imageUrl ? <img loading="lazy" src={row.matchedProduct.imageUrl} alt="" className="h-10 w-10 shrink-0 rounded object-cover bg-bg-subtle" /> : <div aria-hidden="true" className="h-10 w-10 shrink-0 rounded bg-bg-subtle" />}<div className="min-w-0"><div className="fh-text-caption text-text-muted">{translate('workspace:workspace.preview.sourceLabel')}</div><LocalizedText className="block truncate fh-text-body font-medium text-text-base" text={sourceName} /><div className="fh-text-caption fh-text-mono mt-0.5">{translate('workspace:workspace.preview.sku')}: {sku} · {row.source.worksheet}:{row.source.rowNumber}</div>{(row.source.sourceProductKey || row.source.productId) && <div className="fh-text-caption fh-text-mono">{translate('workspace:workspace.preview.sourceProductKey')}: {row.source.sourceProductKey || row.source.productId}</div>}</div></div>{row.matchedProduct?.itemType === 'variation' && <div className="fh-text-caption mt-1 truncate">{translate('workspace:workspace.preview.variation')} · <LocalizedText text={attrs || '-'} /> · {translate('workspace:workspace.preview.parent')} {row.matchedProduct.parentProductId || row.matchedProduct.parentId || '-'}{row.matchedProduct.parentProductName ? <> · <LocalizedText text={row.matchedProduct.parentProductName} /></> : null}</div>}</td>
      <td className="px-4 py-3 min-w-[220px]"><div className="fh-text-caption text-text-muted">{translate('workspace:workspace.preview.currentWooCommerce')}</div><LocalizedText className="block truncate fh-text-body-sm font-medium" text={channelName} /><div className="fh-text-caption fh-text-mono">{translate('workspace:workspace.preview.productId')}: {row.matchedProduct?.productId || '-'} · {translate('workspace:workspace.preview.sku')}: {row.matchedProduct?.sku || '-'}</div>{row.currentPrice == null ? '-' : fmtPrice(row.currentPrice, currency)}</td>
      <td className="px-4 py-3 min-w-[150px]"><div className="fh-text-caption text-text-muted">{translate('workspace:workspace.preview.sourceChange')}</div>{row.proposedPrice == null ? row.source.rawPrice || '-' : fmtPrice(row.proposedPrice, currency)}<div>{row.changePct == null ? '-' : <ChangePct pct={row.changePct} />}</div>{row.status === 'stock_changed' && <div className="fh-text-caption">{translate('workspace:workspace.preview.stockOnly')} · {row.currentStock ?? '-'} → {row.sourceStock ?? row.source.rawStock ?? '-'} ({row.stockDifference != null ? formatNumber(row.stockDifference, { signDisplay: 'always' }) : '-'})</div>}</td>
      <td className="px-4 py-3 min-w-[140px]"><div className="fh-text-caption text-text-muted">{translate('workspace:workspace.preview.status')}</div><Badge variant={status === 'Ready' ? 'success' : status === 'Warning' ? 'warning' : status === 'Unchanged' ? 'neutral' : 'danger'}>{translate(`workspace:workspace.preview.statuses.${status.toLowerCase()}`)}{issues.length ? ` · ${translate('workspace:workspace.preview.issueCount', { count: issues.length })}` : ''}</Badge><button type="button" className="mt-2 block fh-text-caption underline" onClick={() => setExpanded(value => !value)} aria-expanded={expanded}>{expanded ? translate('workspace:workspace.preview.hideDetails') : translate('workspace:workspace.preview.viewDetails')}</button><span className="sr-only">{issues.join(', ')}</span></td>
    </tr>
    {expanded && <tr className="border-b border-border bg-bg-subtle"><td colSpan={5} className="px-6 py-4"><div className="grid gap-4 md:grid-cols-3 fh-text-caption"><div><p className="font-semibold text-text-base">{translate('workspace:workspace.preview.blockingIssues')}</p>{row.errors.length ? row.errors.map(code => <p key={code} className="mt-1">{validationLabel(code)}{ownerAction(code) && <span className="block text-text-muted">{translate('workspace:workspace.preview.action')}: {ownerAction(code)}</span>}</p>) : <p className="mt-1 text-text-muted">{translate('workspace:workspace.preview.none')}</p>}</div><div><p className="font-semibold text-text-base">{translate('workspace:workspace.preview.warnings')}</p>{row.warnings.length ? row.warnings.map(code => <p key={code} className="mt-1">{validationLabel(code)}</p>) : <p className="mt-1 text-text-muted">{translate('workspace:workspace.preview.none')}</p>}</div><details><summary className="font-semibold cursor-pointer text-text-base">{translate('workspace:workspace.preview.technicalDetails')}</summary><p className="mt-1 font-mono break-all">{translate('workspace:workspace.preview.codes')}: {issues.join(', ') || translate('workspace:workspace.preview.none')}<br />{translate('workspace:workspace.preview.sourceRow')}: {row.source.worksheet}:{row.source.rowNumber}<br />{translate('workspace:workspace.preview.snapshot')}: {row.source.sourceSnapshotId}</p></details></div></td></tr>}
  </Fragment>
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
  const [previewSearch, setPreviewSearch] = useState('')
  const [previewFilter, setPreviewFilter] = useState('all')
  const [previewPage, setPreviewPage] = useState(1)

  // Check if both product and source connectors are configured.
  const [wcConfigured, setWcConfigured] = useState<boolean | null>(null)
  const [ncConfigured, setNcConfigured] = useState<boolean | null>(null)
  const [priceUnit, setPriceUnit] = useState('EUR')
  const [configLoading, setConfigLoading] = useState(true)
  const [sourceBinding, setSourceBinding] = useState<WorkspaceSourceBinding | null>(null)
  const [sourceBindingLoading, setSourceBindingLoading] = useState(true)
  const [sourceBindingError, setSourceBindingError] = useState<string | null>(null)
  const [selectedSourceId, setSelectedSourceId] = useState('')
  const [bindingSaving, setBindingSaving] = useState(false)
  const [sourceRebindRequired, setSourceRebindRequired] = useState(false)
  const previousBoundSourceId = useRef<string | null>(null)
  const previewRequestInFlight = useRef(false)

  useEffect(() => {
    settings.getSettings()
      .then(s => {
        setWcConfigured(s.wcConfigured ?? false)
        setNcConfigured(s.ncConfigured ?? false)
        setPriceUnit(s.currencyUnit || s.currency || 'EUR')
      })
      .catch(() => {
        setWcConfigured(false)
        setNcConfigured(false)
      })
      .finally(() => setConfigLoading(false))
  }, [settings])

  const loadSourceBinding = useCallback(async () => {
    setSourceBindingLoading(true)
    setSourceBindingError(null)
    try {
      const binding = await workspace.getSourceBinding()
      setSourceBinding(binding)
      setSelectedSourceId(binding.boundSource?.status === 'active' ? binding.boundSource.sourceId : '')
      if (binding.boundSource) {
        previousBoundSourceId.current = binding.boundSource.sourceId
        setSourceRebindRequired(binding.boundSource.status !== 'active')
      } else {
        setSourceRebindRequired(previousBoundSourceId.current !== null)
      }
    } catch (error) {
      setSourceBinding(null)
      setSelectedSourceId('')
      setSourceBindingError(localizedApiError(error, 'errors:codes.UNKNOWN'))
    } finally {
      setSourceBindingLoading(false)
    }
  }, [workspace])

  useEffect(() => {
    void loadSourceBinding()
  }, [loadSourceBinding])

  const bindSource = useCallback(async () => {
    if (!selectedSourceId || bindingSaving) return
    setBindingSaving(true)
    setSourceBindingError(null)
    try {
      const boundSource = await workspace.bindSource(selectedSourceId)
      setSourceBinding(current => ({
        boundSource,
        candidates: current?.candidates ?? [],
      }))
      previousBoundSourceId.current = boundSource.sourceId
      setSourceRebindRequired(false)
      setSelectedSourceId(boundSource.sourceId)
    } catch (error) {
      setSourceBindingError(localizedApiError(error, 'errors:codes.UNKNOWN'))
    } finally {
      setBindingSaving(false)
    }
  }, [bindingSaving, selectedSourceId, workspace])

  const activeBoundSource = sourceBinding?.boundSource?.status === 'active'
    ? sourceBinding.boundSource
    : null
  const bindingReady = activeBoundSource !== null

  const startPreview = useCallback(async () => {
    if (previewRequestInFlight.current || !activeBoundSource) return
    previewRequestInFlight.current = true
    setPhase('previewing')
    setErrorTitle(null)
    setErrorMsg(null)
    setCacheEmptyError(false)
    try {
      const p = await workspace.startPreview(activeBoundSource.sourceId)
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
      if (e instanceof ApiError && (
        e.code === 'SOURCE_WORKSPACE_REBIND_REQUIRED'
        || e.code === 'SOURCE_WORKSPACE_BINDING_INVALID'
      )) {
        setSourceRebindRequired(true)
        await loadSourceBinding()
        setPhase('idle')
      } else {
        setPhase('error')
      }
    } finally {
      previewRequestInFlight.current = false
    }
  }, [activeBoundSource, info, loadSourceBinding, workspace])

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
  const pageLoading = configLoading || sourceBindingLoading
  const eligibleRows = preview?.rows.filter(row => row.eligible_for_dry_run) ?? []
  const blockedRows = preview?.rows.filter(row => row.errors.length > 0).length ?? 0
  const stockOnlyRows = preview?.rows.filter(row => row.status === 'stock_changed').length ?? 0
  const filteredPreviewRows = useMemo(() => {
    if (!preview) return []
    const query = previewSearch.trim().toLocaleLowerCase()
    return preview.rows.filter(row => {
      const haystack = [row.source.sourceDisplayName, row.source.productName, row.source.sku, row.source.productId, row.matchedProduct?.name, row.matchedProduct?.productId, row.matchedProduct?.sku].filter(Boolean).join(' ').toLocaleLowerCase()
      const matchesSearch = !query || haystack.includes(query)
      const matchesFilter = previewFilter === 'all' || (previewFilter === 'ready' && row.eligible_for_dry_run && !row.errors.length && !row.warnings.length) || (previewFilter === 'blocked' && row.errors.length > 0) || (previewFilter === 'warnings' && row.warnings.length > 0) || (previewFilter === 'unchanged' && row.status === 'unchanged') || (previewFilter === 'missing_product' && row.errors.includes('missing_product')) || (previewFilter === 'duplicate_sku' && row.errors.includes('duplicate_sku')) || (previewFilter === 'price' && row.errors.some(code => code.includes('price'))) || (previewFilter === 'variation' && row.matchedProduct?.itemType === 'variation')
      return matchesSearch && matchesFilter
    })
  }, [preview, previewFilter, previewSearch])
  const previewPageSize = 50
  const visiblePreviewRows = filteredPreviewRows.slice((previewPage - 1) * previewPageSize, previewPage * previewPageSize)
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
      {pageLoading && (
        <div className="fh-card fh-card-pad flex items-center gap-2 fh-text-body-sm">
          <Spinner size="sm" />
          {translate('workspace:workspace.loadingConfiguration')}
        </div>
      )}

      {/* Not configured */}
      {!pageLoading && !bothConfigured && phase === "idle" && (
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
      {!pageLoading && bothConfigured && phase === "idle" && (
        <div className="fh-card fh-card-pad flex flex-col gap-5">
          {!bindingReady && (
            <Alert
              variant="warning"
              title={sourceRebindRequired || sourceBinding?.boundSource ? translate('workspace:workspace.sourceRebindRequired') : translate('workspace:workspace.sourceBindingRequired')}
              message={sourceRebindRequired || sourceBinding?.boundSource
                ? translate('workspace:workspace.sourceBindingInactive')
                : translate('workspace:workspace.sourceBindingDescription')}
            />
          )}
          {bindingReady && (
            <div>
              <p className="fh-section-title">{translate('workspace:statusDisplay.ready')}</p>
              <p className="fh-section-subtitle mt-1">
                {translate('workspace:workspace.flowhubWillFetchProductsFromTheConnected')}
              </p>
            </div>
          )}
          <div className="flex flex-col gap-3">
            <label className="fh-field-label" htmlFor="workspace-source-binding">
              {translate('workspace:workspace.workspaceSource')}
              <select
                id="workspace-source-binding"
                aria-label={translate('workspace:workspace.workspaceSource')}
                className="fh-input mt-1"
                value={selectedSourceId}
                onChange={event => setSelectedSourceId(event.target.value)}
                disabled={bindingSaving}
              >
                <option value="">{translate('workspace:workspace.selectActiveSource')}</option>
                {(sourceBinding?.candidates ?? []).map(candidate => (
                  <option key={candidate.sourceId} value={candidate.sourceId}>
                    {candidate.sourceName}
                  </option>
                ))}
              </select>
            </label>
            {sourceBindingError && (
              <Alert
                variant="error"
                title={translate('workspace:workspace.previewUnavailable')}
                message={sourceBindingError}
              />
            )}
            {!sourceBindingError && (sourceBinding?.candidates.length ?? 0) === 0 && !bindingReady && (
              <p className="fh-text-caption">{translate('workspace:workspace.noActiveSourceCandidate')}</p>
            )}
            <button
              type="button"
              onClick={() => void bindSource()}
              disabled={!selectedSourceId || bindingSaving}
              className="fh-button-secondary self-start disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {bindingReady ? translate('workspace:workspace.rebindSource') : translate('workspace:workspace.bindSource')}
            </button>
          </div>
          <button
            onClick={() => void startPreview()}
            disabled={!bindingReady}
            className="fh-button-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
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

          <Alert
            variant="warning"
            title={`${preview.summary.valid_changes + preview.summary.warning_rows} ${translate('workspace:workspace.eligibleRow')}${preview.summary.valid_changes + preview.summary.warning_rows !== 1 ? 's' : ''}; ${preview.summary.error_rows} ${translate('workspace:workspace.blockingError')}${preview.summary.error_rows !== 1 ? 's' : ''}`}
            message={translate('workspace:workspace.previewFirstThenRunSafetyChecksBefore')}
          />

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="fh-section-title">{translate('dataQuality:dataQuality.summary')}</h2>
              <p className="fh-text-caption">{translate('dataQuality:dataQuality.summaryFirstDescription')}</p>
            </div>
            <a className="fh-button-secondary" href="/data-quality"><Icon name="alert" /> {translate('workspace:workspace.openDataQualityReport')}</a>
          </div>
          <div className="fh-stat-grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8">
            {[
              [translate('workspace:workspace.preview.summary.sourceRows'), preview.summary.total_rows],
              [translate('workspace:workspace.preview.summary.ready'), preview.summary.valid_changes],
              [translate('workspace:workspace.preview.summary.blockedRows'), preview.summary.blocked_rows ?? preview.summary.error_rows],
              [translate('workspace:workspace.preview.summary.blockingIssues'), preview.rows.reduce((count, row) => count + row.errors.length, 0)],
              [translate('workspace:workspace.preview.summary.warnings'), preview.summary.warning_rows],
              [translate('workspace:workspace.preview.summary.missingProducts'), preview.summary.missing_products],
              [translate('workspace:workspace.preview.summary.duplicates'), preview.summary.duplicate_rows],
              [translate('workspace:workspace.preview.summary.unchanged'), preview.summary.unchanged_rows],
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
            <details className="fh-card fh-card-pad">
              <summary className="fh-section-label cursor-pointer">
                {translate('workspace:workspace.spreadsheetWarnings')}{preview.duplicateWarnings!.length})
              </summary>
              <div className="mt-3">{preview.duplicateWarnings!.map((w, i) => (
                <p key={i} className="fh-text-caption py-1 border-b border-border last:border-0">{w}</p>
              ))}</div>
            </details>
          )}

          <div className="fh-card overflow-hidden">
            <div className="fh-panel-header">
              <div>
                <span className="fh-section-title">
                {translate('workspace:workspace.preview2')} {preview.summary.total_rows} {translate('workspace:workspace.sourceRows')}
                </span>
              <p className="fh-text-caption mt-1">{translate('workspace:workspace.preview.ownerViewDescription')}</p>
              </div>
              <div className="flex flex-wrap items-center gap-3 fh-text-caption">
                <span>
                  <span className="font-mono">{translate('workspace:workspace.source')} </span>
                  <LocalizedText text={preview.sourceName} />
                </span>
                <span className="fh-text-caption">{translate('workspace:workspace.preview.context', { file: preview.sourceContext?.filePath || preview.rows[0]?.source.sourceFilePath || '-', worksheet: preview.sourceContext?.worksheet || preview.rows[0]?.source.worksheet || '-', rows: preview.sourceContext?.rowsRead ?? preview.summary.total_rows, revision: preview.sourceContext?.mappingRevision ?? translate('workspace:workspace.preview.unavailable') })}</span>
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

            <div className="grid gap-3 border-b border-border bg-bg-subtle px-4 py-3 md:grid-cols-[minmax(220px,1fr)_180px_auto]">
              <label className="sr-only" htmlFor="workspace-preview-search">{translate('workspace:workspace.preview.searchLabel')}</label><input id="workspace-preview-search" className="fh-input" aria-label={translate('workspace:workspace.preview.searchLabel')} value={previewSearch} onChange={event => { setPreviewSearch(event.target.value); setPreviewPage(1) }} />
              <select className="fh-input" aria-label={translate('workspace:workspace.preview.filterLabel')} value={previewFilter} onChange={event => { setPreviewFilter(event.target.value); setPreviewPage(1) }}><option value="all">{translate('workspace:workspace.preview.filters.all')}</option><option value="ready">{translate('workspace:workspace.preview.filters.ready')}</option><option value="blocked">{translate('workspace:workspace.preview.filters.blocked')}</option><option value="warnings">{translate('workspace:workspace.preview.filters.warnings')}</option><option value="unchanged">{translate('workspace:workspace.preview.filters.unchanged')}</option><option value="missing_product">{translate('workspace:workspace.preview.filters.missingProduct')}</option><option value="duplicate_sku">{translate('workspace:workspace.preview.filters.duplicateSku')}</option><option value="price">{translate('workspace:workspace.preview.filters.price')}</option><option value="mismatch">{translate('workspace:workspace.preview.filters.mismatch')}</option><option value="variation">{translate('workspace:workspace.preview.filters.variations')}</option></select>
              <span className="self-center fh-text-caption">{translate('workspace:workspace.preview.showing', { visible: visiblePreviewRows.length, total: filteredPreviewRows.length })}</span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 px-4 py-3 border-b border-border bg-bg-subtle fh-text-caption">
              <span>{translate('workspace:workspace.selected')} <strong>{selectedRowIds.size}</strong></span>
              <span>{translate('workspace:workspace.eligible')} <strong>{eligibleRows.length}</strong></span>
              <span>{translate('workspace:workspace.blocked')} <strong>{blockedRows}</strong></span>
              <span>{translate('workspace:workspace.stockOnly')} <strong>{stockOnlyRows}</strong></span>
              <span>{translate('workspace:workspace.estimatedWoocommerceCalls')} <strong>{selectedRowIds.size}</strong></span>
            </div>

            {filteredPreviewRows.length > previewPageSize && <div className="fh-panel-footer !justify-center gap-3"><button type="button" className="fh-button-secondary" disabled={previewPage === 1} onClick={() => setPreviewPage(page => page - 1)}>{translate('workspace:workspace.preview.previous')}</button><span className="fh-text-caption">{translate('workspace:workspace.preview.page', { page: previewPage, pages: Math.ceil(filteredPreviewRows.length / previewPageSize) })}</span><button type="button" className="fh-button-secondary" disabled={previewPage >= Math.ceil(filteredPreviewRows.length / previewPageSize)} onClick={() => setPreviewPage(page => page + 1)}>{translate('workspace:workspace.preview.next')}</button></div>}

            <div className="overflow-x-auto">
              <table className="fh-table fh-table-compact min-w-[920px]">
                <thead>
                  <tr>
                    {[translate('workspace:gridModel.select'), translate('workspace:workspace.preview.productIdentity'), translate('workspace:workspace.preview.currentWooCommerce'), translate('workspace:workspace.preview.sourceChange'), translate('workspace:workspace.preview.status')].map((h, index) => (
                      <th key={h} className={index === 0 ? 'w-16 text-center' : undefined}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.length > 0
                    ? visiblePreviewRows.map(row => (
                        <OwnerPreviewRowReadable key={row.id} row={row} selected={selectedRowIds.has(row.id)} onToggle={toggleRow} priceUnit={priceUnit} />
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
          <Alert
            variant="error"
            title={errorTitle ?? "An error occurred"}
            message={errorMsg ?? "Please try again."}
          />
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
