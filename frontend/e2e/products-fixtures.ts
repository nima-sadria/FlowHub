import { readFileSync } from 'node:fs'
import path from 'node:path'
import type { Page, Route } from '@playwright/test'

// Shared Products Playwright fixtures/mocks. Not a .spec.ts file itself --
// Playwright forbids importing one spec file into another, so the harness
// products-screen.spec.ts originally defined lives here and both it and
// products-price-edit-regression.spec.ts import from this module instead.

const mockLogo = readFileSync(path.resolve('public', 'flowhub-logo.png'))

export const WORKSPACE_ID = 'products-catalog-workspace'
export const CHANNELS = [
  { channelId: 'woocommerce:primary', name: 'WooCommerce' },
  { channelId: 'snappshop:main', name: 'SnappShop' },
  { channelId: 'digikala:main', name: 'Digikala' },
  { channelId: 'technolife:main', name: 'Technolife' },
]

interface ListingFixture {
  listingId: string
  channelId: string
  price: number
  stock: number
  status: 'in_stock' | 'low_stock'
}
interface ProductFixture {
  productId: string
  name: string
  listings: ListingFixture[]
}

export const PRODUCTS: ProductFixture[] = [
  { productId: 'p1', name: 'Classic T-Shirt', listings: [
    { listingId: 'p1-woo', channelId: 'woocommerce:primary', price: 129, stock: 84, status: 'in_stock' },
    { listingId: 'p1-snap', channelId: 'snappshop:main', price: 135, stock: 80, status: 'in_stock' },
    { listingId: 'p1-digi', channelId: 'digikala:main', price: 125, stock: 79, status: 'in_stock' },
  ] },
  { productId: 'p2', name: 'Canvas Backpack', listings: [
    { listingId: 'p2-woo', channelId: 'woocommerce:primary', price: 350, stock: 31, status: 'in_stock' },
    { listingId: 'p2-snap', channelId: 'snappshop:main', price: 380, stock: 28, status: 'in_stock' },
  ] },
  { productId: 'p3', name: 'Running Shoes', listings: [
    { listingId: 'p3-woo', channelId: 'woocommerce:primary', price: 599, stock: 12, status: 'in_stock' },
    { listingId: 'p3-digi', channelId: 'digikala:main', price: 575, stock: 10, status: 'in_stock' },
  ] },
  { productId: 'p4', name: 'Ceramic Mug', listings: [
    { listingId: 'p4-woo', channelId: 'woocommerce:primary', price: 89, stock: 126, status: 'in_stock' },
    { listingId: 'p4-snap', channelId: 'snappshop:main', price: 92, stock: 120, status: 'in_stock' },
    { listingId: 'p4-tech', channelId: 'technolife:main', price: 85, stock: 115, status: 'in_stock' },
  ] },
  { productId: 'p5', name: 'Linen Shirt', listings: [
    { listingId: 'p5-woo', channelId: 'woocommerce:primary', price: 320, stock: 45, status: 'low_stock' },
    { listingId: 'p5-snap', channelId: 'snappshop:main', price: 335, stock: 40, status: 'in_stock' },
  ] },
  { productId: 'p6', name: 'Desk Lamp', listings: [
    { listingId: 'p6-woo', channelId: 'woocommerce:primary', price: 445, stock: 8, status: 'in_stock' },
    { listingId: 'p6-digi', channelId: 'digikala:main', price: 425, stock: 6, status: 'in_stock' },
    { listingId: 'p6-tech', channelId: 'technolife:main', price: 435, stock: 7, status: 'in_stock' },
  ] },
]
export const TOTAL_PRODUCTS = 248

export interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

export function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

export function field(current: string, target: string, currency: string | null, unit: string | null) {
  return { current, target, changed: false, readOnly: false, status: 'unchanged', currency, unit }
}

export function groupedGridResource() {
  return {
    items: PRODUCTS.map(product => ({
      sourceProductId: product.productId,
      name: product.name,
      sourceKey: product.productId.toUpperCase(),
      cost: null,
      category: null,
      brand: null,
      productType: 'simple',
      primaryImageUrl: product.productId === 'p1'
        ? 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="36" height="36"%3E%3Crect width="36" height="36" fill="%233b82f6"/%3E%3C/svg%3E'
        : null,
      media: product.productId === 'p1' ? [{
        type: 'image',
        url: 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="36" height="36"%3E%3Crect width="36" height="36" fill="%233b82f6"/%3E%3C/svg%3E',
        position: 0,
        source: 'woocommerce',
      }] : [],
      mappedChannelCount: product.listings.length,
      listingCount: product.listings.length,
      changedListingCount: 0,
      selectedListingCount: 0,
      state: 'unchanged',
      children: product.listings.map(listing => ({
        listingId: listing.listingId,
        channelId: listing.channelId,
        listingLabel: product.name,
        externalId: `${listing.listingId}-external`,
        externalIdType: 'external_id',
        sku: `${product.productId}-${listing.channelId.split(':')[0]}`,
        mappingState: 'resolved',
        cacheFreshness: 'fresh',
        state: 'unchanged',
        changedFields: [],
        selected: false,
        reviewItemIds: [],
        fields: {
          price: field(String(listing.price), String(listing.price), 'USD', 'USD'),
          stock: field(String(listing.stock), String(listing.stock), null, null),
          status: field(listing.status, listing.status, null, null),
        },
      })),
    })),
    total: TOTAL_PRODUCTS,
    page: 1,
    pageSize: 100,
    view: 'all',
    summary: { ready: 0, blocked: 0, unchanged: TOTAL_PRODUCTS, selected: 0 },
    draftVersion: 0,
    revisionId: null,
    reviewId: null,
    reviewStatus: null,
    selectionChecksum: null,
  }
}

export function workspaceResource() {
  return {
    id: WORKSPACE_ID,
    name: 'Pricing workspace',
    entryPoint: 'manual',
    ownerUserId: 1,
    status: 'active',
    version: 1,
    snapshot: { id: 'snapshot-1', checksum: 'hash', schemaVersion: '1', createdAt: '2026-07-18T08:00:00Z' },
    draft: { id: 'draft-1', version: 0, currentRevisionId: null, status: 'draft' },
    createdAt: '2026-07-18T08:00:00Z',
  }
}

export async function installProductsMocks(page: Page, audit: TrafficAudit) {
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    if (url.hostname === 'static.userback.io') {
      return route.fulfill({ status: 200, contentType: 'application/javascript', body: 'window.Userback={identify:function(){}}' })
    }
    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      audit.externalRequests.push(`${method} ${url.href}`)
      return route.abort('blockedbyclient')
    }
    if (url.pathname.startsWith('/static/logos/')) return route.fulfill({ status: 200, contentType: 'image/png', body: mockLogo })
    if (!url.pathname.startsWith('/api/')) return route.continue()

    if (url.pathname === '/api/auth/me' && method === 'GET') {
      return json(route, {
        username: 'products-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'products-visual-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me' && method === 'GET') return json(route, { selections: [], rates: [] })
    if (url.pathname === '/api/v2/settings' && method === 'GET') return json(route, {
      woocommerceUrl: '', nextcloudUrl: '', syncIntervalMinutes: 15, timezone: 'UTC',
      currency: 'USD', currencyUnit: 'USD', environment: 'test', wcConfigured: true, ncConfigured: false,
    })
    if (url.pathname === '/api/v2/products/categories' && method === 'GET') return json(route, { items: [] })
    if (url.pathname === '/api/v2/source-profiles/channels' && method === 'GET') {
      return json(route, {
        items: CHANNELS.map(channel => ({
          channelId: channel.channelId,
          name: channel.name,
          connectorType: channel.channelId.split(':')[0],
          capabilityVersion: 'products-visual-v1',
          capabilities: {
            writePrice: true,
            writeStock: true,
            writeStatus: true,
            writeAvailable: true,
            supportedStatuses: ['in_stock', 'low_stock', 'out_of_stock'],
            currency: 'USD',
            unit: 'USD',
          },
          enabled: true,
          implementationState: 'implemented',
          available: true,
        })),
      })
    }
    if (url.pathname === '/api/v2/unified-workspaces/manual' && method === 'POST') {
      return json(route, workspaceResource())
    }
    if (url.pathname === `/api/v2/unified-workspaces/${WORKSPACE_ID}` && method === 'GET') {
      return json(route, workspaceResource())
    }
    if (url.pathname === `/api/v2/unified-workspaces/${WORKSPACE_ID}/grouped-grid` && method === 'GET') {
      return json(route, groupedGridResource())
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

export async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'products-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}
