import { useCallback, useEffect, useState } from 'react'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import IconButton from '../components/IconButton'
import LocalizedText from '../components/LocalizedText'
import PageShell from '../components/PageShell'
import { useServices } from '../services/ServiceContext'
import type { Product } from '../services/types'
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

function ProductRow({ product }: { product: Product }) {
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
              <svg viewBox="0 0 24 24" className="fh-icon-sm text-border" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
          )}
          <div className="min-w-0">
            <div className="fh-text-body font-medium truncate">
              <LocalizedText text={product.name} />
            </div>
            <div className="fh-text-caption fh-text-mono mt-0.5">{product.sku || '-'}</div>
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
    </tr>
  )
}

function SkeletonRow() {
  return (
    <tr className="border-b border-border">
      {[240, 70, 80, 120].map((w, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-3 bg-border/40 animate-pulse rounded" style={{ width: w }} />
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
          <svg viewBox="0 0 24 24" className="absolute left-2.5 top-1/2 -translate-y-1/2 fh-icon-sm text-wp-muted pointer-events-none" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
          </svg>
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

      <div className="fh-table-wrapper">
        <div className="fh-panel-header">
          <span className="fh-text-body font-semibold">
            {loading ? 'Loading...' : total === 0 ? 'No products found' : `Showing ${start}-${end} of ${total}`}
          </span>
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <IconButton label="Previous page" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} size="sm">
                <svg viewBox="0 0 24 24" className="fh-icon-sm" fill="none" stroke="currentColor" strokeWidth="2.25" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg>
              </IconButton>
              <span className="fh-text-caption px-1">{page} / {totalPages}</span>
              <IconButton label="Next page" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} size="sm">
                <svg viewBox="0 0 24 24" className="fh-icon-sm" fill="none" stroke="currentColor" strokeWidth="2.25" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
              </IconButton>
            </div>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="fh-table min-w-[560px]">
            <thead>
              <tr>
                {['Product', 'Type', 'Price', 'Categories'].map(h => (
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
                      <td colSpan={4}>
                        <Empty title="No products match" description="Try adjusting the search or filter." />
                      </td>
                    </tr>
                    )
                  : items.map(p => <ProductRow key={p.id} product={p} />)}
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
                <svg viewBox="0 0 24 24" className="fh-icon-sm" fill="none" stroke="currentColor" strokeWidth="2.25" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg>
              </IconButton>
              <span className="fh-text-caption px-1.5">{page} / {totalPages}</span>
              <IconButton label="Next page" onClick={() => setPage(p => p + 1)} disabled={page === totalPages} size="sm">
                <svg viewBox="0 0 24 24" className="fh-icon-sm" fill="none" stroke="currentColor" strokeWidth="2.25" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
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
