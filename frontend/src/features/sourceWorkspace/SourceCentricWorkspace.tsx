import { translate } from '../../i18n'
import { formatNumber } from '../../i18n/format'
import { localizedApiError } from '../../i18n/errors'
import { formatField, formatStatus } from '../../i18n/display'
import { useCallback, useEffect, useMemo, useState } from 'react'
import PageShell from '../../components/PageShell'
import Icon from '../../components/Icon'
import { ResourceStateBadge } from '../../components/ResourceOrdering'
import { useNotification } from '../../notifications/NotificationProvider'
import type { UnifiedWorkspaceService } from '../../services/unifiedWorkspace/UnifiedWorkspaceService'
import type { ApplyResource, DraftChangeInput, ReviewResource, UnifiedWorkspaceResource } from '../../services/unifiedWorkspace/types'
import { formatChannelDisplayName } from '../unifiedWorkspace/channelDisplayName'
import {
  channelIdentitySignals,
  orderRelatedItems,
  prepareResourceCollection,
} from '../resourceOrdering/resourceOrdering'
import { workspaceApplyIdempotencyKey } from '../unifiedWorkspace/useUnifiedWorkspaceController'
import { sourceWorkspaceApi } from './api'
import type { GroupedWorkspacePage } from './types'

type View = 'changed' | 'ready' | 'blocked' | 'unchanged' | 'all'

function orderedItemsByChannel<T extends { channelId: string }>(items: readonly T[]): Array<T & { resourceBadge: 'configured' | 'healthy' | 'warning' | 'disabled' | 'comingSoon' }> {
  const channels = [...new Set(items.map(item => item.channelId))].map(channelId => ({ channelId }))
  const resources = prepareResourceCollection(channels, item => channelIdentitySignals(item))
  const badges = new Map(resources.ordered.map(resource => [resource.id, resource.badge]))
  return orderRelatedItems(items, resources, item => item.channelId)
    .map(item => ({ ...item, resourceBadge: badges.get(item.channelId) ?? 'configured' }))
}

export default function SourceCentricWorkspace({ workspace, service }: { workspace: UnifiedWorkspaceResource; service: UnifiedWorkspaceService }) {
  const notify = useNotification()
  const [grid, setGrid] = useState<GroupedWorkspacePage | null>(null)
  const [page, setPage] = useState(1)
  const [view, setView] = useState<View>(() => workspace.entryPoint === 'manual' ? 'all' : 'changed')
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [changes, setChanges] = useState<Map<string, DraftChangeInput>>(new Map())
  const [busy, setBusy] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [applyResult, setApplyResult] = useState<ApplyResource | null>(null)
  const [review, setReview] = useState<ReviewResource | null>(null)

  const load = useCallback(() => sourceWorkspaceApi.groupedGrid(workspace.id, page, view, search).then(result => {
    setGrid(result)
    setExpanded(current => current.size ? current : new Set(result.items.filter(item => item.state !== 'unchanged').slice(0, 5).map(item => item.sourceProductId)))
  }), [workspace.id, page, view, search])
  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const cleanup: Array<() => void> = []
    const fieldNames = ['price', 'stock', 'status'] as const
    const inputs = Array.from(document.querySelectorAll<HTMLInputElement>('[data-listing-id] input.fh-input'))
    for (const input of inputs) {
      const container = input.closest<HTMLElement>('[data-listing-id]')
      if (!container) continue
      const field = fieldNames[Array.from(container.querySelectorAll('input.fh-input')).indexOf(input)]
      if (!field) continue
      input.dataset.targetField = field
      const onKeyDown = (event: KeyboardEvent) => {
        if (event.key === 'Escape') { input.blur(); return }
        if (event.key !== 'Enter') return
        event.preventDefault()
        const sameField = Array.from(document.querySelectorAll<HTMLInputElement>('input[data-target-field="' + field + '"]'))
        sameField[sameField.indexOf(input) + 1]?.focus()
      }
      const onPaste = (event: ClipboardEvent) => {
        const values = event.clipboardData?.getData('text/plain').split(/\r?\n/).map(value => value.trim()).filter(Boolean) ?? []
        if (values.length < 2) return
        event.preventDefault()
        const sameField = Array.from(document.querySelectorAll<HTMLInputElement>('input[data-target-field="' + field + '"]'))
        const start = sameField.indexOf(input)
        values.forEach((value, offset) => {
          const target = sameField[start + offset]
          const listingId = target?.dataset.listingId
          const resolved = listingId ? listingForId(listingId) : null
          if (!target || target.disabled || !resolved || !listingId) return
          const cell = resolved.listing.fields[field]
          edit(resolved.product.sourceProductId, listingId, resolved.listing.channelId, field, value, cell.currency, cell.unit)
        })
      }
      input.addEventListener('keydown', onKeyDown)
      input.addEventListener('paste', onPaste)
      cleanup.push(() => { input.removeEventListener('keydown', onKeyDown); input.removeEventListener('paste', onPaste) })
    }
    return () => cleanup.forEach(dispose => dispose())
  }, [expanded, grid])
  const dirty = changes.size
  const pageCount = Math.max(1, Math.ceil((grid?.total ?? 0) / 100))
  const selectedCount = grid?.summary.selected ?? 0

  function edit(productId: string, listingId: string, channelId: string, field: 'price' | 'stock' | 'status', value: string, currency: string | null, unit: string | null) {
    setChanges(current => {
      const next = new Map(current)
      next.set(`${listingId}:${field}`, { canonical_product_id: productId, listing_id: listingId, channel_id: channelId, field, target_value: value, currency, unit })
      return next
    })
  }
  function listingForId(listingId: string) {
    for (const product of grid?.items ?? []) {
      const listing = product.children.find(item => item.listingId === listingId)
      if (listing) return { product, listing }
    }
    return null
  }
  async function saveAndReview() {
    if (!grid || !dirty) return
    setBusy(translate('workspace:sourceCentricWorkspace.savingDraft'))
    try {
      const revision = await service.saveDraft(workspace.id, grid.draftVersion, [...changes.values()])
      const review = await service.createReview(workspace.id, revision.id)
      const eligible = review.items.filter(item => item.eligible).map(item => item.id)
      if (eligible.length) await service.saveSelection(workspace.id, review.id, eligible)
      setReview(review)
      setChanges(new Map()); await load()
      notify.success({ title: translate('workspace:sourceCentricWorkspace.reviewAndDryRunComplete'), description: translate('workspace:sourceCentricWorkspace.eligibleChangesWereAutomaticallySelectedBlockedItems', { value1: eligible.length }) })
    } catch (error) { notify.error({ title: translate('workspace:sourceCentricWorkspace.reviewCouldNotBeCompleted'), description: localizedApiError(error, 'workspace:sourceCentricWorkspace.checkDataQualityIssues') }) }
    finally { setBusy(null) }
  }
  async function apply() {
    if (!grid?.reviewId || !grid.selectionChecksum || !grid.revisionId) return
    setBusy(translate('workspace:sourceCentricWorkspace.applyingSelectedListings'))
    try {
      const key = await workspaceApplyIdempotencyKey(workspace.id, grid.reviewId, grid.revisionId, grid.selectionChecksum)
      const result = await service.applySelected(workspace.id, grid.reviewId, grid.selectionChecksum, key)
      setApplyResult(result); setConfirming(false); await load()
    } catch (error) { notify.error({ title: translate('workspace:sourceCentricWorkspace.applyWasBlocked'), description: localizedApiError(error, 'workspace:sourceCentricWorkspace.generateAFreshReview') }) }
    finally { setBusy(null) }
  }
  async function toggleListingSelection(listingId: string, selected: boolean) {
    if (!grid?.reviewId) return
    setBusy(translate('workspace:sourceCentricWorkspace.updatingSelectedChanges'))
    try {
      const review = await sourceWorkspaceApi.review(workspace.id, grid.reviewId)
      const selectedIds = new Set(review.items.filter(item => item.selected).map(item => item.id))
      const listingItems = review.items.filter(item => item.listingId === listingId && item.eligible)
      for (const item of listingItems) {
        if (selected) selectedIds.add(item.id)
        else selectedIds.delete(item.id)
      }
      if (!selectedIds.size) {
        notify.warning({ title: translate('workspace:sourceCentricWorkspace.keepOneSelectedChange'), description: translate('workspace:sourceCentricWorkspace.applyRemainsDisabledUnlessAtLeastOne') })
        return
      }
      await service.saveSelection(workspace.id, grid.reviewId, [...selectedIds])
      await load()
    } catch (error) { notify.error({ title: translate('workspace:sourceCentricWorkspace.selectionWasNotSaved'), description: localizedApiError(error, 'workspace:sourceCentricWorkspace.generateAFreshReview') }) }
    finally { setBusy(null) }
  }
  const summary = useMemo(() => grid?.summary ?? { ready: 0, blocked: 0, unchanged: 0, selected: 0 }, [grid])
  // i18n-ignore
  const reviewSummary = review && grid ? <section className="fh-card mt-4" aria-label={translate('workspace:unifiedWorkspace.reviewChanges')}><div className="fh-panel-header"><div><h2 className="fh-section-title">{translate('workspace:unifiedWorkspace.reviewChanges')}</h2><p className="fh-text-caption">{review.summary.total} {translate('workspace:sourceCentricWorkspace.readyChanges')} · {review.summary.eligible} {translate('workspace:sourceCentricWorkspace.selected')}</p></div><span className={`fh-status-label fh-status-${review.status}`}><Icon name={review.status === 'ready' ? 'success' : 'warning'} /> {formatStatus(review.status)}</span></div><div className="overflow-x-auto"><table className="min-w-full text-sm"><thead><tr className="border-b border-border"><th className="p-3 text-start">{translate('workspace:gridModel.product')}</th><th className="p-3 text-start">{translate('workspace:unifiedWorkspace.channel')}</th><th className="p-3 text-start">{translate('workspace:gridModel.currentField', { field: '' })}</th><th className="p-3 text-start">{translate('workspace:gridModel.targetField', { field: '' })}</th><th className="p-3 text-start">{translate('workspace:sourceCentricWorkspace.selected')}</th></tr></thead><tbody>{review.items.map(item => { const product = grid.items.find(row => row.children.some(child => child.listingId === item.listingId)); return <tr className="border-b border-border" key={item.id}><td className="p-3">{product?.name ?? item.canonicalProductId}</td><td className="p-3">{formatChannelDisplayName(item.channelId)}</td><td className="p-3">{item.current ?? '—'}</td><td className="p-3">{item.target}</td><td className="p-3" aria-label={item.selected ? translate('workspace:sourceCentricWorkspace.selected') : translate('workspace:sourceCentricWorkspace.notSelected')}>{item.selected ? '✓' : '—'}</td></tr> })}</tbody></table></div></section> : null
  if (!grid) return <PageShell><div className="fh-card fh-card-pad">{translate('workspace:sourceCentricWorkspace.loadingSourceProductWorkspace')}</div></PageShell>

  return <PageShell>
    {reviewSummary}
    <div className="fh-page-header"><div><h1 className="fh-page-title">{workspace.name}</h1><p className="fh-page-subtitle">{translate('workspace:sourceCentricWorkspace.sourceProductWorkspaceImmutableSnapshot')} {workspace.snapshot.id.slice(0, 8)}</p></div><span className={`fh-workspace-dirty ${dirty ? "fh-workspace-dirty-active" : ''}`}>{dirty ? translate('workspace:sourceCentricWorkspace.unsavedEdits', { value1: dirty }) : translate('workspace:sourceCentricWorkspace.draftSaved')}</span></div>
    <section className="grid gap-3 sm:grid-cols-4" aria-label={translate('workspace:sourceCentricWorkspace.workspaceChangeSummary')}>
      {([["ready", summary.ready, translate('workspace:sourceCentricWorkspace.readyChanges')], ["blocked", summary.blocked, translate('workspace:sourceCentricWorkspace.blockedRows')], ["unchanged", summary.unchanged, translate('workspace:sourceCentricWorkspace.unchangedProducts')], ["changed", summary.selected, translate('workspace:sourceCentricWorkspace.selectedChanges')]] as const).map(([state, count, label]) => <button type="button" key={label} className={`fh-card fh-card-pad text-start ${view === state ? "border-accent" : ''}`} onClick={() => { setView(state); setPage(1) }}><span className="block text-2xl font-semibold text-text-base">{formatNumber(count)}</span><span className="fh-text-caption">{label}</span></button>)}
    </section>
    <section className="fh-card fh-card-pad mt-4" aria-label={translate('workspace:sourceCentricWorkspace.dailyActionSequence')}><div className="flex flex-wrap items-center gap-3"><span className="fh-step-active">{translate('workspace:sourceCentricWorkspace.1ChangesDetected')}</span><span aria-hidden="true">→</span><span className={grid.reviewId ? "fh-step-active" : "fh-text-caption"}>{translate('workspace:sourceCentricWorkspace.2ReviewDryRun')}</span><span aria-hidden="true">→</span><span className={grid.selectionChecksum ? "fh-step-active" : "fh-text-caption"}>{translate('workspace:sourceCentricWorkspace.3Approve')}</span><span aria-hidden="true">→</span><span className="fh-text-caption">{translate('workspace:sourceCentricWorkspace.4ApplySelected')}</span><div className="ms-auto flex gap-2"><button className="fh-button-secondary" type="button" disabled={!dirty || busy !== null} onClick={() => void saveAndReview()}><Icon name="dryRun" /> {translate('workspace:sourceCentricWorkspace.reviewDryRun')}</button><button className="fh-button-primary" type="button" disabled={dirty > 0 || !grid.reviewId || !grid.selectionChecksum || selectedCount === 0 || grid.reviewStatus !== "ready" || busy !== null} onClick={() => setConfirming(true)}><Icon name="apply" /> {translate('workspace:sourceCentricWorkspace.apply')} {selectedCount} {translate('workspace:sourceCentricWorkspace.selected')}</button></div></div>{busy && <p className="fh-text-caption mt-3" role="status">{busy}...</p>}</section>
    <section className="fh-card mt-4"><div className="fh-panel-header"><div><p className="fh-section-title">{translate('workspace:sourceCentricWorkspace.sourceProducts')}</p><p className="fh-text-caption">{translate('workspace:sourceCentricWorkspace.productsAreParentsEachChannelListingRemains')}</p></div><form onSubmit={event => { event.preventDefault(); setPage(1); void load() }}><input className="fh-input" type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder={translate('workspace:sourceCentricWorkspace.searchSourceProducts')} /></form></div>
      <div className="divide-y divide-border">{grid.items.length === 0 ? <p className="fh-card-pad fh-text-caption">{translate('workspace:sourceCentricWorkspace.noProductsMatchThisView')}</p> : grid.items.map(product => { const open = expanded.has(product.sourceProductId); return <article key={product.sourceProductId}><button className="grid w-full grid-cols-[32px_minmax(0,1fr)_auto] items-center gap-3 p-4 text-start" type="button" aria-expanded={open} onClick={() => setExpanded(current => { const next = new Set(current); if (next.has(product.sourceProductId)) next.delete(product.sourceProductId); else next.add(product.sourceProductId); return next })}><span aria-hidden="true">{open ? '▼' : '▶'}</span><span><strong className="block text-text-base">{product.name}</strong><span className="fh-text-caption">{product.sourceKey ? translate('workspace:sourceCentricWorkspace.sourceKey', { value1: product.sourceKey }) : ''}{translate('workspace:sourceCentricWorkspace.listingChannelSummary', { listings: product.listingCount, channels: product.mappedChannelCount })}</span></span><span className={`fh-status-label fh-status-${product.state}`} aria-label={translate('workspace:sourceCentricWorkspace.productStatus', { status: formatStatus(product.state) })}><Icon name={product.state === "blocked" ? "alert" : product.state === "ready" ? "success" : "info"} /> {formatStatus(product.state)}</span></button>{open && <div className="bg-bg-base/40 px-4 pb-4"><div className="grid gap-3"><h3 className="fh-text-caption font-semibold uppercase tracking-wide text-wp-muted">{translate('common:resourceGroup.active')}</h3>{orderedItemsByChannel(product.children).map(listing => <div className="rounded-xl border border-border bg-bg-card p-3" key={listing.listingId} data-listing-id={listing.listingId}><div className="flex flex-wrap items-center gap-2"><label className="inline-flex items-center gap-2 text-sm font-medium text-text-base"><input type="checkbox" aria-label={translate('workspace:sourceCentricWorkspace.selectListing', { channel: formatChannelDisplayName(listing.channelId), listing: listing.listingLabel })} checked={listing.selected} disabled={!listing.reviewItemIds.length || listing.state === "blocked" || dirty > 0 || busy !== null} onChange={event => void toggleListingSelection(listing.listingId, event.target.checked)} /> {translate('workspace:sourceCentricWorkspace.select')}</label><strong className="text-text-base">{formatChannelDisplayName(listing.channelId)}</strong><ResourceStateBadge badge={listing.resourceBadge} /><span className="fh-text-caption">{listing.listingLabel} · {listing.externalIdType}: {listing.externalId}</span><span className={`fh-status-label fh-status-${listing.state} ms-auto`}><Icon name={listing.state === "blocked" ? "alert" : listing.state === "ready" ? "success" : "info"} /> {formatStatus(listing.state)}</span></div><div className="mt-3 grid gap-3 md:grid-cols-3">{(["price", "stock", "status"] as const).map(field => { const cell = listing.fields[field]; return <label className="grid gap-1" key={field}><span className="fh-field-label">{formatField(field)}{cell.unit ? translate('workspace:sourceCentricWorkspace.fieldUnit', { unit: cell.unit }) : ''}</span><span className="grid grid-cols-2 gap-2"><span className="fh-readonly-value" title={translate('workspace:sourceCentricWorkspace.latestChannelCache')}>{translate('workspace:sourceCentricWorkspace.current')} {cell.current ?? '—'}</span><input className={`fh-input ${cell.status === "blocked" ? "border-danger" : ''}`} aria-label={translate('workspace:sourceCentricWorkspace.targetField', { channel: formatChannelDisplayName(listing.channelId), field: formatField(field) })} disabled={cell.readOnly} value={changes.get(`${listing.listingId}:${field}`)?.target_value ?? cell.target ?? ''} onChange={event => edit(product.sourceProductId, listing.listingId, listing.channelId, field, event.target.value, cell.currency, cell.unit)} /></span></label> })}</div></div>)}</div></div>}</article> })}</div>
      <div className="flex items-center justify-between border-t border-border p-4"><span className="fh-text-caption">{translate('workspace:sourceCentricWorkspace.page')} {page} {translate('workspace:sourceCentricWorkspace.of')} {pageCount}</span><div className="flex gap-2"><button className="fh-button-secondary fh-button-sm" disabled={page <= 1 || busy !== null} onClick={() => setPage(value => value - 1)}>{translate('workspace:sourceCentricWorkspace.previous')}</button><button className="fh-button-secondary fh-button-sm" disabled={page >= pageCount || busy !== null} onClick={() => setPage(value => value + 1)}>{translate('workspace:sourceCentricWorkspace.next')}</button></div></div>
    </section>
    {confirming && <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label={translate('workspace:sourceCentricWorkspace.applyConfirmation')}><div className="fh-card fh-card-pad max-w-lg"><h2 className="fh-page-title">{translate('workspace:sourceCentricWorkspace.confirmSelectedApply')}</h2><p className="fh-text-caption mt-2">{translate('workspace:sourceCentricWorkspace.only')} {selectedCount} {translate('workspace:sourceCentricWorkspace.explicitlySelectedReviewedChangesWillEnterThe')}</p><div className="mt-5 flex justify-end gap-2"><button className="fh-button-secondary" type="button" onClick={() => setConfirming(false)}>{translate('workspace:sourceCentricWorkspace.cancel')}</button><button className="fh-button-primary" type="button" onClick={() => void apply()}><Icon name="apply" /> {translate('workspace:sourceCentricWorkspace.confirmApply')}</button></div></div></div>}
    {applyResult && <section className="fh-card fh-card-pad mt-4" aria-label={translate('workspace:sourceCentricWorkspace.applyResults')}><h2 className="fh-section-title">{translate('workspace:sourceCentricWorkspace.applyResultStatus', { status: formatStatus(applyResult.status) })}</h2><p className="fh-text-caption">{translate('workspace:sourceCentricWorkspace.verifiedSuccessIsShownOnlyAfterExact')}</p><div className="mt-3 grid gap-2"><h3 className="fh-text-caption font-semibold uppercase tracking-wide text-wp-muted">{translate('common:resourceGroup.active')}</h3>{orderedItemsByChannel(applyResult.items).map(item => <div className="flex items-center gap-2 rounded border border-border p-2" key={item.id}><Icon name={item.status === "applied" ? "success" : item.status === "failed" ? "error" : "warning"} /><span>{formatChannelDisplayName(item.channelId)} · {formatField(item.field)}</span><ResourceStateBadge badge={item.resourceBadge} /><strong className="ms-auto">{formatStatus(item.status)}</strong></div>)}</div></section>}
  </PageShell>
}
