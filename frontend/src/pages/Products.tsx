import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiErrorMessage } from '../api/client'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import IconButton from '../components/IconButton'
import LocalizedText from '../components/LocalizedText'
import PageShell from '../components/PageShell'
import { useServices } from '../services/ServiceContext'
import type {
  Product,
  ProductChannelPriceChange,
  ProductChannelPriceOperation,
  ProductChannelPriceState,
  ProductChannelPriceStateSet,
} from '../services/types'
import type { Category } from '../services/products/ProductService'
import { inputHint } from '../utils/inputHint'

const PAGE_SIZE = 20
const CHANNEL_OPTIONS = [
  { id: '', label: 'All Channels' },
  { id: 'woocommerce:primary', label: 'WooCommerce' },
  { id: 'snappshop:main', label: 'Snapp Shop' },
  { id: 'tapsishop:main', label: 'Tapsi Shop' },
]

function fmtPrice(p: number, currency: string): string {
  return `${currency} ${p.toFixed(2)}`
}

function fmtValue(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${unit}`
}

function productChannelLabel(connectorId?: string): string {
  if (connectorId === 'snappshop:main') return 'SnappShop'
  if (connectorId === 'tapsishop:main') return 'TapsiShop'
  if (connectorId === 'woocommerce:primary') return 'WooCommerce'
  return connectorId ?? 'FlowHub'
}

function ProductRow({ product, onEditPrices }: { product: Product; onEditPrices: (product: Product) => void }) {
  return (
    <tr className="border-b border-border hover:bg-bg-base/60 transition-colors">
      <td className="px-4 py-3 min-w-0 max-w-[260px]">
        <div className="flex items-center gap-3 min-w-0">
          {product.imageUrl ? (
            <img
              src={product.imageUrl}
              alt=""
              className="w-9 h-9 rounded object-cover border border-border flex-shrink-0 bg-bg-base"
              loading="lazy"
            />
          ) : (
            <div className="w-9 h-9 rounded border border-border bg-bg-base flex-shrink-0 flex items-center justify-center">
              <Icon name="products" className="text-border" />
            </div>
          )}
          <div className="min-w-0">
            <div className="fh-text-body font-medium truncate">
              <LocalizedText text={product.name} />
            </div>
            <div className="flex flex-wrap items-center gap-1.5 mt-0.5">
              <span className="fh-text-caption fh-text-mono">{product.sku || '-'}</span>
              <Badge variant="neutral">{productChannelLabel(product.connectorId)}</Badge>
            </div>
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <Badge className="capitalize" variant="neutral">{product.productType ?? 'simple'}</Badge>
      </td>
      <td className="px-4 py-3 fh-text-body font-medium font-mono">
        {fmtPrice(product.currentPrice, product.currency)}
      </td>
      <td className="px-4 py-3">
        {(product.categoryNames ?? []).slice(0, 2).map(c => (
          <Badge key={c} className="me-1" variant="neutral">
            <LocalizedText text={c} />
          </Badge>
        ))}
        {(product.categoryNames ?? []).length > 2 && (
          <span className="fh-text-caption">+{product.categoryNames.length - 2}</span>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        <button
          type="button"
          className="fh-button fh-button-secondary fh-button-sm whitespace-nowrap"
          onClick={() => onEditPrices(product)}
        >
          <Icon name="edit" />
          Edit prices
        </button>
      </td>
    </tr>
  )
}

function SkeletonRow() {
  return (
    <tr className="border-b border-border">
      {[240, 70, 80, 120, 96].map((w, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-3 bg-border/40 animate-pulse rounded" style={{ width: w }} />
        </td>
      ))}
    </tr>
  )
}

function ProductPriceEditor({
  state,
  operation,
  draftValues,
  loading,
  error,
  selectedCount,
  onDraftChange,
  onValidate,
  onDryRun,
  onApprove,
  onApply,
  onClose,
}: {
  state: ProductChannelPriceStateSet | null
  operation: ProductChannelPriceOperation | null
  draftValues: Record<string, string>
  loading: boolean
  error: string | null
  selectedCount: number
  onDraftChange: (channelId: string, value: string) => void
  onValidate: () => void
  onDryRun: () => void
  onApprove: () => void
  onApply: () => void
  onClose: () => void
}) {
  const canDryRun = Boolean(state && selectedCount > 0 && !loading)
  const canApprove = operation?.status === 'dry_run_ready' && !loading
  const canApply = operation?.status === 'approved' && !loading

  return (
    <section className="fh-card fh-card-pad space-y-4" aria-label="Multi-channel price editor">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="fh-section-title">Channel prices</h2>
          <p className="fh-text-caption">
            {state ? <><LocalizedText text={state.product.name} /> <span className="fh-text-mono">({state.product.sku || state.product.id})</span></> : 'Loading product price state...'}
          </p>
        </div>
        <IconButton label="Close channel price editor" onClick={onClose} size="sm">
          <Icon name="close" />
        </IconButton>
      </div>

      {error && (
        <div className="rounded border border-danger/30 bg-danger/5 px-3 py-2 fh-text-body text-danger" role="alert">
          {error}
        </div>
      )}

      {state && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <InfoTile label="Canonical/business price" value={fmtValue(state.canonical.value, state.canonical.currency)} />
            <InfoTile label="Dry Run" value={state.dryRunRequired ? 'Required before Apply' : 'Optional'} />
            <InfoTile label="Pending edits" value={String(selectedCount)} />
          </div>

          <div className="overflow-x-auto rounded border border-border" tabIndex={0} aria-label="Channel price comparison table">
            <table className="fh-table min-w-[1120px]">
              <thead>
                <tr>
                  {['Channel', 'State', 'Capability', 'Current', 'Proposed', 'Unit', 'Normalized', 'Freshness', 'Validation', 'Pending'].map(label => (
                    <th key={label}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {state.channels.map(channel => (
                  <ChannelPriceRow
                    key={channel.channelId}
                    channel={channel}
                    draftValue={draftValues[channel.channelId] ?? ''}
                    operationItem={operation?.items.find(item => item.channelId === channel.channelId)}
                    onDraftChange={onDraftChange}
                  />
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="fh-text-caption">
              Editing fields only creates local pending changes. Dry Run performs validation without external writes.
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className="fh-button fh-button-secondary" onClick={onValidate} disabled={loading || selectedCount === 0}>
                <Icon name="testConnection" />
                Validate
              </button>
              <button type="button" className="fh-button fh-button-primary" onClick={onDryRun} disabled={!canDryRun}>
                <Icon name="dryRun" />
                Preview / Dry Run
              </button>
              <button type="button" className="fh-button fh-button-secondary" onClick={onApprove} disabled={!canApprove}>
                <Icon name="apply" />
                Approve
              </button>
              <button type="button" className="fh-button fh-button-danger" onClick={onApply} disabled={!canApply}>
                <Icon name="apply" />
                Apply
              </button>
            </div>
          </div>
        </>
      )}

      {operation && (
        <OperationResult operation={operation} />
      )}
    </section>
  )
}

function ChannelPriceRow({
  channel,
  draftValue,
  operationItem,
  onDraftChange,
}: {
  channel: ProductChannelPriceState
  draftValue: string
  operationItem?: ProductChannelPriceOperation['items'][number]
  onDraftChange: (channelId: string, value: string) => void
}) {
  const validationVariant = channel.validationState === 'valid' ? 'success' : channel.validationState === 'error' ? 'error' : 'warning'
  const connectionVariant = channel.connectionState === 'connected' ? 'success' : channel.connectionState === 'disconnected' ? 'warning' : 'neutral'
  const editable = channel.canWrite
  return (
    <tr className="border-b border-border">
      <td className="px-4 py-3 sticky left-0 bg-bg-surface z-[1] min-w-[170px]">
        <div className="fh-text-body font-semibold">{channel.channelName}</div>
        <div className="fh-text-caption fh-text-mono">{channel.channelId}</div>
      </td>
      <td className="px-4 py-3">
        <Badge variant={connectionVariant} dot>{channel.connectionState}</Badge>
        <div className="fh-text-caption mt-1" title={`Health: ${channel.healthStatus}`}>Health: {channel.healthStatus}</div>
      </td>
      <td className="px-4 py-3">
        <Badge variant={editable ? 'success' : 'warning'}>{editable ? 'Read/write' : channel.readOnly ? 'Read-only' : 'Unavailable'}</Badge>
        <div className="fh-text-caption mt-1">{channel.writeCapability}</div>
      </td>
      <td className="px-4 py-3 fh-text-mono">{fmtValue(channel.currentValue, channel.unit)}</td>
      <td className="px-4 py-3 min-w-[180px]">
        <div className="flex items-center gap-2">
          <input
            type="number"
            min="0"
            step={channel.unit === 'rial' || channel.unit === 'toman' ? '1' : '0.01'}
            value={draftValue}
            onChange={event => onDraftChange(channel.channelId, event.target.value)}
            disabled={!editable}
            aria-label={`${channel.channelName} proposed price`}
            className="fh-input h-9 w-28 font-mono"
          />
          <span className="fh-text-caption" title={`Editable value unit: ${channel.unit}`}>{channel.unit}</span>
        </div>
      </td>
      <td className="px-4 py-3">{channel.unit}</td>
      <td className="px-4 py-3">
        <div className="fh-text-mono">{fmtValue(channel.normalizedValue, channel.normalizedUnit)}</div>
        {channel.unit !== channel.normalizedUnit && (
          <div className="fh-text-caption">source unit: {channel.unit}</div>
        )}
      </td>
      <td className="px-4 py-3">
        <Badge variant={channel.freshness === 'fresh' ? 'success' : 'warning'}>{channel.freshness}</Badge>
        <div className="fh-text-caption mt-1">{channel.lastSyncedAt ? new Date(channel.lastSyncedAt).toLocaleString() : 'Never synced'}</div>
      </td>
      <td className="px-4 py-3 min-w-[180px]">
        <Badge variant={validationVariant}>{channel.validationState}</Badge>
        <div className="fh-text-caption mt-1">{operationItem?.errorMessage ?? channel.validationMessage ?? operationItem?.status ?? 'Ready'}</div>
      </td>
      <td className="px-4 py-3">
        <Badge variant={operationItem?.status === 'failed' ? 'error' : channel.pendingChange ? 'warning' : operationItem?.status === 'applied' ? 'success' : 'neutral'}>
          {operationItem?.status ?? (channel.pendingChange ? 'pending' : 'unchanged')}
        </Badge>
      </td>
    </tr>
  )
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-border bg-bg-base px-3 py-2">
      <div className="fh-text-caption">{label}</div>
      <div className="fh-text-body font-semibold mt-1">{value}</div>
    </div>
  )
}

function OperationResult({ operation }: { operation: ProductChannelPriceOperation }) {
  return (
    <div className="rounded border border-border bg-bg-base px-3 py-3" aria-label="Channel price operation result">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="fh-text-body font-semibold">Operation {operation.id}</div>
          <div className="fh-text-caption">Status: {operation.status}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="neutral">Total {operation.summary.total}</Badge>
          <Badge variant="success">Success {operation.summary.success}</Badge>
          <Badge variant={operation.summary.failed ? 'error' : 'neutral'}>Failed {operation.summary.failed}</Badge>
          <Badge variant={operation.externalWritePerformed ? 'warning' : 'success'}>
            {operation.externalWritePerformed ? 'External write performed' : 'No external write'}
          </Badge>
        </div>
      </div>
      {operation.items.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="fh-table min-w-[760px]">
            <thead>
              <tr>
                {['Channel', 'Previous', 'Proposed', 'Outbound', 'Result'].map(label => <th key={label}>{label}</th>)}
              </tr>
            </thead>
            <tbody>
              {operation.items.map(item => (
                <tr key={item.id} className="border-b border-border">
                  <td className="px-4 py-2 fh-text-mono">{item.channelId}</td>
                  <td className="px-4 py-2">{fmtValue(item.currentValue, item.unit)}</td>
                  <td className="px-4 py-2">{fmtValue(item.proposedValue, item.unit)}</td>
                  <td className="px-4 py-2">{fmtValue(item.outboundValue, item.outboundUnit)}</td>
                  <td className="px-4 py-2">
                    <Badge variant={item.status === 'failed' ? 'error' : item.status === 'applied' ? 'success' : 'warning'}>{item.status}</Badge>
                    {item.errorMessage && <div className="fh-text-caption mt-1">{item.errorMessage}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function Products() {
  const { products: productService } = useServices()

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [productType, setProductType] = useState<'all' | 'simple' | 'variable'>('all')
  const [channelId, setChannelId] = useState('')
  const [page, setPage] = useState(1)

  const [items, setItems] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [configured, setConfigured] = useState<boolean | undefined>(undefined)
  const [loading, setLoading] = useState(true)

  const [categories, setCategories] = useState<Category[]>([])
  const [priceState, setPriceState] = useState<ProductChannelPriceStateSet | null>(null)
  const [priceOperation, setPriceOperation] = useState<ProductChannelPriceOperation | null>(null)
  const [draftValues, setDraftValues] = useState<Record<string, string>>({})
  const [editorLoading, setEditorLoading] = useState(false)
  const [editorError, setEditorError] = useState<string | null>(null)

  useEffect(() => {
    if (productService.getCategories) {
      productService.getCategories().then(setCategories).catch(() => {})
    }
  }, [productService])

  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => { setPage(1) }, [categoryId, productType, channelId])

  const fetchProducts = useCallback(() => {
    setLoading(true)
    productService.getProducts({
      search: debouncedSearch,
      status: 'all',
      page,
      pageSize: PAGE_SIZE,
      categoryId: categoryId ?? undefined,
      productType: productType === 'all' ? undefined : productType,
      channelId: channelId || undefined,
    })
      .then(r => {
        setItems(r.items)
        setTotal(r.total)
        setConfigured(r.configured)
      })
      .finally(() => setLoading(false))
  }, [productService, debouncedSearch, categoryId, productType, channelId, page])

  useEffect(() => { fetchProducts() }, [fetchProducts])

  const selectedChanges = useMemo<ProductChannelPriceChange[]>(() => {
    if (!priceState) return []
    return priceState.channels
      .map(channel => {
        const raw = draftValues[channel.channelId]
        const value = raw === undefined || raw.trim() === '' ? channel.proposedValue : Number(raw)
        if (value === null || value === undefined || Number.isNaN(value)) return null
        const current = channel.currentValue
        if (current !== null && current !== undefined && Math.abs(current - value) < 0.0001) return null
        return {
          channelId: channel.channelId,
          proposedValue: value,
          unit: channel.unit,
          staleToken: channel.staleToken,
        }
      })
      .filter((change): change is ProductChannelPriceChange => change !== null)
  }, [priceState, draftValues])

  const openPriceEditor = useCallback((product: Product) => {
    setEditorLoading(true)
    setEditorError(null)
    setPriceOperation(null)
    productService.getChannelPrices(product.id)
      .then(state => {
        setPriceState(state)
        setDraftValues(Object.fromEntries(state.channels.map(channel => [
          channel.channelId,
          channel.proposedValue === null || channel.proposedValue === undefined ? '' : String(channel.proposedValue),
        ])))
      })
      .catch(error => setEditorError(apiErrorMessage(error, 'Unable to load channel prices.')))
      .finally(() => setEditorLoading(false))
  }, [productService])

  const validatePrices = useCallback(() => {
    if (!priceState) return
    setEditorLoading(true)
    setEditorError(null)
    productService.validateChannelPrices(priceState.product.id, { changes: selectedChanges })
      .then(setPriceState)
      .catch(error => setEditorError(apiErrorMessage(error, 'Unable to validate channel prices.')))
      .finally(() => setEditorLoading(false))
  }, [priceState, productService, selectedChanges])

  const createDryRun = useCallback(() => {
    if (!priceState) return
    setEditorLoading(true)
    setEditorError(null)
    productService.createChannelPriceDryRun(priceState.product.id, { version: priceState.version, changes: selectedChanges })
      .then(setPriceOperation)
      .catch(error => setEditorError(apiErrorMessage(error, 'Unable to create Dry Run.')))
      .finally(() => setEditorLoading(false))
  }, [priceState, productService, selectedChanges])

  const approveOperation = useCallback(() => {
    if (!priceOperation) return
    setEditorLoading(true)
    setEditorError(null)
    productService.approveChannelPriceOperation(priceOperation.id, 'Approved from Products multi-channel price editor')
      .then(setPriceOperation)
      .catch(error => setEditorError(apiErrorMessage(error, 'Unable to approve Dry Run.')))
      .finally(() => setEditorLoading(false))
  }, [priceOperation, productService])

  const applyOperation = useCallback(() => {
    if (!priceOperation) return
    setEditorLoading(true)
    setEditorError(null)
    productService.applyChannelPriceOperation(priceOperation.id)
      .then(operation => {
        setPriceOperation(operation)
        if (priceState) {
          productService.getChannelPrices(priceState.product.id)
            .then(state => {
              setPriceState(state)
              setDraftValues(current => ({ ...current, ...Object.fromEntries(state.channels.map(channel => [
                channel.channelId,
                current[channel.channelId] ?? String(channel.proposedValue ?? ''),
              ])) }))
            })
            .catch(() => {})
        }
      })
      .catch(error => setEditorError(apiErrorMessage(error, 'Unable to apply channel prices.')))
      .finally(() => setEditorLoading(false))
  }, [priceOperation, priceState, productService])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const end = Math.min(page * PAGE_SIZE, total)

  if (!loading && configured === false) {
    return (
      <PageShell>
        <div>
          <h1 className="fh-page-title">Products</h1>
          <p className="fh-page-subtitle">Product catalog</p>
        </div>
        <div className="fh-card">
          <Empty
            title="No product connector configured"
            description="Connect a product source from Sources to browse products."
            action={{ label: 'Open Sources', onClick: () => { window.location.href = '/sources' } }}
          />
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">Products</h1>
          <p className="fh-page-subtitle">
            {loading ? 'Loading...' : `${total} product${total !== 1 ? 's' : ''}`}
          </p>
        </div>
      </div>

      <div className="fh-card fh-card-pad flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[180px]">
          <Icon name="search" className="absolute left-2.5 top-1/2 -translate-y-1/2 text-wp-muted pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            {...inputHint('Search name or SKU...')}
            className="fh-input pl-8"
          />
        </div>

        <select
          value={channelId}
          onChange={e => setChannelId(e.target.value)}
          className="fh-select w-auto min-w-[150px]"
        >
          {CHANNEL_OPTIONS.map(channel => (
            <option key={channel.id || 'all'} value={channel.id}>{channel.label}</option>
          ))}
        </select>

        {categories.length > 0 && (
          <select
            value={categoryId ?? ''}
            onChange={e => setCategoryId(e.target.value ? Number(e.target.value) : null)}
            className="fh-select w-auto min-w-[170px]"
          >
            <option value="">All Categories</option>
            {categories.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        )}

        <div className="fh-segmented">
          {(['all', 'simple', 'variable'] as const).map(t => (
            <button
              key={t}
              onClick={() => setProductType(t)}
              className={[
                'fh-segmented-button capitalize',
                productType === t ? 'fh-segmented-button-active' : '',
              ].join(' ')}
            >
              {t === 'all' ? 'All Types' : t}
            </button>
          ))}
        </div>
      </div>

      {(priceState || editorLoading || editorError) && (
        <ProductPriceEditor
          state={priceState}
          operation={priceOperation}
          draftValues={draftValues}
          loading={editorLoading}
          error={editorError}
          selectedCount={selectedChanges.length}
          onDraftChange={(channelId, value) => {
            setDraftValues(current => ({ ...current, [channelId]: value }))
            setPriceOperation(null)
          }}
          onValidate={validatePrices}
          onDryRun={createDryRun}
          onApprove={approveOperation}
          onApply={applyOperation}
          onClose={() => {
            setPriceState(null)
            setPriceOperation(null)
            setEditorError(null)
            setDraftValues({})
          }}
        />
      )}

      <div className="fh-table-wrapper">
        <div className="fh-panel-header">
          <span className="fh-text-body font-semibold">
            {loading ? 'Loading...' : total === 0 ? 'No products found' : `Showing ${start}-${end} of ${total}`}
          </span>
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <IconButton label="Previous page" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} size="sm">
                <Icon name="previous" mirrorRtl />
              </IconButton>
              <span className="fh-text-caption px-1">{page} / {totalPages}</span>
              <IconButton label="Next page" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} size="sm">
                <Icon name="next" mirrorRtl />
              </IconButton>
            </div>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="fh-table min-w-[560px]">
            <thead>
              <tr>
                {['Product', 'Type', 'Price', 'Categories', 'Actions'].map(h => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className={loading ? 'opacity-40 pointer-events-none' : ''}>
              {loading && items.length === 0
                ? Array.from({ length: PAGE_SIZE }).map((_, i) => <SkeletonRow key={i} />)
                : items.length === 0
                  ? (
                    <tr>
                      <td colSpan={5}>
                        <Empty title="No products match" description="Try adjusting the search or filter." />
                      </td>
                    </tr>
                    )
                  : items.map(p => <ProductRow key={p.id} product={p} onEditPrices={openPriceEditor} />)}
            </tbody>
          </table>
        </div>

        {!loading && totalPages > 1 && (
          <div className="fh-panel-footer !justify-between">
            <span className="fh-text-caption">{start}-{end} of {total}</span>
            <div className="flex items-center gap-1">
              <IconButton label="First page" onClick={() => setPage(1)} disabled={page === 1} size="sm">
                <span aria-hidden="true" className="fh-text-caption">«</span>
              </IconButton>
              <IconButton label="Previous page" onClick={() => setPage(p => p - 1)} disabled={page === 1} size="sm">
                <Icon name="previous" mirrorRtl />
              </IconButton>
              <span className="fh-text-caption px-1.5">{page} / {totalPages}</span>
              <IconButton label="Next page" onClick={() => setPage(p => p + 1)} disabled={page === totalPages} size="sm">
                <Icon name="next" mirrorRtl />
              </IconButton>
              <IconButton label="Last page" onClick={() => setPage(totalPages)} disabled={page === totalPages} size="sm">
                <span aria-hidden="true" className="fh-text-caption">»</span>
              </IconButton>
            </div>
          </div>
        )}
      </div>
    </PageShell>
  )
}
