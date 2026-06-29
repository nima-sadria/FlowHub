import type { Product, ProductFilter, PaginatedResult } from '../types'

export interface Category {
  id: number
  name: string
  parent: number
}

export interface ProductService {
  getProducts(filter: ProductFilter): Promise<PaginatedResult<Product>>
  getProduct(id: string): Promise<Product>
  getCategories?(): Promise<Category[]>
}
