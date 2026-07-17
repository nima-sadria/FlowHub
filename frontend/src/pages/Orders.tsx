import { useCallback, useEffect, useMemo, useState } from 'react'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import PageShell from '../components/PageShell'
import { SkeletonCard } from '../components/loading/Skeleton'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { translate } from '../i18n'
import { formatStatus } from '../i18n/display'
import { formatDateTime } from '../i18n/format'
import { useServices } from '../services/ServiceContext'
import type { OrderSyncStatus } from '../services/orders/OrderService'
import type { ChannelOrderDetail, ChannelOrderListItem } from '../services/types'
import { formatMoney } from '../utils/price'

function formatTime(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : formatDateTime(date)
}

function statusVariant(status: string): 'info' | 'success' | 'warning' | 'danger' {
  const normalized = status.toLowerCase()
  if (normalized.includes('cancel') || normalized.includes('fail')) return 'danger'
  if (normalized.includes('fulfill') || normalized.includes('deliver') || normalized === 'paid') return 'success'
  if (normalized.includes('pending') || normalized.includes('hold')) return 'warning'
  return 'info'
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
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<ChannelOrderDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

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

  const pages = Math.max(1, Math.ceil(total / pageSize))
  const selectedSyncStatus = useMemo(
    () => syncStatuses.find(item => item.channelId === channelId)
      ?? syncStatuses.find(item => item.connectorType === 'woocommerce')
      ?? syncStatuses[0],
    [channelId, syncStatuses],
  )

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

  const emptyState = selectedSyncStatus?.state === 'disabled'
    ? { title: translate('orders:orders.syncDisabled'), description: translate('orders:orders.enableChannelToSync') }
    : selectedSyncStatus?.state === 'never_run'
      ? { title: translate('orders:orders.syncNeverRun'), description: translate('orders:orders.runReadOnlySync') }
      : selectedSyncStatus?.state === 'error'
        ? { title: translate('orders:orders.lastSyncFailed'), description: translate('orders:orders.retryReadOnlySync') }
        : { title: translate('orders:orders.noMatchingOrders'), description: translate('orders:orders.adjustFilters') }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div><h1 className="fh-page-title">{translate('orders:orders.orders')}</h1><p className="fh-page-subtitle">{translate('orders:orders.businessSubtitle')}</p></div>
        <button className="fh-button-primary" type="button" disabled={syncing || selectedSyncStatus?.state === 'disabled' || selectedSyncStatus?.connectorType !== 'woocommerce'} onClick={() => void synchronize()}>
          {syncing ? translate('orders:orders.syncing') : translate('orders:orders.syncOrders')}
        </button>
      </div>

      <section className="fh-card fh-card-pad mb-4">
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          <label className="fh-field-label">{translate('activity:activity.search')}<input className="fh-input mt-1" value={search} onChange={event => { setSearch(event.target.value); setPage(1) }} /></label>
          <label className="fh-field-label">{translate('orders:orders.channel')}<select className="fh-input mt-1" value={channelId} onChange={event => { setChannelId(event.target.value); setPage(1) }}><option value="">{translate('common:selector.allChannels')}</option>{syncStatuses.map(item => <option key={item.channelId} value={item.channelId}>{formatChannelDisplayName(item.channelId, { displayName: item.displayName })}</option>)}</select></label>
          <label className="fh-field-label">{translate('orders:orders.status')}<select className="fh-input mt-1" value={orderStatus} onChange={event => { setOrderStatus(event.target.value); setPage(1) }}><option value="">{translate('common:selector.allStatuses')}</option>{['pending', 'processing', 'fulfilled', 'cancelled', 'refunded', 'failed'].map(value => <option key={value} value={value}>{formatStatus(value)}</option>)}</select></label>
          <label className="fh-field-label">{translate('orders:orders.dateFrom')}<input className="fh-input mt-1" type="date" value={dateFrom} onChange={event => { setDateFrom(event.target.value); setPage(1) }} /></label>
          <label className="fh-field-label">{translate('orders:orders.dateTo')}<input className="fh-input mt-1" type="date" value={dateTo} onChange={event => { setDateTo(event.target.value); setPage(1) }} /></label>
          <label className="fh-field-label">{translate('common:pagination.rowsPerPage')}<select className="fh-input mt-1" value={pageSize} onChange={event => { setPageSize(Number(event.target.value)); setPage(1) }}>{[25, 50, 100].map(value => <option key={value}>{value}</option>)}</select></label>
        </div>
        {selectedSyncStatus && <p className="fh-text-caption mt-3">{translate('orders:orders.lastSuccessfulSync')} {formatTime(selectedSyncStatus.lastSuccessAt)}</p>}
      </section>

      {error && <div className="fh-alert fh-alert-danger mb-4" role="alert"><span>{error}</span><button className="fh-button-secondary fh-button-sm ms-auto" type="button" onClick={() => void load()}>{translate('common:action.retry')}</button></div>}

      <div className="fh-card">
        <div className="fh-panel-header"><span className="fh-section-title">{loading ? translate('orders:orders.loading') : translate('orders:orders.orders2', { value1: total })}</span></div>
        <div className="fh-panel-body !p-0">
          {loading ? <div className="space-y-3 p-4"><SkeletonCard /><SkeletonCard /></div> : items.length === 0 ? <div className="p-6"><Empty title={emptyState.title} description={emptyState.description} action={selectedSyncStatus?.connectorType === 'woocommerce' && selectedSyncStatus.state !== 'disabled' ? { label: translate('orders:orders.syncOrders'), onClick: () => void synchronize() } : undefined} /></div> : (
            <div className="overflow-x-auto"><table className="fh-table min-w-[1320px]"><thead><tr><th className="sticky left-0 z-10 bg-bg-card">{translate('orders:orders.marketplaceOrderId')}</th><th>{translate('orders:orders.channel')}</th><th>{translate('orders:orders.status')}</th><th>{translate('orders:orders.customer')}</th><th>{translate('orders:orders.total')}</th><th>{translate('orders:orders.currency')}</th><th>{translate('orders:orders.paymentStatus')}</th><th>{translate('orders:orders.fulfillmentStatus')}</th><th>{translate('orders:orders.created')}</th><th>{translate('orders:orders.latestUpdate')}</th></tr></thead><tbody>{items.map(order => <tr key={order.internalId}><td className="sticky left-0 z-10 bg-bg-card"><button className="font-medium text-accent hover:underline" onClick={() => void openDetail(order)}>{order.orderNumber || order.providerOrderId}</button></td><td>{formatChannelDisplayName(order.channelId)}</td><td><Badge variant={statusVariant(order.normalizedStatus)}>{formatStatus(order.normalizedStatus)}</Badge></td><td>{order.customerDisplay || '—'}</td><td>{formatMoney(order.finalAmount, { currency: order.currency })}</td><td>{order.currency || '—'}</td><td>{formatStatus(order.paymentStatus)}</td><td>{formatStatus(order.fulfillmentStatus)}</td><td>{formatTime(order.createdAtProvider)}</td><td>{formatTime(order.updatedAtProvider || order.lastSeenAt)}</td></tr>)}</tbody></table></div>
          )}
        </div>
        <div className="fh-panel-footer">
          <span className="fh-text-caption">{translate('common:pagination.pageOf', { page, total: pages })}</span>
          <div className="ms-auto flex gap-2"><button className="fh-button-secondary fh-button-sm" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>{translate('common:pagination.previous')}</button><button className="fh-button-secondary fh-button-sm" disabled={page >= pages} onClick={() => setPage(value => value + 1)}>{translate('common:pagination.next')}</button></div>
        </div>
        {detailLoading && <div className="fh-panel-footer !justify-start"><span className="fh-text-caption">{translate('orders:orders.loadingOrderDetail')}</span></div>}
        {selected && !detailLoading && <OrderDetail order={selected} />}
      </div>
    </PageShell>
  )
}
