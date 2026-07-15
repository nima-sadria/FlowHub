// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SourceChannel, SourceWorksheetRule } from '../../features/sourceWorkspace/types'
import { changeLocale } from '../../i18n'
import WorksheetRuleEditor from './WorksheetRuleEditor'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const CHANNELS: SourceChannel[] = [
  { channelId: 'digikala:main', name: 'Digikala', connectorType: 'digikala', capabilityVersion: 'none', capabilities: {}, enabled: false, implementationState: 'coming_soon', available: false },
  { channelId: 'woocommerce:primary', name: 'WooCommerce Primary', connectorType: 'woocommerce', capabilityVersion: '1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
  { channelId: 'shopify:secondary', name: 'Shopify Secondary', connectorType: 'shopify', capabilityVersion: '1', capabilities: {}, enabled: false, implementationState: 'implemented', available: true },
  { channelId: 'tapsishop:main', name: 'TapsiShop Main', connectorType: 'tapsishop', capabilityVersion: '1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
  { channelId: 'snappshop:main', name: 'SnappShop Main', connectorType: 'snappshop', capabilityVersion: '1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
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
})
