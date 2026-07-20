import { useEffect, useMemo, useState } from 'react'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import IconButton from '../components/IconButton'
import { SkeletonCard } from '../components/loading/Skeleton'
import PageShell from '../components/PageShell'
import { useServices } from '../services/ServiceContext'
import type { ChannelOrderDetail, ChannelOrderListItem } from '../services/types'
import { inputHint } from '../utils/inputHint'
import { formatMoney } from '../utils/price'

const PAGE_SIZE = 20

const CHANNEL_OPTIONS = [
  { id: '', label: 'All channels' },
  { id: 'woocommerce:primary', label: 'WooCommerce' },
  { id: 'snappshop:main', label: 'Snapp Shop' },
  { id: 'tapsishop:main', label: 'Tapsi Shop' },
]

function formatTime(value: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function relTime(value: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const s = Math.floor((Date.now() - date.getTime()) / 1000)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} minute${m === 1 ? '' : 's'} ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} hour${h === 1 ? '' : 's'} ago`
  return `${Math.floor(h / 24)} days ago`
}

function isToday(value: string | null): boolean {
  if (!value) return false
  const d = new Date(value)
  const now = new Date()
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
}

function statusVariant(status: string): 'info' | 'success' | 'warning' | 'danger' {
  const normalized = status.toLowerCase()
  if (normalized.includes('cancel') || normalized.includes('fail')) return 'danger'
  if (normalized.includes('fulfill') || normalized.includes('deliver') || normalized.includes('complete')) return 'success'
  if (normalized.includes('process') || normalized.includes('pending') || normalized.includes('stale')) return 'warning'
  return 'info'
}

function syncBadge(order: ChannelOrderListItem): { variant: 'success' | 'error' | 'neutral'; label: string } {
  if (order.errorState) return { variant: 'error', label: 'Retry' }
  const state = order.synchronizationState.toLowerCase()
  if (state.includes('sync') || state.includes('ok') || state.includes('complete')) {
    return { variant: 'success', label: 'Synced' }
  }
  return { variant: 'neutral', label: order.synchronizationState }
}

function OrderDetail({ order }: { order: ChannelOrderDetail }) {
  return (
    <div className="border-t border-border bg-bg-base/50 px-4 py-4">
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <section>
          <h3 className="fh-section-title mb-3">Items</h3>
          <div className="overflow-x-auto">
            <table className="fh-table min-w-[720px]">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Name</th>
                  <th>Provider item</th>
                  <th>Qty</th>
                  <th>Canceled</th>
                  <th>Deliverable</th>
                  <th>Final price</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {order.items.map(item => (
                  <tr key={item.providerItemId}>
                    <td>{item.sku || '-'}</td>
                    <td>{item.name || '-'}</td>
                    <td>{item.providerItemId}</td>
                    <td>{item.quantity}</td>
                    <td>{item.canceledQuantity}</td>
                    <td>{item.deliverableQuantity ?? '-'}</td>
                    <td>{formatMoney(item.finalPrice, { currency: order.currency })}</td>
                    <td>{item.itemStatus || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h3 className="fh-section-title mb-3">Shipments</h3>
          {order.shipments.length === 0 ? (
            <p className="fh-text-caption">No shipment data</p>
          ) : (
            <div className="space-y-2">
              {order.shipments.map(item => (
                <div className="rounded-md border border-border bg-bg-card p-3" key={item.shipmentNumber}>
                  <div className="fh-text-body font-medium">{item.shipmentNumber}</div>
                  <div className="fh-text-caption">{item.statusCode || '-'} {item.statusTitle || ''}</div>
                  <div className="fh-text-caption">{item.deliveryMethod || '-'} {item.pickupOrSendWindow || ''}</div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section>
          <h3 className="fh-section-title mb-3">Timeline</h3>
          <div className="space-y-2">
            {order.timeline.map((event, index) => (
              <div className="rounded-md border border-border bg-bg-card p-3" key={`${event.eventName}-${index}`}>
                <div className="fh-text-body font-medium">{event.eventName.replace(/_/g, ' ')}</div>
                <div className="fh-text-caption">{event.message}</div>
                <div className="fh-text-caption">{formatTime(event.createdAt)}</div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

export default function Orders() {
  const { orders } = useServices()
  const [items, setItems] = useState<ChannelOrderListItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [channelId, setChannelId] = useState('')
  const [search, setSearch] = useState('')
  const [stateFilter, setStateFilter] = useState('')
  const [selected, setSelected] = useState<ChannelOrderDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => { setPage(1) }, [channelId])

  useEffect(() => {
    let alive = true
    if (!orders) {
      setLoading(false)
      return () => { alive = false }
    }
    setLoading(true)
    orders.getOrders({ page, pageSize: PAGE_SIZE, channelId: channelId || null })
      .then(result => {
        if (!alive) return
        setItems(result.items)
        setTotal(result.total)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => { alive = false }
  }, [orders, page, channelId])

  const normalizedStates = useMemo(
    () => Array.from(new Set(items.map(order => order.normalizedStatus))).sort(),
    [items],
  )

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase()
    return items.filter(order => {
      if (stateFilter && order.normalizedStatus !== stateFilter) return false
      if (!term) return true
      return (order.orderNumber ?? '').toLowerCase().includes(term)
        || order.providerOrderId.toLowerCase().includes(term)
        || order.channelId.toLowerCase().includes(term)
    })
  }, [items, search, stateFilter])

  const lastSeen = useMemo(() => items.reduce<string | null>((best, order) => {
    const candidate = order.lastSeenAt ?? order.updatedAtProvider
    if (!candidate) return best
    return !best || candidate > best ? candidate : best
  }, null), [items])
  const ordersToday = items.filter(order => isToday(order.createdAtProvider)).length
  const failedCount = items.filter(order => order.errorState).length
  const syncedCount = items.length - failedCount

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const end = Math.min(page * PAGE_SIZE, total)

  async function openDetail(order: ChannelOrderListItem) {
    if (!orders) return
    setDetailLoading(true)
    try {
      setSelected(await orders.getOrder(order.internalId))
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">Orders</h1>
          <p className="fh-page-subtitle">Unified orders across every connected channel.</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-bg-card px-3 py-2">
        <Badge dot variant={failedCount > 0 ? 'warning' : 'success'}>
          {failedCount > 0 ? 'Attention' : 'Synced'}
        </Badge>
        <span className="text-[13px] leading-5 text-[color:var(--fh-text-secondary)]">
          {loading ? 'Loading synchronization state...' : `Last synchronized ${relTime(lastSeen)} · ${ordersToday} order${ordersToday === 1 ? '' : 's'} today`}
        </span>
        {failedCount > 0 && (
          <span className="ms-auto">
            <Badge dot variant="error">{`${failedCount} failed`}</Badge>
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Icon name="search" className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-wp-muted" />
          <input
            type="search"
            value={search}
            onChange={event => setSearch(event.target.value)}
            {...inputHint('Search orders')}
            className="fh-input !min-h-[40px] rounded-lg ps-9"
          />
        </div>
        <select
          value={stateFilter}
          onChange={event => setStateFilter(event.target.value)}
          aria-label="Filter by order state"
          className="fh-select w-auto !min-h-[40px] rounded-lg capitalize"
        >
          <option value="">All order states</option>
          {normalizedStates.map(state => (
            <option key={state} value={state}>{state}</option>
          ))}
        </select>
        <select
          value={channelId}
          onChange={event => setChannelId(event.target.value)}
          aria-label="Filter by channel"
          className="fh-select w-auto !min-h-[40px] rounded-lg"
        >
          {CHANNEL_OPTIONS.map(channel => (
            <option key={channel.id || 'all'} value={channel.id}>{channel.label}</option>
          ))}
        </select>
      </div>

      <div className="fh-table-wrapper">
        <div className="fh-panel-header !min-h-0 !py-3">
          <span className="text-[13px] font-medium text-text-base">
            {loading ? 'Loading...' : `${total} order${total === 1 ? '' : 's'}`}
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
        {loading ? (
          <div className="space-y-3 p-4">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : visible.length === 0 ? (
          <div className="p-6">
            {items.length === 0 ? (
              <Empty title="No synchronized orders" description="Marketplace orders will appear after webhook processing or polling synchronization runs." />
            ) : (
              <Empty title="No orders match" description="Try adjusting the search or filters." />
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="fh-table min-w-[960px]">
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Channel</th>
                  <th>Status</th>
                  <th>Provider status</th>
                  <th>Items</th>
                  <th>Total</th>
                  <th>Created</th>
                  <th>Sync</th>
                </tr>
              </thead>
              <tbody>
                {visible.map(order => {
                  const sync = syncBadge(order)
                  return (
                    <tr key={order.internalId}>
                      <td>
                        <button
                          className="font-medium text-accent hover:underline"
                          onClick={() => void openDetail(order)}
                        >
                          #{order.orderNumber || order.providerOrderId}
                        </button>
                      </td>
                      <td className="capitalize">{order.connectorType}<span className="fh-text-caption block normal-case">{order.channelId}</span></td>
                      <td><Badge dot variant={statusVariant(order.normalizedStatus)} className="capitalize">{order.normalizedStatus}</Badge></td>
                      <td className="capitalize">{order.providerStatus}</td>
                      <td>{order.itemCount}</td>
                      <td className="whitespace-nowrap font-medium text-text-base">{formatMoney(order.finalAmount, { currency: order.currency })}</td>
                      <td className="whitespace-nowrap">{formatTime(order.createdAtProvider)}</td>
                      <td>
                        <span title={order.errorState ?? undefined}>
                          <Badge dot variant={sync.variant} className="capitalize">
                            {sync.label}
                          </Badge>
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        {!loading && total > 0 && (
          <div className="fh-panel-footer !justify-between">
            <span className="fh-text-caption">{start}-{end} of {total}</span>
            {totalPages > 1 && (
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
            )}
          </div>
        )}
      </div>

      {!loading && items.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[color:var(--fh-info-border)] bg-[color:var(--fh-info-surface)] px-4 py-3">
          <div className="min-w-0">
            <p className="text-[13px] font-semibold leading-5 text-text-base">Order synchronization</p>
            <p className="text-xs leading-4 text-[color:var(--fh-text-secondary)]">
              {`${syncedCount} synchronized on this page${failedCount > 0 ? ` · ${failedCount} need${failedCount === 1 ? 's' : ''} retry` : ''}`}
            </p>
          </div>
        </div>
      )}

      {detailLoading && (
        <div className="fh-card fh-card-pad">
          <span className="fh-text-caption">Loading order detail...</span>
        </div>
      )}
      {selected && !detailLoading && (
        <div className="fh-card">
          <div className="fh-panel-header">
            <span className="fh-section-title">Order #{selected.orderNumber || selected.providerOrderId}</span>
            <IconButton label="Close order detail" onClick={() => setSelected(null)} size="sm">
              <Icon name="close" />
            </IconButton>
          </div>
          <OrderDetail order={selected} />
        </div>
      )}
    </PageShell>
  )
}
