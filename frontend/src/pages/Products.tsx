import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import LocalizedText from '../components/LocalizedText'
import PageShell from '../components/PageShell'
import DensePricingWorkspace from '../features/sourceWorkspace/DensePricingWorkspace'
import { translate } from '../i18n'
import { formatProductType } from '../i18n/display'
import { formatNumber } from '../i18n/format'
import { useServices } from '../services/ServiceContext'
import type { Product } from '../services/types'
import type { Category } from '../services/products/ProductService'
import type { UnifiedWorkspaceResource } from '../services/unifiedWorkspace/types'

const ACTIVE_WORKSPACE_KEY = 'flowhub.products.active_workspace'
const FALLBACK_PAGE_SIZE = 50

function storedWorkspaceId(): string {
  try { return window.sessionStorage.getItem(ACTIVE_WORKSPACE_KEY)?.trim() ?? '' } catch { return '' }
}

function rememberWorkspaceId(workspaceId: string) {
  try { window.sessionStorage.setItem(ACTIVE_WORKSPACE_KEY, workspaceId) } catch { /* Session persistence is optional. */ }
}

function forgetWorkspaceId() {
  try { window.sessionStorage.removeItem(ACTIVE_WORKSPACE_KEY) } catch { /* Session persistence is optional. */ }
}

function bootstrapFailure(error: unknown): string {
  if (error instanceof ApiError) {
    return translate('products:products.inlinePricingUnavailableHttp', { status: error.status })
  }
  return translate('products:products.inlinePricingUnavailable')
}

function CachedProductRow({ product }: { product: Product }) {
  return <tr data-product-id={product.id}>
    <td><div className="font-medium"><LocalizedText text={product.name} /></div></td>
    <td className="fh-text-mono">{product.sku || '—'}</td>
    <td><Badge variant="neutral">{formatProductType(product.productType)}</Badge></td>
    <td>{(product.categoryNames ?? []).join(', ') || '—'}</td>
    <td className="fh-text-mono text-end">{formatNumber(product.currentPrice)} <span className="fh-text-caption">{product.currency}</span></td>
  </tr>
}

export default function Products() {
  const { products: productService, unifiedWorkspace } = useServices()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryWorkspaceId = searchParams.get('workspace')?.trim() ?? ''
  const generation = useRef(0)
  const catalogBootstrap = useRef<Promise<UnifiedWorkspaceResource> | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [ignoreExisting, setIgnoreExisting] = useState(false)
  const [workspace, setWorkspace] = useState<UnifiedWorkspaceResource | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [cachedProducts, setCachedProducts] = useState<Product[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [catalogConfigured, setCatalogConfigured] = useState<boolean | undefined>(undefined)
  const [catalogLoading, setCatalogLoading] = useState(false)

  useEffect(() => {
    let active = true
    productService.getCategories?.()
      .then(result => { if (active) setCategories(result) })
      .catch(() => { if (active) setCategories([]) })
    return () => { active = false }
  }, [productService])

  useEffect(() => {
    if (!error) return
    let active = true
    setCatalogLoading(true)
    productService.getProducts({ search: '', status: 'all', page: 1, pageSize: FALLBACK_PAGE_SIZE })
      .then(result => {
        if (!active) return
        setCachedProducts(result.items)
        setCatalogConfigured(result.configured)
      })
      .catch(() => { if (active) setCachedProducts([]) })
      .finally(() => { if (active) setCatalogLoading(false) })
    return () => { active = false }
  }, [error, productService])

  const bootstrap = useCallback(async () => {
    const requestGeneration = ++generation.current
    setLoading(true)
    setError(null)
    setWorkspace(null)
    try {
      if (!unifiedWorkspace) throw new Error('catalog_workspace_unavailable')
      const existingId = ignoreExisting ? '' : queryWorkspaceId || storedWorkspaceId()
      const result = existingId
        ? await unifiedWorkspace.getWorkspace(existingId)
        : unifiedWorkspace.createCatalog
          ? await (() => {
              if (!catalogBootstrap.current) {
                const request = unifiedWorkspace.createCatalog!(translate('products:products.pricingWorkspace'))
                catalogBootstrap.current = request
                void request.finally(() => { if (catalogBootstrap.current === request) catalogBootstrap.current = null }).catch(() => {})
              }
              return catalogBootstrap.current
            })()
          : (() => { throw new Error('catalog_workspace_unavailable') })()
      if (result.entryPoint !== 'manual' && result.entryPoint !== 'source') {
        throw new Error('catalog_workspace_invalid_entry_point')
      }
      if (requestGeneration !== generation.current) return
      // A legacy /workspace/:id redirect is a one-time compatibility handoff.
      // It must not replace the catalog-wide Products session for later visits.
      if (!queryWorkspaceId) rememberWorkspaceId(result.id)
      setWorkspace(result)
    } catch (cause) {
      if (requestGeneration !== generation.current) return
      forgetWorkspaceId()
      setError(bootstrapFailure(cause))
    } finally {
      if (requestGeneration === generation.current) setLoading(false)
    }
  }, [ignoreExisting, queryWorkspaceId, unifiedWorkspace])

  useEffect(() => { void bootstrap(); return () => { generation.current += 1 } }, [bootstrap, attempt])

  const retry = () => {
    forgetWorkspaceId()
    setCachedProducts([])
    setCatalogConfigured(undefined)
    setIgnoreExisting(true)
    setAttempt(value => value + 1)
  }

  if (workspace && unifiedWorkspace) {
    return <PageShell><DensePricingWorkspace
      workspace={workspace}
      service={unifiedWorkspace}
      embedded
      categoryOptions={categories.map(category => ({ value: category.name, label: category.name }))}
    /></PageShell>
  }

  if (!catalogLoading && catalogConfigured === false) {
    return <PageShell><div><h1 className="fh-page-title">{translate('products:products.products')}</h1><p className="fh-page-subtitle">{translate('products:products.productCatalog')}</p></div><div className="fh-card"><Empty title={translate('products:products.noProductConnectorConfigured')} description={translate('products:products.connectAProductSourceFromSourcesTo')} action={{ label: translate('products:products.openSources'), onClick: () => navigate('/sources') }} /></div></PageShell>
  }

  if (loading && !error) {
    return <PageShell><div className="fh-card fh-card-pad flex items-center gap-3" role="status"><span className="fh-spinner" aria-hidden="true" /><span>{translate('products:products.preparingInlinePricing')}</span></div></PageShell>
  }

  return <PageShell>
    <div className="fh-page-header"><div><h1 className="fh-page-title">{translate('products:products.products')}</h1><p className="fh-page-subtitle">{translate('products:products.cachedProductsReadOnly')}</p></div><button type="button" className="fh-button-secondary" onClick={retry}><Icon name="refresh" /> {translate('products:products.retryInlinePricing')}</button></div>
    <div className="fh-alert fh-alert-warning" role="alert"><Icon name="alert" /><span>{error ?? translate('products:products.inlinePricingUnavailable')}</span></div>
    <div className="fh-card mt-3 overflow-hidden">
      <div className="overflow-x-auto"><table className="fh-table min-w-[760px]"><thead><tr><th>{translate('products:column.product')}</th><th>{translate('products:column.sku')}</th><th>{translate('products:column.type')}</th><th>{translate('products:column.categories')}</th><th className="text-end">{translate('products:column.current')}</th></tr></thead><tbody>{cachedProducts.length ? cachedProducts.map(product => <CachedProductRow key={`${product.connectorId ?? ''}:${product.id}`} product={product} />) : <tr><td colSpan={5}><Empty title={translate('products:products.noProductsFound')} description={translate('products:products.retryInlinePricing')} /></td></tr>}</tbody></table></div>
    </div>
  </PageShell>
}
