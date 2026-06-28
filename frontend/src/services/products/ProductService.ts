import type { Product, ProductFilter, PaginatedResult } from '../types'

export interface ProductService {
  getProducts(filter: ProductFilter): Promise<PaginatedResult<Product>>
  getProduct(id: string): Promise<Product>
}
