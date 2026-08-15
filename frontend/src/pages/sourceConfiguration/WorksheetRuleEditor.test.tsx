// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SourceChannel, SourceWorksheetRule } from '../../features/sourceWorkspace/types'
import { changeLocale } from '../../i18n'
import WorksheetRuleEditor, { requiredChannelMappingFields, smartInputDisplayValue } from './WorksheetRuleEditor'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const CHANNELS: SourceChannel[] = [
  { channelId: 'digikala:main', name: 'Digikala', connectorType: 'digikala', capabilityVersion: 'none', capabilities: {}, enabled: false, implementationState: 'coming_soon', available: false },
  { channelId: 'woocommerce:primary', name: 'WooCommerce Primary', connectorType: 'woocommerce', capabilityVersion: '1', capabilities: { mappingRequiredFields: ['external_id'] }, enabled: true, implementationState: 'implemented', available: true },
  { channelId: 'shopify:secondary', name: 'Shopify Secondary', connectorType: 'shopify', capabilityVersion: '1', capabilities: { mappingRequiredFields: [] }, enabled: false, implementationState: 'implemented', available: true },
  { channelId: 'tapsishop:main', name: 'TapsiShop Main', connectorType: 'tapsishop', capabilityVersion: '1', capabilities: { mappingRequiredFields: ['external_id', 'stock', 'status'] }, enabled: true, implementationState: 'implemented', available: true },
  { channelId: 'snappshop:main', name: 'SnappShop Main', connectorType: 'snappshop', capabilityVersion: '1', capabilities: { mappingRequiredFields: ['external_id', 'stock', 'status'] }, enabled: true, implementationState: 'implemented', available: true },
]

const RULE: SourceWorksheetRule = {
  worksheetName: 'Pricing',
  enabled: true,
  dataStartRow: 2,
  valuePolicy: {},
  sourceFields: [{ field: 'name', referenceType: 'column_letter', referenceValue: 'A', required: true }],
  channels: CHANNELS.map(channel => ({
    channelId: channel.channelId,
    worksheetName: 'Pricing',
    enabled: channel.available,
    fields: [
      { field: 'external_id', referenceType: 'column_letter' as const, referenceValue: 'B' },
      { field: 'price', referenceType: 'column_letter' as const, referenceValue: 'C' },
      { field: 'stock', referenceType: 'disabled' as const, referenceValue: null },
      { field: 'status', referenceType: 'disabled' as const, referenceValue: null },
    ],
  })),
}

describe('smart column mapping', () => {
  it('displays the value for the explicitly selected reference type without syntax guessing', () => {
    expect(smartInputDisplayValue({ field: 'price', referenceType: 'column_letter', referenceValue: 'H' })).toBe('H')
    expect(smartInputDisplayValue({ field: 'price', referenceType: 'header_name', referenceValue: 'H' })).toBe('H')
    expect(smartInputDisplayValue({ field: 'price', referenceType: 'column_id', referenceValue: 'wc-price' })).toBe('wc-price')
    expect(smartInputDisplayValue({ field: 'price', referenceType: 'disabled', referenceValue: null })).toBe('')
  })

  it('honors an explicitly empty capability requirement list', () => {
    expect([...requiredChannelMappingFields('shopify', { mappingRequiredFields: [] })]).toEqual([])
    expect([...requiredChannelMappingFields('future-provider', {})]).toEqual(['external_id'])
  })
})

describe('WorksheetRuleEditor resource ordering', () => {
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
    await changeLocale('en')
  })

  it.each([
    ['en', 'ltr'],
    ['fa', 'rtl'],
  ] as const)('groups worksheet Channels consistently in %s (%s)', async (locale, direction) => {
    await changeLocale(locale)
    await act(async () => {
      root.render(
        <WorksheetRuleEditor
          rule={RULE}
          channels={CHANNELS}
          sourceKind="flowhub_sheet"
          onChange={vi.fn()}
          onRemove={vi.fn()}
        />,
      )
    })

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
    expect(container.textContent).not.toContain('woocommerce:primary')

    const wooCommerce = container.querySelector<HTMLElement>('[data-resource-id="woocommerce:primary"]')
    const copySelector = Array.from(wooCommerce?.querySelectorAll('select') ?? [])
      .find(select => select.querySelector('option[value="snappshop:main"]')) as HTMLSelectElement
    expect(Array.from(copySelector.options).map(option => option.value)).toEqual([
      '',
      'snappshop:main',
      'tapsishop:main',
      'shopify:secondary',
      'digikala:main',
    ])
  })

  it('uses discovered headers as the primary picker and keeps manual modes advanced', async () => {
    const onChange = vi.fn()
    await act(async () => {
      root.render(
        <WorksheetRuleEditor
          rule={RULE}
          columns={[
            { id: 'A', letter: 'A', header: 'Product Name' },
            { id: 'B', letter: 'B', header: 'Cost' },
            { id: 'H', letter: 'H', header: 'Stock' },
          ]}
          channels={CHANNELS}
          sourceKind="external"
          onChange={onChange}
          onRemove={vi.fn()}
        />,
      )
    })
    const picker = container.querySelector('[aria-label="Source Product Name column reference"]') as HTMLSelectElement
    expect(Array.from(picker.options).map(option => [option.value, option.textContent])).toContainEqual(['H', 'H — Stock'])
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set?.call(picker, 'H')
      picker.dispatchEvent(new Event('change', { bubbles: true }))
    })
    const changed = onChange.mock.calls[0][0] as SourceWorksheetRule
    expect(changed.sourceFields.find(item => item.field === 'name')).toMatchObject({ referenceType: 'column_letter', referenceValue: 'H' })

    const advanced = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.includes('Advanced manual mapping')) as HTMLButtonElement
    await act(async () => advanced.click())
    expect(container.textContent).toContain('Exact header')
    const manualType = Array.from(container.querySelectorAll('select')).find(select => select.querySelector('option[value="column_id"]')) as HTMLSelectElement
    expect(manualType.querySelector<HTMLOptionElement>('option[value="column_id"]')?.disabled).toBe(true)
  })

  it('keeps Name, Key, and Cost primary while Classification remains optional and collapsed', async () => {
    await act(async () => {
      root.render(
        <WorksheetRuleEditor
          rule={RULE}
          channels={CHANNELS}
          sourceKind="external"
          onChange={vi.fn()}
          onRemove={vi.fn()}
        />,
      )
    })
    const primary = container.querySelector('[data-source-field-group="primary"]') as HTMLFieldSetElement
    const optional = container.querySelector('[data-source-field-group="classification"]') as HTMLElement
    expect(primary.textContent).toContain('Source Product Name')
    expect(primary.textContent).toContain('Source Product Key')
    expect(primary.textContent).toContain('Cost')
    expect(primary.textContent).not.toContain('Category')
    expect(optional.querySelector('h4')?.textContent).toContain('Optional attributes')
    expect(optional.textContent).toContain('Category')
    expect(optional.textContent).toContain('Brand')
  })
})
