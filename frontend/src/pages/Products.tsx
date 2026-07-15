import { translate } from '../i18n'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { localizedApiError } from '../i18n/errors'
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
import { formatMoney, formatMoneyInput, normalizeMoneyInteger, parseMoneyInput } from '../utils/price'
import { formatDate, formatDateTime } from '../i18n/format'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { formatCapability, formatProductType, formatStatus } from '../i18n/display'

const PAGE_SIZE = 20
const CHANNEL_OPTIONS = [
  { id: '', labelKey: 'products:products.allChannels' },
  { id: 'woocommerce:primary', labelKey: 'products:products.woocommerce' },
  { id: 'snappshop:main', labelKey: 'products:products.snappShop' },
  { id: 'tapsishop:main', labelKey: 'products:products.tapsiShop' },
]

function fmtValue(value: number | null | undefined, unit: string): string {
  return formatMoney(value, { unit })
}

function productChannelLabel(connectorId?: string): string {
  return connectorId ? formatChannelDisplayName(connectorId) : 'FlowHub'
}

function ProductRow({ product, onEditPrices, selected, onSelected }: { product: Product; onEditPrices: (product: Product) => void; selected: boolean; onSelected: (selected: boolean) => void }) {
  return (
    <tr className="border-b border-border hover:bg-bg-base/60 transition-colors">
      <td className="px-3 py-3 text-center">
        <input type="checkbox" checked={selected} onChange={event => onSelected(event.target.checked)} aria-label={translate('products:products.selectProductForWorkspace', { product: product.name })} />
      </td>
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
        <Badge className="capitalize" variant="neutral">{formatProductType(product.productType)}</Badge>
      </td>
      <td className="px-4 py-3 fh-text-body font-medium font-mono">
        {formatMoney(product.currentPrice, { currency: product.currency, position: "prefix" })}
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
          {translate('products:products.editPrices')}
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
    <section className="fh-card fh-card-pad space-y-4" aria-label={translate('products:products.multiChannelPriceEditor')}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="fh-section-title">{translate('products:products.channelPrices')}</h2>
          <p className="fh-text-caption">
            {state ? <><LocalizedText text={state.product.name} /> <span className="fh-text-mono">({state.product.sku || state.product.id})</span></> : translate('products:products.loadingProductPriceState')}
          </p>
        </div>
        <IconButton label={translate('products:products.closeChannelPriceEditor')} onClick={onClose} size="sm">
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
            <InfoTile label={translate('products:products.canonicalBusinessPrice')} value={fmtValue(state.canonical.value, state.canonical.currency)} />
            <InfoTile label={translate('products:products.dryRun')} value={state.dryRunRequired ? translate('products:priceEditor.requiredBeforeApply') : translate('products:priceEditor.optional')} />
            <InfoTile label={translate('products:products.pendingEdits')} value={String(selectedCount)} />
          </div>

          <div className="overflow-x-auto rounded border border-border" tabIndex={0} aria-label={translate('products:products.channelPriceComparisonTable')}>
            <table className="fh-table min-w-[1120px]">
              <thead>
                <tr>
                  {['channel', 'state', 'capability', 'current', 'proposed', 'unit', 'normalized', 'freshness', 'validation', 'pending'].map(key => (
                    <th key={key}>{translate(`products:column.${key}`)}</th>
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
              {translate('products:products.editingFieldsOnlyCreatesLocalPendingChanges')}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className="fh-button fh-button-secondary" onClick={onValidate} disabled={loading || selectedCount === 0}>
                <Icon name="testConnection" />
                {translate('products:products.validate')}
              </button>
              <button type="button" className="fh-button fh-button-primary" onClick={onDryRun} disabled={!canDryRun}>
                <Icon name="dryRun" />
                {translate('products:products.previewDryRun')}
              </button>
              <button type="button" className="fh-button fh-button-secondary" onClick={onApprove} disabled={!canApprove}>
                <Icon name="apply" />
                {translate('products:products.approve')}
              </button>
              <button type="button" className="fh-button fh-button-danger" onClick={onApply} disabled={!canApply}>
                <Icon name="apply" />
                {translate('products:products.apply')}
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
        <Badge variant={connectionVariant} dot>{formatStatus(channel.connectionState)}</Badge>
        <div className="fh-text-caption mt-1" title={translate('products:products.healthStatus', { status: formatStatus(channel.healthStatus) })}>{translate('products:products.health')} {formatStatus(channel.healthStatus)}</div>
      </td>
      <td className="px-4 py-3">
        <Badge variant={editable ? "success" : "warning"}>{editable ? translate('products:products.readWrite') : channel.readOnly ? translate('products:products.readOnly') : translate('products:products.unavailable')}</Badge>
        <div className="fh-text-caption mt-1">{formatCapability(channel.writeCapability)}</div>
      </td>
      <td className="px-4 py-3 fh-text-mono">{fmtValue(channel.currentValue, channel.unit)}</td>
      <td className="px-4 py-3 min-w-[180px]">
        <div className="flex items-center gap-2">
          <input
            type="text"
            inputMode="numeric"
            value={draftValue}
            onChange={event => {
              const raw = event.target.value
              if (raw.trim() === '') {
                onDraftChange(channel.channelId, '')
                return
              }
              const normalized = normalizeMoneyInteger(raw)
              if (normalized !== null && !normalized.startsWith('-')) {
                onDraftChange(channel.channelId, formatMoneyInput(normalized))
              }
            }}
            disabled={!editable}
            aria-label={translate('products:products.proposedPrice', { channel: channel.channelName })}
            className="fh-input h-9 w-28 font-mono"
          />
          <span className="fh-text-caption" title={translate('products:products.editableValueUnit', { unit: channel.unit })}>{channel.unit}</span>
        </div>
      </td>
      <td className="px-4 py-3">{channel.unit}</td>
      <td className="px-4 py-3">
        <div className="fh-text-mono">{fmtValue(channel.normalizedValue, channel.normalizedUnit)}</div>
        {channel.unit !== channel.normalizedUnit && (
          <div className="fh-text-caption">{translate('products:products.sourceUnit')} {channel.unit}</div>
        )}
      </td>
      <td className="px-4 py-3">
        <Badge variant={channel.freshness === "fresh" ? "success" : "warning"}>{formatStatus(channel.freshness)}</Badge>
        <div className="fh-text-caption mt-1">{channel.lastSyncedAt ? formatDateTime(channel.lastSyncedAt) : translate('products:products.neverSynced')}</div>
      </td>
      <td className="px-4 py-3 min-w-[180px]">
        <Badge variant={validationVariant}>{formatStatus(channel.validationState)}</Badge>
        <div className="fh-text-caption mt-1">{operationItem?.errorMessage ?? channel.validationMessage ?? formatStatus(operationItem?.status ?? 'ready')}</div>
      </td>
      <td className="px-4 py-3">
        <Badge variant={operationItem?.status === "failed" ? "error" : channel.pendingChange ? "warning" : operationItem?.status === "applied" ? "success" : "neutral"}>
          {operationItem?.status ? formatStatus(operationItem.status) : (channel.pendingChange ? translate('products:products.pending') : translate('products:products.unchanged'))}
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
    <div className="rounded border border-border bg-bg-base px-3 py-3" aria-label={translate('products:products.channelPriceOperationResult')}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="fh-text-body font-semibold">{translate('products:products.operation')} {operation.id}</div>
          <div className="fh-text-caption">{translate('products:products.status')} {formatStatus(operation.status)}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="neutral">{translate('products:products.total')} {operation.summary.total}</Badge>
          <Badge variant="success">{translate('products:products.success2')} {operation.summary.success}</Badge>
          <Badge variant={operation.summary.failed ? "error" : "neutral"}>{translate('products:products.failed2')} {operation.summary.failed}</Badge>
          <Badge variant={operation.externalWritePerformed ? "warning" : "success"}>
            {operation.externalWritePerformed ? translate('products:products.externalWritePerformed') : translate('products:products.noExternalWrite')}
          </Badge>
        </div>
      </div>
      {operation.items.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="fh-table min-w-[760px]">
            <thead>
              <tr>
                {['channel', 'previous', 'proposed', 'outbound', 'result'].map(key => <th key={key}>{translate(`products:column.${key}`)}</th>)}
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
                    <Badge variant={item.status === "failed" ? "error" : item.status === "applied" ? "success" : "warning"}>{formatStatus(item.status)}</Badge>
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
  const { products: productService, unifiedWorkspace } = useServices()

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [productType, setProductType] = useState<'all' | 'simple' | 'variable' | 'variation'>('all')
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
  const [workspaceSelection, setWorkspaceSelection] = useState<Map<string, Product>>(new Map())
  const [workspaceCreating, setWorkspaceCreating] = useState(false)
  const [workspaceError, setWorkspaceError] = useState<string | null>(null)

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
        const value = raw === undefined || raw.trim() === '' ? channel.proposedValue : parseMoneyInput(raw)
        if (value === null || value === undefined) return null
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
          formatMoneyInput(channel.proposedValue),
        ])))
      })
      .catch(error => setEditorError(localizedApiError(error, 'products:products.unableToLoadChannelPrices')))
      .finally(() => setEditorLoading(false))
  }, [productService])

  const validatePrices = useCallback(() => {
    if (!priceState) return
    setEditorLoading(true)
    setEditorError(null)
    productService.validateChannelPrices(priceState.product.id, { changes: selectedChanges })
      .then(setPriceState)
      .catch(error => setEditorError(localizedApiError(error, 'products:products.unableToValidateChannelPrices')))
      .finally(() => setEditorLoading(false))
  }, [priceState, productService, selectedChanges])

  const createDryRun = useCallback(() => {
    if (!priceState) return
    setEditorLoading(true)
    setEditorError(null)
    productService.createChannelPriceDryRun(priceState.product.id, { version: priceState.version, changes: selectedChanges })
      .then(setPriceOperation)
      .catch(error => setEditorError(localizedApiError(error, 'products:products.unableToCreateDryRun')))
      .finally(() => setEditorLoading(false))
  }, [priceState, productService, selectedChanges])

  const approveOperation = useCallback(() => {
    if (!priceOperation) return
    setEditorLoading(true)
    setEditorError(null)
    productService.approveChannelPriceOperation(priceOperation.id,
      /* i18n-ignore -- stable API audit reason, never displayed as interface copy */ 'Approved from Products multi-channel price editor')
      .then(setPriceOperation)
      .catch(error => setEditorError(localizedApiError(error, 'products:products.unableToApproveDryRun')))
      .finally(() => setEditorLoading(false))
  }, [priceOperation, productService])

  const applyOperation = useCallback(() => {
    if (!priceOperation) return
    setEditorLoading(true)
    setEditorError(null)
    productService.applyChannelPriceOperation(priceOperation.id)
      .then(operation => {
        setPriceOperation(operation)
        const failedChannels = new Set(operation.items.filter(item => item.status === 'failed').map(item => item.channelId))
        if (priceState) {
          productService.getChannelPrices(priceState.product.id)
            .then(state => {
              setPriceState(state)
              setDraftValues(current => Object.fromEntries(state.channels.map(channel => [
                channel.channelId,
                failedChannels.has(channel.channelId)
                  ? current[channel.channelId] ?? formatMoneyInput(channel.currentValue)
                  : formatMoneyInput(channel.currentValue),
              ])))
            })
            .catch(() => {})
        }
        fetchProducts()
      })
      .catch(error => setEditorError(localizedApiError(error, 'products:products.unableToApplyChannelPrices')))
      .finally(() => setEditorLoading(false))
  }, [fetchProducts, priceOperation, priceState, productService])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const end = Math.min(page * PAGE_SIZE, total)

  const createManualWorkspace = useCallback(async () => {
    if (!unifiedWorkspace || workspaceSelection.size === 0) return
    setWorkspaceCreating(true)
    setWorkspaceError(null)
    try {
      const workspace = await unifiedWorkspace.createManual(
        translate('products:products.manualWorkspaceDated', { date: formatDate(new Date()) }),
        [...workspaceSelection.values()].map(product => ({ connector_id: product.connectorId ?? '', product_id: product.id })),
      )
      window.location.href = `/workspace/${workspace.id}`
    } catch (error) {
      setWorkspaceError(localizedApiError(error, 'products:products.unableToCreateManualWorkspace'))
    } finally {
      setWorkspaceCreating(false)
    }
  }, [unifiedWorkspace, workspaceSelection])

  if (!loading && configured === false) {
    return (
      <PageShell>
        <div>
          <h1 className="fh-page-title">{translate('products:products.products')}</h1>
          <p className="fh-page-subtitle">{translate('products:products.productCatalog')}</p>
        </div>
        <div className="fh-card">
          <Empty
            title={translate('products:products.noProductConnectorConfigured')}
            description={translate('products:products.connectAProductSourceFromSourcesTo')}
            action={{ label: translate('products:products.openSources'), onClick: () => { window.location.href = '/sources' } }}
          />
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('products:products.products')}</h1>
          <p className="fh-page-subtitle">
            {loading ? translate('products:products.loading') : translate('products:products.productCount', { count: total })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="fh-text-caption">{workspaceSelection.size} {translate('products:products.selected')}</span>
          <button type="button" className="fh-button-primary" disabled={!unifiedWorkspace || workspaceSelection.size === 0 || workspaceCreating} onClick={() => void createManualWorkspace()}>
            <Icon name="workspace" /> {workspaceCreating ? translate('products:products.creating') : translate('products:products.createWorkspace')}
          </button>
        </div>
      </div>

      {workspaceError && <div className="fh-alert fh-alert-danger" role="alert"><Icon name="alert" /><span>{workspaceError}</span></div>}

      <div className="fh-card fh-card-pad flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[180px]">
          <Icon name="search" className="absolute left-2.5 top-1/2 -translate-y-1/2 text-wp-muted pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            {...inputHint(translate('products:products.searchNameOrSku'))}
            className="fh-input pl-8"
          />
        </div>

        <select
          value={channelId}
          onChange={e => setChannelId(e.target.value)}
          className="fh-select w-auto min-w-[150px]"
        >
          {CHANNEL_OPTIONS.map(channel => (
            <option key={channel.id || "all"} value={channel.id}>{translate(channel.labelKey)}</option>
          ))}
        </select>

        {categories.length > 0 && (
          <select
            value={categoryId ?? ''}
            onChange={e => setCategoryId(e.target.value ? Number(e.target.value) : null)}
            className="fh-select w-auto min-w-[170px]"
          >
            <option value="">{translate('products:products.allCategories')}</option>
            {categories.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        )}

        <div className="fh-segmented">
          {(["all", "simple", "variation", "variable"] as const).map(t => (
            <button
              key={t}
              onClick={() => setProductType(t)}
              className={[
                "fh-segmented-button capitalize",
                productType === t ? "fh-segmented-button-active" : '',
              ].join(' ')}
            >
              {t === "all" ? translate('products:products.allTypes') : t}
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
            {loading ? translate('products:products.loading') : total === 0 ? translate('products:products.noProductsFound') : translate('products:products.showingOf', { value1: start, value2: end, value3: total })}
          </span>
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <IconButton label={translate('products:products.previousPage')} onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} size="sm">
                <Icon name="previous" mirrorRtl />
              </IconButton>
              <span className="fh-text-caption px-1">{page} / {totalPages}</span>
              <IconButton label={translate('products:products.nextPage')} onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} size="sm">
                <Icon name="next" mirrorRtl />
              </IconButton>
            </div>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="fh-table min-w-[560px]">
            <thead>
              <tr>
                {['select', 'product', 'type', 'price', 'categories', 'actions'].map(key => (
                  <th key={key}>{translate(`products:column.${key}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody className={loading ? "opacity-40 pointer-events-none" : ''}>
              {loading && items.length === 0
                ? Array.from({ length: PAGE_SIZE }).map((_, i) => <SkeletonRow key={i} />)
                : items.length === 0
                  ? (
                    <tr>
                      <td colSpan={6}>
                        <Empty title={translate('products:products.noProductsMatch')} description={translate('products:products.tryAdjustingTheSearchOrFilter')} />
                      </td>
                    </tr>
                    )
                  : items.map(p => {
                    const selectionKey = `${p.connectorId ?? ''}:${p.id}`
                    return (
                      <ProductRow
                        key={selectionKey}
                        product={p}
                        onEditPrices={openPriceEditor}
                        selected={workspaceSelection.has(selectionKey)}
                        onSelected={selected => setWorkspaceSelection(current => {
                          const next = new Map(current)
                          if (selected) next.set(selectionKey, p)
                          else next.delete(selectionKey)
                          return next
                        })}
                      />
                    )
                  })}
            </tbody>
          </table>
        </div>

        {!loading && totalPages > 1 && (
          <div className="fh-panel-footer !justify-between">
            <span className="fh-text-caption">{start}-{end} {translate('products:products.of')} {total}</span>
            <div className="flex items-center gap-1">
              <IconButton label={translate('products:products.firstPage')} onClick={() => setPage(1)} disabled={page === 1} size="sm">
                <span aria-hidden="true" className="fh-text-caption">«</span>
              </IconButton>
              <IconButton label={translate('products:products.previousPage')} onClick={() => setPage(p => p - 1)} disabled={page === 1} size="sm">
                <Icon name="previous" mirrorRtl />
              </IconButton>
              <span className="fh-text-caption px-1.5">{page} / {totalPages}</span>
              <IconButton label={translate('products:products.nextPage')} onClick={() => setPage(p => p + 1)} disabled={page === totalPages} size="sm">
                <Icon name="next" mirrorRtl />
              </IconButton>
              <IconButton label={translate('products:products.lastPage')} onClick={() => setPage(totalPages)} disabled={page === totalPages} size="sm">
                <span aria-hidden="true" className="fh-text-caption">»</span>
              </IconButton>
            </div>
          </div>
        )}
      </div>
    </PageShell>
  )
}
