// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceChannel, SourceMapping, SourceProfile } from '../features/sourceWorkspace/types'
import { changeLocale } from '../i18n'
import { NotificationProvider } from '../notifications/NotificationProvider'
import SourceConfiguration from './SourceConfiguration'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const channels: SourceChannel[] = [
  { channelId: 'woocommerce:primary', name: 'WooCommerce Primary', connectorType: 'woocommerce', capabilityVersion: '1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
  { channelId: 'snappshop:main', name: 'SnappShop Main', connectorType: 'snappshop', capabilityVersion: '1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
  { channelId: 'tapsishop:main', name: 'TapsiShop Main', connectorType: 'tapsishop', capabilityVersion: '1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
  { channelId: 'digikala:main', name: 'Digikala', connectorType: 'digikala', capabilityVersion: 'none', capabilities: {}, enabled: false, implementationState: 'coming_soon', available: false },
]

const mapping: SourceMapping = {
  id: 'mapping-1',
  version: 1,
  checksum: 'a'.repeat(64),
  worksheetMode: 'selected',
  worksheetName: 'Sheet1',
  dataStartRow: 2,
  valuePolicy: {},
  sourceFields: [{ field: 'name', referenceType: 'column_letter', referenceValue: 'A', required: true }],
  channels: [
    {
      channelId: 'woocommerce:primary',
      worksheetName: null,
      enabled: true,
      fields: [
        { field: 'external_id', referenceType: 'column_letter', referenceValue: 'B' },
        { field: 'price', referenceType: 'column_letter', referenceValue: 'C' },
        { field: 'stock', referenceType: 'column_letter', referenceValue: 'D' },
        { field: 'status', referenceType: 'disabled', referenceValue: null },
      ],
    },
    {
      channelId: 'snappshop:main',
      worksheetName: null,
      enabled: true,
      fields: [
        { field: 'external_id', referenceType: 'column_letter', referenceValue: 'O' },
        { field: 'price', referenceType: 'header_name', referenceValue: 'قیمت اسنپ' },
        { field: 'stock', referenceType: 'disabled', referenceValue: null },
        { field: 'status', referenceType: 'disabled', referenceValue: null },
      ],
    },
  ],
}

const source: SourceProfile & { mapping: SourceMapping | null } = {
  id: 'source-1',
  name: 'Daily prices',
  sourceKind: 'flowhub_sheet',
  externalSourceId: null,
  worksheetMode: 'selected',
  worksheetName: 'Sheet1',
  dataStartRow: 2,
  status: 'active',
  version: 2,
  mappingVersion: 1,
  sheetId: 'sheet-1',
  mapping,
}

async function renderPage() {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/sources/source-1']}>
        <NotificationProvider>
          <Routes>
            <Route path="/sources/:sourceId" element={<SourceConfiguration />} />
          </Routes>
        </NotificationProvider>
      </MemoryRouter>,
    )
    await Promise.resolve()
    await Promise.resolve()
  })
}

function button(text: string): HTMLButtonElement {
  const item = Array.from(container.querySelectorAll('button')).find(node => node.textContent?.includes(text))
  expect(item).toBeTruthy()
  return item as HTMLButtonElement
}

describe('SourceConfiguration per-Channel mappings', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    vi.spyOn(sourceWorkspaceApi, 'source').mockResolvedValue(source)
    vi.spyOn(sourceWorkspaceApi, 'channels').mockResolvedValue({ items: channels })
    vi.spyOn(sourceWorkspaceApi, 'saveMapping').mockResolvedValue(mapping)
  })

  afterEach(async () => {
    act(() => root.unmount())
    container.remove()
    vi.restoreAllMocks()
    await changeLocale('en')
  })

  it('renders dynamic friendly Channel sections and keeps unavailable Channels disabled', async () => {
    await renderPage()
    expect(container.textContent).toContain('WooCommerce — Primary')
    expect(container.textContent).toContain('SnappShop — Main')
    expect(container.textContent).toContain('TapsiShop — Main')
    expect(container.textContent).not.toContain('woocommerce:primary')
    expect(container.textContent).toContain('Coming Soon')
    const digikala = Array.from(container.querySelectorAll('details')).find(item => item.textContent?.includes('Digikala'))
    expect(digikala?.querySelector('input[type="checkbox"]')).toHaveProperty('disabled', true)
    expect(container.textContent).toContain('Column letter')
    expect(container.textContent).toContain('Exact header')
    expect(container.textContent).toContain('Internal column ID')
  })

  it('preserves technical Channel identities in the API payload and supports explicit enablement', async () => {
    await renderPage()
    const tapsi = Array.from(container.querySelectorAll('details')).find(item => item.textContent?.includes('TapsiShop'))
    const checkbox = tapsi?.querySelector('input[type="checkbox"]') as HTMLInputElement
    await act(async () => checkbox.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    await act(async () => {
      button('Save Mapping Revision').dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })
    const payload = vi.mocked(sourceWorkspaceApi.saveMapping).mock.calls[0][1] as {
      channel_mappings: Array<{ channel_id: string; enabled: boolean }>
    }
    expect(payload.channel_mappings.map(item => item.channel_id)).toEqual([
      'woocommerce:primary',
      'snappshop:main',
      'tapsishop:main',
    ])
    expect(payload.channel_mappings.find(item => item.channel_id === 'tapsishop:main')?.enabled).toBe(true)
  })

  it('shows Price and Stock in Persian without translating technical values', async () => {
    await changeLocale('fa')
    await renderPage()
    expect(container.textContent).toContain('قیمت')
    expect(container.textContent).toContain('موجودی')
    expect(container.textContent).toContain('WooCommerce')
  })

  it('previews each Channel using only its independently resolved values', async () => {
    vi.spyOn(sourceWorkspaceApi, 'previewSource').mockResolvedValue({
      recognized: 1,
      ignored: 0,
      issues: [],
      items: [{
        rowKey: 'row-1',
        rowNumber: 2,
        recognized: true,
        sourceProduct: { name: 'iPhone Cable' },
        channels: [
          { channelId: 'woocommerce:primary', fields: { external_id: '51550', price: '12500000', stock: '8', status: null } },
          { channelId: 'snappshop:main', fields: { external_id: '1826345203', price: '12900000', stock: null, status: null } },
          { channelId: 'tapsishop:main', fields: { external_id: '7785746738', price: '12700000', stock: null, status: null } },
        ],
      }],
    })
    await renderPage()
    await act(async () => {
      button('Preview recognized rows').dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })
    expect(container.textContent).toContain('51550')
    expect(container.textContent).toContain('12500000')
    expect(container.textContent).toContain('1826345203')
    expect(container.textContent).toContain('12900000')
    expect(container.textContent).toContain('7785746738')
    expect(container.textContent).toContain('12700000')
  })
})
