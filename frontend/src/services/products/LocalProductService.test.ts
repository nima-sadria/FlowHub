// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest'
import { LocalProductService } from './LocalProductService'

let svc: LocalProductService

beforeEach(() => { svc = new LocalProductService() })

describe('LocalProductService.getProducts', () => {
  it('returns all 12 products with no filter', async () => {
    const r = await svc.getProducts({ search: '', status: 'all', page: 1, pageSize: 20 })
    expect(r.total).toBe(12)
    expect(r.items.length).toBe(12)
  })

  it('paginates correctly', async () => {
    const page1 = await svc.getProducts({ search: '', status: 'all', page: 1, pageSize: 5 })
    expect(page1.items.length).toBe(5)
    expect(page1.total).toBe(12)

    const page3 = await svc.getProducts({ search: '', status: 'all', page: 3, pageSize: 5 })
    expect(page3.items.length).toBe(2)
  })

  it('filters by status=pending returns 3', async () => {
    const r = await svc.getProducts({ search: '', status: 'pending', page: 1, pageSize: 20 })
    expect(r.total).toBe(3)
    expect(r.items.every(p => p.status === 'pending')).toBe(true)
  })

  it('filters by status=stale returns 1', async () => {
    const r = await svc.getProducts({ search: '', status: 'stale', page: 1, pageSize: 20 })
    expect(r.total).toBe(1)
    expect(r.items[0].sku).toBe('CMK-009')
  })

  it('filters by status=error returns 1', async () => {
    const r = await svc.getProducts({ search: '', status: 'error', page: 1, pageSize: 20 })
    expect(r.total).toBe(1)
    expect(r.items[0].sku).toBe('SSD-010')
  })

  it('filters by status=synced returns 7', async () => {
    const r = await svc.getProducts({ search: '', status: 'synced', page: 1, pageSize: 20 })
    expect(r.total).toBe(7)
  })

  it('searches by name (case insensitive)', async () => {
    const r = await svc.getProducts({ search: 'headphones', status: 'all', page: 1, pageSize: 20 })
    expect(r.total).toBe(1)
    expect(r.items[0].sku).toBe('WHP-001')
  })

  it('searches by SKU', async () => {
    const r = await svc.getProducts({ search: 'SSD-010', status: 'all', page: 1, pageSize: 20 })
    expect(r.total).toBe(1)
    expect(r.items[0].name).toBe('Portable SSD 1TB')
  })

  it('returns zero results for non-matching search', async () => {
    const r = await svc.getProducts({ search: 'xyznotfound', status: 'all', page: 1, pageSize: 20 })
    expect(r.total).toBe(0)
    expect(r.items.length).toBe(0)
  })
})

describe('LocalProductService.getProduct', () => {
  it('returns product by id', async () => {
    const p = await svc.getProduct('prod-001')
    expect(p.sku).toBe('WHP-001')
  })

  it('throws for unknown id', async () => {
    await expect(svc.getProduct('unknown')).rejects.toThrow('not found')
  })
})
