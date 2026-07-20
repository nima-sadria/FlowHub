import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import type { IconName } from '../components/Icon'
import LocalizedText from '../components/LocalizedText'
import { SkeletonCard } from '../components/loading/Skeleton'
import PageShell from '../components/PageShell'
import { useServices } from '../services/ServiceContext'
import type {
  ActivityEvent,
  ChannelHealthResponse,
  ChannelOrderListItem,
  Source,
} from '../services/types'
import { formatMoney } from '../utils/price'

// Figma: Screen/Dashboard (159:12911) — seller-first overview built from
// live data only: products, orders, sources, channel health, activity.

const CARD = 'rounded-lg border border-border bg-bg-card'

function relTime(d: Date | null): string {
  if (!d) return '-'
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} h`
  return `${Math.floor(h / 24)} d`
}

function formatAction(action: string): string {
  return action.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function isToday(iso: string | null): boolean {
  if (!iso) return false
  const d = new Date(iso)
  const now = new Date()
  return d.getFullYear() === now.getFullYear()
    && d.getMonth() === now.getMonth()
    && d.getDate() === now.getDate()
}

const EXCLUDED_ORDER_STATUSES = new Set(['cancelled', 'canceled', 'refunded', 'failed'])

function KpiCard({ label, value, trend, trendTone = 'neutral', icon }: {
  label: string
  value: string
  trend?: string
  trendTone?: 'up' | 'neutral' | 'warning'
  icon: IconName
}) {
  const trendCls =
    trendTone === 'up' ? 'text-wp-green' :
    trendTone === 'warning' ? 'text-wp-yellow' :
    'text-wp-muted'
  return (
    <div className={[CARD, 'flex h-[132px] flex-col gap-3 p-4'].join(' ')}>
      <div className="flex items-center gap-2">
        <p className="text-[13px] font-medium leading-[18px] text-[color:var(--fh-text-secondary)]">{label}</p>
        <span className="ms-auto inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-[color:var(--fh-info-surface)] text-accent">
          <Icon name={icon} size="sm" />
        </span>
      </div>
      <div className="flex items-end gap-2 overflow-hidden">
        <span className="truncate text-[28px] font-semibold leading-9 text-text-base">{value}</span>
        {trend && (
          <span className={['mb-1.5 flex-shrink-0 text-xs font-medium leading-[18px]', trendCls].join(' ')}>
            {trend}
          </span>
        )}
      </div>
    </div>
  )
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className={[CARD, 'flex h-[300px] flex-col gap-4 p-[18px]'].join(' ')}>
      <div className="flex items-center">
        <p className="text-[15px] font-semibold leading-5 text-text-base">{title}</p>
        <span className="ms-auto text-xs text-[color:var(--fh-text-secondary)]">Last 30 days</span>
      </div>
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center">
        {children}
      </div>
    </div>
  )
}

function RevenueLineChart({ points }: { points: Array<{ day: string; total: number }> }) {
  const width = 440
  const height = 150
  const max = Math.max(...points.map(p => p.total), 1)
  const step = points.length > 1 ? width / (points.length - 1) : width
  const path = points
    .map((p, i) => {
      const x = points.length > 1 ? i * step : width / 2
      const y = height - 10 - (p.total / max) * (height - 30)
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-[150px] w-full max-w-[440px]"
      role="img"
      aria-label="Revenue trend by day"
    >
      <line x1="0" y1="12" x2={width} y2="12" stroke="var(--fh-ui-border)" strokeWidth="3" />
      <path d={path} fill="none" stroke="var(--color-accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function OrdersBarChart({ bars }: { bars: Array<{ channel: string; count: number }> }) {
  const max = Math.max(...bars.map(b => b.count), 1)
  return (
    <div className="flex h-[150px] w-full max-w-[420px] items-end justify-center gap-6" role="img" aria-label="Orders by channel">
      {bars.map(bar => (
        <div
          key={bar.channel}
          title={`${bar.channel}: ${bar.count}`}
          className="w-7 rounded bg-accent"
          style={{ height: `${Math.max((bar.count / max) * 150, 6)}px` }}
        />
      ))}
    </div>
  )
}

export default function Dashboard() {
  const { sources, products, activity, health: healthService, orders } = useServices()
  const navigate = useNavigate()

  const [channelHealth, setChannelHealth] = useState<ChannelHealthResponse | null>(null)
  const [sourceList, setSourceList] = useState<Source[]>([])
  const [totalProducts, setTotalProducts] = useState<number | null>(null)
  const [recentEvents, setRecentEvents] = useState<ActivityEvent[]>([])
  const [orderWindow, setOrderWindow] = useState<ChannelOrderListItem[] | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([
      healthService.getChannelHealth(),
      sources.getSources(),
      products.getProducts({ search: '', status: 'all', page: 1, pageSize: 1 }),
      activity.getEvents({ page: 1, pageSize: 4 }),
      Promise.resolve().then(() => {
        if (!orders?.getOrders) throw new Error('orders service unavailable')
        return orders.getOrders({ page: 1, pageSize: 50 })
      }),
    ]).then(([healthR, sourcesR, productsR, eventsR, ordersR]) => {
      if (cancelled) return
      if (healthR.status === 'fulfilled') setChannelHealth(healthR.value)
      if (sourcesR.status === 'fulfilled') setSourceList(sourcesR.value)
      if (productsR.status === 'fulfilled') setTotalProducts(productsR.value.total)
      if (eventsR.status === 'fulfilled') setRecentEvents(eventsR.value.items)
      setOrderWindow(ordersR.status === 'fulfilled' ? ordersR.value.items : [])
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [healthService, sources, products, activity, orders])

  const activeSources = sourceList.filter(s => s.status === 'active')
  const lastSync = activeSources.reduce<Date | null>((best, s) => {
    if (!s.lastSynced) return best
    return !best || s.lastSynced > best ? s.lastSynced : best
  }, null)

  const counts = channelHealth?.summary.counts
  const operationalChannels = counts?.Operational ?? 0
  const totalChannels = channelHealth?.items.length ?? 0
  const warningCount = counts?.Warning ?? 0
  const blockingCount = (counts?.Error ?? 0) + (counts?.['Unable to check'] ?? 0)

  const countedOrders = useMemo(
    () => (orderWindow ?? []).filter(o => !EXCLUDED_ORDER_STATUSES.has(o.normalizedStatus.toLowerCase())),
    [orderWindow],
  )
  const ordersToday = countedOrders.filter(o => isToday(o.createdAtProvider))
  const revenueCurrency = ordersToday.find(o => o.currency)?.currency ?? countedOrders.find(o => o.currency)?.currency ?? ''
  const revenueToday = ordersToday.reduce((sum, o) => sum + (o.finalAmount ?? 0), 0)

  const revenueByDay = useMemo(() => {
    const days = new Map<string, number>()
    for (const order of countedOrders) {
      if (!order.createdAtProvider || order.finalAmount === null) continue
      const day = order.createdAtProvider.slice(0, 10)
      days.set(day, (days.get(day) ?? 0) + order.finalAmount)
    }
    return Array.from(days.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-30)
      .map(([day, total]) => ({ day, total }))
  }, [countedOrders])

  const ordersByChannel = useMemo(() => {
    const channels = new Map<string, number>()
    for (const order of countedOrders) {
      channels.set(order.channelId, (channels.get(order.channelId) ?? 0) + 1)
    }
    return Array.from(channels.entries())
      .sort(([, a], [, b]) => b - a)
      .slice(0, 8)
      .map(([channel, count]) => ({ channel, count }))
  }, [countedOrders])

  const today = new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date())

  const healthBadge =
    blockingCount > 0
      ? { variant: 'error' as const, label: `${blockingCount} blocking` }
      : warningCount > 0
        ? { variant: 'warning' as const, label: `${warningCount} warning${warningCount > 1 ? 's' : ''}` }
        : { variant: 'success' as const, label: 'Operational' }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">Dashboard</h1>
          <p className="fh-page-subtitle">{today} · Live commerce overview</p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/workspace')}
          className="fh-button-primary fh-button-sm"
        >
          Open workspace
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label="Products Synced"
            value={totalProducts !== null ? totalProducts.toLocaleString() : '-'}
            icon="products"
          />
          <KpiCard
            label="Orders Today"
            value={String(ordersToday.length)}
            trend={countedOrders.length > 0 ? `${countedOrders.length} recent` : undefined}
            icon="orders"
          />
          <KpiCard
            label="Active Sources"
            value={String(activeSources.length)}
            trend={sourceList.length > activeSources.length ? `${sourceList.length} configured` : undefined}
            icon="sources"
          />
          <KpiCard
            label="Channels"
            value={totalChannels > 0 ? `${operationalChannels}/${totalChannels}` : '-'}
            trend={
              blockingCount > 0 ? `${blockingCount} blocking` :
              warningCount > 0 ? `${warningCount} warning` :
              totalChannels > 0 ? 'Operational' : undefined
            }
            trendTone={blockingCount > 0 ? 'warning' : warningCount > 0 ? 'warning' : 'up'}
            icon="channels"
          />
        </div>
      )}

      <div className={[CARD, 'flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2'].join(' ')}>
        <span className="flex items-center gap-1.5">
          <span className="text-[11px] leading-4 text-wp-muted">Revenue today</span>
          <span className="text-[13px] font-semibold leading-[22px] text-wp-green">
            {orderWindow === null ? '-' : formatMoney(String(revenueToday), { currency: revenueCurrency, empty: '-' })}
          </span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-[11px] leading-4 text-wp-muted">Blocking</span>
          <span className={['text-[13px] font-semibold leading-[22px]', blockingCount > 0 ? 'text-wp-red' : 'text-text-base'].join(' ')}>
            {channelHealth ? blockingCount : '-'}
          </span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-[11px] leading-4 text-wp-muted">Warnings</span>
          <span className={['text-[13px] font-semibold leading-[22px]', warningCount > 0 ? 'text-wp-yellow' : 'text-text-base'].join(' ')}>
            {channelHealth ? warningCount : '-'}
          </span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-[11px] leading-4 text-wp-muted">Source freshness</span>
          <span className="text-[13px] font-semibold leading-[22px] text-wp-green">
            {lastSync ? relTime(lastSync) : '-'}
          </span>
        </span>
        <span className="ms-auto flex items-center gap-2">
          <span className="text-[11px] font-medium leading-4 text-[color:var(--fh-text-secondary)]">Connections</span>
          <Badge dot variant="info">{`${activeSources.length} source${activeSources.length === 1 ? '' : 's'}`}</Badge>
          <Badge dot variant={healthBadge.variant}>{`${totalChannels} channel${totalChannels === 1 ? '' : 's'}`}</Badge>
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <ChartCard title="Revenue trend">
          {orderWindow === null ? (
            <SkeletonCard />
          ) : revenueByDay.length > 1 ? (
            <RevenueLineChart points={revenueByDay} />
          ) : (
            <Empty title="Not enough order data" description="Revenue appears here once orders synchronize." />
          )}
        </ChartCard>
        <ChartCard title="Orders by channel">
          {orderWindow === null ? (
            <SkeletonCard />
          ) : ordersByChannel.length > 0 ? (
            <OrdersBarChart bars={ordersByChannel} />
          ) : (
            <Empty title="No orders yet" description="Orders appear here once channels synchronize." />
          )}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className={[CARD, 'flex flex-col gap-2 p-3.5'].join(' ')}>
          <div className="flex items-center">
            <p className="text-sm font-semibold leading-[22px] text-text-base">Recent activity</p>
            <button
              type="button"
              onClick={() => navigate('/activity')}
              className="ms-auto text-xs font-medium leading-4 text-accent hover:text-accent-hover"
            >
              View all
            </button>
          </div>
          {loading ? (
            <SkeletonCard />
          ) : recentEvents.length === 0 ? (
            <Empty title="No events yet" />
          ) : (
            recentEvents.map(event => (
              <div key={event.id} className="flex items-center gap-3 rounded-md px-3 py-2.5">
                <span className="inline-flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-[7px] bg-bg-subtle text-[color:var(--fh-text-secondary)]">
                  <Icon name={/order/i.test(event.action) || /order/i.test(event.kind) ? 'orders' : 'products'} size="md" />
                </span>
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="truncate text-[13px] font-medium leading-[18px] text-text-base">
                    {formatAction(event.action)}
                  </span>
                  <span className="truncate text-xs leading-4 text-[color:var(--fh-text-secondary)]">
                    <LocalizedText text={event.detail ?? event.actor} />
                  </span>
                </span>
                <span className="flex-shrink-0 text-xs leading-4 text-wp-muted">{relTime(event.timestamp)}</span>
              </div>
            ))
          )}
        </div>

        <div className={[CARD, 'flex flex-col gap-2 p-3.5'].join(' ')}>
          <div className="flex items-center">
            <p className="text-sm font-semibold leading-[22px] text-text-base">Channel health</p>
            <span className="ms-auto">
              <Badge dot variant={healthBadge.variant}>{healthBadge.label}</Badge>
            </span>
          </div>
          {!channelHealth ? (
            loading ? <SkeletonCard /> : <Empty title="Channel health unavailable" />
          ) : channelHealth.items.length === 0 ? (
            <Empty title="No channels monitored" />
          ) : (
            channelHealth.items.slice(0, 4).map(channel => (
              <button
                key={channel.channelId}
                type="button"
                onClick={() => navigate('/diagnostics')}
                className="flex items-center gap-2.5 rounded-md px-3 py-2.5 text-start hover:bg-bg-subtle"
              >
                <span
                  className={[
                    'inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md',
                    channel.status === 'Operational'
                      ? 'bg-[color:var(--fh-success-surface)] text-wp-green'
                      : channel.status === 'Error'
                        ? 'bg-[color:var(--fh-danger-surface)] text-wp-red'
                        : 'bg-[color:var(--fh-warning-surface)] text-wp-yellow',
                  ].join(' ')}
                >
                  <Icon name="channels" size="sm" />
                </span>
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="truncate text-[13px] font-medium capitalize leading-[18px] text-text-base">
                    {channel.channelType}
                  </span>
                  <span className="truncate text-xs leading-4 text-[color:var(--fh-text-secondary)]">
                    {channel.summary}
                  </span>
                </span>
                <Badge
                  className="flex-shrink-0 capitalize"
                  variant={channel.status === 'Operational' ? 'success' : channel.status === 'Error' ? 'error' : 'warning'}
                >
                  {channel.status}
                </Badge>
                <Icon name="next" size="sm" mirrorRtl className="flex-shrink-0 text-wp-muted" />
              </button>
            ))
          )}
        </div>
      </div>
    </PageShell>
  )
}
