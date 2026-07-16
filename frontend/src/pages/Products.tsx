import { translate } from '../i18n'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { localizedApiError } from '../i18n/errors'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import IconButton from '../components/IconButton'
import LocalizedText from '../components/LocalizedText'
import PageShell from '../components/PageShell'
import { useServices } from '../services/ServiceContext'
import type { Product } from '../services/types'
import type { Category } from '../services/products/ProductService'
import { inputHint } from '../utils/inputHint'
import { formatDate } from '../i18n/format'
import { formatProductType } from '../i18n/display'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceChannel } from '../features/sourceWorkspace/types'
import { ResourceOptionGroups } from '../components/ResourceOrdering'
import { prepareResourceCollection, sourceChannelSignals } from '../features/resourceOrdering/resourceOrdering'

const PAGE_SIZE = 50

function ProductRow({ product, selected, onSelected }: { product: Product; selected: boolean; onSelected: (selected: boolean) => void }) {
  return (
    <tr className="border-b border-border hover:bg-bg-base/60 transition-colors" data-product-id={product.id}>
      <td className="px-3 py-3 text-center">
        <input type="checkbox" checked={selected} onChange={event => onSelected(event.target.checked)} aria-label={translate('products:products.selectProductForWorkspace', { product: product.name })} />
      </td>
      <td className="px-4 py-3 min-w-0 max-w-[340px]">
        <div className="flex items-center gap-3 min-w-0">
          {product.imageUrl ? <img src={product.imageUrl} alt="" className="w-9 h-9 rounded object-cover border border-border flex-shrink-0 bg-bg-base" loading="lazy" /> : <div className="w-9 h-9 rounded border border-border bg-bg-base flex-shrink-0 flex items-center justify-center"><Icon name="products" className="text-border" /></div>}
          <div className="min-w-0">
            <div className="fh-text-body font-medium truncate"><LocalizedText text={product.name} /></div>
            <div className="flex flex-wrap items-center gap-1.5 mt-0.5"><span className="fh-text-caption fh-text-mono">{product.sku || '-'}</span><Badge variant="neutral">{product.connectorId ? formatChannelDisplayName(product.connectorId) : translate('commerce:commerceHub.source')}</Badge></div>
          </div>
        </div>
      </td>
      <td className="px-4 py-3"><Badge className="capitalize" variant="neutral">{formatProductType(product.productType)}</Badge></td>
      <td className="px-4 py-3 fh-text-body font-medium font-mono">{product.currentPrice.toLocaleString()} <span className="fh-text-caption">{product.currency}</span></td>
      <td className="px-4 py-3">{(product.categoryNames ?? []).slice(0, 2).map(category => <Badge key={category} className="me-1" variant="neutral"><LocalizedText text={category} /></Badge>)}{(product.categoryNames ?? []).length > 2 && <span className="fh-text-caption">+{product.categoryNames.length - 2}</span>}</td>
      <td className="px-4 py-3 text-end"><span className="fh-text-caption">{translate('products:products.inlineEditingInWorkspace')}</span></td>
    </tr>
  )
}

function SkeletonRow() {
  return <tr className="border-b border-border">{[44, 340, 90, 120, 140, 160].map((width, index) => <td key={index} className="px-4 py-3"><div className="h-3 bg-border/40 animate-pulse rounded" style={{ width }} /></td>)}</tr>
}

export default function Products() {
  const { products: productService, unifiedWorkspace } = useServices()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [productType, setProductType] = useState<'all' | 'simple' | 'variable' | 'variation'>('all')
  const [channelId, setChannelId] = useState('')
  const [page, setPage] = useState(1)
  const [items, setItems] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [configured, setConfigured] = useState<boolean | undefined>(undefined)
  const [availableChannels, setAvailableChannels] = useState<SourceChannel[]>([])
  const [channelInventoryUnavailable, setChannelInventoryUnavailable] = useState(false)
  const [loading, setLoading] = useState(true)
  const [categories, setCategories] = useState<Category[]>([])
  const [workspaceSelection, setWorkspaceSelection] = useState<Map<string, Product>>(new Map())
  const [workspaceCreating, setWorkspaceCreating] = useState(false)
  const [workspaceError, setWorkspaceError] = useState<string | null>(null)
  const [selectionError, setSelectionError] = useState<string | null>(null)

  useEffect(() => { productService.getCategories?.().then(setCategories).catch(() => {}) }, [productService])
  useEffect(() => {
    let mounted = true
    sourceWorkspaceApi.channels().then(result => { if (mounted) { setAvailableChannels(result.items); setChannelInventoryUnavailable(false) } }).catch(() => { if (mounted) setChannelInventoryUnavailable(true) })
    return () => { mounted = false }
  }, [])
  useEffect(() => { const timer = setTimeout(() => { setDebouncedSearch(search); setPage(1) }, 250); return () => clearTimeout(timer) }, [search])
  useEffect(() => { setPage(1) }, [categoryId, productType, channelId])

  const fetchProducts = useCallback(() => {
    setLoading(true)
    productService.getProducts({ search: debouncedSearch, status: 'all', page, pageSize: PAGE_SIZE, categoryId: categoryId ?? undefined, productType: productType === 'all' ? undefined : productType, channelId: channelId || undefined })
      .then(result => { setItems(result.items); setTotal(result.total); setConfigured(result.configured) })
      .catch(error => setWorkspaceError(localizedApiError(error, 'products:products.unableToLoadProducts')))
      .finally(() => setLoading(false))
  }, [categoryId, channelId, debouncedSearch, page, productService, productType])
  useEffect(() => { fetchProducts() }, [fetchProducts])

  const channelResources = useMemo(() => prepareResourceCollection(availableChannels, sourceChannelSignals), [availableChannels])
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const end = Math.min(page * PAGE_SIZE, total)
  const visibleSelectionCount = items.reduce((count, product) => count + (workspaceSelection.has(`${product.connectorId ?? ''}:${product.id}`) ? 1 : 0), 0)

  const selectVisible = useCallback(() => {
    setSelectionError(null)
    setWorkspaceSelection(current => {
      const next = new Map(current)
      for (const product of items) next.set(`${product.connectorId ?? ''}:${product.id}`, product)
      return next
    })
  }, [items])

  const clearVisible = useCallback(() => {
    setWorkspaceSelection(current => {
      const next = new Map(current)
      for (const product of items) next.delete(`${product.connectorId ?? ''}:${product.id}`)
      return next
    })
  }, [items])

  const createPricingWorkspace = useCallback(async () => {
    if (!unifiedWorkspace || workspaceSelection.size === 0) { setSelectionError(translate('products:products.selectAtLeastOneForPricingWorkspace')); return }
    setWorkspaceCreating(true); setWorkspaceError(null); setSelectionError(null)
    try {
      const workspace = await unifiedWorkspace.createManual(translate('products:products.pricingWorkspaceDated', { date: formatDate(new Date()) }), [...workspaceSelection.values()].map(product => ({ connector_id: product.connectorId ?? '', product_id: product.id })))
      navigate(`/workspace/${workspace.id}`)
    } catch (error) { setWorkspaceError(localizedApiError(error, 'products:products.unableToCreateManualWorkspace')) }
    finally { setWorkspaceCreating(false) }
  }, [navigate, unifiedWorkspace, workspaceSelection])

  if (!loading && configured === false) return <PageShell><div><h1 className="fh-page-title">{translate('products:products.products')}</h1><p className="fh-page-subtitle">{translate('products:products.productCatalog')}</p></div><div className="fh-card"><Empty title={translate('products:products.noProductConnectorConfigured')} description={translate('products:products.connectAProductSourceFromSourcesTo')} action={{ label: translate('products:products.openSources'), onClick: () => navigate('/sources') }} /></div></PageShell>

  return <PageShell>
    <div className="fh-page-header">
      <div><h1 className="fh-page-title">{translate('products:products.pricingWorkspace')}</h1><p className="fh-page-subtitle">{loading ? translate('products:products.loading') : translate('products:products.productCount', { count: total })}</p></div>
      <div className="flex flex-wrap items-center justify-end gap-2"><span className="fh-text-caption" aria-live="polite">{translate('products:products.productsSelected', { count: workspaceSelection.size })}</span><button type="button" className="fh-button-primary" disabled={!unifiedWorkspace || workspaceSelection.size === 0 || workspaceCreating} onClick={() => void createPricingWorkspace()}><Icon name="workspace" /> {workspaceCreating ? translate('products:products.creating') : translate('products:products.openPricingWorkspace')}</button></div>
    </div>
    <p className="fh-text-caption mb-3">{translate('products:products.pricingWorkspaceHint')}</p>
    {workspaceError && <div className="fh-alert fh-alert-danger" role="alert"><Icon name="alert" /><span>{workspaceError}</span></div>}
    {selectionError && <div className="fh-alert fh-alert-warning" role="alert"><Icon name="info" /><span>{selectionError}</span></div>}
    <div className="fh-card fh-card-pad flex flex-wrap items-center gap-3">
      <div className="relative flex-1 min-w-[220px]"><Icon name="search" className="absolute start-2.5 top-1/2 -translate-y-1/2 text-wp-muted pointer-events-none" /><input type="text" value={search} onChange={event => setSearch(event.target.value)} {...inputHint(translate('products:products.searchNameOrSku'))} className="fh-input ps-8" /></div>
      <select value={channelId} onChange={event => setChannelId(event.target.value)} className="fh-select w-auto min-w-[150px]"><option value="">{translate('products:products.allChannels')}</option>{channelInventoryUnavailable && <option value="" disabled>{translate('common:status.unavailable')}</option>}<ResourceOptionGroups resources={channelResources} /></select>
      {categories.length > 0 && <select value={categoryId ?? ''} onChange={event => setCategoryId(event.target.value ? Number(event.target.value) : null)} className="fh-select w-auto min-w-[170px]"><option value="">{translate('products:products.allCategories')}</option>{categories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select>}
      <div className="fh-segmented">{(['all', 'simple', 'variation', 'variable'] as const).map(type => <button type="button" key={type} onClick={() => setProductType(type)} className={["fh-segmented-button capitalize", productType === type ? "fh-segmented-button-active" : ''].join(' ')}>{type === 'all' ? translate('products:products.allTypes') : translate(`products:productType.${type}`)}</button>)}</div>
    </div>
    <div className="fh-card mt-3"><div className="fh-panel-header"><div><span className="fh-text-body font-semibold">{loading ? translate('products:products.loading') : total === 0 ? translate('products:products.noProductsFound') : translate('products:products.showingOf', { value1: start, value2: end, value3: total })}</span><p className="fh-text-caption mt-1">{translate('products:products.selectProductsThenEditInline')}</p></div><div className="flex flex-wrap items-center gap-2"><button type="button" className="fh-button-secondary fh-button-sm" onClick={selectVisible} disabled={loading || items.length === 0}>{translate('products:products.selectVisible')}</button><button type="button" className="fh-button-secondary fh-button-sm" onClick={clearVisible} disabled={visibleSelectionCount === 0}>{translate('products:products.clearVisible')}</button></div></div>
      <div className="overflow-x-auto"><table className="fh-table min-w-[900px]"><thead><tr>{['select', 'product', 'type', 'price', 'categories', 'actions'].map(key => <th key={key}>{translate(`products:column.${key}`)}</th>)}</tr></thead><tbody className={loading ? 'opacity-40 pointer-events-none' : ''}>{loading && items.length === 0 ? Array.from({ length: 10 }).map((_, index) => <SkeletonRow key={index} />) : items.length === 0 ? <tr><td colSpan={6}><Empty title={translate('products:products.noProductsMatch')} description={translate('products:products.tryAdjustingTheSearchOrFilter')} /></td></tr> : items.map(product => <ProductRow key={`${product.connectorId ?? ''}:${product.id}`} product={product} selected={workspaceSelection.has(`${product.connectorId ?? ''}:${product.id}`)} onSelected={selected => setWorkspaceSelection(current => { const next = new Map(current); const key = `${product.connectorId ?? ''}:${product.id}`; if (selected) next.set(key, product); else next.delete(key); return next })} />)}</tbody></table></div>
      {!loading && totalPages > 1 && <div className="fh-panel-footer !justify-between"><span className="fh-text-caption">{start}–{end} {translate('products:products.of')} {total}</span><div className="flex items-center gap-1"><IconButton label={translate('products:products.previousPage')} onClick={() => setPage(value => Math.max(1, value - 1))} disabled={page === 1} size="sm"><Icon name="previous" mirrorRtl /></IconButton><span className="fh-text-caption px-1">{page} / {totalPages}</span><IconButton label={translate('products:products.nextPage')} onClick={() => setPage(value => Math.min(totalPages, value + 1))} disabled={page === totalPages} size="sm"><Icon name="next" mirrorRtl /></IconButton></div></div>}
    </div>
  </PageShell>
}
