import { useCallback, useEffect, useState } from 'react'
import { useServices } from '../services/ServiceContext'
import type { Product, ProductSyncStatus } from '../services/types'
import Empty from '../components/Empty'

type StatusFilter = ProductSyncStatus | 'all'

const STATUS_TABS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'synced', label: 'Synced' },
  { key: 'pending', label: 'Pending' },
  { key: 'stale', label: 'Stale' },
  { key: 'error', label: 'Error' },
]

const STATUS_BADGE: Record<ProductSyncStatus, { cls: string; label: string }> = {
  synced:  { cls: 'bg-wp-green/10 text-wp-green',   label: 'Synced' },
  pending: { cls: 'bg-wp-yellow/10 text-wp-yellow', label: 'Pending' },
  stale:   { cls: 'bg-wp-orange/10 text-wp-orange', label: 'Stale' },
  error:   { cls: 'bg-wp-red/10 text-wp-red',       label: 'Error' },
}

const PAGE_SIZE = 10

function fmtPrice(p: number, currency: string): string {
  return `${currency} ${p.toFixed(2)}`
}

function relTime(d: Date | null): string {
  if (!d) return '—'
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function ProductRow({ product }: { product: Product }) {
  const badge = STATUS_BADGE[product.status]
  return (
    <tr className="border-b border-border hover:bg-bg-base/60 transition-colors">
      <td className="px-4 py-3 min-w-0 max-w-[220px]">
        <div className="text-[13px] font-medium text-text-base truncate">{product.name}</div>
        <div className="text-[11px] font-mono text-wp-muted mt-0.5">{product.sku}</div>
      </td>
      <td className="px-4 py-3">
        <span className={['text-[11px] font-semibold px-2 py-0.5 rounded-full', badge.cls].join(' ')}>
          {badge.label}
        </span>
      </td>
      <td className="px-4 py-3 text-[13px] font-medium text-text-base">
        {fmtPrice(product.currentPrice, product.currency)}
      </td>
      <td className="px-4 py-3 text-[13px] text-wp-muted">
        {product.sourcePrice !== null ? fmtPrice(product.sourcePrice, product.currency) : '—'}
      </td>
      <td className="px-4 py-3">
        {product.categoryNames.map(c => (
          <span key={c} className="me-1 text-[11px] px-1.5 py-0.5 bg-bg-base border border-border rounded text-wp-muted">
            {c}
          </span>
        ))}
      </td>
      <td className="px-4 py-3 text-[12px] text-wp-muted whitespace-nowrap">
        {relTime(product.lastSynced)}
      </td>
    </tr>
  )
}

function SkeletonRow() {
  return (
    <tr className="border-b border-border">
      {[180, 80, 80, 80, 100, 80].map((w, i) => (
        <td key={i} className="px-4 py-3">
          <div className={`h-3 bg-border/40 animate-pulse rounded w-[${w}px]`} />
        </td>
      ))}
    </tr>
  )
}

export default function Products() {
  const { products: productService } = useServices()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [page, setPage] = useState(1)
  const [items, setItems] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const t = setTimeout(() => { setDebouncedSearch(search); setPage(1) }, 300)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => { setPage(1) }, [statusFilter])

  const fetchProducts = useCallback(() => {
    setLoading(true)
    productService.getProducts({ search: debouncedSearch, status: statusFilter, page, pageSize: PAGE_SIZE })
      .then(r => { setItems(r.items); setTotal(r.total) })
      .finally(() => setLoading(false))
  }, [productService, debouncedSearch, statusFilter, page])

  useEffect(() => { fetchProducts() }, [fetchProducts])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const end = Math.min(page * PAGE_SIZE, total)

  return (
    <div className="p-4 sm:p-7 flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold text-text-base">Products</h1>
          <p className="text-[13px] text-wp-muted mt-0.5">Mock product catalogue — {total} items</p>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px] flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[180px]">
          <svg viewBox="0 0 24 24" className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-wp-muted pointer-events-none" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search name or SKU…"
            className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-border bg-bg-base text-[13px] placeholder:text-wp-muted focus:outline-none focus:border-accent transition-colors"
          />
        </div>

        {/* Status tabs */}
        <div className="flex items-center gap-1 bg-bg-base rounded-lg p-1 border border-border">
          {STATUS_TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setStatusFilter(tab.key)}
              className={[
                'px-2.5 py-1 text-[12px] font-medium rounded transition-colors',
                statusFilter === tab.key
                  ? 'bg-bg-card text-text-base shadow-card'
                  : 'text-wp-muted hover:text-text-base',
              ].join(' ')}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-bg-card border border-border rounded-card shadow-card overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <span className="text-[13px] font-semibold text-text-base">
            {loading ? 'Loading…' : total === 0 ? 'No products found' : `Showing ${start}–${end} of ${total}`}
          </span>
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="w-7 h-7 flex items-center justify-center rounded border border-border text-wp-muted hover:text-text-base disabled:opacity-40 transition-colors"
              >
                <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="m15 18-6-6 6-6" /></svg>
              </button>
              <span className="text-[12px] text-wp-muted px-1">{page} / {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="w-7 h-7 flex items-center justify-center rounded border border-border text-wp-muted hover:text-text-base disabled:opacity-40 transition-colors"
              >
                <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="m9 18 6-6-6-6" /></svg>
              </button>
            </div>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-[13px]">
            <thead>
              <tr className="border-b border-border bg-bg-base">
                {['Product', 'Status', 'Current Price', 'Source Price', 'Categories', 'Last Synced'].map(h => (
                  <th key={h} className="px-4 py-2.5 text-start text-[11px] font-semibold text-wp-muted uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className={loading ? 'opacity-40 pointer-events-none' : ''}>
              {loading && items.length === 0
                ? Array.from({ length: PAGE_SIZE }).map((_, i) => <SkeletonRow key={i} />)
                : items.length === 0
                  ? (
                    <tr>
                      <td colSpan={6}>
                        <Empty title="No products match" description="Try adjusting the search or filter." />
                      </td>
                    </tr>
                  )
                  : items.map(p => <ProductRow key={p.id} product={p} />)
              }
            </tbody>
          </table>
        </div>

        {!loading && totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border">
            <span className="text-[12px] text-wp-muted">{start}–{end} of {total}</span>
            <div className="flex items-center gap-1">
              <button onClick={() => setPage(1)} disabled={page === 1} className="w-7 h-7 flex items-center justify-center rounded border border-border text-wp-muted hover:text-text-base disabled:opacity-40 transition-colors text-[12px]">«</button>
              <button onClick={() => setPage(p => p - 1)} disabled={page === 1} className="w-7 h-7 flex items-center justify-center rounded border border-border text-wp-muted hover:text-text-base disabled:opacity-40 transition-colors">
                <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="m15 18-6-6 6-6" /></svg>
              </button>
              <span className="text-[12px] text-wp-muted px-1.5">{page} / {totalPages}</span>
              <button onClick={() => setPage(p => p + 1)} disabled={page === totalPages} className="w-7 h-7 flex items-center justify-center rounded border border-border text-wp-muted hover:text-text-base disabled:opacity-40 transition-colors">
                <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="m9 18 6-6-6-6" /></svg>
              </button>
              <button onClick={() => setPage(totalPages)} disabled={page === totalPages} className="w-7 h-7 flex items-center justify-center rounded border border-border text-wp-muted hover:text-text-base disabled:opacity-40 transition-colors text-[12px]">»</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
