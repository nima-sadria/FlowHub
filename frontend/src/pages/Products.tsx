import { useCallback, useEffect, useState } from 'react'
import { useServices } from '../services/ServiceContext'
import type { Product } from '../services/types'
import type { Category } from '../services/products/ProductService'
import Empty from '../components/Empty'
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

function ProductRow({ product }: { product: Product }) {
  return (
    <tr className="border-b border-border hover:bg-bg-base/60 transition-colors">
      {/* Image + Name */}
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
              <svg viewBox="0 0 24 24" className="w-4 h-4 text-border" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
          )}
          <div className="min-w-0">
            <div className="text-[13px] font-medium text-text-base truncate">{product.name}</div>
            <div className="text-[11px] font-mono text-wp-muted mt-0.5">{product.sku || '-'}</div>
          </div>
        </div>
      </td>
      {/* Type */}
      <td className="px-4 py-3">
        <span className="text-[11px] font-medium px-2 py-0.5 rounded-full capitalize bg-bg-base border border-border text-wp-muted">
          {product.productType ?? 'simple'}
        </span>
      </td>
      {/* Price */}
      <td className="px-4 py-3 text-[13px] font-medium text-text-base font-mono">
        {fmtPrice(product.currentPrice, product.currency)}
      </td>
      {/* Categories */}
      <td className="px-4 py-3">
        {(product.categoryNames ?? []).slice(0, 2).map(c => (
          <span key={c} className="me-1 text-[11px] px-1.5 py-0.5 bg-bg-base border border-border rounded text-wp-muted">
            {c}
          </span>
        ))}
        {(product.categoryNames ?? []).length > 2 && (
          <span className="text-[11px] text-wp-muted">+{product.categoryNames.length - 2}</span>
        )}
      </td>
    </tr>
  )
}

function SkeletonRow() {
  return (
    <tr className="border-b border-border">
      {[240, 70, 80, 120].map((w, i) => (
        <td key={i} className="px-4 py-3">
          <div className={`h-3 bg-border/40 animate-pulse rounded`} style={{ width: w }} />
        </td>
      ))}
    </tr>
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

  // Load categories once
  useEffect(() => {
    if (productService.getCategories) {
      productService.getCategories().then(setCategories).catch(() => {})
    }
  }, [productService])

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => { setDebouncedSearch(search); setPage(1) }, 300)
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

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const end = Math.min(page * PAGE_SIZE, total)

  // Not configured
  if (!loading && configured === false) {
    return (
      <div className="fh-page max-w-2xl">
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
      </div>
    )
  }

  return (
    <div className="fh-page">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="fh-page-title">Products</h1>
          <p className="fh-page-subtitle">
            {loading ? 'Loading...' : `${total} product${total !== 1 ? 's' : ''}`}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="fh-card fh-card-pad flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[180px]">
          <svg viewBox="0 0 24 24" className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-wp-muted pointer-events-none" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            {...inputHint('Search name or SKU...')}
            className="fh-input pl-8 py-1.5"
          />
        </div>

        {/* Channel filter */}
        <select
          value={channelId}
          onChange={e => setChannelId(e.target.value)}
          className="fh-input w-auto py-1.5"
        >
          {CHANNEL_OPTIONS.map(channel => (
            <option key={channel.id || 'all'} value={channel.id}>{channel.label}</option>
          ))}
        </select>

        {/* Category filter */}
        {categories.length > 0 && (
          <select
            value={categoryId ?? ''}
            onChange={e => setCategoryId(e.target.value ? Number(e.target.value) : null)}
            className="fh-input w-auto py-1.5"
          >
            <option value="">All Categories</option>
            {categories.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        )}

        {/* Type filter */}
        <div className="flex items-center gap-1 bg-bg-base rounded-lg p-1 border border-border">
          {(['all', 'simple', 'variable'] as const).map(t => (
            <button
              key={t}
              onClick={() => setProductType(t)}
              className={[
                'px-2.5 py-1 text-[12px] font-medium rounded transition-colors capitalize',
                productType === t
                  ? 'bg-bg-card text-accent shadow-sm'
                  : 'text-wp-muted hover:text-text-base',
              ].join(' ')}
            >
              {t === 'all' ? 'All Types' : t}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="fh-card overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <span className="text-[13px] font-semibold text-text-base">
            {loading ? 'Loading...' : total === 0 ? 'No products found' : `Showing ${start}-${end} of ${total}`}
          </span>
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                className="w-7 h-7 flex items-center justify-center rounded-lg border border-border bg-bg-card text-wp-muted shadow-sm hover:text-accent hover:border-accent disabled:opacity-40 transition-colors">
                <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="m15 18-6-6 6-6" /></svg>
              </button>
              <span className="text-[12px] text-wp-muted px-1">{page} / {totalPages}</span>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                className="w-7 h-7 flex items-center justify-center rounded-lg border border-border bg-bg-card text-wp-muted shadow-sm hover:text-accent hover:border-accent disabled:opacity-40 transition-colors">
                <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="m9 18 6-6-6-6" /></svg>
              </button>
            </div>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-[13px]">
            <thead>
              <tr className="border-b border-border bg-bg-base">
                {['Product', 'Type', 'Price', 'Categories'].map(h => (
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
                      <td colSpan={4}>
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
            <span className="text-[12px] text-wp-muted">{start}-{end} of {total}</span>
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
