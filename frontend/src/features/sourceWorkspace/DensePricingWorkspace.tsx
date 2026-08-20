import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ApiError } from '../../api/client'
import Badge from '../../components/Badge'
import Empty from '../../components/Empty'
import Icon from '../../components/Icon'
import PageShell from '../../components/PageShell'
import { ResourceOptionGroups } from '../../components/ResourceOrdering'
import { translate } from '../../i18n'
import { formatField, formatStatus } from '../../i18n/display'
import { localizedApiError } from '../../i18n/errors'
import { formatCurrencyLabel, formatNumber } from '../../i18n/format'
import { useNotification } from '../../notifications/NotificationProvider'
import type { UnifiedWorkspaceService } from '../../services/unifiedWorkspace/UnifiedWorkspaceService'
import type { ApplyResource, ManifestOperationResource, ReviewItemResource, ReviewResource, UnifiedWorkspaceResource } from '../../services/unifiedWorkspace/types'
import {
  applyBulkTransformation,
  createPricingWorkspaceState,
  editPricingFields,
  isPricingFieldSelected,
  persistPricingWorkspaceState,
  previewBulkTransformation,
  pricingFieldChange,
  pricingFieldKey,
  pricingWorkspaceSummary,
  redoPricingWorkspace,
  registerPricingFields,
  restorePricingWorkspaceState,
  selectedPricingChanges,
  selectedPricingDraftChanges,
  setPricingFieldSelected,
  undoPricingWorkspace,
  type BulkPreviewItem,
  type BulkTransformationKind,
  type BulkTransformationPreview,
  type PricingFieldDescriptor,
  type PricingFieldChange,
  type PricingWorkspaceState,
} from '../pricingWorkspace'
import { channelIdentitySignals, prepareResourceCollection, sourceChannelSignals } from '../resourceOrdering/resourceOrdering'
import { formatSourceChannelDisplayName } from '../unifiedWorkspace/channelDisplayName'
import { workspaceApplyIdempotencyKey } from '../unifiedWorkspace/useUnifiedWorkspaceController'
import { inputHint } from '../../utils/inputHint'
import { sourceWorkspaceApi } from './api'
import PricingWorkspaceStartup from './PricingWorkspaceStartup'
import type { GroupedListing, GroupedProduct, GroupedWorkspacePage, SourceChannel } from './types'

// Figma: Screen/Products (21 Product Screens) — page header with Save Changes
// and Bulk Edit, search + filter chips, and one product-grouped channel table
// with inline price/stock/availability editing. Review, dry run, and apply
// continue through the existing draft dialogs; Modal/BulkEdit hosts the bulk
// transformation workflow.

type View = 'changed' | 'ready' | 'blocked' | 'unchanged' | 'all'
type PricingField = 'price' | 'stock' | 'status'

const FIELDS: readonly PricingField[] = ['price', 'stock', 'status']
const VIEWS: readonly View[] = ['all', 'changed', 'ready', 'blocked', 'unchanged']

interface ReviewContext {
  reviewId: string
  revisionId: string
  selectionChecksum: string
  selectedCount: number
  manifestId: string
  manifestChecksum: string
  operations: ManifestOperationResource[]
  affectedChannelIds: string[]
}

export interface DensePricingWorkspaceProps {
  workspace: UnifiedWorkspaceResource
  service: UnifiedWorkspaceService
  /** Products owns the sole page shell when the pricing grid is embedded on /products. */
  embedded?: boolean
  categoryOptions?: readonly { value: string; label: string }[]
  /** Global Products search supplied by the q query parameter. */
  initialSearch?: string
  /** Settings-owned unified display/pricing unit. Native Listing units remain
   * unchanged in draft and Apply state. */
  displayProfile?: PricingDisplayProfile | null
}

export interface PricingDisplayProfile {
  currency: string
  unit: string
}

export default function DensePricingWorkspace({
  workspace,
  service,
  embedded = false,
  categoryOptions = [],
  initialSearch = '',
  displayProfile = null,
}: DensePricingWorkspaceProps) {
  const notify = useNotification()
  const gridLoaderRef = useRef(createLatestGridLoader<GroupedWorkspacePage>())
  const persistenceScope = `${workspace.snapshot.id}:${workspace.snapshot.checksum}:${workspace.draft.id}`
  const [grid, setGrid] = useState<GroupedWorkspacePage | null>(null)
  const [channelInventory, setChannelInventory] = useState<SourceChannel[]>([])
  const [channelInventoryReady, setChannelInventoryReady] = useState(false)
  const [page, setPage] = useState(1)
  const [view, setView] = useState<View>(() => (
    workspace.entryPoint === 'manual' || workspace.draft.currentRevisionId === null ? 'all' : 'changed'
  ))
  const [searchInput, setSearchInput] = useState(() => initialSearch.trim())
  const [search, setSearch] = useState(() => initialSearch.trim())
  const [channelFilter, setChannelFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [productTypeFilter, setProductTypeFilter] = useState<'' | 'simple' | 'variable' | 'variation'>('')
  const [stockFilter, setStockFilter] = useState<'' | 'in_stock' | 'out_of_stock'>('')
  const [pricingState, setPricingState] = useState<PricingWorkspaceState>(() => restoreState(workspace.id, persistenceScope))
  const pricingStateRef = useRef(pricingState)
  const [draftVersion, setDraftVersion] = useState(workspace.draft.version)
  const [busy, setBusy] = useState<string | null>(null)
  // React's `disabled` attribute only takes effect after the next render, so
  // two click events dispatched in the same tick (a genuine double-click,
  // not just a fast double `.click()` call) both fire before `busy` state
  // updates the DOM. This ref is checked and set synchronously, so it
  // actually blocks a same-tick double Apply where `disabled={busy !== null}`
  // alone cannot.
  const applyInFlightRef = useRef(false)
  const [review, setReview] = useState<ReviewResource | null>(null)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [reviewContext, setReviewContext] = useState<ReviewContext | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [applyResult, setApplyResult] = useState<ApplyResource | null>(null)
  const [bulkOpen, setBulkOpen] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [rowMenuFor, setRowMenuFor] = useState<string | null>(null)
  const [gridError, setGridError] = useState<string | null>(null)
  const [channelInventoryError, setChannelInventoryError] = useState<string | null>(null)

  const load = useCallback(async () => {
    await gridLoaderRef.current.run(
      () => sourceWorkspaceApi.groupedGrid(workspace.id, page, view, search, {
        categoryId: categoryFilter || undefined,
        productType: productTypeFilter || undefined,
        channelId: channelFilter || undefined,
        stockState: stockFilter || undefined,
      }),
      result => {
        setGrid(result)
        setGridError(null)
        setDraftVersion(current => Math.max(current, result.draftVersion))
      },
      error => setGridError(localizedApiError(error, 'products:products.unableToLoadProducts')),
    )
  }, [categoryFilter, channelFilter, page, productTypeFilter, search, stockFilter, view, workspace.id])

  const loadChannelInventory = useCallback(async () => {
    try {
      const result = await sourceWorkspaceApi.channels()
      setChannelInventory(result.items)
      setChannelInventoryError(null)
    } catch (error) {
      // Keep the last verified inventory. If none exists, the table remains a
      // useful cached read surface while all target fields fail closed.
      setChannelInventoryError(localizedApiError(error, 'products:products.inlinePricingUnavailable'))
    } finally {
      setChannelInventoryReady(true)
    }
  }, [])

  useEffect(() => {
    const normalized = initialSearch.trim()
    setSearchInput(normalized)
    setSearch(normalized)
    setPage(1)
  }, [initialSearch])
  useEffect(() => {
    void load()
    return () => gridLoaderRef.current.cancel()
  }, [load])
  useEffect(() => {
    void loadChannelInventory()
  }, [loadChannelInventory])
  useEffect(() => {
    pricingStateRef.current = pricingState
    try { persistPricingWorkspaceState(window.sessionStorage, pricingState) } catch { /* Storage is optional. */ }
  }, [pricingState])
  useEffect(() => {
    if (pricingState.scopeId !== persistenceScope) setPricingState(restoreState(workspace.id, persistenceScope))
  }, [persistenceScope, pricingState.scopeId, workspace.id])

  const channelById = useMemo(() => new Map(channelInventory.map(channel => [channel.channelId, channel])), [channelInventory])
  const discoveredChannelIds = useMemo(() => [...new Set(grid?.items.flatMap(product => product.children.map(listing => listing.channelId)) ?? [])], [grid])
  const channelResources = useMemo(() => channelInventory.length
    ? prepareResourceCollection(channelInventory, item => sourceChannelSignals(item))
    : prepareResourceCollection(discoveredChannelIds.map(channelId => ({ channelId })), item => channelIdentitySignals(item)),
  [channelInventory, discoveredChannelIds])
  const baseDescriptors = useMemo(() => grid ? pricingDescriptors(grid, channelById) : [], [channelById, grid])
  const descriptors = useMemo(() => baseDescriptors.map(descriptor => validateDescriptorTarget(
    descriptor,
    channelById.get(descriptor.identity.channelId),
    pricingFieldChange(pricingState, descriptor.identity)?.targetValue ?? descriptor.targetValue ?? descriptor.currentValue ?? '',
  )), [baseDescriptors, channelById, pricingState])
  const visibleDescriptors = useMemo(() => channelFilter
    ? descriptors.filter(descriptor => descriptor.identity.channelId === channelFilter)
    : descriptors, [channelFilter, descriptors])
  const descriptorMap = useMemo(() => new Map(descriptors.map(descriptor => [pricingFieldKey(descriptor.identity), descriptor])), [descriptors])
  useEffect(() => {
    if (!descriptors.length) return
    const refreshed = refreshRegisteredPricingState(pricingState, descriptors)
    if (!refreshed.changed) return
    setPricingState(refreshed.state)
    setReview(null)
    setReviewContext(null)
    setReviewOpen(false)
    setConfirming(false)
    setApplyResult(null)
  }, [descriptors, pricingState])

  const visibleGrid = useMemo(() => grid ? {
    ...grid,
    items: grid.items.map(product => ({
      ...product,
      children: product.children
        .filter(listing => !channelFilter || listing.channelId === channelFilter)
        .map(listing => channelById.has(listing.channelId) ? listing : {
          ...listing,
          fields: Object.fromEntries(Object.entries(listing.fields).map(([field, value]) => [field, { ...value, readOnly: true }])) as GroupedListing['fields'],
        }),
    })).filter(product => product.children.length > 0),
  } : null, [channelById, channelFilter, grid])
  const visibleKeys = useMemo(() => new Set(visibleDescriptors.map(descriptor => pricingFieldKey(descriptor.identity))), [visibleDescriptors])
  const summary = useMemo(() => pricingWorkspaceSummary(pricingState, visibleKeys), [pricingState, visibleKeys])
  const pageCount = Math.max(1, Math.ceil((grid?.total ?? 0) / (grid?.pageSize || 100)))
  // Price presentation follows the Settings-owned unified unit when it matches
  // the visible currency. Native Listing values remain the draft/apply contract.
  const priceLabel = useMemo(() => {
    const currencies = new Set<string>()
    const units = new Set<string>()
    for (const product of visibleGrid?.items ?? []) {
      for (const listing of product.children) {
        const currency = listing.fields.price.currency?.trim()
        const unit = listing.fields.price.unit?.trim()
        if (currency) currencies.add(currency.toUpperCase())
        if (unit) units.add(unit.toUpperCase())
      }
    }
    const currency = currencies.size === 1 ? [...currencies][0] : null
    if (!currency) return null
    const configuredCurrency = displayProfile?.currency.trim().toUpperCase()
    const configuredUnit = displayProfile?.unit.trim().toUpperCase()
    if (configuredCurrency === currency && configuredUnit) return formatPricingUnitLabel(currency, configuredUnit)
    const nativeUnit = units.size === 1 ? [...units][0] : null
    return nativeUnit ? formatPricingUnitLabel(currency, nativeUnit) : formatCurrencyLabel(currency)
  }, [displayProfile, visibleGrid])

  // A filter/view change can immediately re-fetch and re-filter the grid,
  // unmounting the row currently under edit before its onBlur commit fires --
  // TargetInput only commits on blur, so an in-progress keystroke would be
  // silently discarded along with the unmounted <input>. Flushing here forces
  // that commit through the input's own existing blur handler first.
  const flushPendingEdit = useCallback(() => {
    const active = document.activeElement
    if (active instanceof HTMLElement && active.hasAttribute('data-target-field')) active.blur()
  }, [])

  const mutatePricingState = useCallback((update: (current: PricingWorkspaceState) => PricingWorkspaceState) => {
    setPricingState(current => update(current))
    setReview(null)
    setReviewContext(null)
    setReviewOpen(false)
    setApplyResult(null)
  }, [])

  const commitEdit = useCallback((descriptor: PricingFieldDescriptor, rawValue: string) => {
    const targetValue = rawValue.trim()
    mutatePricingState(current => editPricingFields(current, [{
      descriptor: validateDescriptorTarget(descriptor, channelById.get(descriptor.identity.channelId), targetValue),
      targetValue,
    }]))
  }, [channelById, mutatePricingState])

  const resetListingChanges = useCallback((listing: GroupedListing, product: GroupedProduct) => {
    mutatePricingState(current => {
      const edits: Array<{ descriptor: PricingFieldDescriptor; targetValue: string }> = []
      for (const field of FIELDS) {
        const identity = { productId: product.sourceProductId, listingId: listing.listingId, channelId: listing.channelId, field }
        if (!pricingFieldChange(current, identity)) continue
        const descriptor = descriptorMap.get(pricingFieldKey(identity))
        if (descriptor) edits.push({ descriptor, targetValue: descriptor.currentValue ?? '' })
      }
      return edits.length ? editPricingFields(current, edits) : current
    })
  }, [descriptorMap, mutatePricingState])

  const setListingSelected = useCallback((listing: GroupedListing, product: GroupedProduct, selected: boolean) => {
    mutatePricingState(current => {
      let next = current
      for (const field of FIELDS) {
        const identity = { productId: product.sourceProductId, listingId: listing.listingId, channelId: listing.channelId, field }
        if (pricingFieldChange(next, identity)) next = setPricingFieldSelected(next, identity, selected)
      }
      return next
    })
  }, [mutatePricingState])

  async function saveAndReview() {
    if (!grid || summary.changed === 0 || summary.selected === 0) return
    const requestedRevision = pricingState.revision
    const requestedChanges = selectedPricingChanges(pricingState)
    setBusy(translate('workspace:sourceCentricWorkspace.savingDraft'))
    try {
      const revision = await service.saveDraft(workspace.id, draftVersion, [...selectedPricingDraftChanges(pricingState)], 'replace')
      // The Draft save itself is now durably committed server-side (draft.version
      // has advanced) regardless of whether Review/Selection below succeed or get
      // superseded by a newer local edit. Reconciling here -- not only on the full
      // success path -- keeps the CAS expected_version this component sends on the
      // *next* Save attempt in sync with the server. Skipping this on an early
      // return previously left draftVersion pointing at the pre-save value forever,
      // so the next legitimate Save was rejected as DRAFT_VERSION_CONFLICT even
      // though nothing was actually stale.
      setDraftVersion(revision.draftVersion)
      const created = await service.createReview(workspace.id, revision.id)
      if (pricingStateRef.current.revision !== requestedRevision) {
        notify.error({ title: translate('workspace:sourceCentricWorkspace.reviewCouldNotBeCompleted'), description: translate('workspace:sourceCentricWorkspace.generateAFreshReview') })
        return
      }
      let selectedIds: string[]
      try {
        selectedIds = resolveExactReviewSelection(created.items, requestedChanges)
      } catch {
        throw new Error(translate('workspace:densePricing.noEligibleSelectedChanges'))
      }
      if (!selectedIds.length) throw new Error(translate('workspace:densePricing.noEligibleSelectedChanges'))
      const selection = await service.saveSelection(workspace.id, created.id, selectedIds)
      if (pricingStateRef.current.revision !== requestedRevision) {
        notify.error({ title: translate('workspace:sourceCentricWorkspace.reviewCouldNotBeCompleted'), description: translate('workspace:sourceCentricWorkspace.generateAFreshReview') })
        return
      }
      const selectedIdSet = new Set(selectedIds)
      setReview({ ...created, items: created.items.map(item => ({ ...item, selected: selectedIdSet.has(item.id) })) })
      setReviewContext({
        reviewId: created.id,
        revisionId: revision.id,
        selectionChecksum: selection.selectionChecksum,
        selectedCount: selectedIds.length,
        manifestId: selection.manifestId,
        manifestChecksum: selection.manifestChecksum,
        operations: selection.operations,
        affectedChannelIds: selection.affectedChannelIds,
      })
      setReviewOpen(true)
      notify.success({ title: translate('workspace:sourceCentricWorkspace.reviewAndDryRunComplete'), description: translate('workspace:densePricing.selectionBoundToReview', { count: selectedIds.length }) })
    } catch (error) {
      notify.error({ title: translate('workspace:sourceCentricWorkspace.reviewCouldNotBeCompleted'), description: localizedApiError(error, 'workspace:sourceCentricWorkspace.checkDataQualityIssues') })
    } finally { setBusy(null) }
  }

  async function apply() {
    if (!reviewContext) return
    if (applyInFlightRef.current) return
    applyInFlightRef.current = true
    setBusy(translate('workspace:sourceCentricWorkspace.applyingSelectedListings'))
    try {
      const key = await workspaceApplyIdempotencyKey(
        workspace.id,
        reviewContext.reviewId,
        reviewContext.revisionId,
        reviewContext.selectionChecksum,
        reviewContext.manifestChecksum,
      )
      const result = await service.applySelected(
        workspace.id,
        reviewContext.reviewId,
        reviewContext.selectionChecksum,
        reviewContext.manifestId,
        reviewContext.manifestChecksum,
        key,
      )
      setApplyResult(result)
      setReviewContext(null)
      setConfirming(false)
      setReviewOpen(false)
      await load()
    } catch (error) {
      if (error instanceof ApiError && [
        'STALE_APPLY_MANIFEST',
        'APPLY_MANIFEST_NOT_FOUND',
        'APPLY_MANIFEST_CHECKSUM_MISMATCH',
      ].includes(error.code ?? '')) {
        setConfirming(false)
        setReviewOpen(false)
        setReviewContext(null)
        setReview(null)
      }
      notify.error({ title: translate('workspace:sourceCentricWorkspace.applyWasBlocked'), description: localizedApiError(error, 'workspace:sourceCentricWorkspace.generateAFreshReview') })
    } finally { applyInFlightRef.current = false; setBusy(null) }
  }

  const undo = useCallback(() => mutatePricingState(undoPricingWorkspace), [mutatePricingState])
  const redo = useCallback(() => mutatePricingState(redoPricingWorkspace), [mutatePricingState])
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return
      const target = event.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')) return
      const key = event.key.toLowerCase()
      if (key === 'z' && !event.shiftKey) { event.preventDefault(); undo() }
      if (key === 'y' || (key === 'z' && event.shiftKey)) { event.preventDefault(); redo() }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [redo, undo])
  useEffect(() => {
    if (!confirming) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.stopPropagation()
      setConfirming(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [confirming])
  useEffect(() => {
    if (!rowMenuFor && !filtersOpen) return
    const close = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null
      if (target?.closest('[data-row-actions]') || target?.closest('[data-row-actions-portal]') || target?.closest('[data-products-filters]')) return
      setRowMenuFor(null)
      setFiltersOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [filtersOpen, rowMenuFor])

  if (!grid || !channelInventoryReady) {
    const loadingState = gridError ? <div className="fh-card fh-card-pad">
      <div className="fh-alert fh-alert-danger" role="alert"><Icon name="alert" /><span>{gridError}</span><button className="fh-button-secondary fh-button-sm ms-auto" type="button" onClick={() => void load()}>{translate('products:products.retryInlinePricing')}</button></div>
    </div> : <PricingWorkspaceStartup />
    return embedded ? loadingState : <PageShell>{loadingState}</PageShell>
  }

  const totalProducts = grid.total
  const filterCount = (categoryFilter ? 1 : 0) + (productTypeFilter ? 1 : 0)
  const content = <>
    <div className="fh-products-screen" data-pricing-workspace data-products-critical-controls>
      <div className="fh-page-header">
        <h1 className="fh-page-title">{translate('products:products.products')}</h1>
        {/* i18n-ignore: utility classes, not user-facing copy */}
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            className="fh-button-primary fh-button-sm"
            data-products-save
            disabled={summary.changed === 0 || summary.selected === 0 || busy !== null}
            onClick={() => reviewContext ? setReviewOpen(true) : void saveAndReview()}
          >
            {translate('products:products.saveChanges')}
          </button>
          <button
            type="button"
            className="fh-button-secondary fh-button-sm"
            data-products-bulk-edit
            disabled={busy !== null}
            onClick={() => setBulkOpen(true)}
          >
            {translate('products:products.bulkEdit')}
          </button>
        </div>
      </div>

      {gridError && <div className="fh-alert fh-alert-danger" role="alert"><Icon name="alert" /><span>{gridError}</span><button className="fh-button-secondary fh-button-sm ms-auto" type="button" onClick={() => void load()}>{translate('products:products.retryInlinePricing')}</button></div>}
      {channelInventoryError && <div className="fh-alert fh-alert-warning" role="alert"><Icon name="info" /><span>{channelInventoryError}</span><button className="fh-button-secondary fh-button-sm ms-auto" type="button" onClick={() => void loadChannelInventory()}>{translate('products:products.retryInlinePricing')}</button></div>}

      <div className="fh-products-toolbar" aria-label={translate('workspace:densePricing.pricingToolbar')}>
        <form className="fh-products-search" onSubmit={event => { event.preventDefault(); setPage(1); setSearch(searchInput.trim()) }}>
          <Icon name="search" size="sm" className="fh-products-search-icon" />
          <input
            className="fh-products-search-input"
            type="search"
            value={searchInput}
            onChange={event => setSearchInput(event.target.value)}
            {...inputHint(translate('products:products.searchProducts'))}
            aria-label={translate('products:products.searchProducts')}
          />
          {searchInput && <button
            type="button"
            className="fh-products-search-clear"
            aria-label={translate('products:products.clearSearch')}
            onClick={() => { setSearchInput(''); setSearch(''); setPage(1) }}
          ><Icon name="close" size="sm" /></button>}
        </form>
        <label className="fh-chip-select">
          <span className="sr-only">{translate('products:products.allStatuses')}</span>
          <select value={stockFilter} onChange={event => { flushPendingEdit(); setStockFilter(event.target.value as typeof stockFilter); setPage(1) }}>
            <option value="">{translate('products:products.allStatuses')}</option>
            <option value="in_stock">{translate('products:products.inStock')}</option>
            <option value="out_of_stock">{translate('products:products.outOfStock')}</option>
          </select>
          <Icon name="chevronDown" size="sm" className="fh-chip-caret" />
        </label>
        <label className="fh-chip-select">
          <span className="sr-only">{translate('products:products.allChannels')}</span>
          <select name="channelId" value={channelFilter} onChange={event => { flushPendingEdit(); setChannelFilter(event.target.value); setPage(1) }}>
            <option value="">{translate('products:products.allChannels')}</option>
            <ResourceOptionGroups resources={channelResources} isOptionDisabled={channel => channel.section !== 'active'} />
          </select>
          <Icon name="chevronDown" size="sm" className="fh-chip-caret" />
        </label>
        <label className="fh-chip-select">
          <span className="sr-only">{translate('products:products.savedViews')}</span>
          <select value={view} onChange={event => { flushPendingEdit(); setView(event.target.value as View); setPage(1) }} data-products-view>
            <option value="all" disabled hidden>{translate('products:products.savedViews')}</option>
            {VIEWS.map(value => <option key={value} value={value}>{translate(`workspace:densePricing.view.${value}`)}</option>)}
          </select>
          <Icon name="chevronDown" size="sm" className="fh-chip-caret" />
        </label>
        <div className="fh-products-filters" data-products-filters>
          <button
            type="button"
            className={`fh-chip ${filterCount ? 'fh-chip-active' : ''}`}
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen(open => !open)}
          >
            <Icon name="filter" size="sm" /> {translate('products:products.filters')}{filterCount ? ` (${formatNumber(filterCount)})` : ''}
          </button>
          {filtersOpen && <div className="fh-dropdown fh-products-filters-panel">
            <label className="fh-field">
              <span className="fh-label">{translate('products:column.categories')}</span>
              <select className="fh-select" name="categoryId" value={categoryFilter} onChange={event => { flushPendingEdit(); setCategoryFilter(event.target.value); setPage(1) }}>
                <option value="">{translate('products:products.allCategories')}</option>
                {categoryOptions.map(category => <option key={category.value} value={category.value}>{category.label}</option>)}
              </select>
            </label>
            <label className="fh-field">
              <span className="fh-label">{translate('products:column.type')}</span>
              <select className="fh-select" name="productType" value={productTypeFilter} onChange={event => { flushPendingEdit(); setProductTypeFilter(event.target.value as typeof productTypeFilter); setPage(1) }}>
                <option value="">{translate('products:products.allTypes')}</option>
                {(['simple', 'variation', 'variable'] as const).map(type => <option key={type} value={type}>{translate(`products:productType.${type}`)}</option>)}
              </select>
            </label>
          </div>}
        </div>
      </div>

      <div className="fh-products-card" data-products-table>
        <table className="fh-products-table">
          <thead>
            <tr>
              <th scope="col" className="fh-products-col-product">{translate('products:column.product')}</th>
              <th scope="col">{translate('products:column.channel')}</th>
              <th scope="col" data-price-unit={priceLabel ?? undefined}>{priceLabel
                ? translate('products:products.priceWithCurrency', { currency: priceLabel })
                : translate('products:column.price')}</th>
              <th scope="col">{translate('products:column.stock')}</th>
              <th scope="col">{translate('products:column.availability')}</th>
              <th scope="col">{translate('products:column.lastSync')}</th>
              <th scope="col" className="fh-products-col-actions">{translate('products:column.actions')}</th>
            </tr>
          </thead>
          {visibleGrid && visibleGrid.items.length === 0 && <tbody>
            <tr><td colSpan={7}><Empty title={translate('products:products.noProductsFound')} description={translate('products:products.tryAdjustingTheSearchOrFilter')} /></td></tr>
          </tbody>}
          {visibleGrid?.items.map(product => <ProductGroup
            key={product.sourceProductId}
            product={product}
            channelById={channelById}
            descriptorMap={descriptorMap}
            pricingState={pricingState}
            rowMenuFor={rowMenuFor}
            onToggleRowMenu={setRowMenuFor}
            onCommitEdit={commitEdit}
            onResetListing={resetListingChanges}
            onSetListingSelected={setListingSelected}
            displayProfile={displayProfile}
          />)}
        </table>
      </div>

      <div className="fh-products-footer">
        <span className="fh-text-caption" data-products-count>
          {translate('products:products.showingProducts', { count: totalProducts, value: formatNumber(totalProducts) })}
        </span>
        {pageCount > 1 && <div className="flex items-center gap-2">
          <button className="fh-button-secondary fh-button-sm" type="button" disabled={page <= 1 || busy !== null} onClick={() => setPage(value => value - 1)}>{translate('workspace:sourceCentricWorkspace.previous')}</button>
          <span className="fh-text-caption">{translate('workspace:sourceCentricWorkspace.page')} {formatNumber(page)} {translate('workspace:sourceCentricWorkspace.of')} {formatNumber(pageCount)}</span>
          <button className="fh-button-secondary fh-button-sm" type="button" disabled={page >= pageCount || busy !== null} onClick={() => setPage(value => value + 1)}>{translate('workspace:sourceCentricWorkspace.next')}</button>
        </div>}
      </div>
      {busy && <p className="fh-text-caption" role="status">{busy}...</p>}
    </div>

    {bulkOpen && <BulkEditDialog
      grid={grid}
      descriptors={descriptors}
      channelById={channelById}
      channelFilter={channelFilter}
      pricingState={pricingState}
      onClose={() => setBulkOpen(false)}
      onApply={sections => {
        mutatePricingState(current => applyBulkSections(current, sections, descriptors, channelById, channelFilter))
        setBulkOpen(false)
      }}
    />}
    {reviewOpen && review && <ReviewDialog
      review={review}
      grid={grid}
      channelById={channelById}
      canApply={review.status === 'ready' && reviewContext !== null && busy === null}
      onApply={() => setConfirming(true)}
      onClose={() => setReviewOpen(false)}
    />}
    {confirming && reviewContext && grid && <div className="fh-pricing-dialog fixed inset-0 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label={translate('workspace:sourceCentricWorkspace.applyConfirmation')}><div className="fh-card fh-card-pad max-w-3xl">
      <h2 className="fh-page-title">{translate('workspace:sourceCentricWorkspace.confirmSelectedApply')}</h2>
      <p className="fh-text-caption mt-2">{translate('workspace:densePricing.confirmApplyScope', { count: reviewContext.selectedCount })}</p>
      {/* i18n-ignore: utility classes, not user-facing copy */}
      <div className="mt-4 max-h-[50vh] overflow-auto">
        <table className="fh-table min-w-[640px]">
          <thead><tr>
            <th>{translate('workspace:gridModel.product')}</th>
            <th>{translate('workspace:unifiedWorkspace.channel')}</th>
            <th>{translate('workspace:densePricing.field')}</th>
            <th>{translate('workspace:densePricing.previousValue')}</th>
            <th>{translate('workspace:gridModel.targetField', { field: '' })}</th>
          </tr></thead>
          <tbody>{reviewContext.operations.map(operation => {
            const product = grid.items.find(row => row.children.some(child => child.listingId === operation.listingId))
            return <tr key={operation.id}>
              <td>{product?.name ?? operation.canonicalProductId}</td>
              <td>{sourceChannelDisplayName(operation.channelId, channelById)}</td>
              <td>{formatField(operation.field)}</td>
              <td>{operation.current ?? '—'}</td>
              <td>{operation.target}</td>
            </tr>
          })}</tbody>
        </table>
      </div>
      <p className="fh-text-caption mt-3">{translate('workspace:densePricing.manifestAffectedChannels', { count: reviewContext.affectedChannelIds.length })}</p>
      {/* i18n-ignore: utility classes, not user-facing copy */}
      <div className="mt-5 flex justify-end gap-2">
        <button className="fh-button-secondary" type="button" disabled={busy !== null} onClick={() => setConfirming(false)}>{translate('workspace:sourceCentricWorkspace.cancel')}</button>
        <button className="fh-button-primary" type="button" disabled={busy !== null} onClick={() => void apply()}><Icon name="apply" /> {translate('workspace:sourceCentricWorkspace.confirmApply')}</button>
      </div>
    </div></div>}
    {applyResult && <ApplyResults result={applyResult} channelById={channelById} />}
  </>
  return embedded ? content : <PageShell>{content}</PageShell>
}

interface ProductGroupProps {
  product: GroupedProduct
  channelById: ReadonlyMap<string, SourceChannel>
  descriptorMap: ReadonlyMap<string, PricingFieldDescriptor>
  pricingState: PricingWorkspaceState
  rowMenuFor: string | null
  onToggleRowMenu: (listingId: string | null) => void
  onCommitEdit: (descriptor: PricingFieldDescriptor, rawValue: string) => void
  onResetListing: (listing: GroupedListing, product: GroupedProduct) => void
  onSetListingSelected: (listing: GroupedListing, product: GroupedProduct, selected: boolean) => void
  displayProfile: PricingDisplayProfile | null
}

const ROW_ACTIONS_MENU_MARGIN = 4
const ROW_ACTIONS_MENU_VIEWPORT_PADDING = 8

// The trigger lives inside .fh-products-card, which clips overflow-y for the
// table's own scroll region. An absolutely-positioned menu there gets hard-
// clipped for any row near the bottom (or the right edge, once the table's
// horizontal scroll kicks in on narrow viewports). Portaling to document.body
// with position: fixed escapes that ancestor entirely -- it reuses the same
// .fh-dropdown class (and its --fh-z-dropdown token) for styling, it just no
// longer inherits page-flow positioning from it.
function RowActionsMenu({
  listingId,
  open,
  onToggle,
  ariaLabel,
  children,
}: {
  listingId: string
  open: boolean
  onToggle: () => void
  ariaLabel: string
  children: ReactNode
}) {
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const [style, setStyle] = useState<{ top: number; left: number; visible: boolean }>({ top: 0, left: 0, visible: false })

  useLayoutEffect(() => {
    if (!open) { setStyle(current => current.visible ? { ...current, visible: false } : current); return }
    const reposition = () => {
      const trigger = triggerRef.current
      const menu = menuRef.current
      if (!trigger || !menu) return
      const triggerRect = trigger.getBoundingClientRect()
      const menuRect = menu.getBoundingClientRect()
      const rtl = document.documentElement.dir === 'rtl'
      const spaceBelow = window.innerHeight - triggerRect.bottom
      const openUpward = spaceBelow < menuRect.height + ROW_ACTIONS_MENU_MARGIN && triggerRect.top > menuRect.height + ROW_ACTIONS_MENU_MARGIN
      const rawLeft = rtl ? triggerRect.right - menuRect.width : triggerRect.left
      const maxLeft = window.innerWidth - menuRect.width - ROW_ACTIONS_MENU_VIEWPORT_PADDING
      const left = Math.min(Math.max(rawLeft, ROW_ACTIONS_MENU_VIEWPORT_PADDING), Math.max(maxLeft, ROW_ACTIONS_MENU_VIEWPORT_PADDING))
      const top = openUpward ? triggerRect.top - menuRect.height - ROW_ACTIONS_MENU_MARGIN : triggerRect.bottom + ROW_ACTIONS_MENU_MARGIN
      setStyle({ top, left, visible: true })
    }
    reposition()
    window.addEventListener('resize', reposition)
    window.addEventListener('scroll', reposition, true)
    return () => {
      window.removeEventListener('resize', reposition)
      window.removeEventListener('scroll', reposition, true)
    }
  }, [open])

  return (
    <div className="fh-row-actions" data-row-actions>
      <button
        ref={triggerRef}
        type="button"
        className="fh-row-actions-trigger"
        data-row-menu-trigger
        data-listing-id={listingId}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={onToggle}
      >
        <Icon name="more" size="sm" />
      </button>
      {open && createPortal(
        <div
          ref={menuRef}
          className="fh-dropdown fh-row-actions-menu"
          role="menu"
          data-row-actions-portal
          style={{ position: 'fixed', top: style.top, left: style.left, insetInlineEnd: 'auto', visibility: style.visible ? 'visible' : 'hidden' }}
        >
          {children}
        </div>,
        document.body,
      )}
    </div>
  )
}

const ProductGroup = memo(function ProductGroup({
  product,
  channelById,
  descriptorMap,
  pricingState,
  rowMenuFor,
  onToggleRowMenu,
  onCommitEdit,
  onResetListing,
  onSetListingSelected,
  displayProfile,
}: ProductGroupProps) {
  return (
    <tbody className="fh-products-group" data-product-group data-product-id={product.sourceProductId}>
      {product.children.map((listing, index) => {
        const channelName = sourceChannelDisplayName(listing.channelId, channelById)
        const changedIdentities = FIELDS
          .map(field => ({ productId: product.sourceProductId, listingId: listing.listingId, channelId: listing.channelId, field }))
          .filter(identity => pricingFieldChange(pricingState, identity))
        const hasChanges = changedIdentities.length > 0
        const allSelected = hasChanges && changedIdentities.every(identity => {
          const change = pricingFieldChange(pricingState, identity)
          return change ? isPricingFieldSelected(change) : false
        })
        return (
          <tr key={listing.listingId} data-pricing-row data-listing-id={listing.listingId} data-channel-id={listing.channelId}>
            {/* Every row keeps the same cell count (fixed table layout requires
                stable column counts per row); the product cell is only
                populated on the group's first row and left empty after. */}
            <td className="fh-products-product-cell">
              {index === 0 && <span className="fh-products-product-inner">
                <ProductThumbnail imageUrl={product.primaryImageUrl} />
                <span className="fh-products-name">{product.name}</span>
              </span>}
            </td>
            <td className="fh-products-channel-cell">{channelName}</td>
            <td className="fh-products-input-cell">
              <TargetInput
                descriptor={descriptorMap.get(fieldKey(product, listing, 'price'))}
                pricingState={pricingState}
                field="price"
                inputMode="decimal"
                ariaLabel={translate('products:products.fieldEditLabel', {
                  product: product.name,
                  channel: channelName,
                  field: formatField('price'),
                })}
                onCommit={onCommitEdit}
                displayProfile={displayProfile}
              />
            </td>
            <td className="fh-products-input-cell">
              <TargetInput
                descriptor={descriptorMap.get(fieldKey(product, listing, 'stock'))}
                pricingState={pricingState}
                field="stock"
                inputMode="numeric"
                narrow
                ariaLabel={translate('products:products.fieldEditLabel', {
                  product: product.name,
                  channel: channelName,
                  field: formatField('stock'),
                })}
                onCommit={onCommitEdit}
              />
            </td>
            <td className="fh-products-availability-cell">
              <AvailabilitySelect
                descriptor={descriptorMap.get(fieldKey(product, listing, 'status'))}
                channel={channelById.get(listing.channelId)}
                pricingState={pricingState}
                ariaLabel={translate('products:products.fieldEditLabel', {
                  product: product.name,
                  channel: channelName,
                  field: formatField('status'),
                })}
                onCommit={onCommitEdit}
              />
            </td>
            <td className="fh-products-sync-cell">{formatStatus(listing.cacheFreshness)}</td>
            <td className="fh-products-actions-cell">
              <RowActionsMenu
                listingId={listing.listingId}
                open={rowMenuFor === listing.listingId}
                onToggle={() => onToggleRowMenu(rowMenuFor === listing.listingId ? null : listing.listingId)}
                ariaLabel={translate('products:products.rowActions', {
                  product: product.name,
                  channel: channelName,
                })}
              >
                <button type="button" role="menuitem" className="fh-dropdown-item" data-row-menu-action="reset" disabled={!hasChanges} onClick={() => { onResetListing(listing, product); onToggleRowMenu(null) }}>
                  {translate('products:products.resetRowChanges')}
                </button>
                <button type="button" role="menuitem" className="fh-dropdown-item" data-row-menu-action="toggle-selection" disabled={!hasChanges} onClick={() => { onSetListingSelected(listing, product, !allSelected); onToggleRowMenu(null) }}>
                  {allSelected ? translate('products:products.excludeFromSave') : translate('products:products.includeInSave')}
                </button>
              </RowActionsMenu>
            </td>
          </tr>
        )
      })}
    </tbody>
  )
})

function ProductThumbnail({ imageUrl }: { imageUrl?: string | null }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [imageUrl])
  return (
    <span className="fh-products-thumb" aria-hidden="true" data-product-thumbnail>
      {imageUrl && !failed
        ? <img src={imageUrl} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} />
        : <Icon name="products" />}
    </span>
  )
}

interface TargetInputProps {
  descriptor: PricingFieldDescriptor | undefined
  pricingState: PricingWorkspaceState
  field: PricingField
  inputMode: 'decimal' | 'numeric'
  narrow?: boolean
  ariaLabel: string
  onCommit: (descriptor: PricingFieldDescriptor, rawValue: string) => void
  displayProfile?: PricingDisplayProfile | null
}

function TargetInput({ descriptor, pricingState, field, inputMode, narrow = false, ariaLabel, onCommit, displayProfile = null }: TargetInputProps) {
  const change = descriptor ? pricingFieldChange(pricingState, descriptor.identity) : undefined
  const committedValue = change?.targetValue ?? descriptor?.targetValue ?? descriptor?.currentValue ?? ''
  const displayedValue = field === 'price' && descriptor && displayProfile
    ? convertPricingUnit(committedValue, descriptor.currency, descriptor.unit, displayProfile.unit, displayProfile.currency)
    : committedValue
  const [draft, setDraft] = useState<string | null>(null)
  const status = cellEditStatus(descriptor, change)
  const disabled = !descriptor || !descriptor.policy.writable || descriptor.policy.comingSoon || !descriptor.policy.channelEnabled || !descriptor.policy.supported || !descriptor.policy.mapped
  return (
    <input
      className={`fh-cell-input ${narrow ? 'fh-cell-input-narrow' : ''}`}
      type="text"
      inputMode={inputMode}
      dir="ltr"
      value={draft ?? displayedValue}
      disabled={disabled}
      aria-label={ariaLabel}
      data-target-field={field}
      data-listing-id={descriptor?.identity.listingId}
      data-channel-id={descriptor?.identity.channelId}
      data-cell-status={status}
      onChange={event => setDraft(event.target.value)}
      onFocus={() => setDraft(displayedValue)}
      onBlur={() => {
        if (descriptor && draft !== null && draft.trim() !== displayedValue) {
          const nativeValue = field === 'price' && displayProfile
            ? convertPricingUnit(draft, descriptor.currency, displayProfile.unit, descriptor.unit, displayProfile.currency)
            : draft
          onCommit(descriptor, nativeValue)
        }
        setDraft(null)
      }}
      onKeyDown={event => {
        if (event.key === 'Enter') { event.preventDefault(); event.currentTarget.blur() }
        if (event.key === 'Escape') { setDraft(null); event.currentTarget.blur() }
      }}
    />
  )
}

interface AvailabilitySelectProps {
  descriptor: PricingFieldDescriptor | undefined
  channel: SourceChannel | undefined
  pricingState: PricingWorkspaceState
  ariaLabel: string
  onCommit: (descriptor: PricingFieldDescriptor, rawValue: string) => void
}

function AvailabilitySelect({ descriptor, channel, pricingState, ariaLabel, onCommit }: AvailabilitySelectProps) {
  const change = descriptor ? pricingFieldChange(pricingState, descriptor.identity) : undefined
  const value = change?.targetValue ?? descriptor?.targetValue ?? descriptor?.currentValue ?? ''
  const supported = channel ? capabilityStatuses(channel.capabilities) ?? [] : []
  const options = [...new Set([...(value ? [value] : []), ...supported])]
  const disabled = !descriptor || !descriptor.policy.writable || descriptor.policy.comingSoon || !descriptor.policy.channelEnabled || !descriptor.policy.supported || !descriptor.policy.mapped || options.length === 0
  const status = cellEditStatus(descriptor, change)
  if (!value && options.length === 0) {
    return <span className="fh-text-caption">{'—'}</span>
  }
  return (
    <span className="fh-availability" data-tone={statusTone(value)}>
      <select
        value={value}
        disabled={disabled}
        aria-label={ariaLabel}
        data-target-field="status"
        data-listing-id={descriptor?.identity.listingId}
        data-channel-id={descriptor?.identity.channelId}
        data-cell-status={status}
        onChange={event => { if (descriptor) onCommit(descriptor, event.target.value) }}
      >
        {options.map(option => <option key={option} value={option}>{formatStatus(option)}</option>)}
      </select>
      <Icon name="chevronDown" size="sm" className="fh-availability-caret" />
    </span>
  )
}

interface BulkSectionConfig {
  pricingEnabled: boolean
  pricingKind: Extract<BulkTransformationKind, 'increase_price_percent' | 'decrease_price_percent' | 'set_price'>
  pricingValue: string
  stockEnabled: boolean
  stockValue: string
  statusEnabled: boolean
  statusValue: string
  scope: 'all' | 'selected_channel'
}

interface BulkEditDialogProps {
  grid: GroupedWorkspacePage
  descriptors: readonly PricingFieldDescriptor[]
  channelById: ReadonlyMap<string, SourceChannel>
  channelFilter: string
  pricingState: PricingWorkspaceState
  onClose: () => void
  onApply: (sections: BulkSectionConfig) => void
}

// Figma: Modal/BulkEdit — Pricing, Stock Quantity, and Availability Status
// sections with channel scope and an auto-updating preview, applied to the
// local draft through the shared bulk transformation engine.
function BulkEditDialog({ grid, descriptors, channelById, channelFilter, pricingState, onClose, onApply }: BulkEditDialogProps) {
  const [pricingEnabled, setPricingEnabled] = useState(true)
  const [pricingKind, setPricingKind] = useState<BulkSectionConfig['pricingKind']>('increase_price_percent')
  const [pricingValue, setPricingValue] = useState('')
  const [stockEnabled, setStockEnabled] = useState(false)
  const [stockValue, setStockValue] = useState('')
  const [statusEnabled, setStatusEnabled] = useState(false)
  const [statusValue, setStatusValue] = useState('')
  const [scope, setScope] = useState<BulkSectionConfig['scope']>(channelFilter ? 'selected_channel' : 'all')

  const sections: BulkSectionConfig = {
    pricingEnabled, pricingKind, pricingValue,
    stockEnabled, stockValue,
    statusEnabled, statusValue,
    scope,
  }
  const scopedDescriptors = useMemo(
    () => bulkScopeDescriptors(descriptors, channelFilter, scope),
    [channelFilter, descriptors, scope],
  )
  const preview = useMemo(
    () => previewBulkSections(pricingState, sections, scopedDescriptors, channelById),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sections is rebuilt per render from its parts.
    [channelById, pricingState, scopedDescriptors, pricingEnabled, pricingKind, pricingValue, stockEnabled, stockValue, statusEnabled, statusValue],
  )
  const listingById = useMemo(() => {
    const map = new Map<string, { productName: string; sku: string | null }>()
    for (const product of grid.items) {
      for (const listing of product.children) {
        map.set(listing.listingId, { productName: product.name, sku: listing.sku })
      }
    }
    return map
  }, [grid])
  const statusOptions = useMemo(() => {
    const options = new Set<string>()
    for (const descriptor of scopedDescriptors) {
      if (descriptor.identity.field !== 'status') continue
      const channel = channelById.get(descriptor.identity.channelId)
      for (const status of channel ? capabilityStatuses(channel.capabilities) ?? [] : []) options.add(status)
    }
    return [...options]
  }, [channelById, scopedDescriptors])

  const scopedProducts = new Set(scopedDescriptors.map(descriptor => descriptor.identity.productId)).size
  const scopedListings = new Set(scopedDescriptors.map(descriptor => descriptor.identity.listingId)).size
  const channelCount = new Set(descriptors.map(descriptor => descriptor.identity.channelId)).size
  const affectedProducts = new Set(preview.items.filter(item => !item.blockedReason && item.resultingValue !== null).map(item => item.descriptor.identity.productId)).size
  const applyDisabled = preview.fieldsAffected === 0

  return (
    <div className="fh-pricing-dialog fixed inset-0 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" data-bulk-edit-dialog aria-label={translate('products:products.bulkEditProducts')}>
      <div className="fh-card fh-bulk-modal">
        <div className="fh-panel-header">
          <div className="min-w-0">
            <h2 className="fh-section-title">{translate('products:products.bulkEditProducts')}</h2>
            <p className="fh-text-caption fh-bulk-subtitle">
              <Badge variant="neutral">{translate('products:products.productsSelected', { value: formatNumber(scopedProducts) })}</Badge>
              <span>{translate('products:products.channelListingsAffected', { count: scopedListings, value: formatNumber(scopedListings) })}</span>
            </p>
          </div>
          <button type="button" className="fh-icon-button fh-bulk-close" aria-label={translate('workspace:sourceCentricWorkspace.cancel')} onClick={onClose}><Icon name="close" size="sm" /></button>
        </div>

        <div className="fh-bulk-body">
          <section className="fh-bulk-section" aria-label={translate('products:products.bulkPricing')}>
            <header className="fh-bulk-section-header">
              <span className="fh-bulk-section-title">{translate('products:products.bulkPricing')}</span>
              <BulkToggle checked={pricingEnabled} onChange={setPricingEnabled} label={translate('products:products.bulkPricing')} />
            </header>
            {pricingEnabled && <>
              <div className="fh-bulk-options" role="radiogroup" aria-label={translate('products:products.bulkPricing')}>
                {([
                  ['increase_price_percent', 'products:products.increaseByPercentage'],
                  ['decrease_price_percent', 'products:products.decreaseByPercentage'],
                  ['set_price', 'products:products.setFixedPrice'],
                ] as const).map(([kind, label]) => <label key={kind} className="fh-bulk-radio">
                  <input type="radio" name="bulk-pricing-kind" value={kind} checked={pricingKind === kind} onChange={() => setPricingKind(kind)} />
                  <span>{translate(label)}</span>
                </label>)}
              </div>
              <div className="fh-bulk-value">
                <input className="fh-cell-input" dir="ltr" inputMode="decimal" value={pricingValue} onChange={event => setPricingValue(event.target.value)} aria-label={translate('workspace:densePricing.bulkValue')} data-bulk-pricing-value />
                <span className="fh-text-caption">{pricingKind === 'set_price' ? '' : '%'}</span>
                <span className="fh-bulk-help">{translate('products:products.appliedToBasePrice')}</span>
              </div>
            </>}
          </section>

          <section className="fh-bulk-section" aria-label={translate('products:products.stockQuantity')}>
            <header className="fh-bulk-section-header">
              <span className="fh-bulk-section-title">{translate('products:products.stockQuantity')}</span>
              <BulkToggle checked={stockEnabled} onChange={setStockEnabled} label={translate('products:products.stockQuantity')} />
            </header>
            {stockEnabled && <>
              <div className="fh-bulk-options" role="radiogroup" aria-label={translate('products:products.stockQuantity')}>
                <label className="fh-bulk-radio">
                  <input type="radio" name="bulk-stock-kind" checked readOnly />
                  <span>{translate('products:products.setStockQuantity')}</span>
                </label>
              </div>
              <div className="fh-bulk-value">
                <input className="fh-cell-input fh-cell-input-narrow" dir="ltr" inputMode="numeric" value={stockValue} onChange={event => setStockValue(event.target.value)} aria-label={translate('products:products.stockQuantity')} data-bulk-stock-value />
                <span className="fh-text-caption">{translate('products:products.units')}</span>
                <span className="fh-bulk-help">{translate('products:products.stockOverwriteHelper')}</span>
              </div>
            </>}
          </section>

          <section className="fh-bulk-section" aria-label={translate('products:products.availabilityStatus')}>
            <header className="fh-bulk-section-header">
              <span className="fh-bulk-section-title">{translate('products:products.availabilityStatus')}</span>
              <BulkToggle checked={statusEnabled} onChange={setStatusEnabled} label={translate('products:products.availabilityStatus')} />
            </header>
            <div className="fh-bulk-columns">
              {statusEnabled && <div className="fh-bulk-options" role="radiogroup" aria-label={translate('products:products.availabilityStatus')}>
                {statusOptions.map(option => <label key={option} className="fh-bulk-radio">
                  <input type="radio" name="bulk-status-value" value={option} checked={statusValue === option} onChange={() => setStatusValue(option)} />
                  <span>{formatStatus(option)}</span>
                </label>)}
                <label className="fh-bulk-radio">
                  <input type="radio" name="bulk-status-value" value="" checked={statusValue === ''} onChange={() => setStatusValue('')} />
                  <span>{translate('products:products.noChange')}</span>
                </label>
              </div>}
              <div className="fh-bulk-scope">
                <span className="fh-bulk-section-title">{translate('products:products.channelScope')}</span>
                <label className="fh-bulk-radio">
                  <input type="radio" name="bulk-scope" value="all" checked={scope === 'all'} onChange={() => setScope('all')} />
                  <span>{translate('products:products.allChannelsCount', { value: formatNumber(channelCount) })}</span>
                </label>
                <label className="fh-bulk-radio">
                  <input type="radio" name="bulk-scope" value="selected_channel" checked={scope === 'selected_channel'} disabled={!channelFilter} onChange={() => setScope('selected_channel')} />
                  <span>{channelFilter
                    ? `${translate('products:products.selectedChannel')} · ${sourceChannelDisplayName(channelFilter, channelById)}`
                    : translate('products:products.selectedChannel')}</span>
                </label>
              </div>
            </div>
          </section>

          <section className="fh-bulk-preview" aria-label={translate('products:products.previewOfChanges')} data-bulk-preview>
            <header className="fh-bulk-preview-header">
              <span>{translate('products:products.previewOfChanges')}</span>
              <span className="fh-bulk-preview-live">{translate('products:products.autoUpdating')}</span>
            </header>
            {preview.items.length === 0
              ? <p className="fh-text-caption">{translate('workspace:densePricing.selectedRowsScope', { count: 0, value: formatNumber(0) })}</p>
              : <ul className="fh-bulk-preview-list">
                {preview.items.slice(0, 6).map(item => {
                  const listing = listingById.get(item.descriptor.identity.listingId)
                  return <li key={item.key} className="fh-bulk-preview-row">
                    <span className="fh-text-mono">{listing?.sku ?? item.descriptor.identity.productId}</span>
                    <span className="fh-bulk-preview-name">{listing?.productName ?? item.descriptor.identity.productId}</span>
                    <span className="fh-bulk-preview-values" dir="ltr">
                      {item.previousValue || '—'} → {item.blockedReason ? translate('workspace:sourceCentricWorkspace.blockedRows') : item.resultingValue ?? '—'}
                    </span>
                  </li>
                })}
              </ul>}
          </section>
        </div>

        <div className="fh-panel-footer">
          <button type="button" className="fh-button-secondary fh-button-sm" onClick={onClose}>{translate('workspace:sourceCentricWorkspace.cancel')}</button>
          <button type="button" className="fh-button-primary fh-button-sm" data-bulk-apply disabled={applyDisabled} onClick={() => onApply(sections)}>
            {translate('products:products.applyToDraft', { value: formatNumber(affectedProducts) })}
          </button>
        </div>
      </div>
    </div>
  )
}

function BulkToggle({ checked, onChange, label }: { checked: boolean; onChange: (next: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={`fh-bulk-toggle ${checked ? 'fh-bulk-toggle-on' : ''}`}
      onClick={() => onChange(!checked)}
    >
      <span className="fh-bulk-toggle-knob" />
    </button>
  )
}

function ReviewDialog({ review, grid, channelById, canApply, onApply, onClose }: { review: ReviewResource; grid: GroupedWorkspacePage; channelById: ReadonlyMap<string, SourceChannel>; canApply: boolean; onApply: () => void; onClose: () => void }) {
  return <div className="fh-pricing-dialog fixed inset-0 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label={translate('workspace:unifiedWorkspace.reviewChanges')}><div className="fh-card max-h-[88vh] w-full max-w-6xl overflow-auto"><div className="fh-panel-header"><div><h2 className="fh-page-title">{translate('workspace:unifiedWorkspace.reviewChanges')}</h2><p className="fh-text-caption">{translate('workspace:densePricing.reviewSummary', { total: review.summary.total, selected: review.items.filter(item => item.selected).length, blocked: review.summary.blocked })}</p></div><button className="fh-button-secondary fh-button-sm" onClick={onClose}>{translate('workspace:densePricing.backToGrid')}</button></div><div className="overflow-x-auto"><table className="fh-table min-w-[900px]"><thead><tr><th>{translate('workspace:gridModel.product')}</th><th>{translate('workspace:unifiedWorkspace.channel')}</th><th>{translate('workspace:densePricing.field')}</th><th>{translate('workspace:densePricing.previousValue')}</th><th>{translate('workspace:gridModel.targetField', { field: '' })}</th><th>{translate('workspace:sourceCentricWorkspace.selected')}</th></tr></thead><tbody>{review.items.map(item => { const product = grid.items.find(row => row.children.some(child => child.listingId === item.listingId)); return <tr key={item.id}><td>{product?.name ?? item.canonicalProductId}</td><td>{sourceChannelDisplayName(item.channelId, channelById)}</td><td>{formatField(item.field)}</td><td>{item.current ?? '—'}</td><td>{item.target}</td><td>{item.selected ? '✓' : '—'}</td></tr> })}</tbody></table></div><div className="fh-panel-footer"><button className="fh-button-secondary" type="button" onClick={onClose}>{translate('workspace:densePricing.backToGrid')}</button><button className="fh-button-primary" type="button" data-pricing-apply disabled={!canApply} onClick={onApply}><Icon name="apply" /> {translate('workspace:sourceCentricWorkspace.apply')}</button></div></div></div>
}

function ApplyResults({ result, channelById }: { result: ApplyResource; channelById: ReadonlyMap<string, SourceChannel> }) {
  return <section className="fh-card fh-card-pad" aria-label={translate('workspace:sourceCentricWorkspace.applyResults')}><h2 className="fh-section-title">{translate('workspace:sourceCentricWorkspace.applyResultStatus', { status: formatStatus(result.status) })}</h2><p className="fh-text-caption">{translate('workspace:sourceCentricWorkspace.verifiedSuccessIsShownOnlyAfterExact')}</p><div className="mt-3 grid gap-2">{result.items.map(item => <div className="flex items-center gap-2 rounded border border-border p-2" key={item.id}><Icon name={item.status === 'applied' ? 'success' : item.status === 'failed' ? 'error' : 'warning'} /><span>{sourceChannelDisplayName(item.channelId, channelById)} · {formatField(item.field)}</span><strong className="ms-auto">{formatStatus(item.status)}</strong></div>)}</div></section>
}

// -- Presentation helpers ----------------------------------------------------

export function sourceChannelDisplayName(
  channelId: string,
  channelById: ReadonlyMap<string, SourceChannel>,
): string {
  const channel = channelById.get(channelId)
  return formatSourceChannelDisplayName(channel ?? { channelId })
}

function fieldKey(product: GroupedProduct, listing: GroupedListing, field: PricingField): string {
  return pricingFieldKey({ productId: product.sourceProductId, listingId: listing.listingId, channelId: listing.channelId, field })
}

function cellEditStatus(descriptor: PricingFieldDescriptor | undefined, change: PricingFieldChange | null | undefined): string {
  if (!descriptor) return 'unavailable'
  if (change) return descriptor.policy.valid ? 'edited' : 'blocked'
  if (!descriptor.policy.writable || descriptor.policy.comingSoon || !descriptor.policy.supported || !descriptor.policy.mapped || !descriptor.policy.channelEnabled) return 'read_only'
  return descriptor.policy.valid ? 'unchanged' : 'blocked'
}

const AVAILABLE_STATUS_LITERALS = new Set(['instock', 'in_stock', 'active', 'publish', 'published', 'available', 'enabled'])
const UNAVAILABLE_STATUS_LITERALS = new Set(['outofstock', 'out_of_stock', 'inactive', 'unavailable', 'disabled', 'archived'])

function statusTone(value: string): 'success' | 'warning' | 'danger' | 'neutral' {
  const literal = value.trim().toLowerCase()
  if (!literal) return 'neutral'
  if (AVAILABLE_STATUS_LITERALS.has(literal)) return 'success'
  if (UNAVAILABLE_STATUS_LITERALS.has(literal)) return 'danger'
  return 'warning'
}

function formatPricingUnitLabel(currency: string, unit: string): string {
  const normalizedCurrency = currency.trim().toUpperCase()
  const normalizedUnit = unit.trim().toUpperCase()
  if (normalizedCurrency === 'IRR' && normalizedUnit === 'RIAL') return translate('settings:settings.rial')
  if (normalizedCurrency === 'IRR' && normalizedUnit === 'TOMAN') return translate('settings:settings.toman')
  return formatCurrencyLabel(normalizedCurrency)
}

/** Exact presentation-only conversion between the two explicitly declared IRR
 * units. Unsupported/malformed values stay unchanged and are never guessed. */
export function convertPricingUnit(
  value: string,
  valueCurrency: string | null | undefined,
  fromUnit: string | null | undefined,
  toUnit: string | null | undefined,
  displayCurrency: string | null | undefined,
): string {
  const currency = valueCurrency?.trim().toUpperCase()
  if (!currency || currency !== displayCurrency?.trim().toUpperCase()) return value
  const from = normalizeIrrUnit(fromUnit)
  const to = normalizeIrrUnit(toUnit)
  if (currency !== 'IRR' || !from || !to || from === to) return value
  return shiftDecimal(value, from === 'RIAL' && to === 'TOMAN' ? -1 : 1)
}

function normalizeIrrUnit(unit: string | null | undefined): 'RIAL' | 'TOMAN' | null {
  const normalized = unit?.trim().toUpperCase()
  if (normalized === 'IRR' || normalized === 'RIAL') return 'RIAL'
  return normalized === 'TOMAN' ? 'TOMAN' : null
}

function shiftDecimal(value: string, places: -1 | 1): string {
  const match = value.trim().match(/^([+-]?)(\d+)(?:\.(\d+))?$/)
  if (!match) return value
  const [, sign, integer, fraction = ''] = match
  const digits = `${integer}${fraction}`
  const decimalAt = integer.length + places
  const padded = decimalAt <= 0
    ? `${'0'.repeat(-decimalAt + 1)}${digits}`
    : decimalAt >= digits.length
      ? `${digits}${'0'.repeat(decimalAt - digits.length)}`
      : digits
  const splitAt = decimalAt <= 0 ? 1 : decimalAt
  const rawInteger = padded.slice(0, splitAt) || '0'
  const rawFraction = padded.slice(splitAt)
  const normalizedInteger = rawInteger.replace(/^0+(?=\d)/, '') || '0'
  const normalizedFraction = rawFraction.replace(/0+$/, '')
  const normalized = normalizedFraction ? `${normalizedInteger}.${normalizedFraction}` : normalizedInteger
  return `${normalized === '0' ? '' : sign}${normalized}`
}

export function bulkScopeDescriptors(
  descriptors: readonly PricingFieldDescriptor[],
  channelFilter: string,
  scope: 'all' | 'selected_channel',
): PricingFieldDescriptor[] {
  if (scope === 'selected_channel' && channelFilter) {
    return descriptors.filter(descriptor => descriptor.identity.channelId === channelFilter)
  }
  return [...descriptors]
}

interface ComposedBulkPreview {
  items: BulkTransformationPreview['items']
  fieldsAffected: number
}

function bulkSectionTransformations(sections: BulkSectionConfig): Array<{ kind: BulkTransformationKind; value: string; field: PricingField }> {
  const transformations: Array<{ kind: BulkTransformationKind; value: string; field: PricingField }> = []
  if (sections.pricingEnabled && sections.pricingValue.trim()) {
    transformations.push({ kind: sections.pricingKind, value: sections.pricingValue.trim(), field: 'price' })
  }
  if (sections.stockEnabled && sections.stockValue.trim()) {
    transformations.push({ kind: 'set_stock', value: sections.stockValue.trim(), field: 'stock' })
  }
  if (sections.statusEnabled && sections.statusValue.trim()) {
    transformations.push({ kind: 'set_status', value: sections.statusValue.trim(), field: 'status' })
  }
  return transformations
}

function previewBulkSections(
  state: PricingWorkspaceState,
  sections: BulkSectionConfig,
  scopedDescriptors: readonly PricingFieldDescriptor[],
  channelById: ReadonlyMap<string, SourceChannel>,
): ComposedBulkPreview {
  let current = state
  const items: BulkPreviewItem[] = []
  let fieldsAffected = 0
  for (const transformation of bulkSectionTransformations(sections)) {
    const validatedScope = scopedDescriptors.map(descriptor => validateDescriptorTarget(
      descriptor,
      channelById.get(descriptor.identity.channelId),
      transformation.kind === 'set_status' && descriptor.identity.field === 'status'
        ? transformation.value
        : pricingFieldChange(current, descriptor.identity)?.targetValue ?? descriptor.targetValue ?? descriptor.currentValue ?? '',
    ))
    const preview = previewBulkTransformation(current, validatedScope, { kind: transformation.kind, value: transformation.value })
    items.push(...preview.items.filter(item => item.descriptor.identity.field === transformation.field))
    fieldsAffected += preview.fieldsAffected
    current = applyBulkTransformation(current, preview)
  }
  return { items, fieldsAffected }
}

export function applyBulkSections(
  state: PricingWorkspaceState,
  sections: BulkSectionConfig,
  descriptors: readonly PricingFieldDescriptor[],
  channelById: ReadonlyMap<string, SourceChannel>,
  channelFilter: string,
): PricingWorkspaceState {
  const scoped = bulkScopeDescriptors(descriptors, channelFilter, sections.scope)
  let current = state
  for (const transformation of bulkSectionTransformations(sections)) {
    const validatedScope = scoped.map(descriptor => validateDescriptorTarget(
      descriptor,
      channelById.get(descriptor.identity.channelId),
      transformation.kind === 'set_status' && descriptor.identity.field === 'status'
        ? transformation.value
        : pricingFieldChange(current, descriptor.identity)?.targetValue ?? descriptor.targetValue ?? descriptor.currentValue ?? '',
    ))
    current = applyBulkTransformation(current, previewBulkTransformation(current, validatedScope, { kind: transformation.kind, value: transformation.value }))
  }
  return current
}

// -- Safety-critical helpers (exports covered by DensePricingWorkspace.safety.test) --

export function pricingDescriptors(grid: GroupedWorkspacePage, channelById: ReadonlyMap<string, SourceChannel>): PricingFieldDescriptor[] {
  return grid.items.flatMap(product => product.children.flatMap(listing => (['price', 'stock', 'status'] as PricingField[]).map(field => {
    const cell = listing.fields[field]
    const channel = channelById.get(listing.channelId)
    const productWritable = product.productType !== 'variable'
    const mapped = listing.mappingState === 'resolved'
    // A Listing summary may be blocked because one sibling field is invalid.
    // Eligibility remains field-specific so a blocked Stock value cannot suppress
    // an otherwise safe Price change on the same Listing.
    const sourceValid = cell.status !== 'blocked'
    const comingSoon = channel ? channel.implementationState !== 'implemented' || !channel.available : false
    const supported = !comingSoon && channelSupportsWrite(channel, field)
    const channelEnabled = channel?.enabled === true
    const descriptor: PricingFieldDescriptor = {
      identity: { productId: product.sourceProductId, listingId: listing.listingId, channelId: listing.channelId, field },
      currentValue: cell.current,
      targetValue: cell.target,
      currency: cell.currency,
      unit: cell.unit,
      decimalScale: field === 'stock' ? 0 : undefined,
      policy: {
        writable: productWritable && !cell.readOnly,
        mapped,
        supported,
        channelEnabled,
        comingSoon,
        valid: sourceValid,
        blockedReason: !productWritable
          ? 'variable_parent'
          : !channel
            ? 'channel_capability_unavailable'
          : !channelEnabled
            ? 'channel_disabled'
            : comingSoon
              ? 'coming_soon'
              : !mapped
                ? 'mapping_required'
                : !supported
                  ? 'unsupported_field'
                  : !sourceValid
                    ? 'validation_blocked'
                    : cell.readOnly
                      ? 'read_only'
                      : null,
        warning: sourceValid && listing.cacheFreshness !== 'fresh' ? 'cache_freshness' : null,
      },
    }
    return validateDescriptorTarget(descriptor, channel, cell.target ?? cell.current ?? '')
  })))
}

const WRITE_CAPABILITY_KEYS: Record<PricingField, readonly [string, ...string[]]> = {
  price: ['writePrice', 'price_write', 'write_prices'],
  stock: ['writeStock', 'stock_write', 'write_stock'],
  status: ['writeStatus', 'status_write', 'write_status'],
}

function channelSupportsWrite(channel: SourceChannel | undefined, field: PricingField): boolean {
  if (!channel) return false
  const capabilities = channel.capabilities
  const writeAvailable = strictCapability(capabilities, ['writeAvailable', 'write_available'])
  if (writeAvailable === false) return false
  return strictCapability(capabilities, WRITE_CAPABILITY_KEYS[field]) === true
}

/**
 * Reads the production camelCase key first. Compatibility aliases are accepted only when
 * the production key is absent, and only literal booleans are trusted.
 */
function strictCapability(capabilities: Readonly<Record<string, unknown>>, keys: readonly string[]): boolean | undefined {
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(capabilities, key)) continue
    return typeof capabilities[key] === 'boolean' ? capabilities[key] : false
  }
  return undefined
}

function capabilityText(capabilities: Readonly<Record<string, unknown>>, primary: string, compatibility?: string): string | null {
  const key = Object.prototype.hasOwnProperty.call(capabilities, primary)
    ? primary
    : compatibility && Object.prototype.hasOwnProperty.call(capabilities, compatibility)
      ? compatibility
      : null
  if (!key) return null
  const value = capabilities[key]
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function capabilityStatuses(capabilities: Readonly<Record<string, unknown>>): readonly string[] | null {
  const value = Object.prototype.hasOwnProperty.call(capabilities, 'supportedStatuses')
    ? capabilities.supportedStatuses
    : capabilities.supported_statuses
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string' || !item.trim())) return null
  return value.map(item => String(item).trim())
}

export function validateDescriptorTarget(
  descriptor: PricingFieldDescriptor,
  channel: SourceChannel | undefined,
  targetValue: string,
): PricingFieldDescriptor {
  if (!descriptor.policy.valid || !channel) return descriptor
  const capabilities = channel.capabilities
  let semanticValid = true
  let blockedReason: string | null = descriptor.policy.blockedReason ?? null

  if (descriptor.identity.field === 'price') {
    const expectedCurrency = capabilityText(capabilities, 'currency')?.toUpperCase() ?? null
    const expectedUnit = capabilityText(capabilities, 'unit')?.toUpperCase() ?? null
    const actualCurrency = descriptor.currency?.trim().toUpperCase() || null
    const actualUnit = descriptor.unit?.trim().toUpperCase() || null
    semanticValid = Boolean(
      expectedCurrency
      && expectedUnit
      && actualCurrency
      && actualUnit
      && !['TMN', 'TOMAN'].includes(expectedCurrency)
      && expectedCurrency === actualCurrency
      && expectedUnit === actualUnit,
    )
    if (!semanticValid && !blockedReason) blockedReason = 'currency_unit_invalid'
  }

  if (descriptor.identity.field === 'status') {
    const supportedStatuses = capabilityStatuses(capabilities)
    const target = targetValue.trim()
    semanticValid = Boolean(supportedStatuses && target && supportedStatuses.includes(target))
    if (!semanticValid && !blockedReason) blockedReason = 'unsupported_status'
  }

  if (semanticValid) return descriptor
  return {
    ...descriptor,
    policy: { ...descriptor.policy, valid: false, blockedReason },
  }
}

export function resolveExactReviewSelection(
  reviewItems: readonly ReviewItemResource[],
  selectedChanges: readonly PricingFieldChange[],
): string[] {
  const reviewItemsByKey = new Map<string, ReviewItemResource[]>()
  for (const item of reviewItems) {
    const key = pricingFieldKey({
      productId: item.canonicalProductId,
      listingId: item.listingId,
      channelId: item.channelId,
      field: item.field,
    })
    const matches = reviewItemsByKey.get(key) ?? []
    matches.push(item)
    reviewItemsByKey.set(key, matches)
  }

  const ids: string[] = []
  for (const change of selectedChanges) {
    const matches = reviewItemsByKey.get(change.key) ?? []
    if (matches.length !== 1 || !matches[0].eligible) {
      throw new Error('Selected pricing scope does not match one eligible Review item per field.')
    }
    ids.push(matches[0].id)
  }
  if (new Set(ids).size !== selectedChanges.length) {
    throw new Error('Selected pricing scope contains duplicate Review identities.')
  }
  return ids
}

export function refreshRegisteredPricingState(
  state: PricingWorkspaceState,
  descriptors: readonly PricingFieldDescriptor[],
): { state: PricingWorkspaceState; changed: boolean } {
  const refreshed = registerPricingFields(state, descriptors)
  return { state: refreshed, changed: refreshed !== state }
}

export interface LatestGridLoader<T> {
  run(load: () => Promise<T>, commit: (result: T) => void, fail?: (error: unknown) => void): Promise<boolean>
  cancel(): void
}

export function createLatestGridLoader<T>(): LatestGridLoader<T> {
  let latestRequest = 0
  return {
    async run(load, commit, fail) {
      const request = ++latestRequest
      try {
        const result = await load()
        if (request !== latestRequest) return false
        commit(result)
        return true
      } catch (error) {
        if (request !== latestRequest) return false
        if (!fail) throw error
        fail(error)
        return false
      }
    },
    cancel() { latestRequest += 1 },
  }
}

/**
 * Product-level selection is a convenience projection over authoritative
 * immutable field identities. Unchanged fields are skipped and the existing
 * field policy rejects blocked or otherwise ineligible changed fields.
 */
export function setProductListingsSelected(
  state: PricingWorkspaceState,
  descriptors: readonly PricingFieldDescriptor[],
  listingIds: ReadonlySet<string>,
  selected: boolean,
): PricingWorkspaceState {
  let next = state
  for (const descriptor of descriptors) {
    if (!listingIds.has(descriptor.identity.listingId) || !pricingFieldChange(next, descriptor.identity)) continue
    next = setPricingFieldSelected(next, descriptor.identity, selected)
  }
  return next
}

function restoreState(workspaceId: string, scopeId: string): PricingWorkspaceState {
  if (typeof window === 'undefined') return createPricingWorkspaceState(workspaceId, [], scopeId)
  try { return restorePricingWorkspaceState(window.sessionStorage, workspaceId, scopeId) } catch { return createPricingWorkspaceState(workspaceId, [], scopeId) }
}
