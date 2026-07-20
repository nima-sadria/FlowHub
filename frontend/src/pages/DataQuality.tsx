import { useCallback, useEffect, useMemo, useState } from 'react'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import KpiCard from '../components/KpiCard'
import Spinner from '../components/loading/Spinner'
import PageShell from '../components/PageShell'
import { useServices } from '../services/ServiceContext'
import type { Product } from '../services/types'

type Severity = 'blocking' | 'warning'
type IssueStatus = 'open'

interface QualityIssue {
  id: string
  product: Product
  title: string
  detail: string
  severity: Severity
  status: IssueStatus
}

function buildIssues(products: Product[]): QualityIssue[] {
  return products.flatMap(product => {
    const issues: QualityIssue[] = []
    if (!product.sku.trim()) {
      issues.push({
        id: `${product.connectorId}:${product.id}:sku`,
        product,
        title: 'Missing SKU',
        detail: 'A SKU is required for reliable matching across channels.',
        severity: 'blocking',
        status: 'open',
      })
    }
    if (!product.imageUrl) {
      issues.push({
        id: `${product.connectorId}:${product.id}:image`,
        product,
        title: 'Missing product image',
        detail: 'Add a product image before publishing to sales channels.',
        severity: 'warning',
        status: 'open',
      })
    }
    if (product.status === 'error') {
      issues.push({
        id: `${product.connectorId}:${product.id}:sync-error`,
        product,
        title: 'Synchronization failed',
        detail: 'The last product synchronization ended with an error.',
        severity: 'blocking',
        status: 'open',
      })
    } else if (product.status === 'stale') {
      issues.push({
        id: `${product.connectorId}:${product.id}:stale`,
        product,
        title: 'Product data is stale',
        detail: 'Review this record before the next channel update.',
        severity: 'warning',
        status: 'open',
      })
    }
    return issues
  })
}

function relativeCheckTime(value: Date | null): string {
  if (!value) return 'Not checked'
  const seconds = Math.max(0, Math.floor((Date.now() - value.getTime()) / 1000))
  if (seconds < 60) return 'Just now'
  return `${Math.floor(seconds / 60)}m ago`
}

export default function DataQuality() {
  const { products: productService } = useServices()
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)
  const [search, setSearch] = useState('')
  const [severity, setSeverity] = useState<Severity | 'all'>('all')
  const [status, setStatus] = useState<IssueStatus | 'all'>('all')

  const runCheck = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const first = await productService.getProducts({ search: '', status: 'all', page: 1, pageSize: 200 })
      const pageCount = Math.ceil(first.total / first.pageSize)
      const remaining = []
      for (let startPage = 2; startPage <= pageCount; startPage += 4) {
        const batch = await Promise.all(
          Array.from({ length: Math.min(4, pageCount - startPage + 1) }, (_, index) => (
            productService.getProducts({ search: '', status: 'all', page: startPage + index, pageSize: 200 })
          )),
        )
        remaining.push(...batch)
      }
      setProducts([first, ...remaining].flatMap(page => page.items))
      setCheckedAt(new Date())
    } catch {
      setError('Unable to run the data quality check.')
    } finally {
      setLoading(false)
    }
  }, [productService])

  useEffect(() => { void runCheck() }, [runCheck])

  const issues = useMemo(() => buildIssues(products), [products])
  const filteredIssues = useMemo(() => {
    const query = search.trim().toLowerCase()
    return issues.filter(issue => (
      (severity === 'all' || issue.severity === severity)
      && (status === 'all' || issue.status === status)
      && (!query || `${issue.title} ${issue.detail} ${issue.product.name} ${issue.product.sku}`.toLowerCase().includes(query))
    ))
  }, [issues, search, severity, status])
  const blocking = issues.filter(issue => issue.severity === 'blocking').length
  const warnings = issues.filter(issue => issue.severity === 'warning').length

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">Data Quality</h1>
          <p className="fh-page-subtitle">Resolve issues blocking reliable commerce data.</p>
        </div>
        <button type="button" onClick={() => void runCheck()} disabled={loading} className="fh-button-primary">
          {loading ? <Spinner size="sm" /> : <Icon name="dataQuality" />}
          {loading ? 'Checking...' : 'Run check'}
        </button>
      </div>

      {error && <div className="fh-alert fh-alert-danger" role="alert"><Icon name="error" /><span>{error}</span></div>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Blocking Issues" value={loading ? '—' : String(blocking)} trend={blocking > 0 ? 'Needs attention' : 'Clear'} trendTone={blocking > 0 ? 'danger' : 'up'} icon="error" />
        <KpiCard label="Warnings" value={loading ? '—' : String(warnings)} trend={warnings > 0 ? 'Review advised' : 'Clear'} trendTone={warnings > 0 ? 'warning' : 'up'} icon="warning" />
        <KpiCard label="Products Checked" value={loading ? '—' : products.length.toLocaleString()} trend="Canonical catalog" icon="products" />
        <KpiCard label="Last Check" value={loading ? 'Running' : relativeCheckTime(checkedAt)} trend={checkedAt ? checkedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : undefined} icon="calendar" />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Icon name="search" className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-wp-muted" />
          <input
            type="search"
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder="Search issues..."
            aria-label="Search issues"
            className="fh-input !min-h-[40px] rounded-lg ps-9"
          />
        </div>
        <select value={severity} onChange={event => setSeverity(event.target.value as Severity | 'all')} aria-label="Filter by severity" className="fh-select w-auto !min-h-[40px] rounded-lg">
          <option value="all">All severities</option>
          <option value="blocking">Blocking</option>
          <option value="warning">Warning</option>
        </select>
        <select value={status} onChange={event => setStatus(event.target.value as IssueStatus | 'all')} aria-label="Filter by status" className="fh-select w-auto !min-h-[40px] rounded-lg">
          <option value="all">All statuses</option>
          <option value="open">Open</option>
        </select>
        <span className="fh-text-caption px-2">{filteredIssues.length} issue{filteredIssues.length === 1 ? '' : 's'}</span>
      </div>

      <div className="fh-table-wrapper">
        <div className="overflow-x-auto">
          <table className="fh-table min-w-[820px]">
            <thead>
              <tr>
                <th>Issue</th>
                <th>Record</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Updated</th>
                <th className="text-end">Action</th>
              </tr>
            </thead>
            <tbody className={loading ? 'opacity-50' : ''}>
              {!loading && filteredIssues.map(issue => (
                <tr key={issue.id}>
                  <td>
                    <p className="font-medium text-text-base">{issue.title}</p>
                    <p className="mt-0.5 max-w-[360px] truncate text-xs text-wp-muted">{issue.detail}</p>
                  </td>
                  <td>
                    <p className="font-medium text-text-base">{issue.product.name}</p>
                    <p className="mt-0.5 text-xs text-wp-muted">{issue.product.sku || 'No SKU'} · {issue.product.connectorId || 'Unknown source'}</p>
                  </td>
                  <td><Badge variant={issue.severity === 'blocking' ? 'danger' : 'warning'} dot>{issue.severity === 'blocking' ? 'Blocking' : 'Warning'}</Badge></td>
                  <td><Badge variant="neutral">Open</Badge></td>
                  <td>{issue.product.lastSynced ? issue.product.lastSynced.toLocaleDateString() : 'Not synced'}</td>
                  <td className="text-end">
                    <a href={`/products?search=${encodeURIComponent(issue.product.name)}`} className="fh-button-secondary fh-button-sm inline-flex">Resolve</a>
                  </td>
                </tr>
              ))}
              {!loading && filteredIssues.length === 0 && (
                <tr><td colSpan={6}><Empty title={issues.length === 0 ? 'No data quality issues' : 'No matching issues'} description={issues.length === 0 ? 'The checked catalog passed the current quality rules.' : 'Try adjusting the search or filters.'} /></td></tr>
              )}
            </tbody>
          </table>
        </div>
        {loading && <div className="flex items-center justify-center gap-2 p-8 fh-text-body"><Spinner size="sm" />Checking product data</div>}
      </div>
    </PageShell>
  )
}
