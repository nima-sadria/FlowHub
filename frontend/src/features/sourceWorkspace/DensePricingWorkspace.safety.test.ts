import { describe, expect, it } from 'vitest'
import type { ReviewItemResource } from '../../services/unifiedWorkspace/types'
import {
  createPricingWorkspaceState,
  editPricingField,
  isPricingFieldEligible,
  selectedPricingChanges,
  type PricingFieldDescriptor,
} from '../pricingWorkspace'
import {
  createLatestGridLoader,
  pricingDescriptors,
  refreshRegisteredPricingState,
  resolveExactReviewSelection,
  validateDescriptorTarget,
} from './DensePricingWorkspace'
import type { GroupedWorkspacePage, SourceChannel } from './types'

describe('DensePricingWorkspace safety boundaries', () => {
  it('requires every locally selected field to resolve to exactly one eligible Review item', () => {
    const price = descriptor('price')
    const stock = descriptor('stock')
    let state = createPricingWorkspaceState('workspace-1', [price, stock], 'snapshot-1:draft-1')
    state = editPricingField(state, price, '110')
    state = editPricingField(state, stock, '8')
    const changes = selectedPricingChanges(state)
    const exact = [reviewItem('review-price', 'price', true), reviewItem('review-stock', 'stock', true)]

    expect(resolveExactReviewSelection(exact, changes)).toEqual(['review-price', 'review-stock'])
    expect(resolveExactReviewSelection(exact, changes.slice(0, 1))).toEqual(['review-price'])
    expect(() => resolveExactReviewSelection(exact.slice(0, 1), changes)).toThrow(/one eligible Review item/)
    expect(() => resolveExactReviewSelection([
      exact[0],
      reviewItem('review-stock-blocked', 'stock', false),
    ], changes)).toThrow(/one eligible Review item/)
    expect(() => resolveExactReviewSelection([
      ...exact,
      reviewItem('review-price-duplicate', 'price', true),
    ], changes)).toThrow(/one eligible Review item/)
  })

  it('commits only the latest grid response when an older request resolves last', async () => {
    const loader = createLatestGridLoader<string>()
    const committed: string[] = []
    let resolveOld!: (value: string) => void
    const oldResponse = new Promise<string>(resolve => { resolveOld = resolve })

    const old = loader.run(() => oldResponse, value => committed.push(value))
    const fresh = loader.run(() => Promise.resolve('fresh-filter-page'), value => committed.push(value))
    await expect(fresh).resolves.toBe(true)
    resolveOld('stale-page')
    await expect(old).resolves.toBe(false)
    expect(committed).toEqual(['fresh-filter-page'])
  })

  it('marks a descriptor refresh as review-invalidating only when registered meaning changes', () => {
    const price = descriptor('price')
    const state = createPricingWorkspaceState('workspace-1', [], 'snapshot-1:draft-1')
    const first = refreshRegisteredPricingState(state, [{ ...price, targetValue: '110' }])
    expect(first.changed).toBe(true)
    expect(selectedPricingChanges(first.state)).toHaveLength(1)

    const stable = refreshRegisteredPricingState(first.state, [{ ...price, targetValue: '110' }])
    expect(stable.changed).toBe(false)

    const capabilityChanged = refreshRegisteredPricingState(stable.state, [{
      ...price,
      targetValue: '110',
      policy: { ...price.policy, supported: false, blockedReason: 'unsupported_field' },
    }])
    expect(capabilityChanged.changed).toBe(true)
    expect(selectedPricingChanges(capabilityChanged.state)).toHaveLength(0)
  })

  it('uses production camelCase write capabilities and fails closed on missing or conflicting values', () => {
    const production = channel({ writePrice: true, writeStock: true, writeStatus: true, writeAvailable: true })
    expect(fieldPolicy(production, 'price').supported).toBe(true)

    const primaryFalseAliasTrue = channel({ writePrice: false, price_write: true, writeAvailable: true })
    expect(fieldPolicy(primaryFalseAliasTrue, 'price').supported).toBe(false)
    expect(fieldPolicy(channel({ writePrice: true, writeAvailable: false, write_available: true }), 'price').supported).toBe(false)

    expect(fieldPolicy(channel({ writePrice: undefined, writeAvailable: true }), 'price').supported).toBe(false)
    const legacy = channel({ price_write: true })
    delete legacy.capabilities.writePrice
    delete legacy.capabilities.writeAvailable
    expect(fieldPolicy(legacy, 'price').supported).toBe(true)
    expect(fieldPolicy(channel({ writePrice: 'true', price_write: true }), 'price').supported).toBe(false)
  })

  it('fails closed for missing or mismatched currency/unit and unsupported statuses', () => {
    const production = channel({ writePrice: true, writeStatus: true, writeAvailable: true })
    const price = descriptor('price')
    expect(validateDescriptorTarget(price, production, '110').policy.valid).toBe(true)

    expect(validateDescriptorTarget(
      { ...price, unit: 'TOMAN' },
      production,
      '110',
    ).policy).toMatchObject({ valid: false, blockedReason: 'currency_unit_invalid' })
    expect(validateDescriptorTarget(price, channel({ writePrice: true, currency: null }), '110').policy.valid).toBe(false)
    expect(validateDescriptorTarget(price, channel({ writePrice: true, currency: 'TOMAN', unit: 'TOMAN' }), '110').policy.valid).toBe(false)

    const status = descriptor('status')
    expect(validateDescriptorTarget(status, production, 'active').policy.valid).toBe(true)
    expect(validateDescriptorTarget(status, production, 'archived').policy).toMatchObject({ valid: false, blockedReason: 'unsupported_status' })
    expect(validateDescriptorTarget(status, channel({ writeStatus: true, supportedStatuses: undefined }), 'active').policy.valid).toBe(false)
  })

  it('keeps a valid Price eligible when a sibling Stock field blocks the Listing summary', () => {
    const mixed = grid()
    const listing = mixed.items[0].children[0]
    listing.state = 'blocked'
    listing.fields.stock.status = 'blocked'
    const items = pricingDescriptors(mixed, new Map([['woocommerce:primary', channel({})]]))
    const price = items.find(item => item.identity.field === 'price')!
    const stock = items.find(item => item.identity.field === 'stock')!

    expect(isPricingFieldEligible(price.policy)).toBe(true)
    expect(stock.policy).toMatchObject({ valid: false, blockedReason: 'validation_blocked' })
    expect(isPricingFieldEligible(stock.policy)).toBe(false)
  })
})

function descriptor(field: 'price' | 'stock' | 'status'): PricingFieldDescriptor {
  return {
    identity: { productId: 'product-1', listingId: 'listing-1', channelId: 'woocommerce:primary', field },
    currentValue: field === 'price' ? '100' : field === 'stock' ? '5' : 'active',
    targetValue: field === 'price' ? '100' : field === 'stock' ? '5' : 'active',
    currency: field === 'price' ? 'IRR' : null,
    unit: field === 'price' ? 'IRR' : null,
    policy: {
      writable: true,
      mapped: true,
      supported: true,
      channelEnabled: true,
      comingSoon: false,
      valid: true,
      blockedReason: null,
      warning: null,
    },
  }
}

function reviewItem(id: string, field: 'price' | 'stock' | 'status', eligible: boolean): ReviewItemResource {
  return {
    id,
    canonicalProductId: 'product-1',
    listingId: 'listing-1',
    channelId: 'woocommerce:primary',
    field,
    current: null,
    target: '110',
    validationState: eligible ? 'ready' : 'blocked',
    warnings: [],
    errors: eligible ? [] : ['blocked'],
    eligible,
    selected: false,
  }
}

function channel(overrides: Record<string, unknown>): SourceChannel {
  return {
    channelId: 'woocommerce:primary',
    name: 'WooCommerce',
    connectorType: 'woocommerce',
    capabilityVersion: 'production-shape-v1',
    capabilities: {
      writePrice: true,
      writeStock: true,
      writeStatus: true,
      writeAvailable: true,
      supportedStatuses: ['active', 'inactive'],
      currency: 'IRR',
      unit: 'IRR',
      ...overrides,
    },
    enabled: true,
    implementationState: 'implemented',
    available: true,
  }
}

function fieldPolicy(channelValue: SourceChannel, field: 'price' | 'stock' | 'status') {
  return pricingDescriptors(grid(), new Map([[channelValue.channelId, channelValue]]))
    .find(item => item.identity.field === field)!.policy
}

function grid(): GroupedWorkspacePage {
  const field = (current: string, currency: string | null, unit: string | null) => ({
    current,
    target: current,
    changed: false,
    readOnly: false,
    status: 'ready' as const,
    currency,
    unit,
  })
  return {
    items: [{
      sourceProductId: 'product-1',
      name: 'Product 1',
      sourceKey: 'SKU-1',
      cost: null,
      category: null,
      brand: null,
      productType: 'simple',
      mappedChannelCount: 1,
      listingCount: 1,
      changedListingCount: 0,
      selectedListingCount: 0,
      state: 'ready',
      children: [{
        listingId: 'listing-1',
        channelId: 'woocommerce:primary',
        listingLabel: 'Main',
        externalId: '1001',
        externalIdType: 'product_id',
        sku: 'SKU-1',
        mappingState: 'resolved',
        cacheFreshness: 'fresh',
        state: 'ready',
        changedFields: [],
        selected: false,
        reviewItemIds: [],
        fields: {
          price: field('100', 'IRR', 'IRR'),
          stock: field('5', null, null),
          status: field('active', null, null),
        },
      }],
    }],
    total: 1,
    page: 1,
    pageSize: 100,
    view: 'all',
    summary: { ready: 1, blocked: 0, unchanged: 0, selected: 0 },
    draftVersion: 0,
    revisionId: null,
    reviewId: null,
    reviewStatus: null,
    selectionChecksum: null,
  }
}
