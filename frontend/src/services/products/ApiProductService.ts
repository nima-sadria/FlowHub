import type {
  Product,
  ProductChannelPriceOperation,
  ProductChannelPriceRequest,
  ProductChannelPriceStateSet,
  ProductFilter,
  PaginatedResult,
} from '../types'
import type { ProductService, Category } from './ProductService'
import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'

interface RawProduct {
  id: string
  connectorId: string
  wcId?: number
  name: string
  sku: string
  currentPrice: number
  sourcePrice: number | null
  currency: string
  categoryNames: string[]
  imageUrl?: string | null
  productType?: string
  status: string
  lastSynced: string | null
}

interface RawPage {
  items: RawProduct[]
  total: number
  page: number
  pageSize: number
  configured?: boolean
}

function mapProduct(r: RawProduct): Product {
  return {
    id: r.id,
    connectorId: r.connectorId,
    name: r.name,
    sku: r.sku,
    currentPrice: r.currentPrice,
    sourcePrice: r.sourcePrice ?? null,
    currency: r.currency,
    categoryNames: r.categoryNames ?? [],
    imageUrl: r.imageUrl ?? null,
    productType: r.productType as Product['productType'] ?? 'simple',
    status: (r.status as Product['status']) ?? 'pending',
    lastSynced: r.lastSynced ? new Date(r.lastSynced) : null,
  }
}

export class ApiProductService implements ProductService {
  async getProducts(filter: ProductFilter): Promise<PaginatedResult<Product>> {
    const params = new URLSearchParams({
      page: String(filter.page),
      pageSize: String(filter.pageSize),
    })
    if (filter.search) params.set('search', filter.search)
    if (filter.categoryId) params.set('categoryId', String(filter.categoryId))
    if (filter.productType) {
      params.set('productType', filter.productType)
    }
    if (filter.channelId) params.set('channelId', filter.channelId)

    const data = await apiFetch<RawPage>(`/api/v2/products?${params}`, authFetch)
    return {
      items: data.items.map(mapProduct),
      total: data.total,
      page: data.page,
      pageSize: data.pageSize,
      configured: data.configured,
    }
  }

  async getProduct(id: string): Promise<Product> {
    const data = await apiFetch<RawProduct>(`/api/v2/products/${id}`, authFetch)
    return mapProduct(data)
  }

  async getCategories(): Promise<Category[]> {
    const data = await apiFetch<{ items: Category[] }>('/api/v2/products/categories', authFetch)
    return data.items
  }

  async getChannelPrices(productId: string): Promise<ProductChannelPriceStateSet> {
    return apiFetch<ProductChannelPriceStateSet>(`/api/v2/products/${encodeURIComponent(productId)}/channel-prices`, authFetch)
  }

  async validateChannelPrices(productId: string, request: ProductChannelPriceRequest): Promise<ProductChannelPriceStateSet> {
    return apiFetch<ProductChannelPriceStateSet>(`/api/v2/products/${encodeURIComponent(productId)}/channel-prices/validate`, authFetch, jsonRequest(request))
  }

  async createChannelPriceDryRun(productId: string, request: ProductChannelPriceRequest): Promise<ProductChannelPriceOperation> {
    return apiFetch<ProductChannelPriceOperation>(`/api/v2/products/${encodeURIComponent(productId)}/channel-prices/dry-run`, authFetch, jsonRequest(request))
  }

  async getChannelPriceOperation(operationId: string): Promise<ProductChannelPriceOperation> {
    return apiFetch<ProductChannelPriceOperation>(`/api/v2/products/channel-price-operations/${encodeURIComponent(operationId)}`, authFetch)
  }

  async approveChannelPriceOperation(operationId: string, reason?: string): Promise<ProductChannelPriceOperation> {
    return apiFetch<ProductChannelPriceOperation>(
      `/api/v2/products/channel-price-operations/${encodeURIComponent(operationId)}/approve`,
      authFetch,
      jsonRequest({ reason: reason ?? '' }),
    )
  }

  async applyChannelPriceOperation(operationId: string): Promise<ProductChannelPriceOperation> {
    return apiFetch<ProductChannelPriceOperation>(
      `/api/v2/products/channel-price-operations/${encodeURIComponent(operationId)}/apply`,
      authFetch,
      jsonRequest({}),
    )
  }
}

function jsonRequest(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}
