import { useEffect, useState } from 'react'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import { SkeletonCard } from '../components/loading/Skeleton'
import PageShell from '../components/PageShell'
import { useServices } from '../services/ServiceContext'
import type { ChannelOrderDetail, ChannelOrderListItem } from '../services/types'
import { formatMoney } from '../utils/price'

function formatTime(value: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function statusVariant(status: string): 'info' | 'success' | 'warning' | 'danger' {
  const normalized = status.toLowerCase()
  if (normalized.includes('cancel')) return 'danger'
  if (normalized.includes('fulfill') || normalized.includes('deliver')) return 'success'
  if (normalized.includes('error') || normalized.includes('stale')) return 'warning'
  return 'info'
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
  const [selected, setSelected] = useState<ChannelOrderDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    let alive = true
    if (!orders) {
      setLoading(false)
      return () => { alive = false }
    }
    setLoading(true)
    orders.getOrders({ page: 1, pageSize: 50 })
      .then(result => {
        if (!alive) return
        setItems(result.items)
        setTotal(result.total)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => { alive = false }
  }, [orders])

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
          <p className="fh-page-subtitle">Normalized marketplace order synchronization</p>
        </div>
      </div>

      <div className="fh-card">
        <div className="fh-panel-header">
          <span className="fh-section-title">{loading ? 'Loading...' : `${total} orders`}</span>
        </div>
        <div className="fh-panel-body !p-0">
          {loading ? (
            <div className="p-4 space-y-3">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : items.length === 0 ? (
            <div className="p-6">
              <Empty title="No synchronized orders" description="Marketplace orders will appear after webhook processing or polling synchronization runs." />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="fh-table min-w-[1180px]">
                <thead>
                  <tr>
                    <th className="sticky left-0 bg-bg-card z-10">Order</th>
                    <th>Channel</th>
                    <th>Provider status</th>
                    <th>Normalized status</th>
                    <th>Created</th>
                    <th>Latest update</th>
                    <th>Items</th>
                    <th>Final amount</th>
                    <th>Sync state</th>
                    <th>Source</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map(order => (
                    <tr key={order.internalId}>
                      <td className="sticky left-0 bg-bg-card z-10">
                        <button
                          className="text-accent font-medium hover:underline"
                          onClick={() => void openDetail(order)}
                        >
                          {order.orderNumber || order.providerOrderId}
                        </button>
                      </td>
                      <td>{order.connectorType}<span className="fh-text-caption block">{order.channelId}</span></td>
                      <td>{order.providerStatus}</td>
                      <td><Badge variant={statusVariant(order.normalizedStatus)}>{order.normalizedStatus}</Badge></td>
                      <td>{formatTime(order.createdAtProvider)}</td>
                      <td>{formatTime(order.updatedAtProvider || order.lastSeenAt)}</td>
                      <td>{order.itemCount}</td>
                      <td>{formatMoney(order.finalAmount, { currency: order.currency })}</td>
                      <td>{order.synchronizationState}</td>
                      <td>{order.eventSource}</td>
                      <td>{order.errorState || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        {detailLoading && (
          <div className="fh-panel-footer !justify-start">
            <span className="fh-text-caption">Loading order detail...</span>
          </div>
        )}
        {selected && !detailLoading && <OrderDetail order={selected} />}
      </div>
    </PageShell>
  )
}
