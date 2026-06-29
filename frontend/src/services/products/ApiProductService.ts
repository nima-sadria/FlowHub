import type { Product, ProductFilter, PaginatedResult } from '../types'
import type { ProductService, Category } from './ProductService'
import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'

interface RawProduct {
  id: string
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
}
