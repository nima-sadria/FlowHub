import { HotTable, type HotTableRef } from '@handsontable/react-wrapper'
import Handsontable from 'handsontable'
import { CheckboxCellType, NumericCellType, TextCellType, registerCellType } from 'handsontable/cellTypes'
import {
  Autofill,
  CopyPaste,
  DataProvider,
  DragToScroll,
  DropdownMenu,
  Filters,
  ManualColumnResize,
  MultiColumnSorting,
  NestedHeaders,
  StretchColumns,
  registerPlugin,
} from 'handsontable/plugins'
import type { BaseRenderer } from 'handsontable/renderers'
import 'handsontable/styles/handsontable.min.css'
import 'handsontable/styles/ht-theme-main.min.css'
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Icon from '../../components/Icon'
import PageShell from '../../components/PageShell'
import { ResourceOptionGroups, ResourceSectionList, ResourceStateBadge } from '../../components/ResourceOrdering'
import { translate } from '../../i18n'
import { formatField, formatStatus } from '../../i18n/display'
import { localizedApiError } from '../../i18n/errors'
import { formatNumber } from '../../i18n/format'
import { useNotification } from '../../notifications/NotificationProvider'
import type { UnifiedWorkspaceService } from '../../services/unifiedWorkspace/UnifiedWorkspaceService'
import type { ApplyResource, ReviewItemResource, ReviewResource, UnifiedWorkspaceResource } from '../../services/unifiedWorkspace/types'
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
  type BulkTransformationKind,
  type BulkTransformationPreview,
  type PricingFieldDescriptor,
  type PricingFieldChange,
  type PricingFieldIdentity,
  type PricingWorkspaceState,
} from '../pricingWorkspace'
import { channelIdentitySignals, prepareResourceCollection, sourceChannelSignals } from '../resourceOrdering/resourceOrdering'
import { formatChannelDisplayName } from '../unifiedWorkspace/channelDisplayName'
import { sanitizeGridHtml } from '../unifiedWorkspace/handsontableIdentity'
import { resolveHandsontableLicense } from '../unifiedWorkspace/handsontableLicense'
import { workspaceApplyIdempotencyKey } from '../unifiedWorkspace/useUnifiedWorkspaceController'
import { inputHint } from '../../utils/inputHint'
import { sourceWorkspaceApi } from './api'
import PricingWorkspaceStartup from './PricingWorkspaceStartup'
import {
  buildDensePricingDefinition,
  cellIsReadOnly,
  cellStatus,
  identityForCell,
  listingIdsForRecord,
  type DensePricingDefinition,
  type DensePricingColumnMeta,
  type DensePricingRecord,
  type PricingField,
} from './densePricingGrid'
import type { GroupedWorkspacePage, SourceChannel } from './types'

registerCellType(CheckboxCellType)
registerCellType(NumericCellType)
registerCellType(TextCellType)
for (const plugin of [
  Autofill,
  CopyPaste,
  DataProvider,
  DragToScroll,
  DropdownMenu,
  Filters,
  ManualColumnResize,
  MultiColumnSorting,
  NestedHeaders,
  StretchColumns,
]) registerPlugin(plugin)

type View = 'changed' | 'ready' | 'blocked' | 'unchanged' | 'all'

interface ReviewContext {
  reviewId: string
  revisionId: string
  selectionChecksum: string
  selectedCount: number
}

const BULK_ACTIONS: Array<{ kind: BulkTransformationKind; label: string }> = [
  { kind: 'set_price', label: 'workspace:densePricing.setExactPrice' },
  { kind: 'increase_price_fixed', label: 'workspace:densePricing.increasePriceFixed' },
  { kind: 'decrease_price_fixed', label: 'workspace:densePricing.decreasePriceFixed' },
  { kind: 'increase_price_percent', label: 'workspace:densePricing.increasePricePercent' },
  { kind: 'decrease_price_percent', label: 'workspace:densePricing.decreasePricePercent' },
  { kind: 'set_stock', label: 'workspace:densePricing.setStock' },
  { kind: 'set_status', label: 'workspace:densePricing.setStatus' },
]

export interface DensePricingWorkspaceProps {
  workspace: UnifiedWorkspaceResource
  service: UnifiedWorkspaceService
  /** Products owns the sole page shell when the pricing grid is embedded on /products. */
  embedded?: boolean
  categoryOptions?: readonly { value: string; label: string }[]
}

interface DensePricingGridProps {
  definition: DensePricingDefinition
  gridMinWidth: number
  height: number
  hotRef: React.RefObject<HotTableRef>
  licenseKey: string
  onChange: (changes: Handsontable.CellChange[] | null, source: Handsontable.ChangeSource) => void
  onSelection: (startRow: number, startColumn: number, endRow: number, endColumn: number) => void
  onKeyDown: (event: KeyboardEvent) => void
}

const DensePricingGrid = memo(function DensePricingGrid({
  definition,
  gridMinWidth,
  height,
  hotRef,
  licenseKey,
  onChange,
  onSelection,
  onKeyDown,
}: DensePricingGridProps) {
  const cellProperties = useCallback(
    (row: number, _column: number, prop: string | number) => gridCellSettings(hotRef, definition.columnMeta, row, prop),
    [definition.columnMeta, hotRef],
  )
  const annotateCell = useCallback(
    (td: HTMLTableCellElement, visualRow: number, _visualColumn: number, prop: string | number) => {
      annotatePricingCell(hotRef, definition.columnMeta, td, visualRow, prop)
    },
    [definition.columnMeta, hotRef],
  )
  const markVirtualViewport = useCallback(() => {
    const viewport = hotRef.current?.hotInstance?.rootElement.querySelector<HTMLElement>('.wtHolder')
    if (viewport?.dataset.pricingVirtualViewport !== 'true') viewport?.setAttribute('data-pricing-virtual-viewport', 'true')
  }, [hotRef])

  return (
    <div className="ht-theme-main fh-handsontable fh-pricing-grid" data-pricing-grid style={{ minWidth: gridMinWidth }}>
      <HotTable
        ref={hotRef}
        data={definition.records}
        columns={definition.columns}
        nestedHeaders={definition.nestedHeaders}
        rowHeaders
        width="100%"
        height={height}
        rowHeights={30}
        autoColumnSize={false}
        autoRowSize={false}
        columnHeaderHeight={28}
        fixedColumnsStart={5}
        stretchH="none"
        renderAllRows={false}
        renderAllColumns={false}
        viewportRowRenderingOffset={8}
        viewportColumnRenderingOffset={4}
        manualColumnResize
        multiColumnSorting
        filters
        dropdownMenu={['filter_by_condition', 'filter_by_value', 'filter_action_bar']}
        copyPaste={{ pasteMode: 'overwrite' }}
        fillHandle={{ autoInsertRow: false }}
        undo={false}
        licenseKey={licenseKey}
        sanitizer={sanitizeGridHtml}
        cells={cellProperties}
        afterChange={onChange}
        afterSelection={onSelection}
        beforeKeyDown={onKeyDown}
        afterRenderer={annotateCell}
        afterRender={markVirtualViewport}
      />
    </div>
  )
})

export default function DensePricingWorkspace({ workspace, service, embedded = false, categoryOptions = [] }: DensePricingWorkspaceProps) {
  const notify = useNotification()
  const hotRef = useRef<HotTableRef>(null)
  const gridLoaderRef = useRef(createLatestGridLoader<GroupedWorkspacePage>())
  const persistenceScope = `${workspace.snapshot.id}:${workspace.snapshot.checksum}:${workspace.draft.id}`
  const [grid, setGrid] = useState<GroupedWorkspacePage | null>(null)
  const [channelInventory, setChannelInventory] = useState<SourceChannel[]>([])
  const [channelInventoryReady, setChannelInventoryReady] = useState(false)
  const [page, setPage] = useState(1)
  const [view, setView] = useState<View>(() => workspace.entryPoint === 'manual' ? 'all' : 'changed')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [channelFilter, setChannelFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [productTypeFilter, setProductTypeFilter] = useState<'' | 'simple' | 'variable' | 'variation'>('')
  const [stockFilter, setStockFilter] = useState<'' | 'in_stock' | 'out_of_stock'>('')
  const [pricingState, setPricingState] = useState<PricingWorkspaceState>(() => restoreState(workspace.id, persistenceScope))
  const pricingStateRef = useRef(pricingState)
  const [draftVersion, setDraftVersion] = useState(workspace.draft.version)
  const [busy, setBusy] = useState<string | null>(null)
  const [review, setReview] = useState<ReviewResource | null>(null)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [localReviewOpen, setLocalReviewOpen] = useState(false)
  const [reviewContext, setReviewContext] = useState<ReviewContext | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [applyResult, setApplyResult] = useState<ApplyResource | null>(null)
  const [selectedRowKeys, setSelectedRowKeys] = useState<Set<string>>(new Set())
  const [bulkKind, setBulkKind] = useState<BulkTransformationKind>('increase_price_percent')
  const [bulkValue, setBulkValue] = useState('5')
  const [bulkPreview, setBulkPreview] = useState<BulkTransformationPreview | null>(null)
  const [tableHeight, setTableHeight] = useState(() => viewportTableHeight())
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
      // Keep the last verified inventory. If none exists, the Grid remains a
      // useful cached read surface while all target fields fail closed.
      setChannelInventoryError(localizedApiError(error, 'products:products.inlinePricingUnavailable'))
    } finally {
      setChannelInventoryReady(true)
    }
  }, [])

  useEffect(() => {
    void load()
    return () => gridLoaderRef.current.cancel()
  }, [load])
  useEffect(() => {
    void loadChannelInventory()
  }, [loadChannelInventory])
  useEffect(() => {
    let frame = 0
    const resize = () => {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(() => {
        const nextHeight = viewportTableHeight()
        setTableHeight(current => current === nextHeight ? current : nextHeight)
      })
    }
    window.addEventListener('resize', resize)
    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('resize', resize)
    }
  }, [])
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
  const stableChannelIds = useMemo(() => channelResources.ordered
    .filter(channel => channel.section === 'active')
    .map(channel => channel.id), [channelResources])
  const displayedChannelIds = useMemo(() => channelFilter ? [channelFilter] : stableChannelIds, [channelFilter, stableChannelIds])
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
    setLocalReviewOpen(false)
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
          fields: Object.fromEntries(Object.entries(listing.fields).map(([field, value]) => [field, { ...value, readOnly: true }])) as GroupedWorkspacePage['items'][number]['children'][number]['fields'],
        }),
    })),
  } : null, [channelById, channelFilter, grid])
  const definition = useMemo(() => visibleGrid ? buildDensePricingDefinition(visibleGrid, identity => {
    const change = pricingFieldChange(pricingState, identity)
    return change ? { targetValue: change.targetValue, selected: isPricingFieldSelected(change) } : null
  }, displayedChannelIds) : null, [displayedChannelIds, pricingState, visibleGrid])
  const visibleKeys = useMemo(() => new Set(visibleDescriptors.map(descriptor => pricingFieldKey(descriptor.identity))), [visibleDescriptors])
  const summary = useMemo(() => pricingWorkspaceSummary(pricingState, visibleKeys), [pricingState, visibleKeys])
  const bulkScopeCount = selectedRowKeys.size || new Set(selectedPricingChanges(pricingState).map(change => change.identity.listingId)).size
  const pageCount = Math.max(1, Math.ceil((grid?.total ?? 0) / (grid?.pageSize || 100)))
  const gridMinWidth = Math.max(1180, (definition?.columns.length ?? 1) * 104)
  const license = resolveHandsontableLicense(import.meta.env.VITE_HANDSONTABLE_LICENSE_KEY, import.meta.env.PROD)
  const mutatePricingState = useCallback((update: (current: PricingWorkspaceState) => PricingWorkspaceState) => {
    setPricingState(current => update(current))
    setReview(null)
    setReviewContext(null)
    setReviewOpen(false)
    setLocalReviewOpen(false)
    setApplyResult(null)
  }, [])

  const handleGridChanges = useCallback((changes: Handsontable.CellChange[] | null, source: Handsontable.ChangeSource) => {
    if (!changes || source === 'loadData' || !definition) return
    const targetEdits: Array<{ descriptor: PricingFieldDescriptor; targetValue: string }> = []
    const selections: Array<{ identity: PricingFieldIdentity; selected: boolean }> = []
    const productSelections: Array<{ listingIds: ReadonlySet<string>; selected: boolean }> = []
    for (const [visualRow, propValue, , value] of changes) {
      const prop = String(propValue)
      const physicalRow = hotRef.current?.hotInstance?.toPhysicalRow(visualRow) ?? visualRow
      const record = hotRef.current?.hotInstance?.getSourceDataAtRow(physicalRow) as DensePricingRecord | undefined
      const meta = definition.columnMeta.get(prop)
      if (!record || !meta) continue
      if (meta.kind === 'product_selection') {
        productSelections.push({ listingIds: listingIdsForRecord(record, definition.channelIds), selected: Boolean(value) })
        continue
      }
      const identity = identityForCell(record, meta)
      if (!identity) continue
      if (meta.kind === 'selection') selections.push({ identity, selected: Boolean(value) })
      if (meta.kind === 'target') {
        const descriptor = descriptorMap.get(pricingFieldKey(identity))
        if (descriptor) {
          const targetValue = String(value ?? '')
          targetEdits.push({
            descriptor: validateDescriptorTarget(descriptor, channelById.get(identity.channelId), targetValue),
            targetValue,
          })
        }
      }
    }
    if (!targetEdits.length && !selections.length && !productSelections.length) return
    mutatePricingState(current => {
      let next = targetEdits.length ? editPricingFields(current, targetEdits) : current
      for (const selection of selections) next = setPricingFieldSelected(next, selection.identity, selection.selected)
      for (const productSelection of productSelections) {
        next = setProductListingsSelected(next, descriptors, productSelection.listingIds, productSelection.selected)
      }
      return next
    })
  }, [channelById, definition, descriptorMap, descriptors, mutatePricingState])

  const handleGridSelection = useCallback((startRow: number, startColumn: number, endRow: number, endColumn: number) => {
    // Cell focus is not a bulk-row selection. Only an explicit row-header
    // selection changes this scope; otherwise selected changed Listings apply.
    if (startColumn >= 0 && endColumn >= 0) return
    const selected = new Set<string>()
    const first = Math.min(startRow, endRow)
    const last = Math.max(startRow, endRow)
    for (let visualRow = first; visualRow <= last; visualRow += 1) {
      const physicalRow = hotRef.current?.hotInstance?.toPhysicalRow(visualRow) ?? visualRow
      const record = hotRef.current?.hotInstance?.getSourceDataAtRow(physicalRow) as DensePricingRecord | undefined
      if (record?.rowKey) selected.add(record.rowKey)
    }
    setSelectedRowKeys(current => setsEqual(current, selected) ? current : selected)
  }, [])

  async function saveAndReview() {
    if (!grid || summary.changed === 0 || summary.selected === 0) return
    const requestedRevision = pricingState.revision
    const requestedChanges = selectedPricingChanges(pricingState)
    setBusy(translate('workspace:sourceCentricWorkspace.savingDraft'))
    try {
      const revision = await service.saveDraft(workspace.id, draftVersion, [...selectedPricingDraftChanges(pricingState)], 'replace')
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
      setReviewContext({ reviewId: created.id, revisionId: revision.id, selectionChecksum: selection.selectionChecksum, selectedCount: selectedIds.length })
      setDraftVersion(revision.draftVersion)
      setLocalReviewOpen(false)
      setReviewOpen(true)
      notify.success({ title: translate('workspace:sourceCentricWorkspace.reviewAndDryRunComplete'), description: translate('workspace:densePricing.selectionBoundToReview', { count: selectedIds.length }) })
    } catch (error) {
      notify.error({ title: translate('workspace:sourceCentricWorkspace.reviewCouldNotBeCompleted'), description: localizedApiError(error, 'workspace:sourceCentricWorkspace.checkDataQualityIssues') })
    } finally { setBusy(null) }
  }

  async function apply() {
    if (!reviewContext) return
    setBusy(translate('workspace:sourceCentricWorkspace.applyingSelectedListings'))
    try {
      const key = await workspaceApplyIdempotencyKey(workspace.id, reviewContext.reviewId, reviewContext.revisionId, reviewContext.selectionChecksum)
      const result = await service.applySelected(workspace.id, reviewContext.reviewId, reviewContext.selectionChecksum, key)
      setApplyResult(result)
      setReviewContext(null)
      setConfirming(false)
      setReviewOpen(false)
      await load()
    } catch (error) {
      notify.error({ title: translate('workspace:sourceCentricWorkspace.applyWasBlocked'), description: localizedApiError(error, 'workspace:sourceCentricWorkspace.generateAFreshReview') })
    } finally { setBusy(null) }
  }

  function previewBulk() {
    const scoped = bulkScopeDescriptors(descriptors, definition?.records ?? [], selectedRowKeys, pricingState)
    const value = bulkValue.trim()
    const validatedScope = scoped.map(descriptor => validateDescriptorTarget(
      descriptor,
      channelById.get(descriptor.identity.channelId),
      bulkKind === 'set_status' && descriptor.identity.field === 'status'
        ? value
        : descriptor.targetValue ?? descriptor.currentValue ?? '',
    ))
    setBulkPreview(previewBulkTransformation(pricingState, validatedScope, { kind: bulkKind, value }))
  }

  function confirmBulk() {
    if (!bulkPreview) return
    mutatePricingState(current => applyBulkTransformation(current, bulkPreview))
    setBulkPreview(null)
  }

  const undo = useCallback(() => mutatePricingState(undoPricingWorkspace), [mutatePricingState])
  const redo = useCallback(() => mutatePricingState(redoPricingWorkspace), [mutatePricingState])
  const handleGridKeyDown = useCallback((event: KeyboardEvent) => {
    if (!(event.ctrlKey || event.metaKey)) return
    const key = event.key.toLowerCase()
    if (key === 'z' && !event.shiftKey) { event.preventDefault(); undo() }
    if (key === 'y' || (key === 'z' && event.shiftKey)) { event.preventDefault(); redo() }
  }, [redo, undo])

  if (!grid || !definition || !channelInventoryReady) {
    const loadingState = gridError ? <div className="fh-card fh-card-pad">
      <div className="fh-alert fh-alert-danger" role="alert"><Icon name="alert" /><span>{gridError}</span><button className="fh-button-secondary fh-button-sm ms-auto" type="button" onClick={() => void load()}>{translate('products:products.retryInlinePricing')}</button></div>
    </div> : <PricingWorkspaceStartup workspaceName={workspace.name} />
    return embedded ? loadingState : <PageShell>{loadingState}</PageShell>
  }

  const content = <>
    <div className="fh-pricing-workspace" data-pricing-workspace data-products-critical-controls>
      {!embedded && <header className="fh-pricing-header">
        <div className="min-w-0"><h1 className="fh-page-title truncate">{workspace.name}</h1><p className="fh-text-caption">{translate('workspace:sourceCentricWorkspace.sourceProductWorkspaceImmutableSnapshot')} {workspace.snapshot.id.slice(0, 8)}</p></div>
        <span className={`fh-workspace-dirty ${summary.changed ? 'fh-workspace-dirty-active' : ''}`}>{summary.changed ? translate('workspace:densePricing.pendingChanges', { count: summary.changed }) : translate('workspace:sourceCentricWorkspace.draftSaved')}</span>
      </header>}

      {gridError && <div className="fh-alert fh-alert-danger m-2" role="alert"><Icon name="alert" /><span>{gridError}</span><button className="fh-button-secondary fh-button-sm ms-auto" type="button" onClick={() => void load()}>{translate('products:products.retryInlinePricing')}</button></div>}
      {channelInventoryError && <div className="fh-alert fh-alert-warning m-2" role="alert"><Icon name="info" /><span>{channelInventoryError}</span><button className="fh-button-secondary fh-button-sm ms-auto" type="button" onClick={() => void loadChannelInventory()}>{translate('products:products.retryInlinePricing')}</button></div>}

      <div className="fh-pricing-controls-sticky" data-pricing-controls-sticky>
      <section className="fh-pricing-toolbar" aria-label={translate('workspace:densePricing.pricingToolbar')}>
        <form className="flex min-w-[240px] flex-1 items-center gap-2" onSubmit={event => { event.preventDefault(); setPage(1); setSearch(searchInput.trim()) }}>
          <input className="fh-input h-9 min-w-0" type="search" value={searchInput} onChange={event => setSearchInput(event.target.value)} {...inputHint(translate('workspace:sourceCentricWorkspace.searchSourceProducts'))} aria-label={translate('workspace:sourceCentricWorkspace.searchSourceProducts')} />
          <button className="fh-button-secondary fh-button-sm" type="submit"><Icon name="search" /> {translate('workspace:unifiedWorkspace.filterServerData')}</button>
          <select className="fh-select h-9 w-auto" value={view} onChange={event => { setView(event.target.value as View); setPage(1) }} aria-label={translate('workspace:densePricing.changeStateFilter')}>
            {(['all', 'changed', 'ready', 'blocked', 'unchanged'] as const).map(value => <option key={value} value={value}>{translate(`workspace:densePricing.view.${value}`)}</option>)}
          </select>
          <select className="fh-select h-9 w-auto" name="channelId" value={channelFilter} onChange={event => { setChannelFilter(event.target.value); setSelectedRowKeys(new Set()); setPage(1) }} aria-label={translate('workspace:unifiedWorkspace.channel')}>
            <option value="">{translate('common:selector.allChannels')}</option>
            <ResourceOptionGroups resources={channelResources} isOptionDisabled={channel => channel.section !== 'active'} />
          </select>
          <select className="fh-select h-9 w-auto" name="categoryId" value={categoryFilter} onChange={event => { setCategoryFilter(event.target.value); setPage(1) }} aria-label={translate('products:column.categories')}>
            <option value="">{translate('products:products.allCategories')}</option>
            {categoryOptions.map(category => <option key={category.value} value={category.value}>{category.label}</option>)}
          </select>
          <select className="fh-select h-9 w-auto" name="productType" value={productTypeFilter} onChange={event => { setProductTypeFilter(event.target.value as typeof productTypeFilter); setPage(1) }} aria-label={translate('products:column.type')}>
            <option value="">{translate('products:products.allTypes')}</option>
            {(['simple', 'variation', 'variable'] as const).map(type => <option key={type} value={type}>{translate(`products:productType.${type}`)}</option>)}
          </select>
          <select className="fh-select h-9 w-auto" name="stockState" value={stockFilter} onChange={event => { setStockFilter(event.target.value as typeof stockFilter); setPage(1) }} aria-label={translate('common:field.stock')}>
            <option value="">{translate('products:products.allStockStates')}</option>
            <option value="in_stock">{translate('products:products.inStock')}</option>
            <option value="out_of_stock">{translate('products:products.outOfStock')}</option>
          </select>
        </form>
        <button type="button" className="fh-button-secondary fh-button-sm" data-pricing-sort="product" onClick={() => {
          const plugin = hotRef.current?.hotInstance?.getPlugin('multiColumnSorting')
          const current = plugin?.getSortConfig() as { sortOrder?: 'asc' | 'desc' }[] | undefined
          plugin?.sort({ column: 1, sortOrder: current?.[0]?.sortOrder === 'asc' ? 'desc' : 'asc' })
        }}><Icon name="filter" /> {translate('workspace:densePricing.sortProduct')}</button>
        <button type="button" className="fh-button-secondary fh-button-sm" data-pricing-undo disabled={!pricingState.past.length} onClick={undo}>{translate('workspace:densePricing.undo')}</button>
        <button type="button" className="fh-button-secondary fh-button-sm" data-pricing-redo disabled={!pricingState.future.length} onClick={redo}>{translate('workspace:densePricing.redo')}</button>
      </section>

      <section className="fh-pricing-summary" aria-label={translate('workspace:sourceCentricWorkspace.workspaceChangeSummary')}>
        {(['changed', 'selected', 'ready', 'warning', 'blocked'] as const).map(key => <span key={key} className={`fh-pricing-counter fh-pricing-counter-${key}`}><strong>{formatNumber(summary[key])}</strong> {translate(`workspace:densePricing.counter.${key}`)}</span>)}
        <div className="fh-pricing-channels" aria-label={translate('workspace:sourceCentricWorkspace.channels')}>
          {/* i18n-ignore: utility classes, not user-facing copy */}
          <ResourceSectionList resources={channelResources} className="flex flex-wrap gap-2" renderItem={channel => <span className="inline-flex items-center gap-1 text-xs"><span>{channel.displayName}</span><ResourceStateBadge badge={channel.badge} /></span>} />
        </div>
        <span className="fh-text-caption" data-pending-summary>{translate('workspace:densePricing.pendingHidden', { pending: summary.changed, hidden: summary.hidden })}</span>
      </section>

      <section className="fh-pricing-bulk" data-bulk-toolbar aria-label={translate('workspace:densePricing.bulkTransformationToolbar')}>
        <select className="fh-select h-9 w-auto min-w-[190px]" data-bulk-action value={bulkKind} onChange={event => setBulkKind(event.target.value as BulkTransformationKind)} aria-label={translate('workspace:densePricing.bulkAction')}>
          {BULK_ACTIONS.map(action => <option key={action.kind} value={action.kind}>{translate(action.label)}</option>)}
        </select>
        <input className="fh-input h-9 w-32" data-bulk-value value={bulkValue} onChange={event => setBulkValue(event.target.value)} aria-label={translate('workspace:densePricing.bulkValue')} />
        <button type="button" className="fh-button-secondary fh-button-sm" data-bulk-preview disabled={bulkScopeCount === 0} onClick={previewBulk}><Icon name="preview" /> {translate('workspace:densePricing.previewBulkChange')}</button>
        <span className="fh-text-caption">{translate('workspace:densePricing.selectedRowsScope', { count: bulkScopeCount })}</span>
        {/* i18n-ignore: utility classes, not user-facing copy */}
        <div className="ms-auto flex items-center gap-2">
          <button data-pricing-review className="fh-button-secondary fh-button-sm" type="button" disabled={summary.selected === 0 || busy !== null} onClick={() => reviewContext ? setReviewOpen(true) : setLocalReviewOpen(true)}>{translate('workspace:unifiedWorkspace.review')}</button>
          <button data-pricing-dry-run className="fh-button-secondary fh-button-sm" type="button" disabled={summary.changed === 0 || summary.selected === 0 || busy !== null || reviewContext !== null} onClick={() => void saveAndReview()}><Icon name="dryRun" /> {translate('products:products.dryRun')}</button>
          <button data-pricing-apply className="fh-button-primary fh-button-sm" type="button" disabled={!reviewContext || review?.status !== 'ready' || busy !== null} onClick={() => setConfirming(true)}><Icon name="apply" /> {translate('workspace:sourceCentricWorkspace.apply')} {reviewContext?.selectedCount ?? 0}</button>
        </div>
      </section>
      </div>

      {!license.licenseKey ? <div className="fh-alert fh-alert-danger"><Icon name="alert" /><span>{translate('workspace:unifiedWorkspace.productionGridIsDisabledConfigureAValid')}</span></div> :
        <div className="fh-grid-scroll fh-pricing-grid-scroll" data-pricing-grid-scroll role="region" aria-label={translate('workspace:unifiedWorkspace.scrollableWorkspaceGrid')}>
          {/* i18n-ignore: Handsontable theme and component classes */}
          <DensePricingGrid
            definition={definition}
            gridMinWidth={gridMinWidth}
            height={tableHeight}
            hotRef={hotRef}
            licenseKey={license.licenseKey}
            onChange={handleGridChanges}
            onSelection={handleGridSelection}
            onKeyDown={handleGridKeyDown}
          />
        </div>}

      <footer className="fh-pricing-footer">
        <span className="fh-text-caption">{translate('workspace:sourceCentricWorkspace.page')} {page} {translate('workspace:sourceCentricWorkspace.of')} {pageCount}</span>
        <div className="flex gap-2"><button className="fh-button-secondary fh-button-sm" disabled={page <= 1 || busy !== null} onClick={() => setPage(value => value - 1)}>{translate('workspace:sourceCentricWorkspace.previous')}</button><button className="fh-button-secondary fh-button-sm" disabled={page >= pageCount || busy !== null} onClick={() => setPage(value => value + 1)}>{translate('workspace:sourceCentricWorkspace.next')}</button></div>
      </footer>
      {busy && <p className="fh-text-caption px-3 py-2" role="status">{busy}...</p>}
    </div>

    {bulkPreview && <BulkPreviewDialog preview={bulkPreview} onCancel={() => setBulkPreview(null)} onConfirm={confirmBulk} />}
    {localReviewOpen && <LocalReviewDialog changes={selectedPricingChanges(pricingState)} grid={grid} onClose={() => setLocalReviewOpen(false)} />}
    {reviewOpen && review && <ReviewDialog review={review} grid={grid} onClose={() => setReviewOpen(false)} />}
    {confirming && reviewContext && <div className="fh-pricing-dialog fixed inset-0 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label={translate('workspace:sourceCentricWorkspace.applyConfirmation')}><div className="fh-card fh-card-pad max-w-lg"><h2 className="fh-page-title">{translate('workspace:sourceCentricWorkspace.confirmSelectedApply')}</h2><p className="fh-text-caption mt-2">{translate('workspace:densePricing.confirmApplyScope', { count: reviewContext.selectedCount })}</p>{/* i18n-ignore: utility classes, not user-facing copy */}<div className="mt-5 flex justify-end gap-2"><button className="fh-button-secondary" type="button" onClick={() => setConfirming(false)}>{translate('workspace:sourceCentricWorkspace.cancel')}</button><button className="fh-button-primary" type="button" onClick={() => void apply()}><Icon name="apply" /> {translate('workspace:sourceCentricWorkspace.confirmApply')}</button></div></div></div>}
    {applyResult && <ApplyResults result={applyResult} />}
  </>
  return embedded ? content : <PageShell>{content}</PageShell>
}

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

function setsEqual(left: Set<string>, right: Set<string>): boolean {
  if (left.size !== right.size) return false
  for (const value of left) if (!right.has(value)) return false
  return true
}

function bulkScopeDescriptors(
  descriptors: PricingFieldDescriptor[],
  records: DensePricingRecord[],
  selectedRowKeys: Set<string>,
  state: PricingWorkspaceState,
): PricingFieldDescriptor[] {
  const listingIds = selectedRowKeys.size
    ? new Set(records.filter(record => selectedRowKeys.has(record.rowKey)).flatMap(record => Object.entries(record).filter(([key, value]) => key.endsWith('__listing_id') && value).map(([, value]) => String(value))))
    : new Set(selectedPricingChanges(state).map(change => change.identity.listingId))
  if (!listingIds.size) return []
  return descriptors.filter(descriptor => listingIds.has(descriptor.identity.listingId))
}

function gridCellSettings(
  hotRef: React.RefObject<HotTableRef>,
  columnMeta: Map<string, DensePricingColumnMeta>,
  row: number,
  propValue: string | number,
): Handsontable.CellProperties {
  const settings = {} as FlowHubCellProperties
  const instance = hotRef.current?.hotInstance
  const prop = String(propValue)
  // Handsontable's `cells` callback receives physical indexes. Keeping source
  // lookup physical is what preserves Listing policy after visual sorting.
  const record = instance?.getSourceDataAtRow(row) as DensePricingRecord | undefined
  const meta = columnMeta.get(prop)
  if (!record || !meta) return settings
  settings.readOnly = cellIsReadOnly(record, meta)
  if (meta.kind === 'target') {
    const status = cellStatus(record, meta)
    settings.className = `fh-cell-status fh-cell-status-${status}`
    settings.flowhubStatus = status
    settings.renderer = targetCellRenderer
  }
  if (meta.kind === 'selection') {
    settings.flowhubField = meta.field
    settings.renderer = fieldSelectionRenderer
  }
  if (meta.kind === 'product_selection') {
    settings.renderer = productSelectionRenderer
  }
  if (record.productType === 'variable') settings.className = `${settings.className ?? ''} fh-pricing-variable-parent`.trim()
  return settings
}

interface FlowHubCellProperties extends Handsontable.CellProperties {
  flowhubField?: PricingField
  flowhubStatus?: string
}

const targetCellRenderer: BaseRenderer = (hot, td, renderedRow, renderedColumn, cellProp, value, properties) => {
  Handsontable.renderers.TextRenderer(hot, td, renderedRow, renderedColumn, cellProp, value, properties)
  const status = (properties as FlowHubCellProperties).flowhubStatus ?? 'unavailable'
  const formattedStatus = formatStatus(status)
  setDatasetValue(td, 'cellStatus', formattedStatus)
  const label = translate('workspace:densePricing.cellValueStatus', { value: String(value ?? ''), status: formattedStatus })
  if (td.getAttribute('aria-label') !== label) td.setAttribute('aria-label', label)
}

const fieldSelectionRenderer: BaseRenderer = (hot, td, renderedRow, renderedColumn, cellProp, value, properties) => {
  Handsontable.renderers.CheckboxRenderer(hot, td, renderedRow, renderedColumn, cellProp, value, properties)
  const input = td.querySelector('input')
  const field = (properties as FlowHubCellProperties).flowhubField
  if (!input || !field) return
  setDatasetValue(input, 'fieldSelection', 'true')
  setDatasetValue(input, 'field', field)
  const label = translate('workspace:densePricing.selectChangedField', { field: formatField(field) })
  if (input.getAttribute('aria-label') !== label) input.setAttribute('aria-label', label)
}

const productSelectionRenderer: BaseRenderer = (hot, td, renderedRow, renderedColumn, cellProp, value, properties) => {
  Handsontable.renderers.CheckboxRenderer(hot, td, renderedRow, renderedColumn, cellProp, value, properties)
  const input = td.querySelector('input')
  if (!input) return
  setDatasetValue(input, 'productSelection', 'true')
  const label = translate('workspace:workspace.selectAllEligible')
  if (input.getAttribute('aria-label') !== label) input.setAttribute('aria-label', label)
}

function annotatePricingCell(
  hotRef: React.RefObject<HotTableRef>,
  columnMeta: Map<string, DensePricingColumnMeta>,
  td: HTMLTableCellElement,
  visualRow: number,
  propValue: string | number,
) {
  const instance = hotRef.current?.hotInstance
  const physicalRow = instance?.toPhysicalRow(visualRow) ?? visualRow
  const record = instance?.getSourceDataAtRow(physicalRow) as DensePricingRecord | undefined
  const prop = String(propValue)
  const meta = columnMeta.get(prop)
  if (!record) return
  // Walkontable recycles TD elements while scrolling. Remove identity annotations
  // from the previous rendered cell before binding the current immutable identity.
  const input = td.querySelector('input')
  const rowElement = td.parentElement
  if (rowElement) {
    setDatasetValue(rowElement, 'pricingRow', 'true')
    setDatasetValue(rowElement, 'productId', record.productId)
  }
  setDatasetValue(td, 'productId', record.productId)
  setDatasetValue(td, 'channelId', meta?.channelId)
  setDatasetValue(td, 'field', meta?.field)
  setDatasetValue(td, 'targetField', meta?.kind === 'target' ? meta.field : undefined)
  setDatasetValue(td, 'fieldSelection', meta?.kind === 'selection' ? 'true' : undefined)
  setDatasetValue(td, 'productSelection', meta?.kind === 'product_selection' ? 'true' : undefined)
  setDatasetValue(input, 'listingId', undefined)
  setDatasetValue(input, 'channelId', undefined)
  setDatasetValue(input, 'productSelection', meta?.kind === 'product_selection' ? 'true' : undefined)
  if (meta?.kind === 'target' && meta.channelId && meta.field) {
    const identity = identityForCell(record, meta)
    setDatasetValue(td, 'listingId', identity?.listingId)
  } else {
    setDatasetValue(td, 'listingId', undefined)
  }
  if (meta?.kind === 'selection' && meta.channelId && meta.field) {
    const identity = identityForCell(record, meta)
    if (identity) {
      setDatasetValue(td, 'listingId', identity.listingId)
      setDatasetValue(input, 'listingId', identity.listingId)
      setDatasetValue(input, 'channelId', identity.channelId)
    }
  }
}

function setDatasetValue(
  element: HTMLElement | undefined | null,
  key: string,
  value: string | undefined,
) {
  if (!element) return
  if (value === undefined) {
    if (key in element.dataset) delete element.dataset[key]
    return
  }
  if (element.dataset[key] !== value) element.dataset[key] = value
}

function BulkPreviewDialog({ preview, onCancel, onConfirm }: { preview: BulkTransformationPreview; onCancel: () => void; onConfirm: () => void }) {
  return <div className="fh-pricing-dialog fixed inset-0 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" data-bulk-preview-dialog aria-label={translate('workspace:densePricing.bulkPreview')}><div className="fh-card max-h-[85vh] w-full max-w-4xl overflow-auto"><div className="fh-panel-header"><div><h2 className="fh-page-title">{translate('workspace:densePricing.bulkPreview')}</h2><p className="fh-text-caption">{translate('workspace:densePricing.bulkPreviewSummary', { products: preview.productsAffected, listings: preview.listingsAffected, fields: preview.fieldsAffected, blocked: preview.blockedItems })}</p></div></div><div className="overflow-x-auto"><table className="fh-table min-w-[720px]"><thead><tr><th>{translate('workspace:gridModel.product')}</th><th>{translate('workspace:unifiedWorkspace.channel')}</th><th>{translate('workspace:densePricing.field')}</th><th>{translate('workspace:densePricing.previousValue')}</th><th>{translate('workspace:densePricing.resultingValue')}</th><th>{translate('workspace:unifiedWorkspace.status')}</th></tr></thead><tbody>{preview.items.slice(0, 100).map(item => <tr key={item.key}><td>{item.descriptor.identity.productId}</td><td>{formatChannelDisplayName(item.descriptor.identity.channelId)}</td><td>{formatField(item.descriptor.identity.field)}</td><td>{item.previousValue}</td><td>{item.resultingValue ?? '—'}</td><td>{item.blockedReason ? translate('workspace:sourceCentricWorkspace.blockedRows') : translate('workspace:sourceCentricWorkspace.readyChanges')}</td></tr>)}</tbody></table></div><div className="fh-panel-footer"><button className="fh-button-secondary" onClick={onCancel}>{translate('workspace:sourceCentricWorkspace.cancel')}</button><button className="fh-button-primary" data-bulk-confirm disabled={preview.fieldsAffected === 0} onClick={onConfirm}>{translate('workspace:densePricing.applyBulkChanges')}</button></div></div></div>
}

function LocalReviewDialog({ changes, grid, onClose }: { changes: readonly PricingFieldChange[]; grid: GroupedWorkspacePage; onClose: () => void }) {
  return <div className="fh-pricing-dialog fixed inset-0 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" data-local-pricing-review aria-label={translate('workspace:unifiedWorkspace.reviewChanges')}><div className="fh-card max-h-[88vh] w-full max-w-5xl overflow-auto"><div className="fh-panel-header"><div><h2 className="fh-page-title">{translate('workspace:unifiedWorkspace.reviewChanges')}</h2><p className="fh-text-caption">{translate('workspace:densePricing.reviewSummary', { total: changes.length, selected: changes.length, blocked: 0 })}</p></div><button className="fh-button-secondary fh-button-sm" onClick={onClose}>{translate('workspace:densePricing.backToGrid')}</button></div><div className="overflow-x-auto"><table className="fh-table min-w-[760px]"><thead><tr><th>{translate('workspace:gridModel.product')}</th><th>{translate('workspace:unifiedWorkspace.channel')}</th><th>{translate('workspace:densePricing.field')}</th><th>{translate('workspace:densePricing.previousValue')}</th><th>{translate('workspace:gridModel.targetField', { field: '' })}</th></tr></thead><tbody>{changes.map(change => { const product = grid.items.find(row => row.children.some(child => child.listingId === change.identity.listingId)); return <tr key={change.key}><td>{product?.name ?? change.identity.productId}</td><td>{formatChannelDisplayName(change.identity.channelId)}</td><td>{formatField(change.identity.field)}</td><td>{change.currentValue ?? '—'}</td><td>{change.targetValue}</td></tr> })}</tbody></table></div></div></div>
}

function ReviewDialog({ review, grid, onClose }: { review: ReviewResource; grid: GroupedWorkspacePage; onClose: () => void }) {
  return <div className="fh-pricing-dialog fixed inset-0 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label={translate('workspace:unifiedWorkspace.reviewChanges')}><div className="fh-card max-h-[88vh] w-full max-w-6xl overflow-auto"><div className="fh-panel-header"><div><h2 className="fh-page-title">{translate('workspace:unifiedWorkspace.reviewChanges')}</h2><p className="fh-text-caption">{translate('workspace:densePricing.reviewSummary', { total: review.summary.total, selected: review.items.filter(item => item.selected).length, blocked: review.summary.blocked })}</p></div><button className="fh-button-secondary fh-button-sm" onClick={onClose}>{translate('workspace:densePricing.backToGrid')}</button></div><div className="overflow-x-auto"><table className="fh-table min-w-[900px]"><thead><tr><th>{translate('workspace:gridModel.product')}</th><th>{translate('workspace:unifiedWorkspace.channel')}</th><th>{translate('workspace:densePricing.field')}</th><th>{translate('workspace:densePricing.previousValue')}</th><th>{translate('workspace:gridModel.targetField', { field: '' })}</th><th>{translate('workspace:sourceCentricWorkspace.selected')}</th></tr></thead><tbody>{review.items.map(item => { const product = grid.items.find(row => row.children.some(child => child.listingId === item.listingId)); return <tr key={item.id}><td>{product?.name ?? item.canonicalProductId}</td><td>{formatChannelDisplayName(item.channelId)}</td><td>{formatField(item.field)}</td><td>{item.current ?? '—'}</td><td>{item.target}</td><td>{item.selected ? '✓' : '—'}</td></tr> })}</tbody></table></div></div></div>
}

function ApplyResults({ result }: { result: ApplyResource }) {
  return <section className="fh-card fh-card-pad mt-4" aria-label={translate('workspace:sourceCentricWorkspace.applyResults')}><h2 className="fh-section-title">{translate('workspace:sourceCentricWorkspace.applyResultStatus', { status: formatStatus(result.status) })}</h2><p className="fh-text-caption">{translate('workspace:sourceCentricWorkspace.verifiedSuccessIsShownOnlyAfterExact')}</p><div className="mt-3 grid gap-2">{result.items.map(item => <div className="flex items-center gap-2 rounded border border-border p-2" key={item.id}><Icon name={item.status === 'applied' ? 'success' : item.status === 'failed' ? 'error' : 'warning'} /><span>{formatChannelDisplayName(item.channelId)} · {formatField(item.field)}</span><strong className="ms-auto">{formatStatus(item.status)}</strong></div>)}</div></section>
}

function restoreState(workspaceId: string, scopeId: string): PricingWorkspaceState {
  if (typeof window === 'undefined') return createPricingWorkspaceState(workspaceId, [], scopeId)
  try { return restorePricingWorkspaceState(window.sessionStorage, workspaceId, scopeId) } catch { return createPricingWorkspaceState(workspaceId, [], scopeId) }
}

function viewportTableHeight(): number {
  if (typeof window === 'undefined') return 560
  return Math.max(480, window.innerHeight - 320)
}
