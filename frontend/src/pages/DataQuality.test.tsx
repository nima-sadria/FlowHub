// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { Product } from '../services/types'
import DataQuality from './DataQuality'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const products: Product[] = [
  {
    id: '1',
    connectorId: 'woocommerce:primary',
    name: 'Missing identifiers',
    sku: '',
    currentPrice: 10,
    sourcePrice: null,
    currency: 'EUR',
    status: 'error',
    lastSynced: null,
    categoryNames: [],
    imageUrl: null,
  },
  {
    id: '2',
    connectorId: 'snappshop:main',
    name: 'Healthy product',
    sku: 'SKU-2',
    currentPrice: 20,
    sourcePrice: null,
    currency: 'EUR',
    status: 'synced',
    lastSynced: new Date(),
    categoryNames: [],
    imageUrl: '/product.png',
  },
]

function services(): Services {
  return {
    products: {
      getProducts: vi.fn(async () => ({ items: products, total: products.length, page: 1, pageSize: 200 })),
    },
  } as unknown as Services
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
})

async function renderPage() {
  const appServices = services()
  await act(async () => {
    root.render(
      <ServiceProvider services={appServices}>
        <DataQuality />
      </ServiceProvider>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return { container, appServices }
}

describe('DataQuality', () => {
  it('derives catalog issues from canonical products', async () => {
    const { container: page } = await renderPage()
    expect(page.textContent).toContain('Missing SKU')
    expect(page.textContent).toContain('Missing product image')
    expect(page.textContent).toContain('Synchronization failed')
    expect(page.querySelector('a[href="/products?search=Missing%20identifiers"]')).not.toBeNull()
  })

  it('reruns the quality check from the primary action', async () => {
    const { container: page, appServices } = await renderPage()
    const runCheck = Array.from(page.querySelectorAll('button')).find(button => button.textContent?.includes('Run check'))
    await act(async () => {
      runCheck?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })
    expect(appServices.products.getProducts).toHaveBeenCalledTimes(2)
  })
})
