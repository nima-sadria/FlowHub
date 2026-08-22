import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { ApiError } from '../api/client'
import Badge, { type BadgeVariant } from '../components/Badge'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import LocalizedText from '../components/LocalizedText'
import PageShell from '../components/PageShell'
import Spinner from '../components/loading/Spinner'
import { translate } from '../i18n'
import { formatProductType } from '../i18n/display'
import { formatMoney } from '../utils/price'
import { useServices } from '../services/ServiceContext'
import type { ProductService } from '../services/products/ProductService'
import type {
  ChannelPriceValidationState,
  Product,
  ProductChannelField,
  ProductChannelFieldState,
  ProductChannelPriceChange,
  ProductChannelPriceOperation,
  ProductChannelPriceState,
  ProductChannelPriceStateSet,
} from '../services/types'

// Manual Channel Editor: the Owner directly edits Channel fields (today:
// price) with no Source comparison, auto-selection, Dry Run scoring, or
// Apply Manifest business rules. Normal technical/security controls still
// apply: permissions, connector capability, provider validation, safe
// write execution (validate -> Dry Run -> Approve -> Apply), verification,
// and audit. See docs/evidence/workspace-adoption/WORKSPACE_CANONICAL_OWNER_SPEC_2026-08-22.md
// section 9. The automated Source-to-Channel reconciliation engine lives
// at /workspace (frontend/src/pages/Workspace.tsx), not here.

const PAGE_SIZE = 50

const CHANNEL_NAME_KEY: Record<string, string> = {
  'woocommerce:primary': 'products:products.woocommerce',
  'snappshop:main': 'products:products.snappShop',
  'tapsishop:main': 'products:products.tapsiShop',
}

function channelDisplayName(channel: { channelId: string; channelName: string }): string {
  const key = CHANNEL_NAME_KEY[channel.channelId]
  return key ? translate(key) : channel.channelName
}

function describeError(cause: unknown, fallbackKey: string): string {
  if (cause instanceof ApiError && cause.status !== 409 && cause.status !== 422) {
    return `${translate(fallbackKey)} (HTTP ${cause.status})`
  }
  if (cause instanceof ApiError) return cause.message || translate(fallbackKey)
  return translate(fallbackKey)
}

function isStaleConflict(cause: unknown): boolean {
  return cause instanceof ApiError && cause.status === 409
    && (cause.code === 'STALE_PRODUCT_PRICE_STATE' || cause.code === 'STALE_CHANNEL_PRICE_STATE')
}

function ProductRow({ product, onSelect }: { product: Product; onSelect: () => void }) {
  return <tr data-product-id={product.id}>
    <td>
      <button type="button" className="fh-link" onClick={onSelect} data-open-channel-editor={product.id}>
        <LocalizedText text={product.name} />
      </button>
    </td>
    <td className="fh-text-mono">{product.sku || '—'}</td>
    <td><Badge variant="neutral">{formatProductType(product.productType)}</Badge></td>
    <td>{(product.categoryNames ?? []).join(', ') || '—'}</td>
    <td className="fh-text-mono text-end">{formatMoney(product.currentPrice, { unit: product.currency })}</td>
  </tr>
}

export default function Products() {
  const { products: productService } = useServices()
  const [searchParams] = useSearchParams()
  const querySearch = searchParams.get('q')?.trim() ?? ''
  const [items, setItems] = useState<Product[]>([])
  const [configured, setConfigured] = useState<boolean | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setListError(null)
    productService.getProducts({ search: querySearch, status: 'all', page: 1, pageSize: PAGE_SIZE })
      .then(result => {
        if (!active) return
        setItems(result.items)
        setConfigured(result.configured)
      })
      .catch((cause: unknown) => { if (active) { setItems([]); setListError(describeError(cause, 'products:products.unableToLoadProducts')) } })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [productService, querySearch, attempt])

  const header = <div className="fh-page-header">
    <div>
      <h1 className="fh-page-title">{translate('products:products.products')}</h1>
      <p className="fh-page-subtitle">{translate('products:products.manualChannelEditorSubtitle')}</p>
    </div>
  </div>

  if (selectedProductId) {
    return <PageShell>
      {header}
      <ProductChannelEditor
        productId={selectedProductId}
        service={productService}
        onClose={() => setSelectedProductId(null)}
      />
    </PageShell>
  }

  if (!loading && configured === false) {
    return <PageShell>{header}<div className="fh-card"><Empty
      title={translate('products:products.noProductConnectorConfigured')}
      description={translate('products:products.connectAProductSourceFromSourcesTo')}
    /></div></PageShell>
  }

  return <PageShell>
    {header}
    {listError && <div className="fh-alert fh-alert-warning" role="alert">
      <Icon name="alert" /><span>{listError}</span>
      <button type="button" className="fh-button-secondary" onClick={() => setAttempt(value => value + 1)}>
        <Icon name="refresh" /> {translate('products:products.tryAgain')}
      </button>
    </div>}
    {loading ? <Spinner /> : <div className="fh-card mt-3 overflow-hidden">
      <div className="overflow-x-auto"><table className="fh-table min-w-[760px]">
        <thead><tr>
          <th>{translate('products:column.product')}</th>
          <th>{translate('products:column.sku')}</th>
          <th>{translate('products:column.type')}</th>
          <th>{translate('products:column.categories')}</th>
          <th className="text-end">{translate('products:column.current')}</th>
        </tr></thead>
        <tbody>{items.length
          ? items.map(product => <ProductRow key={`${product.connectorId ?? ''}:${product.id}`} product={product} onSelect={() => setSelectedProductId(product.id)} />)
          : <tr><td colSpan={5}><Empty title={translate('products:products.noProductsFound')} /></td></tr>}
        </tbody>
      </table></div>
    </div>}
  </PageShell>
}

// -- Manual Channel Editor -------------------------------------------------

type EditorPhase = 'edit' | 'operation'

const FIELD_KEYS: readonly ProductChannelField[] = ['price', 'stock', 'status']
const STATUS_OPTIONS: readonly ['instock', 'outofstock'] = ['instock', 'outofstock']

const VALIDATION_BADGE: Record<ChannelPriceValidationState, BadgeVariant> = {
  valid: 'success',
  error: 'danger',
  read_only: 'neutral',
  disconnected: 'neutral',
}

function draftKey(channelId: string, field: ProductChannelField): string {
  return `${channelId}:${field}`
}

function fieldLabel(field: ProductChannelField): string {
  if (field === 'price') return translate('products:column.price')
  if (field === 'stock') return translate('products:products.stockQuantity')
  return translate('products:products.stockStatus')
}

function statusLabel(value: string | number | null): string {
  if (value === 'instock') return translate('products:products.inStock')
  if (value === 'outofstock') return translate('products:products.outOfStock')
  return '—'
}

function formatFieldValue(field: ProductChannelField, unit: string, value: number | string | null): string {
  if (field === 'status') return statusLabel(value)
  if (field === 'stock') return value === null ? '—' : String(value)
  return formatMoney(value, { unit })
}

function ProductChannelEditor({ productId, service, onClose }: {
  productId: string
  service: ProductService
  onClose: () => void
}) {
  const [state, setState] = useState<ProductChannelPriceStateSet | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stale, setStale] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [phase, setPhase] = useState<EditorPhase>('edit')
  const [operation, setOperation] = useState<ProductChannelPriceOperation | null>(null)
  const [operationError, setOperationError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    setStale(false)
    return service.getChannelPrices(productId)
      .then(result => { setState(result); setDraft({}) })
      .catch((cause: unknown) => setError(describeError(cause, 'products:products.unableToLoadChannelPrices')))
      .finally(() => setLoading(false))
  }, [productId, service])

  useEffect(() => { void load() }, [load])

  const edited = useMemo(() => {
    if (!state) return []
    const result: { channel: ProductChannelPriceState; field: ProductChannelField; fieldState: ProductChannelFieldState; raw: string }[] = []
    for (const channel of state.channels) {
      for (const field of FIELD_KEYS) {
        const raw = draft[draftKey(channel.channelId, field)]
        if (raw === undefined) continue
        const fieldState = channel.fields[field]
        if (field === 'status') {
          if (raw !== fieldState.currentValue) result.push({ channel, field, fieldState, raw })
          continue
        }
        const parsed = Number(raw)
        if (Number.isFinite(parsed) && parsed !== fieldState.currentValue) result.push({ channel, field, fieldState, raw })
      }
    }
    return result
  }, [state, draft])

  const buildChanges = useCallback((): ProductChannelPriceChange[] => edited.map(({ channel, field, fieldState, raw }) => ({
    channelId: channel.channelId,
    field,
    proposedValue: field === 'status' ? raw : Number(raw),
    unit: fieldState.unit,
    staleToken: channel.staleToken,
  })), [edited])

  const preview = useCallback(async () => {
    if (!state || edited.length === 0) return
    setBusy(true)
    setOperationError(null)
    try {
      setState(await service.validateChannelPrices(productId, { version: state.version, changes: buildChanges() }))
    } catch (cause) {
      if (isStaleConflict(cause)) setStale(true)
      else setOperationError(describeError(cause, 'products:products.unableToValidateChannelPrices'))
    } finally {
      setBusy(false)
    }
  }, [buildChanges, edited.length, productId, service, state])

  const createDryRun = useCallback(async () => {
    if (!state || edited.length === 0) return
    setBusy(true)
    setOperationError(null)
    try {
      setOperation(await service.createChannelPriceDryRun(productId, { version: state.version, changes: buildChanges() }))
      setPhase('operation')
    } catch (cause) {
      if (isStaleConflict(cause)) setStale(true)
      else setOperationError(describeError(cause, 'products:products.unableToCreateDryRun'))
    } finally {
      setBusy(false)
    }
  }, [buildChanges, edited.length, productId, service, state])

  const approve = useCallback(async () => {
    if (!operation) return
    setBusy(true)
    setOperationError(null)
    try {
      setOperation(await service.approveChannelPriceOperation(operation.id))
    } catch (cause) {
      setOperationError(describeError(cause, 'products:products.unableToApproveDryRun'))
    } finally {
      setBusy(false)
    }
  }, [operation, service])

  const apply = useCallback(async () => {
    if (!operation) return
    setBusy(true)
    setOperationError(null)
    try {
      setOperation(await service.applyChannelPriceOperation(operation.id))
    } catch (cause) {
      setOperationError(describeError(cause, 'products:products.unableToApplyChannelPrices'))
    } finally {
      setBusy(false)
    }
  }, [operation, service])

  const startOver = useCallback(() => {
    setPhase('edit')
    setOperation(null)
    setOperationError(null)
    void load()
  }, [load])

  if (loading) return <div className="fh-card mt-3"><Spinner /></div>
  if (error || !state) {
    return <div className="fh-card mt-3"><Empty
      title={translate('products:products.unableToLoadChannelPrices')}
      description={error ?? undefined}
      action={{ label: translate('products:products.tryAgain'), onClick: () => void load() }}
    /></div>
  }

  return <div className="fh-card mt-3" data-channel-editor={productId}>
    <div className="fh-page-header">
      <div>
        <h2 className="fh-page-title">{translate('products:products.multiChannelPriceEditor')}</h2>
        <p className="fh-page-subtitle">
          <LocalizedText text={state.product.name} />{state.product.sku ? ` · ${state.product.sku}` : ''}
        </p>
      </div>
      <button type="button" className="fh-button-secondary" onClick={onClose} aria-label={translate('products:products.closeChannelPriceEditor')}>
        <Icon name="previous" /> {translate('products:products.products')}
      </button>
    </div>

    {state.canonical.value !== null && <p className="fh-text-caption">
      {translate('products:products.canonicalBusinessPrice')}: {formatMoney(state.canonical.value, { unit: state.canonical.unit })}
    </p>}

    {stale && <div className="fh-alert fh-alert-warning" role="alert">
      <Icon name="alert" /><span>{translate('products:products.unableToLoadChannelPrices')}</span>
      <button type="button" className="fh-button-secondary" onClick={() => void load()}>
        <Icon name="refresh" /> {translate('products:products.tryAgain')}
      </button>
    </div>}
    {operationError && <div className="fh-alert fh-alert-warning" role="alert"><Icon name="alert" /><span>{operationError}</span></div>}

    {phase === 'edit'
      ? <ChannelEditForm
          channels={state.channels}
          draft={draft}
          setDraft={setDraft}
          editedCount={edited.length}
          busy={busy}
          onPreview={() => void preview()}
          onCreateDryRun={() => void createDryRun()}
        />
      : operation && <OperationPanel
          operation={operation}
          busy={busy}
          onApprove={() => void approve()}
          onApply={() => void apply()}
          onStartOver={startOver}
        />}
  </div>
}

function ChannelEditForm({ channels, draft, setDraft, editedCount, busy, onPreview, onCreateDryRun }: {
  channels: readonly ProductChannelPriceState[]
  draft: Record<string, string>
  setDraft: (updater: (current: Record<string, string>) => Record<string, string>) => void
  editedCount: number
  busy: boolean
  onPreview: () => void
  onCreateDryRun: () => void
}) {
  return <div>
    <table className="fh-table">
      <thead><tr>
        <th>{translate('products:column.channel')}</th>
        <th>{translate('products:column.state')}</th>
        <th>{translate('products:column.price')}</th>
        <th>{translate('products:products.stockQuantity')}</th>
        <th>{translate('products:products.stockStatus')}</th>
      </tr></thead>
      <tbody>{channels.map(channel => {
        const name = channelDisplayName(channel)
        return <tr key={channel.channelId} data-channel-row={channel.channelId}>
          <td>{name}</td>
          <td><Badge variant={FIELD_KEYS.some(field => channel.fields[field].canWrite) ? 'success' : 'neutral'}>
            {channel.connectionState}
          </Badge></td>
          {FIELD_KEYS.map(field => <td key={field} data-field-cell={field}>
            <FieldEditCell
              channel={channel}
              field={field}
              fieldState={channel.fields[field]}
              draft={draft}
              setDraft={setDraft}
              busy={busy}
              channelName={name}
            />
          </td>)}
        </tr>
      })}</tbody>
    </table>
    <div className="fh-page-header mt-3">
      <span className="fh-text-caption">{translate('products:products.pendingEdits')}: {editedCount}</span>
      <div className="flex gap-2">
        <button type="button" className="fh-button-secondary" disabled={busy || editedCount === 0} onClick={onPreview}>
          {translate('products:products.validate')}
        </button>
        <button type="button" className="fh-button-primary" disabled={busy || editedCount === 0} onClick={onCreateDryRun}>
          {translate('products:products.dryRun')}
        </button>
      </div>
    </div>
  </div>
}

function FieldEditCell({ channel, field, fieldState, draft, setDraft, busy, channelName }: {
  channel: ProductChannelPriceState
  field: ProductChannelField
  fieldState: ProductChannelFieldState
  draft: Record<string, string>
  setDraft: (updater: (current: Record<string, string>) => Record<string, string>) => void
  busy: boolean
  channelName: string
}) {
  const key = draftKey(channel.channelId, field)
  const raw = draft[key] ?? (fieldState.currentValue ?? '').toString()
  const label = translate('products:products.proposedPrice', { channel: `${channelName} ${fieldLabel(field)}` })

  if (!fieldState.canWrite) {
    return <div>
      <span className="fh-text-mono">{formatFieldValue(field, fieldState.unit, fieldState.currentValue)}</span>
      {fieldState.validationMessage && <p className="fh-text-caption">{fieldState.validationMessage}</p>}
    </div>
  }

  return <div>
    <span className="fh-text-caption">{formatFieldValue(field, fieldState.unit, fieldState.currentValue)}</span>
    {field === 'status'
      ? <select
          className="fh-input"
          aria-label={label}
          value={STATUS_OPTIONS.includes(raw as typeof STATUS_OPTIONS[number]) ? raw : String(fieldState.currentValue ?? '')}
          disabled={busy}
          onChange={event => {
            const next = event.target.value
            setDraft(current => ({ ...current, [key]: next }))
          }}
        >
          {STATUS_OPTIONS.map(option => <option key={option} value={option}>{statusLabel(option)}</option>)}
        </select>
      : <input
          type="text"
          inputMode="decimal"
          className="fh-input fh-text-mono"
          aria-label={label}
          value={raw}
          disabled={busy}
          onChange={event => {
            const next = event.target.value
            setDraft(current => ({ ...current, [key]: next }))
          }}
        />}
    {fieldState.validationMessage && <Badge variant={VALIDATION_BADGE[fieldState.validationState]}>{fieldState.validationMessage}</Badge>}
  </div>
}

function OperationPanel({ operation, busy, onApprove, onApply, onStartOver }: {
  operation: ProductChannelPriceOperation
  busy: boolean
  onApprove: () => void
  onApply: () => void
  onStartOver: () => void
}) {
  return <div>
    <div className="fh-page-header">
      <h3 className="fh-page-title">{translate('products:products.operation')}</h3>
      <Badge variant={operationStatusVariant(operation.status)}>{operation.status}</Badge>
    </div>
    <p className="fh-text-caption">
      {translate('products:products.total')}: {operation.summary.total} ·{' '}
      {translate('products:products.success2')}: {operation.summary.success} ·{' '}
      {translate('products:products.failed2')}: {operation.summary.failed}
    </p>
    <table className="fh-table">
      <thead><tr>
        <th>{translate('products:column.channel')}</th>
        <th>{translate('products:products.field')}</th>
        <th className="text-end">{translate('products:column.current')}</th>
        <th className="text-end">{translate('products:column.proposed')}</th>
        <th>{translate('products:column.result')}</th>
      </tr></thead>
      <tbody>{operation.items.map(item => <tr key={item.id} data-operation-item={item.channelId} data-operation-field={item.field}>
        <td>{CHANNEL_NAME_KEY[item.channelId] ? translate(CHANNEL_NAME_KEY[item.channelId]) : item.channelId}</td>
        <td>{fieldLabel(item.field)}</td>
        <td className="fh-text-mono text-end">{formatFieldValue(item.field, item.unit, item.currentValue)}</td>
        <td className="fh-text-mono text-end">{formatFieldValue(item.field, item.unit, item.proposedValue)}</td>
        <td><Badge variant={itemStatusVariant(item.status)}>{item.errorMessage ?? item.status}</Badge></td>
      </tr>)}</tbody>
    </table>
    <div className="fh-page-header mt-3">
      <button type="button" className="fh-button-secondary" onClick={onStartOver} disabled={busy}>
        {translate('products:products.products')}
      </button>
      <div className="flex gap-2">
        {operation.status === 'dry_run_ready' && <button type="button" className="fh-button-primary" disabled={busy} onClick={onApprove}>
          {translate('products:products.approve')}
        </button>}
        {(operation.status === 'approved' || operation.status === 'reconciliation_required') && <button type="button" className="fh-button-primary" disabled={busy} onClick={onApply}>
          {translate('products:products.apply')}
        </button>}
      </div>
    </div>
  </div>
}

function operationStatusVariant(status: ProductChannelPriceOperation['status']): BadgeVariant {
  switch (status) {
    case 'applied': return 'success'
    case 'failed': return 'danger'
    case 'partially_failed': return 'warning'
    case 'reconciliation_required': return 'warning'
    case 'approved': return 'info'
    default: return 'neutral'
  }
}

function itemStatusVariant(status: string): BadgeVariant {
  if (status === 'applied') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'reconciliation_required') return 'warning'
  return 'neutral'
}
