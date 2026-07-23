import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import { SkeletonCard } from '../components/loading/Skeleton'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { translate } from '../i18n'
import { formatStatus } from '../i18n/display'
import { formatDateTime, formatRelativeTime } from '../i18n/format'
import { useServices } from '../services/ServiceContext'
import type { OrderSyncStatus } from '../services/orders/OrderService'
import type { ChannelOrderDetail, ChannelOrderListItem } from '../services/types'
import { formatMoney } from '../utils/price'

type Tone = 'success' | 'warning' | 'danger' | 'info' | 'neutral'
type ColumnKey = 'channel' | 'customer' | 'status' | 'payment' | 'fulfillment' | 'total' | 'created' | 'sync'
type SortField = 'order' | 'channel' | 'customer' | 'status' | 'total' | 'created'

const TOGGLE_COLUMNS: ColumnKey[] = ['channel', 'customer', 'status', 'payment', 'fulfillment', 'total', 'created', 'sync']
const ORDER_STATE_OPTIONS = ['pending', 'processing', 'fulfilled', 'cancelled', 'refunded', 'failed']

function formatTime(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : formatDateTime(date)
}

function statusTone(status: string): Tone {
  const normalized = status.toLowerCase()
  if (normalized.includes('cancel') || normalized.includes('fail')) return 'danger'
  if (normalized.includes('fulfill') || normalized.includes('deliver') || normalized === 'paid') return 'success'
  if (normalized.includes('process') || normalized.includes('pending') || normalized.includes('hold')) return 'warning'
  return 'info'
}

function syncTone(order: ChannelOrderListItem): Tone {
  if (order.errorState) return 'danger'
  if (order.synchronizationState === 'synced') return 'success'
  return 'neutral'
}

function canRetryRow(order: ChannelOrderListItem): boolean {
  return order.connectorType === 'woocommerce' && (Boolean(order.errorState) || order.synchronizationState !== 'synced')
}

function InlineStatus({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`fh-inline-status fh-inline-status-${tone}`}>
      <span aria-hidden="true" className={`fh-status-dot fh-status-dot-${tone}`} />
      {children}
    </span>
  )
}

function pageNumbers(current: number, total: number): (number | 'ellipsis')[] {
  if (total <= 5) return Array.from({ length: total }, (_, index) => index + 1)
  const candidates = new Set<number>([1, 2, 3, total, current - 1, current, current + 1])
  const filtered = [...candidates].filter(value => value >= 1 && value <= total).sort((a, b) => a - b)
  const result: (number | 'ellipsis')[] = []
  let previous = 0
  for (const value of filtered) {
    if (previous && value - previous > 1) result.push('ellipsis')
    result.push(value)
    previous = value
  }
  return result
}

function sortValue(order: ChannelOrderListItem, field: SortField): string | number {
  switch (field) {
    case 'order': return order.orderNumber || order.providerOrderId
    case 'channel': return formatChannelDisplayName(order.channelId)
    case 'customer': return order.customerDisplay || ''
    case 'status': return order.normalizedStatus
    case 'total': return order.finalAmount ?? 0
    case 'created': return order.createdAtProvider || ''
  }
}

function OrderDetail({ order }: { order: ChannelOrderDetail }) {
  return (
    <div className="border-t border-border bg-bg-base/50 px-4 py-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <section>
          <h3 className="fh-section-title mb-3">{translate('orders:orders.items')}</h3>
          <div className="overflow-x-auto">
            <table className="fh-table min-w-[720px]">
              <thead><tr><th>SKU</th><th>{translate('orders:orders.name')}</th><th>{translate('orders:orders.providerItem')}</th><th>{translate('orders:orders.qty')}</th><th>{translate('orders:orders.finalPrice')}</th><th>{translate('orders:orders.status')}</th></tr></thead>
              <tbody>{order.items.map(item => <tr key={item.providerItemId}><td>{item.sku || '—'}</td><td>{item.name || '—'}</td><td>{item.providerItemId}</td><td>{item.quantity}</td><td>{formatMoney(item.finalPrice, { currency: order.currency })}</td><td>{item.itemStatus || '—'}</td></tr>)}</tbody>
            </table>
          </div>
        </section>
        <section>
          <h3 className="fh-section-title mb-3">{translate('orders:orders.shipments')}</h3>
          {order.shipments.length === 0 ? <p className="fh-text-caption">{translate('orders:orders.noShipmentData')}</p> : <div className="space-y-2">{order.shipments.map(item => <div className="rounded-md border border-border bg-bg-card p-3" key={item.shipmentNumber}><div className="font-medium">{item.shipmentNumber}</div><div className="fh-text-caption">{item.statusTitle || item.statusCode || '—'}</div></div>)}</div>}
        </section>
        <section>
          <h3 className="fh-section-title mb-3">{translate('orders:orders.timeline')}</h3>
          <div className="space-y-2">{order.timeline.map((event, index) => <div className="rounded-md border border-border bg-bg-card p-3" key={`${event.eventName}-${index}`}><div className="font-medium">{formatStatus(event.eventName)}</div><div className="fh-text-caption">{event.message}</div><div className="fh-text-caption">{formatTime(event.createdAt)}</div></div>)}</div>
        </section>
      </div>
    </div>
  )
}

export default function Orders() {
  const { orders } = useServices()
  const [items, setItems] = useState<ChannelOrderListItem[]>([])
  const [syncStatuses, setSyncStatuses] = useState<OrderSyncStatus[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [channelId, setChannelId] = useState('')
  const [orderStatus, setOrderStatus] = useState('')
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<ChannelOrderDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [columnsOpen, setColumnsOpen] = useState(false)
  const [sortOpen, setSortOpen] = useState(false)
  const [savedViewsOpen, setSavedViewsOpen] = useState(false)
  const [rowMenuFor, setRowMenuFor] = useState<number | null>(null)
  const [hiddenColumns, setHiddenColumns] = useState<Set<ColumnKey>>(new Set())
  const [sort, setSort] = useState<{ field: SortField; direction: 'asc' | 'desc' } | null>(null)
  const [showOnlyFailed, setShowOnlyFailed] = useState(false)

  const load = useCallback(async () => {
    if (!orders) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    try {
      const [result, statusResult] = await Promise.all([
        orders.getOrders({ page, pageSize, channelId, status: orderStatus, search, dateFrom, dateTo }),
        orders.getSyncStatus(),
      ])
      setItems(result.items)
      setTotal(result.total)
      setSyncStatuses(statusResult.items)
    } catch {
      setError(translate('orders:orders.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [channelId, dateFrom, dateTo, orderStatus, orders, page, pageSize, search])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    if (!rowMenuFor && !filtersOpen && !columnsOpen && !sortOpen && !savedViewsOpen) return
    const close = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null
      if (target?.closest('[data-row-actions]') || target?.closest('[data-orders-filters]') || target?.closest('[data-orders-columns]') || target?.closest('[data-orders-sort]') || target?.closest('[data-orders-saved-views]')) return
      setRowMenuFor(null)
      setFiltersOpen(false)
      setColumnsOpen(false)
      setSortOpen(false)
      setSavedViewsOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [columnsOpen, filtersOpen, rowMenuFor, savedViewsOpen, sortOpen])

  const pages = Math.max(1, Math.ceil(total / pageSize))
  const selectedSyncStatus = useMemo(
    () => syncStatuses.find(item => item.channelId === channelId)
      ?? syncStatuses.find(item => item.connectorType === 'woocommerce')
      ?? syncStatuses[0],
    [channelId, syncStatuses],
  )

  const visibleItems = useMemo(() => {
    const filtered = showOnlyFailed ? items.filter(order => order.errorState || order.synchronizationState !== 'synced') : items
    if (!sort) return filtered
    const copy = [...filtered]
    copy.sort((a, b) => {
      const left = sortValue(a, sort.field)
      const right = sortValue(b, sort.field)
      const compared = typeof left === 'number' && typeof right === 'number' ? left - right : String(left).localeCompare(String(right))
      return sort.direction === 'asc' ? compared : -compared
    })
    return copy
  }, [items, showOnlyFailed, sort])

  const filterCount = [dateFrom, dateTo].filter(Boolean).length
  const rangeFrom = total === 0 ? 0 : (page - 1) * pageSize + 1
  const rangeTo = Math.min(page * pageSize, total)

  async function openDetail(order: ChannelOrderListItem) {
    if (!orders) return
    setDetailLoading(true)
    try {
      setSelected(await orders.getOrder(order.internalId))
    } finally {
      setDetailLoading(false)
    }
  }

  async function synchronize() {
    if (!orders || !selectedSyncStatus || selectedSyncStatus.connectorType !== 'woocommerce') return
    setSyncing(true)
    setError('')
    try {
      await orders.syncChannel(selectedSyncStatus.channelId)
      await load()
    } catch {
      setError(translate('orders:orders.syncFailed'))
    } finally {
      setSyncing(false)
    }
  }

  async function retryRowSync(order: ChannelOrderListItem) {
    if (!orders || !canRetryRow(order)) return
    setSyncing(true)
    setError('')
    try {
      await orders.syncChannel(order.channelId)
      await load()
    } catch {
      setError(translate('orders:orders.syncFailed'))
    } finally {
      setSyncing(false)
    }
  }

  function toggleSort(field: SortField) {
    setSort(current => {
      if (!current || current.field !== field) return { field, direction: 'asc' }
      if (current.direction === 'asc') return { field, direction: 'desc' }
      return null
    })
  }

  function toggleColumn(key: ColumnKey) {
    setHiddenColumns(current => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const emptyState = selectedSyncStatus?.state === 'disabled'
    ? { title: translate('orders:orders.syncDisabled'), description: translate('orders:orders.enableChannelToSync') }
    : selectedSyncStatus?.state === 'never_run'
      ? { title: translate('orders:orders.syncNeverRun'), description: translate('orders:orders.runReadOnlySync') }
      : selectedSyncStatus?.state === 'error'
        ? { title: translate('orders:orders.lastSyncFailed'), description: translate('orders:orders.retryReadOnlySync') }
        : { title: translate('orders:orders.noMatchingOrders'), description: translate('orders:orders.adjustFilters') }

  const stripTone: Tone = selectedSyncStatus?.state === 'error' ? 'danger'
    : selectedSyncStatus?.state === 'disabled' || selectedSyncStatus?.state === 'never_run' ? 'neutral'
      : selectedSyncStatus?.state ? 'success' : 'neutral'
  const stripLabel = selectedSyncStatus?.state === 'error' ? translate('orders:orders.syncError')
    : selectedSyncStatus?.state === 'disabled' ? translate('common:status.disabled')
      : selectedSyncStatus?.state === 'never_run' ? translate('common:status.notRun')
        : translate('orders:orders.synced')
  const bottomSubtitle = selectedSyncStatus?.state === 'error' ? translate('orders:orders.lastSyncFailed')
    : selectedSyncStatus?.state === 'never_run' ? translate('orders:orders.syncNeverRun')
      : selectedSyncStatus?.state === 'disabled' ? translate('orders:orders.syncDisabled')
        : translate('orders:orders.allSynchronized')
  const canSync = Boolean(selectedSyncStatus) && selectedSyncStatus?.connectorType === 'woocommerce' && selectedSyncStatus.state !== 'disabled'

  return (
    <PageShell>
      <div className="fh-page-header">
        <div><h1 className="fh-page-title">{translate('orders:orders.orders')}</h1><p className="fh-page-subtitle">{translate('orders:orders.businessSubtitle')}</p></div>
        <button className="fh-button-primary" type="button" disabled={syncing || selectedSyncStatus?.state === 'disabled' || selectedSyncStatus?.connectorType !== 'woocommerce'} onClick={() => void synchronize()}>
          {syncing ? translate('orders:orders.syncing') : translate('orders:orders.syncOrders')}
        </button>
      </div>

      <section className="fh-card fh-card-pad mb-4 flex flex-wrap items-center justify-between gap-3" data-orders-sync-strip>
        <div className="flex items-center gap-2">
          <InlineStatus tone={stripTone}>{stripLabel}</InlineStatus>
          {selectedSyncStatus?.lastSuccessAt && <span className="fh-text-caption">{translate('orders:orders.lastSynchronized')} {formatRelativeTime(selectedSyncStatus.lastSuccessAt)}</span>}
        </div>
        {selectedSyncStatus?.state === 'error' && (
          <div className="flex items-center gap-2">
            <InlineStatus tone="danger">{translate('orders:orders.syncError')}</InlineStatus>
            <button className="fh-button-secondary fh-button-sm" type="button" disabled={syncing || !canSync} onClick={() => void synchronize()}>{translate('orders:orders.retryFailed')}</button>
          </div>
        )}
      </section>

      <div className="fh-orders-toolbar" aria-label={translate('orders:orders.orders')}>
        <form className="fh-orders-search" onSubmit={event => { event.preventDefault(); setPage(1); setSearch(searchInput.trim()) }}>
          <Icon name="search" size="sm" className="fh-orders-search-icon" />
          <input
            className="fh-orders-search-input"
            type="search"
            value={searchInput}
            onChange={event => setSearchInput(event.target.value)}
            placeholder={translate('orders:orders.searchOrders')}
            aria-label={translate('orders:orders.searchOrders')}
          />
          {searchInput && <button type="button" className="fh-orders-search-clear" aria-label={translate('orders:orders.clearSearch')} onClick={() => { setSearchInput(''); setSearch(''); setPage(1) }}><Icon name="close" size="sm" /></button>}
        </form>
        <label className="fh-chip-select">
          <span className="sr-only">{translate('orders:orders.allOrderStates')}</span>
          <select value={orderStatus} onChange={event => { setOrderStatus(event.target.value); setPage(1) }}>
            <option value="">{translate('orders:orders.allOrderStates')}</option>
            {ORDER_STATE_OPTIONS.map(value => <option key={value} value={value}>{formatStatus(value)}</option>)}
          </select>
          <Icon name="chevronDown" size="sm" className="fh-chip-caret" />
        </label>
        <label className="fh-chip-select">
          <span className="sr-only">{translate('common:selector.allChannels')}</span>
          <select value={channelId} onChange={event => { setChannelId(event.target.value); setPage(1) }}>
            <option value="">{translate('common:selector.allChannels')}</option>
            {syncStatuses.map(item => <option key={item.channelId} value={item.channelId}>{formatChannelDisplayName(item.channelId, { displayName: item.displayName })}</option>)}
          </select>
          <Icon name="chevronDown" size="sm" className="fh-chip-caret" />
        </label>
        <div className="ms-auto flex items-center gap-2">
          <div className="fh-menu-anchor" data-orders-saved-views>
            <button type="button" className="fh-chip" aria-expanded={savedViewsOpen} aria-haspopup="dialog" onClick={() => setSavedViewsOpen(open => !open)}>{translate('orders:orders.savedViews')}</button>
            {savedViewsOpen && <div className="fh-dropdown fh-orders-menu-panel"><p className="fh-text-caption px-2.5 py-2">{translate('orders:orders.noSavedViewsYet')}</p></div>}
          </div>
          <div className="fh-menu-anchor" data-orders-filters>
            <button type="button" className={`fh-chip ${filterCount ? 'fh-chip-active' : ''}`} aria-expanded={filtersOpen} aria-haspopup="dialog" onClick={() => setFiltersOpen(open => !open)}>
              <Icon name="filter" size="sm" /> {translate('orders:orders.filters')}{filterCount ? ` (${filterCount})` : ''}
            </button>
            {filtersOpen && <div className="fh-dropdown fh-orders-filters-panel">
              <label className="fh-field">
                <span className="fh-label">{translate('orders:orders.dateFrom')}</span>
                <input className="fh-select" type="date" value={dateFrom} onChange={event => { setDateFrom(event.target.value); setPage(1) }} />
              </label>
              <label className="fh-field">
                <span className="fh-label">{translate('orders:orders.dateTo')}</span>
                <input className="fh-select" type="date" value={dateTo} onChange={event => { setDateTo(event.target.value); setPage(1) }} />
              </label>
              <label className="fh-field">
                <span className="fh-label">{translate('common:pagination.rowsPerPage')}</span>
                <select className="fh-select" value={pageSize} onChange={event => { setPageSize(Number(event.target.value)); setPage(1) }}>{[25, 50, 100].map(value => <option key={value}>{value}</option>)}</select>
              </label>
            </div>}
          </div>
        </div>
      </div>

      {error && <div className="fh-alert fh-alert-danger mb-4" role="alert"><span>{error}</span><button className="fh-button-secondary fh-button-sm ms-auto" type="button" onClick={() => void load()}>{translate('common:action.retry')}</button></div>}

      <div className="fh-card" data-orders-table>
        <div className="fh-panel-header">
          <span className="fh-section-title">{loading ? translate('orders:orders.loading') : translate('orders:orders.orders2', { value1: total })}</span>
          <div className="ms-auto flex items-center gap-2">
            <div className="fh-menu-anchor" data-orders-columns>
              <button type="button" className="fh-button-secondary fh-button-sm" aria-expanded={columnsOpen} aria-haspopup="menu" onClick={() => setColumnsOpen(open => !open)}>{translate('orders:orders.columns')}</button>
              {columnsOpen && <div className="fh-dropdown fh-orders-menu-panel" role="menu">
                {TOGGLE_COLUMNS.map(key => <label className="fh-dropdown-item fh-inline-check" key={key}>
                  <input type="checkbox" checked={!hiddenColumns.has(key)} onChange={() => toggleColumn(key)} />
                  {translate(`orders:orders.${key}`)}
                </label>)}
              </div>}
            </div>
            <div className="fh-menu-anchor" data-orders-sort>
              <button type="button" className="fh-button-secondary fh-button-sm" aria-expanded={sortOpen} aria-haspopup="menu" onClick={() => setSortOpen(open => !open)}>{translate('orders:orders.sort')}</button>
              {sortOpen && <div className="fh-dropdown fh-orders-menu-panel" role="menu">
                {(['order', 'channel', 'customer', 'status', 'total', 'created'] as SortField[]).map(field => <button type="button" role="menuitem" key={field} className="fh-dropdown-item" onClick={() => toggleSort(field)}>
                  <span className="flex-1 text-left">{field === 'order' ? translate('orders:orders.order') : translate(`orders:orders.${field}`)}</span>
                  {sort?.field === field && <Icon name="next" size="sm" className={sort.direction === 'asc' ? '-rotate-90' : 'rotate-90'} />}
                </button>)}
              </div>}
            </div>
          </div>
        </div>
        <div className="fh-panel-body !p-0">
          {loading ? <div className="space-y-3 p-4"><SkeletonCard /><SkeletonCard /></div> : visibleItems.length === 0 ? <div className="p-6"><Empty title={emptyState.title} description={emptyState.description} action={selectedSyncStatus?.connectorType === 'woocommerce' && selectedSyncStatus.state !== 'disabled' ? { label: translate('orders:orders.syncOrders'), onClick: () => void synchronize() } : undefined} /></div> : (
            <div className="overflow-x-auto"><table className="fh-table min-w-[1020px]">
              <thead><tr>
                <th className="sticky left-0 z-10 bg-bg-card">{translate('orders:orders.order')}</th>
                {!hiddenColumns.has('channel') && <th>{translate('orders:orders.channel')}</th>}
                {!hiddenColumns.has('customer') && <th>{translate('orders:orders.customer')}</th>}
                {!hiddenColumns.has('status') && <th>{translate('orders:orders.status')}</th>}
                {!hiddenColumns.has('payment') && <th>{translate('orders:orders.payment')}</th>}
                {!hiddenColumns.has('fulfillment') && <th>{translate('orders:orders.fulfillment')}</th>}
                {!hiddenColumns.has('total') && <th>{translate('orders:orders.total')}</th>}
                {!hiddenColumns.has('created') && <th>{translate('orders:orders.created')}</th>}
                {!hiddenColumns.has('sync') && <th>{translate('orders:orders.sync')}</th>}
                <th className="fh-products-actions-cell">{translate('orders:orders.actions')}</th>
              </tr></thead>
              <tbody>{visibleItems.map(order => <tr key={order.internalId} data-orders-row data-order-id={order.internalId}>
                <td className="sticky left-0 z-10 bg-bg-card"><button className="font-medium text-accent hover:underline" onClick={() => void openDetail(order)}>{order.orderNumber || order.providerOrderId}</button></td>
                {!hiddenColumns.has('channel') && <td>{formatChannelDisplayName(order.channelId)}</td>}
                {!hiddenColumns.has('customer') && <td>{order.customerDisplay || '—'}</td>}
                {!hiddenColumns.has('status') && <td data-status-cell><InlineStatus tone={statusTone(order.normalizedStatus)}>{formatStatus(order.normalizedStatus)}</InlineStatus></td>}
                {!hiddenColumns.has('payment') && <td>{formatStatus(order.paymentStatus)}</td>}
                {!hiddenColumns.has('fulfillment') && <td>{formatStatus(order.fulfillmentStatus)}</td>}
                {!hiddenColumns.has('total') && <td>{formatMoney(order.finalAmount, { currency: order.currency })}</td>}
                {!hiddenColumns.has('created') && <td>{formatTime(order.createdAtProvider)}</td>}
                {!hiddenColumns.has('sync') && <td data-sync-cell>
                  {syncTone(order) === 'danger' && canRetryRow(order)
                    ? <button type="button" className="fh-inline-status fh-inline-status-danger" onClick={() => void retryRowSync(order)}><span aria-hidden="true" className="fh-status-dot fh-status-dot-danger" />{translate('common:action.retry')}</button>
                    : <InlineStatus tone={syncTone(order)}>{syncTone(order) === 'success' ? translate('orders:orders.synced') : formatStatus(order.synchronizationState)}</InlineStatus>}
                </td>}
                <td className="fh-products-actions-cell">
                  <div className="fh-row-actions" data-row-actions>
                    <button type="button" className="fh-row-actions-trigger" data-row-menu-trigger aria-haspopup="menu" aria-expanded={rowMenuFor === order.internalId} onClick={() => setRowMenuFor(current => current === order.internalId ? null : order.internalId)}>
                      <Icon name="more" size="sm" />
                    </button>
                    {rowMenuFor === order.internalId && <div className="fh-dropdown fh-row-actions-menu" role="menu">
                      <button type="button" role="menuitem" className="fh-dropdown-item" data-row-menu-action="view" onClick={() => { setRowMenuFor(null); void openDetail(order) }}>{translate('orders:orders.viewDetails')}</button>
                      {canRetryRow(order) && <button type="button" role="menuitem" className="fh-dropdown-item" data-row-menu-action="retry" onClick={() => { setRowMenuFor(null); void retryRowSync(order) }}>{translate('orders:orders.retrySync')}</button>}
                    </div>}
                  </div>
                </td>
              </tr>)}</tbody>
            </table></div>
          )}
        </div>
        <div className="fh-panel-footer">
          <span className="fh-text-caption">{translate('orders:orders.rangeOfTotal', { from: rangeFrom, to: rangeTo, total })}</span>
          <nav className="fh-pager ms-auto" aria-label={translate('common:pagination.previous') + ' / ' + translate('common:pagination.next')} data-orders-pager>
            <button type="button" className="fh-pager-arrow" aria-label={translate('common:pagination.previous')} disabled={page <= 1} onClick={() => setPage(value => value - 1)}><Icon name="previous" size="sm" /></button>
            {pageNumbers(page, pages).map((entry, index) => entry === 'ellipsis'
              ? <span className="fh-page-ellipsis" key={`ellipsis-${index}`}>…</span>
              : <button type="button" key={entry} className={`fh-page-btn ${entry === page ? 'fh-page-btn-active' : ''}`} aria-current={entry === page ? 'page' : undefined} onClick={() => setPage(entry)}>{entry}</button>)}
            <button type="button" className="fh-pager-arrow" aria-label={translate('common:pagination.next')} disabled={page >= pages} onClick={() => setPage(value => value + 1)}><Icon name="next" size="sm" /></button>
          </nav>
        </div>
        {detailLoading && <div className="fh-panel-footer !justify-start"><span className="fh-text-caption">{translate('orders:orders.loadingOrderDetail')}</span></div>}
        {selected && !detailLoading && <OrderDetail order={selected} />}
      </div>

      <section className="fh-card fh-card-pad mt-4 flex flex-wrap items-center justify-between gap-3" data-orders-summary-card>
        <div>
          <h2 className="fh-section-title">{translate('orders:orders.orderSynchronization')}</h2>
          <p className="fh-text-caption">{bottomSubtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          {selectedSyncStatus?.state === 'error' && <button type="button" className="fh-button-secondary fh-button-sm" onClick={() => setShowOnlyFailed(value => !value)}>{showOnlyFailed ? translate('orders:orders.showAllOrders') : translate('orders:orders.viewFailed')}</button>}
          <button type="button" className="fh-button-primary fh-button-sm" disabled={syncing || !canSync} onClick={() => void synchronize()}>{translate('orders:orders.syncNow')}</button>
        </div>
      </section>
    </PageShell>
  )
}
