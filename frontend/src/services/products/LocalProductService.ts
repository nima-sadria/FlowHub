import type { Product, ProductFilter, PaginatedResult, ProductSyncStatus } from '../types'
import type { ProductService } from './ProductService'

const delay = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

const now = new Date()
const hoursAgo = (h: number) => new Date(now.getTime() - h * 3600 * 1000)

const ALL_PRODUCTS: Product[] = [
  { id: 'prod-001', name: 'Wireless Headphones Pro', sku: 'WHP-001', currentPrice: 89.99, sourcePrice: 94.99, currency: 'EUR', status: 'pending', lastSynced: hoursAgo(1), categoryNames: ['Audio'] },
  { id: 'prod-002', name: 'USB-C Hub 7-Port', sku: 'UCH-002', currentPrice: 49.99, sourcePrice: 52.99, currency: 'EUR', status: 'pending', lastSynced: hoursAgo(2), categoryNames: ['Accessories'] },
  { id: 'prod-003', name: 'Mechanical Keyboard TKL', sku: 'MKB-003', currentPrice: 129.00, sourcePrice: 129.00, currency: 'EUR', status: 'synced', lastSynced: hoursAgo(2), categoryNames: ['Peripherals'] },
  { id: 'prod-004', name: '27" 4K Monitor', sku: 'MON-004', currentPrice: 299.00, sourcePrice: 319.00, currency: 'EUR', status: 'pending', lastSynced: hoursAgo(3), categoryNames: ['Electronics'] },
  { id: 'prod-005', name: 'Webcam HD 1080p', sku: 'CAM-005', currentPrice: 69.99, sourcePrice: 69.99, currency: 'EUR', status: 'synced', lastSynced: hoursAgo(4), categoryNames: ['Electronics'] },
  { id: 'prod-006', name: 'Mouse Pad XL', sku: 'MPD-006', currentPrice: 19.99, sourcePrice: 19.99, currency: 'EUR', status: 'synced', lastSynced: hoursAgo(4), categoryNames: ['Accessories'] },
  { id: 'prod-007', name: 'Laptop Stand Aluminium', sku: 'LST-007', currentPrice: 39.99, sourcePrice: 39.99, currency: 'EUR', status: 'synced', lastSynced: hoursAgo(5), categoryNames: ['Accessories'] },
  { id: 'prod-008', name: 'Smart Desk Lamp', sku: 'SDL-008', currentPrice: 59.99, sourcePrice: 59.99, currency: 'EUR', status: 'synced', lastSynced: hoursAgo(6), categoryNames: ['Electronics'] },
  { id: 'prod-009', name: 'Cable Management Kit', sku: 'CMK-009', currentPrice: 14.99, sourcePrice: 15.99, currency: 'EUR', status: 'stale', lastSynced: hoursAgo(12), categoryNames: ['Accessories'] },
  { id: 'prod-010', name: 'Portable SSD 1TB', sku: 'SSD-010', currentPrice: 99.99, sourcePrice: null, currency: 'EUR', status: 'error', lastSynced: null, categoryNames: ['Electronics'] },
  { id: 'prod-011', name: 'Noise Cancelling Earbuds', sku: 'NCE-011', currentPrice: 79.99, sourcePrice: 79.99, currency: 'EUR', status: 'synced', lastSynced: hoursAgo(8), categoryNames: ['Audio'] },
  { id: 'prod-012', name: 'HDMI 2.1 Cable 2m', sku: 'HDM-012', currentPrice: 9.99, sourcePrice: 9.99, currency: 'EUR', status: 'synced', lastSynced: hoursAgo(7), categoryNames: ['Accessories'] },
]

export class LocalProductService implements ProductService {
  async getProducts(filter: ProductFilter): Promise<PaginatedResult<Product>> {
    await delay(120)
    let items = [...ALL_PRODUCTS]

    if (filter.search.trim()) {
      const q = filter.search.trim().toLowerCase()
      items = items.filter(p => p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q))
    }

    if (filter.status !== 'all') {
      items = items.filter(p => p.status === (filter.status as ProductSyncStatus))
    }

    const total = items.length
    const start = (filter.page - 1) * filter.pageSize
    const pageItems = items.slice(start, start + filter.pageSize)

    return { items: pageItems, total, page: filter.page, pageSize: filter.pageSize }
  }

  async getProduct(id: string): Promise<Product> {
    await delay(80)
    const p = ALL_PRODUCTS.find(p => p.id === id)
    if (!p) throw new Error(`Product ${id} not found`)
    return p
  }
}
