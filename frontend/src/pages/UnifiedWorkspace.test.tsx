// @vitest-environment jsdom
import { act, forwardRef, useImperativeHandle } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { changeLocale } from '../i18n'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { WorkspaceChannelDefinition, WorkspaceGridPage, WorkspacePreferences } from '../services/unifiedWorkspace/types'
import UnifiedWorkspace from './UnifiedWorkspace'

vi.mock('@handsontable/react-wrapper', () => ({
  HotTable: forwardRef(function MockHotTable(
    props: { afterChange?: (changes: Array<[number, string, unknown, unknown]>, source: string) => void },
    ref,
  ) {
    useImperativeHandle(ref, () => ({
      hotInstance: {
        toPhysicalRow: (row: number) => row,
        getSourceDataAtRow: () => ({ listingId: 'listing-1' }),
      },
    }))
    return (
      <button aria-label="Mock virtualized Workspace Grid" onClick={() => props.afterChange?.([[0, 'woocommerce_primary__price__target', '100', '125']], 'edit')}>
        Virtualized Grid
      </button>
    )
  }),
}))

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(async () => {
  act(() => root.unmount())
  container.remove()
  vi.restoreAllMocks()
  await changeLocale('en')
})

describe('UnifiedWorkspace page', () => {
  it('keeps Grid, Save Draft, Review, Apply ordering and exposes accessible dirty state', async () => {
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={['/workspace/workspace-1']}>
          <ServiceProvider services={services()}>
            <Routes><Route path="/workspace/:workspaceId" element={<UnifiedWorkspace />} /></Routes>
          </ServiceProvider>
        </MemoryRouter>,
      )
    })
    await flush()

    const text = container.textContent ?? ''
    expect(container.querySelector('[aria-label="Mock virtualized Workspace Grid"]')).not.toBeNull()
    expect(text.indexOf('Save Draft')).toBeLessThan(text.indexOf('Review Changes'))
    expect(text.indexOf('Review Changes')).toBeLessThan(text.indexOf('Apply Selected Only'))
    expect(container.textContent).toContain('Draft saved')

    await act(async () => {
      ;(container.querySelector('[aria-label="Mock virtualized Workspace Grid"]') as HTMLButtonElement).click()
    })
    expect(container.textContent).toContain('1 unsaved edit')
    expect(button('Review Changes')?.disabled).toBe(true)
    expect(button('Apply Selected Only')?.disabled).toBe(true)
  })

  it.each([
    ['en', 'ltr'],
    ['fa', 'rtl'],
  ] as const)('renders the same grouped Channel order and safe options in %s (%s)', async (locale, direction) => {
    await changeLocale(locale)
    const grid = gridPage()
    grid.channels = [
      workspaceChannel('digikala:main', 'Digikala', 'coming_soon'),
      workspaceChannel('woocommerce:primary', 'WooCommerce', 'healthy'),
      workspaceChannel('shopify:secondary', 'Shopify Secondary', 'disabled'),
      workspaceChannel('snappshop:main', 'SnappShop', 'warning'),
      workspaceChannel('tapsishop:main', 'TapsiShop', 'healthy'),
    ]

    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={['/workspace/workspace-1']}>
          <ServiceProvider services={services(grid)}>
            <Routes><Route path="/workspace/:workspaceId" element={<UnifiedWorkspace />} /></Routes>
          </ServiceProvider>
        </MemoryRouter>,
      )
    })
    await flush()

    expect(document.documentElement.dir).toBe(direction)
    const sections = Array.from(container.querySelectorAll<HTMLElement>('section[data-resource-section]'))
    expect(sections.map(section => section.dataset.resourceSection)).toEqual(['active', 'disabled', 'comingSoon'])
    const resourceIds = (section: HTMLElement) => Array.from(
      section.querySelectorAll<HTMLElement>(':scope > div > [data-resource-id]'),
      item => item.dataset.resourceId,
    )
    expect(resourceIds(sections[0])).toEqual(['tapsishop:main', 'woocommerce:primary', 'snappshop:main'])
    expect(resourceIds(sections[1])).toEqual(['shopify:secondary'])
    expect(resourceIds(sections[2])).toEqual(['digikala:main'])
    expect(container.textContent).toContain('WooCommerce')
    expect(container.textContent).not.toContain('woocommerce:primary')

    const displayNameSource = container.querySelector('label.fh-channel-toggle select') as HTMLSelectElement
    expect(Array.from(displayNameSource.options).map(option => option.value)).toEqual([
      'canonical',
      'tapsishop:main',
      'woocommerce:primary',
      'snappshop:main',
      'shopify:secondary',
      'digikala:main',
    ])
    expect((displayNameSource.querySelector('option[value="shopify:secondary"]') as HTMLOptionElement).disabled).toBe(true)
    expect((displayNameSource.querySelector('option[value="digikala:main"]') as HTMLOptionElement).disabled).toBe(true)
  })
})

function services(grid = gridPage()): Services {
  const preferences: WorkspacePreferences = {
    visibleChannelIds: ['woocommerce:primary', 'snappshop:main'],
    channelOrder: ['woocommerce:primary', 'snappshop:main'],
    visibleFields: { price: true, stock: true, status: true, sku: true },
    displayNameSource: 'canonical',
    version: 1,
  }
  return {
    unifiedWorkspace: {
      async createManual() { throw new Error('not used') },
      async getWorkspace() {
        return { id: 'workspace-1', name: 'Manual Workspace', entryPoint: 'manual' as const, ownerUserId: 1, status: 'active', version: 1, snapshot: { id: 'snapshot-1', checksum: 'hash', schemaVersion: '1', createdAt: new Date().toISOString() }, draft: { id: 'draft-1', version: 0, currentRevisionId: null, status: 'draft' }, createdAt: new Date().toISOString() }
      },
      async getGrid() { return grid },
      async saveDraft() { return { id: 'revision-1', revisionNumber: 1, checksum: 'rev', draftVersion: 1 } },
      async createReview() { throw new Error('not used') },
      async saveSelection(_id, reviewId, itemIds) {
        return {
          reviewId,
          selectedItemIds: itemIds,
          selectionChecksum: 'a'.repeat(64),
          selectionVersion: 1,
        }
      },
      async applySelected() { throw new Error('not used') },
      async getApply() { throw new Error('not used') },
      async reconcileApply() { throw new Error('not used') },
      async getPreferences() { return preferences },
      async savePreferences(value) { return { ...value, version: value.version + 1 } },
    },
    products: {} as Services['products'], health: {} as Services['health'], sources: {} as Services['sources'],
    workspace: {} as Services['workspace'], settings: {} as Services['settings'], activity: {} as Services['activity'],
    commerce: {} as Services['commerce'], writePipeline: {} as Services['writePipeline'],
  }
}

function workspaceChannel(channelId: string, displayName: string, healthState: string): WorkspaceChannelDefinition {
  return {
    channelId,
    displayName,
    readPrice: true,
    writePrice: true,
    readStock: true,
    writeStock: true,
    readStatus: true,
    writeStatus: true,
    supportsMultipleListings: true,
    maximumBatchSize: 50,
    rateLimitPerMinute: null,
    healthState,
    primaryIdentifierType: 'external_id',
    supportedStatuses: [],
    currency: 'IRR',
    unit: 'IRR',
    writeAvailable: true,
    version: '1',
  }
}

function gridPage(): WorkspaceGridPage {
  return {
    total: 1, page: 1, pageSize: 500, draftVersion: 0, revisionId: null,
    channels: [
      { channelId: 'woocommerce:primary', readPrice: true, writePrice: true, readStock: true, writeStock: false, readStatus: true, writeStatus: false, supportsMultipleListings: false, maximumBatchSize: 100, rateLimitPerMinute: null, healthState: 'configured', primaryIdentifierType: 'woocommerce_product_id', supportedStatuses: [], currency: 'EUR', unit: 'EUR', writeAvailable: true, version: '1' },
      { channelId: 'snappshop:main', readPrice: true, writePrice: true, readStock: true, writeStock: true, readStatus: true, writeStatus: false, supportsMultipleListings: true, maximumBatchSize: 50, rateLimitPerMinute: null, healthState: 'configured', primaryIdentifierType: 'snappshop_product_number', supportedStatuses: [], currency: 'IRR', unit: 'TOMAN', writeAvailable: true, version: '1' },
    ],
    items: [{ rowId: 'row-1', canonicalProductId: 'product-1', canonicalName: 'Product', productType: 'simple', listingId: 'listing-1', listingLabel: 'Listing', channelId: 'woocommerce:primary', externalPrimaryId: '101', externalIdType: 'product_id', sku: 'SKU', mappingState: 'resolved', mappingVersion: 1, fields: {
      price: { current: '100', target: '100', status: 'unchanged', readOnly: false, currency: 'EUR', unit: 'EUR' },
      stock: { current: '5', target: '5', status: 'read_only', readOnly: true, currency: null, unit: null },
      status: { current: 'publish', target: 'publish', status: 'read_only', readOnly: true, currency: null, unit: null },
    } }],
  }
}

function button(label: string): HTMLButtonElement | null {
  return [...container.querySelectorAll('button')].find(item => item.textContent?.includes(label)) ?? null
}

async function flush() {
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0))
  })
}
