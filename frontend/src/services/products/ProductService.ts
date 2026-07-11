import type {
  Product,
  ProductChannelPriceOperation,
  ProductChannelPriceRequest,
  ProductChannelPriceStateSet,
  ProductFilter,
  PaginatedResult,
} from '../types'

export interface Category {
  id: number
  name: string
  parent: number
}

export interface ProductService {
  getProducts(filter: ProductFilter): Promise<PaginatedResult<Product>>
  getProduct(id: string): Promise<Product>
  getCategories?(): Promise<Category[]>
  getChannelPrices(productId: string): Promise<ProductChannelPriceStateSet>
  validateChannelPrices(productId: string, request: ProductChannelPriceRequest): Promise<ProductChannelPriceStateSet>
  createChannelPriceDryRun(productId: string, request: ProductChannelPriceRequest): Promise<ProductChannelPriceOperation>
  getChannelPriceOperation(operationId: string): Promise<ProductChannelPriceOperation>
  approveChannelPriceOperation(operationId: string, reason?: string): Promise<ProductChannelPriceOperation>
  applyChannelPriceOperation(operationId: string): Promise<ProductChannelPriceOperation>
}
