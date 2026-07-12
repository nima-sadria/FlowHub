// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiProductService } from './ApiProductService'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('ApiProductService', () => {
  it('uses the channel product identifier instead of the cache row identifier', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      items: [{
        id: '8767',
        productId: 'O5ekdL',
        connectorId: 'snappshop:main',
        name: 'Product',
        sku: '',
        currentPrice: 49000000,
        sourcePrice: null,
        currency: 'TMN',
        categoryNames: [],
        productType: 'variation',
        status: 'active',
        lastSynced: null,
      }],
      total: 1,
      page: 1,
      pageSize: 20,
      configured: true,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    const result = await new ApiProductService().getProducts({ page: 1, pageSize: 20, search: '', status: 'all' })

    expect(result.items[0].id).toBe('O5ekdL')
  })
})
