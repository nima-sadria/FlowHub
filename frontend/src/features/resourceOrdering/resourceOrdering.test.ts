import { describe, expect, it } from 'vitest'
import type { ChannelHealthItem, ProductChannelPriceState } from '../../services/types'
import type { WorkspaceChannelDefinition } from '../../services/unifiedWorkspace/types'
import {
  channelIdentitySignals,
  diagnosticChannelSignals,
  orderRelatedItems,
  preferredResourceId,
  prepareResourceCollection,
  productChannelSignals,
  sourceProfileSignals,
  sourceChannelSignals,
  workspaceChannelSignals,
  type ResourceOrderingSignals,
} from './resourceOrdering'

interface Fixture {
  id: string
  label: string
  signals: Omit<ResourceOrderingSignals, 'id' | 'displayName'>
}

function fixtureSignals(item: Fixture): ResourceOrderingSignals {
  return { id: item.id, displayName: item.label, ...item.signals }
}

describe('resource ordering', () => {
  it('puts configured and healthy first, warnings inside Active, then disabled and coming soon', () => {
    const items: Fixture[] = [
      { id: 'future', label: 'Aardvark', signals: { placeholder: true } },
      { id: 'warning', label: 'Aaron', signals: { configured: true, healthStatus: 'warning' } },
      { id: 'disabled', label: 'Beta', signals: { enabled: false, configured: true } },
      { id: 'healthy', label: 'Zulu', signals: { configured: true, healthStatus: 'healthy' } },
      { id: 'configured', label: 'Alpha', signals: { configured: true } },
    ]

    const collection = prepareResourceCollection(items, fixtureSignals)

    expect(collection.ordered.map(item => item.id)).toEqual([
      'configured',
      'healthy',
      'warning',
      'disabled',
      'future',
    ])
    expect(collection.sections.map(section => section.key)).toEqual(['active', 'disabled', 'comingSoon'])
    expect(collection.sections[0].items.map(item => item.id)).toEqual(['configured', 'healthy', 'warning'])
    expect(collection.ordered.map(item => item.badge)).toEqual([
      'configured',
      'healthy',
      'warning',
      'disabled',
      'comingSoon',
    ])
    expect(collection.defaultActiveId).toBe('configured')
  })

  it('uses deterministic precedence and fails unknown state into attention', () => {
    const items: Fixture[] = [
      { id: 'future', label: 'Future', signals: { placeholder: true, healthStatus: 'healthy' } },
      { id: 'disabled', label: 'Disabled', signals: { enabled: false, healthStatus: 'warning' } },
      { id: 'attention', label: 'Attention', signals: { configured: true, healthStatus: 'degraded' } },
      { id: 'unknown', label: 'Unknown', signals: {} },
    ]

    const collection = prepareResourceCollection(items, fixtureSignals)
    const tiers = Object.fromEntries(collection.ordered.map(item => [item.id, item.tier]))

    expect(tiers).toEqual({ attention: 'attention', unknown: 'attention', disabled: 'disabled', future: 'comingSoon' })
  })

  it('sorts only by display name and preserves input order when names are identical', () => {
    const items: Fixture[] = [
      { id: 'z-id', label: 'Same', signals: { configured: true } },
      { id: 'beta', label: 'Beta', signals: { configured: true } },
      { id: 'a-id', label: 'Same', signals: { configured: true } },
      { id: 'alpha', label: 'Alpha', signals: { configured: true } },
    ]
    const original = [...items]

    const collection = prepareResourceCollection(items, fixtureSignals)

    expect(collection.ordered.map(item => item.id)).toEqual(['alpha', 'beta', 'z-id', 'a-id'])
    expect(items).toEqual(original)
  })

  it('preserves an explicit selection and otherwise selects the first Active resource only', () => {
    const collection = prepareResourceCollection<Fixture>([
      { id: 'future', label: 'Future', signals: { placeholder: true } },
      { id: 'disabled', label: 'Disabled', signals: { enabled: false } },
      { id: 'active', label: 'Active', signals: { configured: true } },
    ], fixtureSignals)

    expect(preferredResourceId('disabled', collection)).toBe('disabled')
    expect(preferredResourceId('missing', collection)).toBe('active')
    expect(preferredResourceId(null, collection)).toBe('active')

    const unavailableOnly = prepareResourceCollection<Fixture>([
      { id: 'future', label: 'Future', signals: { placeholder: true } },
      { id: 'disabled', label: 'Disabled', signals: { enabled: false } },
    ], fixtureSignals)
    expect(preferredResourceId(null, unavailableOnly)).toBeNull()
  })

  it('orders related items by their resource while retaining their local order', () => {
    const resources = prepareResourceCollection<Fixture>([
      { id: 'disabled', label: 'Beta', signals: { enabled: false } },
      { id: 'active', label: 'Alpha', signals: { configured: true } },
    ], fixtureSignals)
    const related = [
      { id: 'disabled-1', resourceId: 'disabled' },
      { id: 'unknown', resourceId: 'unknown' },
      { id: 'active-1', resourceId: 'active' },
      { id: 'active-2', resourceId: 'active' },
    ]

    expect(orderRelatedItems(related, resources, item => item.resourceId).map(item => item.id)).toEqual([
      'active-1',
      'active-2',
      'disabled-1',
      'unknown',
    ])
  })

  it('applies the same grouping policy to Source and Channel adapters', () => {
    const sourceCollection = prepareResourceCollection([
      { id: 'source-future', label: 'Future', signals: { placeholder: true } },
      { id: 'source-disabled', label: 'Disabled', signals: { enabled: false } },
      { id: 'source-warning', label: 'Warning', signals: { configured: true, status: 'partial' } },
      { id: 'source-active', label: 'Active', signals: { configured: true, status: 'active' } },
    ], fixtureSignals)
    const channelCollection = prepareResourceCollection([
      { id: 'channel-future', label: 'Future', signals: { implemented: false } },
      { id: 'channel-disabled', label: 'Disabled', signals: { enabled: false } },
      { id: 'channel-warning', label: 'Warning', signals: { configured: true, status: 'partial' } },
      { id: 'channel-active', label: 'Active', signals: { configured: true, status: 'active' } },
    ], fixtureSignals)

    expect(sourceCollection.ordered.map(item => item.tier)).toEqual(channelCollection.ordered.map(item => item.tier))
    expect(sourceCollection.sections.map(section => section.key)).toEqual(channelCollection.sections.map(section => section.key))
  })
})

describe('resource signal adapters', () => {
  it('formats identity-only, Workspace, and Diagnostics channel ids as friendly display names', () => {
    expect(channelIdentitySignals({ channelId: 'woocommerce:primary' }).displayName).toBe('WooCommerce')
    expect(channelIdentitySignals({ channelId: 'snappshop:main' }, 'SnappShop Tehran').displayName).toBe('SnappShop Tehran')

    const workspace = {
      channelId: 'woocommerce:primary',
      displayName: null,
      instanceLabel: null,
      healthState: 'healthy',
    } as WorkspaceChannelDefinition
    expect(workspaceChannelSignals(workspace).displayName).toBe('WooCommerce')

    const diagnostic = {
      channelId: 'snappshop:main',
      enabled: true,
      status: 'Operational',
      dimensions: {},
    } as ChannelHealthItem
    expect(diagnosticChannelSignals(diagnostic).displayName).toBe('SnappShop')
  })

  it('recognizes configured product channels without overriding other connection states', () => {
    const base = {
      channelId: 'woocommerce:primary',
      channelName: 'WooCommerce',
      connectionState: 'configured',
      healthStatus: 'healthy',
      validationState: 'valid',
    } as ProductChannelPriceState

    expect(productChannelSignals(base).configured).toBe(true)
    expect(productChannelSignals({ ...base, connectionState: 'not_configured' }).configured).toBe(false)
    expect(productChannelSignals({ ...base, connectionState: 'pending' }).configured).toBeUndefined()
  })

  it('keeps disabled and coming-soon Source channels out of the Active default', () => {
    const collection = prepareResourceCollection([
      { channelId: 'woocommerce:primary', name: 'WooCommerce', enabled: true, available: true, implementationState: 'implemented' },
      { channelId: 'warning:main', name: 'Warning Store', enabled: true, available: true, implementationState: 'warning' },
      { channelId: 'snappshop:main', name: 'SnappShop', enabled: false, available: true, implementationState: 'implemented' },
      { channelId: 'shopify:primary', name: 'Shopify', enabled: true, available: false, implementationState: 'coming_soon' },
    ].map(channel => ({ ...channel, connectorType: '', capabilityVersion: '', capabilities: {} })), sourceChannelSignals)

    expect(collection.defaultActiveId).toBe('woocommerce:primary')
    expect(collection.sections.map(section => section.key)).toEqual(['active', 'disabled', 'comingSoon'])
    expect(collection.ordered.find(item => item.id === 'warning:main')?.badge).toBe('warning')
  })

  it('treats an active managed Source without saved column configuration as needing attention', () => {
    const collection = prepareResourceCollection([
      { id: 'ready', name: 'Ready', status: 'active', mappingVersion: 2 },
      { id: 'incomplete', name: 'Incomplete', status: 'active', mappingVersion: 0 },
    ].map(source => ({
      ...source,
      sourceKind: 'flowhub_sheet' as const,
      externalSourceId: null,
      worksheetMode: 'all' as const,
      worksheetName: null,
      dataStartRow: 1,
      version: 1,
      sheetId: null,
    })), sourceProfileSignals)

    expect(collection.ordered.map(item => [item.id, item.badge])).toEqual([
      ['ready', 'configured'],
      ['incomplete', 'warning'],
    ])
  })
})
