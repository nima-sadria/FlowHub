import type {
  Product,
  ProductChannelPriceOperation,
  ProductChannelPriceRequest,
  ProductChannelPriceStateSet,
  ProductFilter,
  PaginatedResult,
  ProductSyncStatus,
} from '../types'
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

  async getChannelPrices(productId: string): Promise<ProductChannelPriceStateSet> {
    await delay(80)
    return makeChannelPrices(productId)
  }

  async validateChannelPrices(productId: string, request: ProductChannelPriceRequest): Promise<ProductChannelPriceStateSet> {
    await delay(80)
    return validateLocal(productId, request)
  }

  async createChannelPriceDryRun(productId: string, request: ProductChannelPriceRequest): Promise<ProductChannelPriceOperation> {
    await delay(100)
    const validated = validateLocal(productId, request)
    const items = validated.channels.filter(channel => channel.pendingChange && channel.validationState === 'valid').map((channel, index) => ({
      id: index + 1,
      channelId: channel.channelId,
      connectorType: channel.connectorType,
      channelProductId: channel.channelProductId,
      sku: channel.sku,
      currentValue: channel.currentValue ?? 0,
      proposedValue: channel.proposedValue ?? 0,
      currency: channel.currency,
      unit: channel.unit,
      outboundValue: channel.outboundValue ?? channel.proposedValue ?? 0,
      outboundUnit: channel.outboundUnit ?? channel.unit,
      staleToken: channel.staleToken,
      status: 'pending',
      validationState: channel.validationState,
      errorMessage: null,
      result: { dry_run: true, external_write: false },
    }))
    return {
      id: `local_${Date.now()}`,
      productId,
      sku: validated.product.sku,
      productName: validated.product.name,
      status: 'dry_run_ready',
      version: validated.version,
      createdBy: 'local',
      approvedBy: null,
      approvalReason: null,
      createdAt: new Date().toISOString(),
      approvedAt: null,
      appliedAt: null,
      summary: { total: items.length, pending: items.length, success: 0, failed: 0, external_write_performed: false },
      items,
      externalWritePerformed: false,
      applyRequiresApproval: true,
    }
  }

  async getChannelPriceOperation(operationId: string): Promise<ProductChannelPriceOperation> {
    throw new Error(`Local operation ${operationId} is not persisted`)
  }

  async approveChannelPriceOperation(operationId: string, reason?: string): Promise<ProductChannelPriceOperation> {
    return {
      id: operationId,
      productId: 'prod-001',
      sku: 'WHP-001',
      productName: 'Wireless Headphones Pro',
      status: 'approved',
      version: 'local-v1',
      createdBy: 'local',
      approvedBy: 'local',
      approvalReason: reason ?? null,
      createdAt: new Date().toISOString(),
      approvedAt: new Date().toISOString(),
      appliedAt: null,
      summary: { total: 0, pending: 0, success: 0, failed: 0, external_write_performed: false },
      items: [],
      externalWritePerformed: false,
      applyRequiresApproval: true,
    }
  }

  async applyChannelPriceOperation(operationId: string): Promise<ProductChannelPriceOperation> {
    const approved = await this.approveChannelPriceOperation(operationId)
    return { ...approved, status: 'applied', appliedAt: new Date().toISOString(), externalWritePerformed: true }
  }
}

function makeChannelPrices(productId: string): ProductChannelPriceStateSet {
  const product = ALL_PRODUCTS.find(p => p.id === productId) ?? ALL_PRODUCTS[0]
  const base = product.currentPrice
  return {
    product: { id: product.id, name: product.name, sku: product.sku, productType: product.productType ?? 'simple', imageUrl: product.imageUrl },
    version: `local-${product.id}-v1`,
    canonical: {
      label: 'Canonical/business price',
      value: base,
      currency: product.currency,
      unit: 'store currency',
      freshness: 'fresh',
      lastSyncedAt: product.lastSynced?.toISOString() ?? null,
      staleToken: `canonical-${product.id}`,
    },
    dryRunRequired: true,
    applyRequiresApproval: true,
    channels: [
      makeChannel('woocommerce:primary', 'WooCommerce', 'woocommerce', product.sku, base, product.currency, product.currency),
      makeChannel('snappshop:main', 'Snapp Shop', 'snappshop', product.sku, Math.round(base * 1000), 'IRR', 'toman'),
      makeChannel('tapsishop:main', 'Tapsi Shop', 'tapsishop', product.sku, Math.round(base * 10000), 'IRR', 'rial'),
    ],
  }
}

function makeChannel(channelId: string, channelName: string, connectorType: string, sku: string, value: number, currency: string, unit: string) {
  return {
    channelId,
    channelName,
    connectorType,
    channelProductId: `${channelId}:${sku}`,
    sku,
    connectionState: 'connected',
    healthStatus: 'ok',
    canRead: true,
    canWrite: true,
    readOnly: false,
    writeCapability: 'products.write_price',
    currentValue: value,
    proposedValue: value,
    currency,
    unit,
    normalizedValue: channelId === 'snappshop:main' ? value * 10 : value,
    normalizedCurrency: channelId === 'woocommerce:primary' ? currency : 'IRR',
    normalizedUnit: channelId === 'woocommerce:primary' ? currency : 'rial',
    freshness: 'fresh',
    lastSyncedAt: new Date().toISOString(),
    validationState: 'valid' as const,
    validationMessage: null,
    pendingChange: false,
    staleToken: `${channelId}:${sku}:v1`,
  }
}

function validateLocal(productId: string, request: ProductChannelPriceRequest): ProductChannelPriceStateSet {
  const loaded = makeChannelPrices(productId)
  loaded.channels = loaded.channels.map(channel => {
    const change = request.changes.find(item => item.channelId === channel.channelId)
    if (!change) return channel
    const errors: string[] = []
    if (!Number.isFinite(change.proposedValue) || change.proposedValue < 0) errors.push('Price must be numeric and non-negative.')
    if (change.unit !== channel.unit) errors.push(`Expected ${channel.unit}.`)
    return {
      ...channel,
      proposedValue: change.proposedValue,
      outboundValue: change.proposedValue,
      outboundUnit: channel.unit,
      normalizedValue: channel.channelId === 'snappshop:main' ? change.proposedValue * 10 : change.proposedValue,
      pendingChange: channel.currentValue !== change.proposedValue,
      validationState: errors.length ? 'error' : 'valid',
      validationMessage: errors.join('; ') || null,
    }
  })
  return { ...loaded, status: 'validated' }
}
