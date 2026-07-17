// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceChannel, SourceMapping, SourceProfile } from '../features/sourceWorkspace/types'
import { changeLocale, translate } from '../i18n'
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

const emptyPreview = {
  total: 0,
  recognized: 0,
  ignored: 0,
  issues: [],
  businessSummary: { productsFound: 0, productsReady: 0, priceChanges: null, stockChanges: null, unchanged: null, needsAttention: 0, channelsReady: 0, channelsNotConfigured: 0 },
  sheetRevisionId: 'revision-1',
  mappingRevisionId: null,
  items: [],
}

function button(text: string): HTMLButtonElement {
  const item = Array.from(container.querySelectorAll('button')).find(node => node.textContent?.includes(text))
  expect(item).toBeTruthy()
  return item as HTMLButtonElement
}

async function previewThenSave() {
  await act(async () => {
    button('Preview recognized rows').click()
    await Promise.resolve()
  })
  await act(async () => {
    button('Save column setup').click()
    await Promise.resolve()
  })
}

describe('SourceConfiguration per-Channel mappings', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    vi.spyOn(sourceWorkspaceApi, 'source').mockResolvedValue(source)
    vi.spyOn(sourceWorkspaceApi, 'channels').mockResolvedValue({ items: channels })
    vi.spyOn(sourceWorkspaceApi, 'saveMapping').mockResolvedValue(mapping)
    vi.spyOn(sourceWorkspaceApi, 'previewUnsavedMapping').mockResolvedValue(emptyPreview)
  })

  afterEach(async () => {
    act(() => root.unmount())
    container.remove()
    vi.restoreAllMocks()
    await changeLocale('en')
  })

  it('renders dynamic friendly Channel sections and keeps unavailable Channels disabled', async () => {
    await renderPage()
    expect(container.textContent).toContain('WooCommerce Primary')
    expect(container.textContent).toContain('SnappShop Main')
    expect(container.textContent).toContain('TapsiShop Main')
    expect(container.textContent).not.toContain('woocommerce:primary')
    expect(container.textContent).toContain('Coming Soon')
    const digikala = container.querySelector('details[data-channel-id="digikala:main"]')
    expect(digikala?.querySelector('input[type="checkbox"]')).toHaveProperty('disabled', true)
    expect(container.textContent).toContain('Column letter')
    expect(container.textContent).toContain('Exact header')
    expect(container.textContent).toContain('FlowHub Sheet column')
  })

  it.each([
    ['en', 'ltr'],
    ['fa', 'rtl'],
  ] as const)('uses the same grouped Channel order in %s (%s)', async (locale, direction) => {
    await changeLocale(locale)
    vi.mocked(sourceWorkspaceApi.channels).mockResolvedValue({
      items: [
        channels[3],
        channels[0],
        { channelId: 'shopify:secondary', name: 'Shopify Secondary', connectorType: 'shopify', capabilityVersion: '1', capabilities: {}, enabled: false, implementationState: 'implemented', available: true },
        channels[2],
        channels[1],
      ],
    })

    await renderPage()

    expect(document.documentElement.dir).toBe(direction)
    const sections = Array.from(container.querySelectorAll<HTMLElement>('section[data-resource-section]'))
    expect(sections.map(section => section.dataset.resourceSection)).toEqual(['active', 'disabled', 'comingSoon'])
    const resourceIds = (section: HTMLElement) => Array.from(
      section.querySelectorAll<HTMLElement>(':scope > div > [data-resource-id]'),
      item => item.dataset.resourceId,
    )
    expect(resourceIds(sections[0])).toEqual(['snappshop:main', 'tapsishop:main', 'woocommerce:primary'])
    expect(resourceIds(sections[1])).toEqual(['shopify:secondary'])
    expect(resourceIds(sections[2])).toEqual(['digikala:main'])
    expect(container.textContent).toContain('WooCommerce')
    expect(container.textContent).toContain('SnappShop')
    expect(container.textContent).not.toContain('woocommerce:primary')
  })

  it('preserves technical Channel identities in the API payload and supports explicit enablement', async () => {
    await renderPage()
    const tapsi = container.querySelector('details[data-channel-id="tapsishop:main"]')
    const checkbox = tapsi?.querySelector('input[type="checkbox"]') as HTMLInputElement
    await act(async () => checkbox.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    await previewThenSave()
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
    const localizedPriceReference = translate('sources:sourceConfiguration.referenceType', { field: translate('common:field.price') })
    expect(container.querySelector(`[aria-label="${localizedPriceReference}"]`)).not.toBeNull()
    expect(container.querySelector('[aria-label*="external_id"]')).toBeNull()
  })

  it('uses localized field names in conflicting-column guidance', async () => {
    const conflicting: SourceMapping = {
      ...mapping,
      channels: mapping.channels.map(channel => channel.channelId === 'woocommerce:primary'
        ? { ...channel, fields: channel.fields.map(field => field.field === 'stock' ? { ...field, referenceValue: 'C' } : field) }
        : channel),
    }
    vi.mocked(sourceWorkspaceApi.source).mockResolvedValue({ ...source, mapping: conflicting })
    await renderPage()
    expect(container.textContent).toContain('Price and Stock use the same column')
    expect(container.textContent).not.toContain('price and stock use the same column')
  })

  it('previews each Channel using only its independently resolved values', async () => {
    vi.mocked(sourceWorkspaceApi.previewUnsavedMapping).mockResolvedValue({
      total: 1,
      recognized: 1,
      ignored: 0,
      issues: [],
      businessSummary: { productsFound: 1, productsReady: 1, priceChanges: null, stockChanges: null, unchanged: null, needsAttention: 0, channelsReady: 3, channelsNotConfigured: 0 },
      sheetRevisionId: 'revision-1',
      mappingRevisionId: 'mapping-1',
      items: [{
        rowKey: 'row-1',
        rowNumber: 2,
        worksheetName: 'Pricing',
        recognized: true,
        hasIssues: false,
        ready: true,
        sourceProduct: { name: 'iPhone Cable' },
        valuePolicy: {},
        channels: [
          { channelId: 'woocommerce:primary', fields: { external_id: '51550', price: '12500000', stock: '8', status: null } },
          { channelId: 'snappshop:main', fields: { external_id: '1826345203', price: '12900000', stock: null, status: null } },
          { channelId: 'tapsishop:main', fields: { external_id: '7785746738', price: '12700000', stock: null, status: null } },
        ],
        issues: [],
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

  it('uses backend issue-aware readiness and distinguishes equal row numbers across worksheets', async () => {
    vi.mocked(sourceWorkspaceApi.previewUnsavedMapping).mockResolvedValue({
      total: 2,
      recognized: 2,
      ignored: 0,
      issues: [{ category: 'missing_channel_worksheet', severity: 'blocked', channelId: 'snappshop:main', count: 1 }],
      businessSummary: { productsFound: 2, productsReady: 1, priceChanges: null, stockChanges: null, unchanged: null, needsAttention: 1, channelsReady: 2, channelsNotConfigured: 0 },
      sheetRevisionId: 'external:snapshot:1',
      mappingRevisionId: 'mapping-1',
      items: [
        {
          rowKey: 'external:Retail:2', rowNumber: 2, worksheetName: 'Retail', recognized: true, hasIssues: false, ready: true,
          sourceProduct: { name: 'Ready cable' }, channels: [{ channelId: 'woocommerce:primary', fields: { external_id: 'wc-1', price: '100' } }], valuePolicy: {}, issues: [],
        },
        {
          rowKey: 'external:Wholesale:2', rowNumber: 2, worksheetName: 'Wholesale', recognized: true, hasIssues: true, ready: false,
          sourceProduct: { name: 'Needs attention cable' }, channels: [{ channelId: 'woocommerce:primary', fields: { external_id: 'wc-2', price: '200' } }],
          valuePolicy: {},
          issues: [{ category: 'missing_channel_worksheet', severity: 'blocked', channelId: 'snappshop:main', message: 'The selected worksheet is missing.' }],
        },
      ],
    })
    await renderPage()
    await act(async () => { button('Preview recognized rows').click(); await Promise.resolve() })
    expect(container.textContent).toContain('Retail')
    await act(async () => button('Next sample row').click())
    expect(container.textContent).toContain('Wholesale')

    await act(async () => button('Products ready').click())
    expect(container.textContent).toContain('Ready cable')
    expect(container.textContent).not.toContain('Needs attention cable')

    await act(async () => button('Products needing attention').click())
    expect(container.textContent).not.toContain('Ready cable')
    expect(container.textContent).toContain('Needs attention cable')
  })

  it('renders independent rules for differently laid out worksheets and saves their stable names', async () => {
    const perWorksheet: SourceMapping = {
      ...mapping,
      worksheetRuleMode: 'per_worksheet',
      duplicateProductPolicy: 'block',
      worksheetRules: [
        { worksheetName: 'فروش تهران', enabled: true, dataStartRow: 3, valuePolicy: {}, sourceFields: [{ field: 'name', referenceType: 'column_letter', referenceValue: 'A', required: true }], channels: [{ channelId: 'woocommerce:primary', worksheetName: 'فروش تهران', enabled: true, fields: [{ field: 'external_id', referenceType: 'column_letter', referenceValue: 'B' }, { field: 'price', referenceType: 'column_letter', referenceValue: 'C' }, { field: 'stock', referenceType: 'disabled', referenceValue: null }, { field: 'status', referenceType: 'disabled', referenceValue: null }] }] },
        { worksheetName: 'Marketplace', enabled: true, dataStartRow: 6, valuePolicy: {}, sourceFields: [{ field: 'name', referenceType: 'column_letter', referenceValue: 'D', required: true }], channels: [{ channelId: 'snappshop:main', worksheetName: 'Marketplace', enabled: true, fields: [{ field: 'external_id', referenceType: 'column_letter', referenceValue: 'E' }, { field: 'price', referenceType: 'column_letter', referenceValue: 'G' }, { field: 'stock', referenceType: 'disabled', referenceValue: null }, { field: 'status', referenceType: 'disabled', referenceValue: null }] }] },
      ],
    }
    vi.mocked(sourceWorkspaceApi.source).mockResolvedValue({ ...source, mapping: perWorksheet })
    await renderPage()
    expect(container.textContent).toContain('فروش تهران')
    expect(container.textContent).toContain('Marketplace')
    expect(container.textContent).toContain('Configure each worksheet separately')
    await previewThenSave()
    const calls = vi.mocked(sourceWorkspaceApi.saveMapping).mock.calls
    const payload = calls[calls.length - 1]?.[1] as { worksheet_rule_mode: string; worksheet_rules: Array<{ worksheet_name: string; data_start_row: number; channel_mappings: Array<{ channel_id: string; fields: Array<{ field: string; reference_value: string | null }> }> }> }
    expect(payload.worksheet_rule_mode).toBe('per_worksheet')
    expect(payload.worksheet_rules.map(item => item.worksheet_name)).toEqual(['فروش تهران', 'Marketplace'])
    expect(payload.worksheet_rules[0].channel_mappings[0].fields.find(item => item.field === 'price')?.reference_value).toBe('C')
    expect(payload.worksheet_rules[1].channel_mappings[0].fields.find(item => item.field === 'price')?.reference_value).toBe('G')
  })

  it('shows the shared Product Name only once per worksheet and copies it only after explicit confirmation', async () => {
    const perWorksheet: SourceMapping = {
      ...mapping,
      worksheetRuleMode: 'per_worksheet',
      duplicateProductPolicy: 'block',
      worksheetRules: [
        { worksheetName: 'Logitech', enabled: true, dataStartRow: 2, valuePolicy: {}, sourceFields: [{ field: 'name', referenceType: 'column_letter', referenceValue: 'A', required: true }], channels: [{ channelId: 'woocommerce:primary', worksheetName: 'Logitech', enabled: true, fields: [{ field: 'external_id', referenceType: 'column_letter', referenceValue: 'D' }, { field: 'price', referenceType: 'column_letter', referenceValue: 'B' }, { field: 'stock', referenceType: 'column_letter', referenceValue: 'C' }, { field: 'status', referenceType: 'disabled', referenceValue: null }] }] },
        { worksheetName: 'Surface', enabled: true, dataStartRow: 4, valuePolicy: {}, sourceFields: [{ field: 'name', referenceType: 'column_letter', referenceValue: 'K', required: true }], channels: [{ channelId: 'woocommerce:primary', worksheetName: 'Surface', enabled: true, fields: [{ field: 'external_id', referenceType: 'column_letter', referenceValue: 'N' }, { field: 'price', referenceType: 'column_letter', referenceValue: 'L' }, { field: 'stock', referenceType: 'column_letter', referenceValue: 'M' }, { field: 'status', referenceType: 'disabled', referenceValue: null }] }] },
      ],
    }
    vi.mocked(sourceWorkspaceApi.source).mockResolvedValue({ ...source, mapping: perWorksheet })
    await renderPage()

    const productNameReference = translate('sources:sourceConfiguration.columnReference', { field: translate('sources:sourceConfiguration.sourceProductName') })
    const worksheetEditors = Array.from(container.querySelectorAll<HTMLDetailsElement>('details[data-worksheet-rule]'))
    expect(worksheetEditors).toHaveLength(2)
    for (const editor of worksheetEditors) expect(editor.querySelectorAll(`[aria-label="${productNameReference}"]`)).toHaveLength(1)

    const surfaceEditor = worksheetEditors.find(editor => editor.textContent?.includes('Surface')) as HTMLDetailsElement
    const surfaceProductName = surfaceEditor.querySelector(`[aria-label="${productNameReference}"]`) as HTMLInputElement
    expect(surfaceProductName.value).toBe('K')

    const logitechEditor = worksheetEditors.find(editor => editor.textContent?.includes('Logitech')) as HTMLDetailsElement
    const copyShared = Array.from(logitechEditor.querySelectorAll('button')).find(item => item.textContent?.includes('Copy shared product fields')) as HTMLButtonElement
    await act(async () => copyShared.click())
    const dialog = container.querySelector('[role="dialog"]') as HTMLElement
    expect(dialog.textContent).toContain('Logitech')
    expect(surfaceProductName.value).toBe('K')
    const confirm = Array.from(dialog.querySelectorAll('button')).find(item => item.textContent?.includes('Confirm copy')) as HTMLButtonElement
    await act(async () => confirm.click())
    expect(surfaceProductName.value).toBe('A')
  })

  it('copies Channel columns only after confirmation and preserves the destination Channel identity', async () => {
    const perWorksheet: SourceMapping = {
      ...mapping,
      worksheetRuleMode: 'per_worksheet',
      duplicateProductPolicy: 'block',
      worksheetRules: [{
        worksheetName: 'Logitech',
        enabled: true,
        dataStartRow: 2,
        valuePolicy: {},
        sourceFields: [{ field: 'name', referenceType: 'column_letter', referenceValue: 'A', required: true }],
        channels: [
          { channelId: 'woocommerce:primary', worksheetName: 'Logitech', enabled: true, fields: [{ field: 'external_id', referenceType: 'column_letter', referenceValue: 'D' }, { field: 'price', referenceType: 'column_letter', referenceValue: 'B' }, { field: 'stock', referenceType: 'column_letter', referenceValue: 'C' }, { field: 'status', referenceType: 'disabled', referenceValue: null }] },
          { channelId: 'snappshop:main', worksheetName: 'Logitech', enabled: true, fields: [{ field: 'external_id', referenceType: 'column_letter', referenceValue: 'G' }, { field: 'price', referenceType: 'column_letter', referenceValue: 'E' }, { field: 'stock', referenceType: 'column_letter', referenceValue: 'F' }, { field: 'status', referenceType: 'disabled', referenceValue: null }] },
        ],
      }],
    }
    vi.mocked(sourceWorkspaceApi.source).mockResolvedValue({ ...source, mapping: perWorksheet })
    await renderPage()

    const snapp = container.querySelector('[data-worksheet-rule="Logitech"] [data-channel-rule="snappshop:main"]') as HTMLDetailsElement
    const priceInput = snapp.querySelector('[aria-label="Price column reference"]') as HTMLInputElement
    expect(priceInput.value).toBe('E')
    const sourceChannel = Array.from(snapp.querySelectorAll('label')).find(label => label.textContent?.includes('Copy columns from another Channel'))?.querySelector('select') as HTMLSelectElement
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set?.call(sourceChannel, 'woocommerce:primary')
      sourceChannel.dispatchEvent(new Event('change', { bubbles: true }))
    })
    const requestCopy = Array.from(snapp.querySelectorAll('button')).find(item => item.textContent?.includes('Copy column choices')) as HTMLButtonElement
    await act(async () => requestCopy.click())
    expect(priceInput.value).toBe('E')
    const dialog = container.querySelector('[role="dialog"]') as HTMLElement
    expect(dialog.textContent).toContain('WooCommerce')
    expect(dialog.textContent).toContain('SnappShop')
    await act(async () => (Array.from(dialog.querySelectorAll('button')).find(item => item.textContent?.includes('Confirm copy')) as HTMLButtonElement).click())
    expect(priceInput.value).toBe('B')

    await previewThenSave()
    const calls = vi.mocked(sourceWorkspaceApi.saveMapping).mock.calls
    const payload = calls[calls.length - 1]?.[1] as { worksheet_rules: Array<{ channel_mappings: Array<{ channel_id: string; fields: Array<{ field: string; reference_value: string | null }> }> }> }
    const savedSnapp = payload.worksheet_rules[0].channel_mappings.find(item => item.channel_id === 'snappshop:main')
    expect(savedSnapp?.fields.find(item => item.field === 'price')?.reference_value).toBe('B')
  })

  it('copies one Channel configuration to selected worksheets only after confirmation', async () => {
    const perWorksheet: SourceMapping = {
      ...mapping,
      worksheetRuleMode: 'per_worksheet',
      duplicateProductPolicy: 'block',
      worksheetRules: [
        { worksheetName: 'Logitech', enabled: true, dataStartRow: 2, valuePolicy: {}, sourceFields: [{ field: 'name', referenceType: 'column_letter', referenceValue: 'A', required: true }], channels: [{ channelId: 'woocommerce:primary', worksheetName: 'Logitech', enabled: true, fields: [{ field: 'external_id', referenceType: 'column_letter', referenceValue: 'D' }, { field: 'price', referenceType: 'column_letter', referenceValue: 'B' }, { field: 'stock', referenceType: 'column_letter', referenceValue: 'C' }, { field: 'status', referenceType: 'disabled', referenceValue: null }] }] },
        { worksheetName: 'Surface', enabled: true, dataStartRow: 4, valuePolicy: {}, sourceFields: [{ field: 'name', referenceType: 'column_letter', referenceValue: 'K', required: true }], channels: [{ channelId: 'woocommerce:primary', worksheetName: 'Surface', enabled: true, fields: [{ field: 'external_id', referenceType: 'column_letter', referenceValue: 'N' }, { field: 'price', referenceType: 'column_letter', referenceValue: 'L' }, { field: 'stock', referenceType: 'column_letter', referenceValue: 'M' }, { field: 'status', referenceType: 'disabled', referenceValue: null }] }] },
      ],
    }
    vi.mocked(sourceWorkspaceApi.source).mockResolvedValue({ ...source, mapping: perWorksheet })
    await renderPage()

    const logitechWoo = container.querySelector('[data-worksheet-rule="Logitech"] [data-channel-rule="woocommerce:primary"]') as HTMLDetailsElement
    const surfaceWoo = container.querySelector('[data-worksheet-rule="Surface"] [data-channel-rule="woocommerce:primary"]') as HTMLDetailsElement
    const surfacePrice = surfaceWoo.querySelector('[aria-label="Price column reference"]') as HTMLInputElement
    expect(surfacePrice.value).toBe('L')
    const copyToWorksheets = Array.from(logitechWoo.querySelectorAll('button')).find(item => item.textContent?.includes('Copy to worksheets')) as HTMLButtonElement
    await act(async () => copyToWorksheets.click())
    expect(surfacePrice.value).toBe('L')
    const dialog = container.querySelector('[role="dialog"]') as HTMLElement
    expect(dialog.textContent).toContain('Source worksheet: Logitech')
    expect(dialog.textContent).toContain('Surface')
    await act(async () => (Array.from(dialog.querySelectorAll('button')).find(item => item.textContent?.includes('Confirm copy')) as HTMLButtonElement).click())
    expect(surfacePrice.value).toBe('B')
  })

  it('supports bulk enable and ignore actions without expanding every worksheet', async () => {
    const perWorksheet: SourceMapping = {
      ...mapping,
      worksheetRuleMode: 'per_worksheet',
      duplicateProductPolicy: 'block',
      worksheetRules: [
        { worksheetName: 'Logitech', enabled: true, dataStartRow: 2, valuePolicy: {}, sourceFields: [{ field: 'name', referenceType: 'column_letter', referenceValue: 'A', required: true }], channels: [] },
        { worksheetName: 'Surface', enabled: false, dataStartRow: 2, valuePolicy: {}, sourceFields: [{ field: 'name', referenceType: 'column_letter', referenceValue: 'A', required: true }], channels: [] },
      ],
    }
    vi.mocked(sourceWorkspaceApi.source).mockResolvedValue({ ...source, mapping: perWorksheet })
    await renderPage()
    expect(Array.from(container.querySelectorAll<HTMLDetailsElement>('details[data-worksheet-rule]')).filter(item => item.open)).toHaveLength(1)
    await act(async () => button('Select all').click())
    await act(async () => button('Enable selected').click())
    const surfaceEditor = container.querySelector('details[data-worksheet-rule="Surface"]') as HTMLDetailsElement
    expect(surfaceEditor.textContent).toContain('Needs column settings')
    await act(async () => button('Ignore selected').click())
    expect(surfaceEditor.textContent).toContain('Ignored')
  })

  it('creates one independent rule for every selected worksheet when shared rules are split', async () => {
    vi.spyOn(sourceWorkspaceApi, 'worksheets').mockResolvedValue({
      sourceId: source.id,
      sourceRevisionId: 'revision-1',
      items: [
        { name: 'Logitech', rowCount: 261 },
        { name: 'Surface', rowCount: 396 },
      ],
    })
    await renderPage()
    await act(async () => { button('Detect worksheets').click(); await Promise.resolve() })

    const separateMode = container.querySelector('input[name="worksheet-rule-mode"][value="per_worksheet"]') as HTMLInputElement
    await act(async () => separateMode.click())

    const worksheetEditors = Array.from(container.querySelectorAll<HTMLDetailsElement>('details[data-worksheet-rule]'))
    expect(worksheetEditors.map(editor => editor.dataset.worksheetRule)).toEqual(['Logitech', 'Surface'])
    const productNameReference = translate('sources:sourceConfiguration.columnReference', { field: translate('sources:sourceConfiguration.sourceProductName') })
    for (const editor of worksheetEditors) {
      const productNameInputs = editor.querySelectorAll<HTMLInputElement>(`[aria-label="${productNameReference}"]`)
      expect(productNameInputs).toHaveLength(1)
      expect(productNameInputs[0].value).toBe('A')
      expect(editor.querySelector('[data-channel-rule="woocommerce:primary"] [aria-label="Price column reference"]')).toHaveProperty('value', 'C')
      expect(editor.querySelector('[data-channel-rule="snappshop:main"] [aria-label="Price column reference"]')).toHaveProperty('value', 'قیمت اسنپ')
    }
  })

  it('shows a sticky dirty state and warns before closing unsaved column changes', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await renderPage()
    const dataStartInput = Array.from(container.querySelectorAll('label')).find(label => label.textContent?.includes('Data starts at row'))?.querySelector('input') as HTMLInputElement
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(dataStartInput, '3')
      dataStartInput.dispatchEvent(new Event('input', { bubbles: true }))
      await Promise.resolve()
    })
    const actionBar = container.querySelector('[data-testid="source-configuration-actions"]') as HTMLElement
    expect(actionBar.textContent).toContain('Unsaved changes')
    await act(async () => button('Close').click())
    expect(confirm).toHaveBeenCalledWith('Close without saving your column changes?')
  })

  it('applies one shared configuration only to the explicitly selected worksheets', async () => {
    vi.mocked(sourceWorkspaceApi.source).mockResolvedValue({
      ...source,
      mapping: { ...mapping, worksheetName: null, selectedWorksheetNames: ['تهران', 'شیراز'] },
    })
    vi.spyOn(sourceWorkspaceApi, 'worksheets').mockResolvedValue({
      sourceId: source.id,
      sourceRevisionId: 'revision-1',
      items: [
        { name: 'تهران', rowCount: 20 },
        { name: 'شیراز', rowCount: 15 },
        { name: 'یادداشت‌ها', rowCount: 4 },
      ],
    })
    await renderPage()
    await act(async () => { button('Detect worksheets').click(); await Promise.resolve() })

    const worksheetCheckbox = (name: string) => Array.from(container.querySelectorAll('label'))
      .find(label => label.textContent?.includes(name))
      ?.querySelector('input[type="checkbox"]') as HTMLInputElement
    expect(worksheetCheckbox('تهران').checked).toBe(true)
    expect(worksheetCheckbox('شیراز').checked).toBe(true)
    expect(worksheetCheckbox('یادداشت‌ها').checked).toBe(false)

    await previewThenSave()
    const calls = vi.mocked(sourceWorkspaceApi.saveMapping).mock.calls
    const payload = calls[calls.length - 1]?.[1] as { selected_worksheet_names: string[]; worksheet_name: string | null }
    expect(payload.selected_worksheet_names).toEqual(['تهران', 'شیراز'])
    expect(payload.worksheet_name).toBeNull()
  })

  it('associates a required product-name error with the per-worksheet column controls', async () => {
    const perWorksheet: SourceMapping = {
      ...mapping,
      worksheetRuleMode: 'per_worksheet',
      duplicateProductPolicy: 'block',
      worksheetRules: [{
        worksheetName: 'Missing product name',
        enabled: true,
        dataStartRow: 2,
        valuePolicy: {},
        sourceFields: [{ field: 'name', referenceType: 'disabled', referenceValue: null, required: true }],
        channels: [],
      }],
    }
    vi.mocked(sourceWorkspaceApi.source).mockResolvedValue({ ...source, mapping: perWorksheet })
    await renderPage()

    const accessibleName = translate('sources:sourceConfiguration.referenceType', { field: translate('sources:sourceConfiguration.sourceProductName') })
    const worksheetEditor = container.querySelector('details[data-worksheet-rule="Missing product name"]') as HTMLDetailsElement
    const selector = worksheetEditor.querySelector(`[aria-label="${accessibleName}"]`) as HTMLSelectElement
    const error = worksheetEditor.querySelector('[role="alert"]') as HTMLElement
    expect(selector.getAttribute('aria-invalid')).toBe('true')
    expect(selector.getAttribute('aria-describedby')).toBe(error.id)
    expect(error.textContent).toContain('Choose the product-name column')
    const saveButtons = Array.from(container.querySelectorAll('button')).filter(item => item.textContent?.includes('Save column setup')) as HTMLButtonElement[]
    expect(saveButtons[saveButtons.length - 1].disabled).toBe(true)
  })

  it('previews the current unsaved payload before enabling Save', async () => {
    vi.mocked(sourceWorkspaceApi.source).mockResolvedValue({ ...source, mapping: null, mappingVersion: 0 })
    await renderPage()

    const saveButton = button('Save column setup')
    expect(saveButton.disabled).toBe(true)
    expect(sourceWorkspaceApi.saveMapping).not.toHaveBeenCalled()

    await act(async () => {
      button('Preview recognized rows').click()
      await Promise.resolve()
    })

    expect(sourceWorkspaceApi.previewUnsavedMapping).toHaveBeenCalledTimes(1)
    const payload = vi.mocked(sourceWorkspaceApi.previewUnsavedMapping).mock.calls[0][1] as {
      expected_source_version: number
      channel_mappings: Array<{ channel_id: string }>
    }
    expect(payload.expected_source_version).toBe(source.version)
    expect(payload.channel_mappings).toEqual([])
    expect(saveButton.disabled).toBe(false)
  })
})
