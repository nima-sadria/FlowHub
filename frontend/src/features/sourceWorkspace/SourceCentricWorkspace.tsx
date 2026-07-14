import { useCallback, useEffect, useMemo, useState } from 'react'
import PageShell from '../../components/PageShell'
import Icon from '../../components/Icon'
import { useNotification } from '../../notifications/NotificationProvider'
import type { UnifiedWorkspaceService } from '../../services/unifiedWorkspace/UnifiedWorkspaceService'
import type { ApplyResource, DraftChangeInput, UnifiedWorkspaceResource } from '../../services/unifiedWorkspace/types'
import { formatChannelDisplayName } from '../unifiedWorkspace/channelDisplayName'
import { workspaceApplyIdempotencyKey } from '../unifiedWorkspace/useUnifiedWorkspaceController'
import { sourceWorkspaceApi } from './api'
import type { GroupedWorkspacePage } from './types'

type View = 'changed' | 'ready' | 'blocked' | 'unchanged' | 'all'

export default function SourceCentricWorkspace({ workspace, service }: { workspace: UnifiedWorkspaceResource; service: UnifiedWorkspaceService }) {
  const notify = useNotification()
  const [grid, setGrid] = useState<GroupedWorkspacePage | null>(null)
  const [page, setPage] = useState(1)
  const [view, setView] = useState<View>('changed')
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [changes, setChanges] = useState<Map<string, DraftChangeInput>>(new Map())
  const [busy, setBusy] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [applyResult, setApplyResult] = useState<ApplyResource | null>(null)

  const load = useCallback(() => sourceWorkspaceApi.groupedGrid(workspace.id, page, view, search).then(result => {
    setGrid(result)
    setExpanded(current => current.size ? current : new Set(result.items.filter(item => item.state !== 'unchanged').slice(0, 5).map(item => item.sourceProductId)))
  }), [workspace.id, page, view, search])
  useEffect(() => { void load() }, [load])
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
  async function saveAndReview() {
    if (!grid || !dirty) return
    setBusy('Saving Draft')
    try {
      const revision = await service.saveDraft(workspace.id, grid.draftVersion, [...changes.values()])
      const review = await service.createReview(workspace.id, revision.id)
      const eligible = review.items.filter(item => item.eligible).map(item => item.id)
      if (eligible.length) await service.saveSelection(workspace.id, review.id, eligible)
      setChanges(new Map()); await load()
      notify.success({ title: 'Review and Dry Run complete', description: `${eligible.length} eligible changes were automatically selected. Blocked items remain excluded.` })
    } catch (error) { notify.error({ title: 'Review could not be completed', description: error instanceof Error ? error.message : 'Check Data Quality issues.' }) }
    finally { setBusy(null) }
  }
  async function apply() {
    if (!grid?.reviewId || !grid.selectionChecksum || !grid.revisionId) return
    setBusy('Applying selected Listings')
    try {
      const key = await workspaceApplyIdempotencyKey(workspace.id, grid.reviewId, grid.revisionId, grid.selectionChecksum)
      const result = await service.applySelected(workspace.id, grid.reviewId, grid.selectionChecksum, key)
      setApplyResult(result); setConfirming(false); await load()
    } catch (error) { notify.error({ title: 'Apply was blocked', description: error instanceof Error ? error.message : 'Generate a fresh Review.' }) }
    finally { setBusy(null) }
  }
  async function toggleListingSelection(listingId: string, selected: boolean) {
    if (!grid?.reviewId) return
    setBusy('Updating selected changes')
    try {
      const review = await sourceWorkspaceApi.review(workspace.id, grid.reviewId)
      const selectedIds = new Set(review.items.filter(item => item.selected).map(item => item.id))
      const listingItems = review.items.filter(item => item.listingId === listingId && item.eligible)
      for (const item of listingItems) {
        if (selected) selectedIds.add(item.id)
        else selectedIds.delete(item.id)
      }
      if (!selectedIds.size) {
        notify.warning({ title: 'Keep one selected change', description: 'Apply remains disabled unless at least one eligible Review item is selected.' })
        return
      }
      await service.saveSelection(workspace.id, grid.reviewId, [...selectedIds])
      await load()
    } catch (error) { notify.error({ title: 'Selection was not saved', description: error instanceof Error ? error.message : 'Generate a fresh Review.' }) }
    finally { setBusy(null) }
  }
  const summary = useMemo(() => grid?.summary ?? { ready: 0, blocked: 0, unchanged: 0, selected: 0 }, [grid])
  if (!grid) return <PageShell><div className="fh-card fh-card-pad">Loading Source Product Workspace...</div></PageShell>

  return <PageShell>
    <div className="fh-page-header"><div><h1 className="fh-page-title">{workspace.name}</h1><p className="fh-page-subtitle">Source Product Workspace · Immutable Snapshot {workspace.snapshot.id.slice(0, 8)}</p></div><span className={`fh-workspace-dirty ${dirty ? 'fh-workspace-dirty-active' : ''}`}>{dirty ? `${dirty} unsaved edits` : 'Draft saved'}</span></div>
    <section className="grid gap-3 sm:grid-cols-4" aria-label="Workspace change summary">
      {([['ready', summary.ready, 'Ready changes'], ['blocked', summary.blocked, 'Blocked rows'], ['unchanged', summary.unchanged, 'Unchanged products'], ['changed', summary.selected, 'Selected changes']] as const).map(([state, count, label]) => <button type="button" key={label} className={`fh-card fh-card-pad text-start ${view === state ? 'border-accent' : ''}`} onClick={() => { setView(state); setPage(1) }}><span className="block text-2xl font-semibold text-text-base">{count.toLocaleString()}</span><span className="fh-text-caption">{label}</span></button>)}
    </section>
    <section className="fh-card fh-card-pad mt-4" aria-label="Daily action sequence"><div className="flex flex-wrap items-center gap-3"><span className="fh-step-active">1 · Changes detected</span><span aria-hidden="true">→</span><span className={grid.reviewId ? 'fh-step-active' : 'fh-text-caption'}>2 · Review & Dry Run</span><span aria-hidden="true">→</span><span className={grid.selectionChecksum ? 'fh-step-active' : 'fh-text-caption'}>3 · Approve</span><span aria-hidden="true">→</span><span className="fh-text-caption">4 · Apply selected</span><div className="ms-auto flex gap-2"><button className="fh-button-secondary" type="button" disabled={!dirty || busy !== null} onClick={() => void saveAndReview()}><Icon name="dryRun" /> Review & Dry Run</button><button className="fh-button-primary" type="button" disabled={dirty > 0 || !grid.reviewId || !grid.selectionChecksum || selectedCount === 0 || grid.reviewStatus !== 'ready' || busy !== null} onClick={() => setConfirming(true)}><Icon name="apply" /> Apply {selectedCount} selected</button></div></div>{busy && <p className="fh-text-caption mt-3" role="status">{busy}...</p>}</section>
    <section className="fh-card mt-4"><div className="fh-panel-header"><div><p className="fh-section-title">Source Products</p><p className="fh-text-caption">Products are parents. Each Channel Listing remains independently identifiable and selectable.</p></div><form onSubmit={event => { event.preventDefault(); setPage(1); void load() }}><input className="fh-input" type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search Source Products" /></form></div>
      <div className="divide-y divide-border">{grid.items.length === 0 ? <p className="fh-card-pad fh-text-caption">No products match this view.</p> : grid.items.map(product => { const open = expanded.has(product.sourceProductId); return <article key={product.sourceProductId}><button className="grid w-full grid-cols-[32px_minmax(0,1fr)_auto] items-center gap-3 p-4 text-start" type="button" aria-expanded={open} onClick={() => setExpanded(current => { const next = new Set(current); if (next.has(product.sourceProductId)) next.delete(product.sourceProductId); else next.add(product.sourceProductId); return next })}><span aria-hidden="true">{open ? '▼' : '▶'}</span><span><strong className="block text-text-base">{product.name}</strong><span className="fh-text-caption">{product.sourceKey ? `Source key ${product.sourceKey} · ` : ''}{product.listingCount} Listings across {product.mappedChannelCount} Channels</span></span><span className={`fh-status-label fh-status-${product.state}`} aria-label={`Product status ${product.state}`}><Icon name={product.state === 'blocked' ? 'alert' : product.state === 'ready' ? 'success' : 'info'} /> {product.state}</span></button>{open && <div className="bg-bg-base/40 px-4 pb-4"><div className="grid gap-3">{product.children.map(listing => <div className="rounded-xl border border-border bg-bg-card p-3" key={listing.listingId} data-listing-id={listing.listingId}><div className="flex flex-wrap items-center gap-2"><label className="inline-flex items-center gap-2 text-sm font-medium text-text-base"><input type="checkbox" aria-label={`Select ${formatChannelDisplayName(listing.channelId)} ${listing.listingLabel}`} checked={listing.selected} disabled={!listing.reviewItemIds.length || listing.state === 'blocked' || dirty > 0 || busy !== null} onChange={event => void toggleListingSelection(listing.listingId, event.target.checked)} /> Select</label><strong className="text-text-base">{formatChannelDisplayName(listing.channelId)}</strong><span className="fh-text-caption">{listing.listingLabel} · {listing.externalIdType}: {listing.externalId}</span><span className={`fh-status-label fh-status-${listing.state} ms-auto`}><Icon name={listing.state === 'blocked' ? 'alert' : listing.state === 'ready' ? 'success' : 'info'} /> {listing.state}</span></div><div className="mt-3 grid gap-3 md:grid-cols-3">{(['price', 'stock', 'status'] as const).map(field => { const cell = listing.fields[field]; return <label className="grid gap-1" key={field}><span className="fh-field-label capitalize">{field}{cell.unit ? ` (${cell.unit})` : ''}</span><span className="grid grid-cols-2 gap-2"><span className="fh-readonly-value" title="Latest Channel Cache">Current {cell.current ?? '—'}</span><input className={`fh-input ${cell.status === 'blocked' ? 'border-danger' : ''}`} aria-label={`${formatChannelDisplayName(listing.channelId)} ${field} target`} disabled={cell.readOnly} value={changes.get(`${listing.listingId}:${field}`)?.target_value ?? cell.target ?? ''} onChange={event => edit(product.sourceProductId, listing.listingId, listing.channelId, field, event.target.value, cell.currency, cell.unit)} /></span></label> })}</div></div>)}</div></div>}</article> })}</div>
      <div className="flex items-center justify-between border-t border-border p-4"><span className="fh-text-caption">Page {page} of {pageCount}</span><div className="flex gap-2"><button className="fh-button-secondary fh-button-sm" disabled={page <= 1 || dirty > 0} onClick={() => setPage(value => value - 1)}>Previous</button><button className="fh-button-secondary fh-button-sm" disabled={page >= pageCount || dirty > 0} onClick={() => setPage(value => value + 1)}>Next</button></div></div>
    </section>
    {confirming && <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label="Apply confirmation"><div className="fh-card fh-card-pad max-w-lg"><h2 className="fh-page-title">Confirm selected Apply</h2><p className="fh-text-caption mt-2">Only {selectedCount} explicitly selected, Reviewed changes will enter the shared Write Pipeline. Blocked and hidden changes remain excluded.</p><div className="mt-5 flex justify-end gap-2"><button className="fh-button-secondary" type="button" onClick={() => setConfirming(false)}>Cancel</button><button className="fh-button-primary" type="button" onClick={() => void apply()}><Icon name="apply" /> Confirm Apply</button></div></div></div>}
    {applyResult && <section className="fh-card fh-card-pad mt-4" aria-label="Apply results"><h2 className="fh-section-title">Apply {applyResult.status}</h2><p className="fh-text-caption">Verified success is shown only after exact provider verification. Uncertain outcomes require reconciliation.</p><div className="mt-3 grid gap-2">{applyResult.items.map(item => <div className="flex items-center gap-2 rounded border border-border p-2" key={item.id}><Icon name={item.status === 'applied' ? 'success' : item.status === 'failed' ? 'error' : 'warning'} /><span>{formatChannelDisplayName(item.channelId)} · {item.field}</span><strong className="ms-auto">{item.status.replace(/_/g, ' ')}</strong></div>)}</div></section>}
  </PageShell>
}
