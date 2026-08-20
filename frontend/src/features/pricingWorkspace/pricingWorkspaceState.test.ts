import { describe, expect, it } from 'vitest'
import {
  applyBulkTransformation,
  clearPersistedPricingWorkspaceState,
  createPricingWorkspaceState,
  editPricingField,
  editPricingFields,
  hydratePricingWorkspaceState,
  parsePricingFieldKey,
  persistPricingWorkspaceState,
  previewBulkTransformation,
  pricingDraftChanges,
  pricingFieldKey,
  pricingWorkspaceStorageKey,
  pricingWorkspaceSummary,
  redoPricingWorkspace,
  registerPricingFields,
  restorePricingWorkspaceState,
  selectedPricingChanges,
  selectedPricingDraftChanges,
  serializePricingWorkspaceState,
  setPricingFieldSelected,
  setPricingFieldsSelectedByKey,
  undoPricingWorkspace,
  type PricingField,
  type PricingFieldDescriptor,
  type PricingFieldPolicy,
  type PricingWorkspaceStorage,
} from './pricingWorkspaceState'

const ELIGIBLE: PricingFieldPolicy = {
  writable: true,
  mapped: true,
  supported: true,
  channelEnabled: true,
  comingSoon: false,
  valid: true,
}

function field(
  listingId: string,
  channelId: string,
  kind: PricingField = 'price',
  currentValue = '100',
  targetValue: string | null = currentValue,
  policy: PricingFieldPolicy = ELIGIBLE,
  productId = `product-${listingId}`,
): PricingFieldDescriptor {
  return {
    identity: { productId, listingId, channelId, field: kind },
    currentValue,
    targetValue,
    currency: kind === 'price' ? 'IRR' : null,
    unit: kind === 'price' ? 'IRR' : kind === 'stock' ? 'item' : null,
    policy,
    decimalScale: 0,
  }
}

describe('pricing field identity', () => {
  it('round-trips punctuation-heavy immutable identities without delimiter collisions', () => {
    const identity = { productId: 'product:a', listingId: 'listing|1', channelId: 'woocommerce:primary', field: 'price' as const }
    const key = pricingFieldKey(identity)

    expect(parsePricingFieldKey(key)).toEqual(identity)
    expect(pricingFieldKey({ ...identity, listingId: 'listing', channelId: '1|woocommerce:primary' })).not.toBe(key)
    expect(parsePricingFieldKey('not-json')).toBeNull()
  })
})

describe('immediate field-level selection', () => {
  it('auto-selects a valid edit immediately and reports visible and hidden counts', () => {
    const descriptor = field('listing-1', 'woocommerce:primary')
    const state = editPricingField(createPricingWorkspaceState('workspace-1'), descriptor, '125')
    const key = pricingFieldKey(descriptor.identity)

    expect(selectedPricingChanges(state).map(change => change.key)).toEqual([key])
    expect(pricingWorkspaceSummary(state, new Set())).toEqual({
      changed: 1,
      selected: 1,
      ready: 1,
      warning: 0,
      blocked: 0,
      products: 1,
      listings: 1,
      channels: 1,
      hidden: 1,
    })
  })

  it('never auto-selects blocked, read-only, disabled, unsupported, or Coming Soon fields', () => {
    const policies: PricingFieldPolicy[] = [
      { ...ELIGIBLE, blockedReason: 'invalid_value' },
      { ...ELIGIBLE, writable: false },
      { ...ELIGIBLE, channelEnabled: false },
      { ...ELIGIBLE, supported: false },
      { ...ELIGIBLE, comingSoon: true },
    ]
    const descriptors = policies.map((policy, index) => field(`listing-${index}`, 'channel:main', 'price', '100', '110', policy))
    const state = createPricingWorkspaceState('workspace-1', descriptors)

    expect(selectedPricingChanges(state)).toEqual([])
    expect(pricingWorkspaceSummary(state)).toMatchObject({ changed: 5, selected: 0, ready: 0, blocked: 5 })
  })

  it('keeps manual field deselection when the same field is edited again', () => {
    const descriptor = field('listing-1', 'woocommerce:primary')
    let state = editPricingField(createPricingWorkspaceState('workspace-1'), descriptor, '110')
    state = setPricingFieldSelected(state, descriptor.identity, false)
    state = editPricingField(state, descriptor, '120')

    expect(selectedPricingChanges(state)).toEqual([])
    expect(Object.values(state.present.changes)[0]).toMatchObject({ targetValue: '120', selectionMode: 'manual_deselected' })

    state = setPricingFieldSelected(state, descriptor.identity, true)
    expect(selectedPricingChanges(state)).toHaveLength(1)
  })

  it('selects Price and Stock independently on the same Listing', () => {
    const price = field('listing-1', 'woocommerce:primary', 'price')
    const stock = field('listing-1', 'woocommerce:primary', 'stock', '5')
    let state = editPricingFields(createPricingWorkspaceState('workspace-1'), [
      { descriptor: price, targetValue: '120' },
      { descriptor: stock, targetValue: '8' },
    ])
    state = setPricingFieldSelected(state, stock.identity, false)

    expect(selectedPricingChanges(state).map(change => change.identity.field)).toEqual(['price'])
    expect(pricingDraftChanges(state).map(change => change.field)).toEqual(['price', 'stock'])
  })

  it('excludes a manually deselected edit from the selected Draft scope', () => {
    const price = field('listing-1', 'woocommerce:primary', 'price')
    const stock = field('listing-1', 'woocommerce:primary', 'stock', '5')
    let state = editPricingFields(createPricingWorkspaceState('workspace-1'), [
      { descriptor: price, targetValue: '120' },
      { descriptor: stock, targetValue: '8' },
    ])
    state = setPricingFieldSelected(state, stock.identity, false)

    expect(pricingDraftChanges(state).map(change => change.field)).toEqual(['price', 'stock'])
    expect(selectedPricingDraftChanges(state)).toEqual([
      expect.objectContaining({ listing_id: 'listing-1', channel_id: 'woocommerce:primary', field: 'price', target_value: '120' }),
    ])
  })

  it('excludes a blocked edit from the selected Draft scope', () => {
    const ready = field('listing-ready', 'woocommerce:primary', 'price')
    const blocked = field(
      'listing-blocked',
      'snappshop:main',
      'price',
      '100',
      '100',
      { ...ELIGIBLE, valid: false, blockedReason: 'invalid_value' },
    )
    const state = editPricingFields(createPricingWorkspaceState('workspace-1'), [
      { descriptor: ready, targetValue: '120' },
      { descriptor: blocked, targetValue: 'not-a-price' },
    ])

    expect(pricingWorkspaceSummary(state)).toMatchObject({ changed: 2, selected: 1, ready: 1, blocked: 1 })
    expect(selectedPricingDraftChanges(state)).toEqual([
      expect.objectContaining({ listing_id: 'listing-ready', channel_id: 'woocommerce:primary', field: 'price', target_value: '120' }),
    ])
  })

  it('auto-selects both a Source price increase and a Source price decrease from a fresh descriptor set', () => {
    const increase = field('listing-a', 'woocommerce:primary', 'price', '965000', '1015000')
    const decrease = field('listing-b', 'woocommerce:primary', 'price', '1015000', '965000')
    const state = createPricingWorkspaceState('workspace-1', [increase, decrease])

    expect(selectedPricingChanges(state).map(change => change.identity.listingId).sort()).toEqual(['listing-a', 'listing-b'])
    expect(pricingWorkspaceSummary(state)).toMatchObject({ changed: 2, selected: 2, blocked: 0 })
  })

  it('never treats a formatting-only Price difference as a change', () => {
    const trailingZero = field('listing-a', 'woocommerce:primary', 'price', '100', '100.00')
    const wholeNumber = field('listing-b', 'woocommerce:primary', 'price', '100.0', '100')
    const genuineChange = field('listing-c', 'woocommerce:primary', 'price', '100', '100.01')
    const state = createPricingWorkspaceState('workspace-1', [trailingZero, wholeNumber, genuineChange])

    expect(pricingWorkspaceSummary(state).changed).toBe(1)
    expect(selectedPricingChanges(state).map(change => change.identity.listingId)).toEqual(['listing-c'])
  })

  it('selects a Stock formatting difference the same way as Price', () => {
    const trailingZero = field('listing-a', 'woocommerce:primary', 'stock', '5', '5')
    const edited = editPricingField(createPricingWorkspaceState('workspace-1', [trailingZero]), trailingZero, '05')

    // "05" normalizes to the same Stock quantity as "5" -- no genuine change.
    expect(pricingWorkspaceSummary(edited).changed).toBe(0)
  })

  it('selects a Listing variation independently of its sibling variation under the same parent product', () => {
    const variationOne = field('variation-1', 'woocommerce:primary', 'price', '100', '110', ELIGIBLE, 'product-parent')
    const variationTwo = field('variation-2', 'woocommerce:primary', 'price', '200', '200', ELIGIBLE, 'product-parent')
    const state = createPricingWorkspaceState('workspace-1', [variationOne, variationTwo])

    expect(selectedPricingChanges(state).map(change => change.identity.listingId)).toEqual(['variation-1'])
    expect(pricingWorkspaceSummary(state)).toMatchObject({ changed: 1, selected: 1, products: 1, listings: 1 })
  })

  it('provides Select all eligible and Deselect all over an explicit visible key set, skipping blocked rows', () => {
    const eligibleA = field('listing-a', 'woocommerce:primary', 'price', '100', '110')
    const eligibleB = field('listing-b', 'woocommerce:primary', 'price', '100', '90')
    const blocked = field('listing-c', 'snappshop:main', 'price', '100', '150', { ...ELIGIBLE, valid: false, blockedReason: 'invalid_value' })
    let state = createPricingWorkspaceState('workspace-1', [eligibleA, eligibleB, blocked])
    const visibleKeys = new Set([eligibleA, eligibleB, blocked].map(descriptor => pricingFieldKey(descriptor.identity)))

    state = setPricingFieldsSelectedByKey(state, visibleKeys, false)
    expect(selectedPricingChanges(state)).toEqual([])
    expect(pricingWorkspaceSummary(state)).toMatchObject({ changed: 3, selected: 0, blocked: 1 })

    state = setPricingFieldsSelectedByKey(state, visibleKeys, true)
    // The blocked row never becomes selectable, even though it was included
    // in the same visible key set passed to "Select all eligible".
    expect(selectedPricingChanges(state).map(change => change.identity.listingId).sort()).toEqual(['listing-a', 'listing-b'])
    expect(pricingWorkspaceSummary(state)).toMatchObject({ changed: 3, selected: 2, blocked: 1 })
  })

  it('leaves filtering and pagination-scope key sets unable to alter selection outside their own identities', () => {
    const pageOne = field('listing-a', 'woocommerce:primary', 'price', '100', '110')
    const pageTwo = field('listing-b', 'woocommerce:primary', 'price', '100', '90')
    const state = createPricingWorkspaceState('workspace-1', [pageOne, pageTwo])

    // "Deselect all" scoped to only the currently visible (page one) key must
    // never reach into an identity outside that set.
    const pageOneKeys = new Set([pricingFieldKey(pageOne.identity)])
    const deselected = setPricingFieldsSelectedByKey(state, pageOneKeys, false)

    expect(selectedPricingChanges(deselected).map(change => change.identity.listingId)).toEqual(['listing-b'])
  })
})

describe('history and paging-independent registration', () => {
  it('commits multiline paste as one undo step and supports redo', () => {
    const first = field('listing-a', 'woocommerce:primary')
    const second = field('listing-b', 'woocommerce:primary')
    const edited = editPricingFields(createPricingWorkspaceState('workspace-1'), [
      { descriptor: first, targetValue: '110' },
      { descriptor: second, targetValue: '120' },
    ])

    expect(edited.past).toHaveLength(1)
    expect(pricingWorkspaceSummary(edited).changed).toBe(2)
    const undone = undoPricingWorkspace(edited)
    expect(pricingWorkspaceSummary(undone).changed).toBe(0)
    const redone = redoPricingWorkspace(undone)
    expect(pricingWorkspaceSummary(redone).changed).toBe(2)
  })

  it('adds server targets from later pages without replacing prior local edits or history', () => {
    const pageOne = field('listing-a', 'woocommerce:primary')
    const pageTwo = field('listing-b', 'snappshop:main', 'price', '100', '130')
    const edited = editPricingField(createPricingWorkspaceState('workspace-1'), pageOne, '120')
    const registered = registerPricingFields(edited, [pageTwo, { ...pageOne, targetValue: '999' }])

    expect(pricingWorkspaceSummary(registered)).toMatchObject({ changed: 2, selected: 2, hidden: 0 })
    expect(registered.present.changes[pricingFieldKey(pageOne.identity)].targetValue).toBe('120')
    expect(registered.past).toHaveLength(1)
  })

  it('refreshes eligibility when a paged field reappears and fails closed without losing its value', () => {
    const descriptor = field('listing-a', 'woocommerce:primary')
    const firstEdit = editPricingField(createPricingWorkspaceState('workspace-1'), descriptor, '110')
    const edited = editPricingField(firstEdit, descriptor, '120')
    const blocked = registerPricingFields(edited, [{
      ...descriptor,
      policy: { ...ELIGIBLE, valid: false, blockedReason: 'stale_mapping' },
    }])

    expect(blocked.present.changes[pricingFieldKey(descriptor.identity)].targetValue).toBe('120')
    expect(pricingWorkspaceSummary(blocked)).toMatchObject({ changed: 1, selected: 0, ready: 0, blocked: 1 })
    const undone = undoPricingWorkspace(blocked)
    expect(undone.present.changes[pricingFieldKey(descriptor.identity)]?.targetValue).toBe('110')
    expect(pricingWorkspaceSummary(undone)).toMatchObject({ changed: 1, selected: 0, ready: 0, blocked: 1 })
  })

  it('keeps an invalid local target blocked when the field is registered after paging', () => {
    const descriptor = field('listing-a', 'woocommerce:primary')
    const invalid = editPricingField(createPricingWorkspaceState('workspace-1'), descriptor, 'not-a-price')
    const registered = registerPricingFields(invalid, [descriptor])

    expect(registered.present.changes[pricingFieldKey(descriptor.identity)]).toMatchObject({
      targetValue: 'not-a-price',
      policy: { valid: false, blockedReason: 'invalid_value' },
    })
    expect(pricingWorkspaceSummary(registered)).toMatchObject({ changed: 1, selected: 0, blocked: 1 })
  })

  it('removes a local change after refreshed Current reaches its Target', () => {
    const descriptor = field('listing-a', 'woocommerce:primary')
    const edited = editPricingField(createPricingWorkspaceState('workspace-1'), descriptor, '120')
    const refreshed = registerPricingFields(edited, [{ ...descriptor, currentValue: '120', targetValue: '120' }])

    expect(pricingWorkspaceSummary(refreshed)).toMatchObject({ changed: 0, selected: 0 })
  })

  it('clears redo history after a new edit', () => {
    const descriptor = field('listing-1', 'woocommerce:primary')
    const edited = editPricingField(createPricingWorkspaceState('workspace-1'), descriptor, '110')
    const undone = undoPricingWorkspace(edited)
    const replaced = editPricingField(undone, descriptor, '120')

    expect(redoPricingWorkspace(replaced)).toBe(replaced)
  })
})

describe('deterministic bulk transformations', () => {
  it('previews and applies fixed and percentage Price changes in stable identity order', () => {
    const fields = [
      field('listing-z', 'woocommerce:primary', 'price', '105'),
      field('listing-a', 'snappshop:main', 'price', '200'),
    ]
    const initial = createPricingWorkspaceState('workspace-1')
    const percentage = previewBulkTransformation(initial, fields, { kind: 'increase_price_percent', value: '10' })

    expect(percentage.items.map(item => item.descriptor.identity.listingId)).toEqual(['listing-a', 'listing-z'])
    expect(percentage.items.map(item => item.resultingValue)).toEqual(['220', '116'])
    expect(percentage).toMatchObject({ productsAffected: 2, listingsAffected: 2, fieldsAffected: 2, blockedItems: 0 })

    const applied = applyBulkTransformation(initial, percentage)
    expect(Object.values(applied.present.changes).map(change => change.targetValue)).toEqual(['220', '116'])
    expect(applied.past).toHaveLength(1)

    const fixed = previewBulkTransformation(applied, fields, { kind: 'decrease_price_fixed', value: '20' })
    expect(fixed.items.map(item => item.resultingValue)).toEqual(['200', '96'])
  })

  it('supports exact Price, Stock, and Status operations as individual deterministic changes', () => {
    const price = field('listing-1', 'woocommerce:primary', 'price', '100')
    const stock = field('listing-1', 'woocommerce:primary', 'stock', '5')
    const status = field('listing-1', 'woocommerce:primary', 'status', 'draft')
    let state = createPricingWorkspaceState('workspace-1')

    state = applyBulkTransformation(state, previewBulkTransformation(state, [price], { kind: 'set_price', value: '125' }))
    state = applyBulkTransformation(state, previewBulkTransformation(state, [stock], { kind: 'set_stock', value: '8' }))
    state = applyBulkTransformation(state, previewBulkTransformation(state, [status], { kind: 'set_status', value: 'publish' }))

    expect(pricingDraftChanges(state)).toEqual([
      expect.objectContaining({ field: 'price', target_value: '125' }),
      expect.objectContaining({ field: 'status', target_value: 'publish' }),
      expect.objectContaining({ field: 'stock', target_value: '8' }),
    ])
  })

  it('reports blocked fields in the preview and never commits them', () => {
    const blocked = field('listing-blocked', 'channel:main', 'price', '100', '100', { ...ELIGIBLE, valid: false, blockedReason: 'invalid_mapping' })
    const ready = field('listing-ready', 'channel:main', 'price', '100')
    const preview = previewBulkTransformation(createPricingWorkspaceState('workspace-1'), [blocked, ready], { kind: 'increase_price_fixed', value: '10' })
    const applied = applyBulkTransformation(createPricingWorkspaceState('workspace-1'), preview)

    expect(preview.blockedItems).toBe(1)
    expect(preview.items.find(item => item.key === pricingFieldKey(blocked.identity))?.blockedReason).toBe('invalid_mapping')
    expect(pricingWorkspaceSummary(applied)).toMatchObject({ changed: 1, selected: 1 })
  })

  it('fails closed when state changed after a preview was displayed', () => {
    const descriptor = field('listing-1', 'channel:main')
    const initial = createPricingWorkspaceState('workspace-1')
    const preview = previewBulkTransformation(initial, [descriptor], { kind: 'set_price', value: '120' })
    const changed = editPricingField(initial, descriptor, '110')

    expect(() => applyBulkTransformation(changed, preview)).toThrow('Stale bulk preview')
  })

  it('fails closed when field eligibility changes after a preview was displayed', () => {
    const descriptor = field('listing-1', 'channel:main')
    const initial = editPricingField(createPricingWorkspaceState('workspace-1'), descriptor, '110')
    const preview = previewBulkTransformation(initial, [descriptor], { kind: 'set_price', value: '120' })
    const disabled = {
      ...descriptor,
      policy: { ...descriptor.policy, channelEnabled: false, blockedReason: 'channel_disabled' },
    }
    const refreshed = registerPricingFields(initial, [disabled])

    expect(refreshed.revision).toBeGreaterThan(initial.revision)
    expect(() => applyBulkTransformation(refreshed, preview)).toThrow('Stale bulk preview')
  })

  it('rejects invalid, negative, and fractional Stock values', () => {
    const price = field('listing-1', 'channel:main', 'price', '10')
    const stock = field('listing-1', 'channel:main', 'stock', '5')

    expect(previewBulkTransformation(createPricingWorkspaceState('workspace-1'), [price], { kind: 'decrease_price_fixed', value: '20' }).items[0].blockedReason).toBe('negative_value')
    expect(previewBulkTransformation(createPricingWorkspaceState('workspace-1'), [stock], { kind: 'set_stock', value: '1.5' }).items[0].blockedReason).toBe('invalid_stock')
  })
})

describe('versioned local persistence', () => {
  it('restores edits, field selection, undo, and redo independently of display order or locale', () => {
    const first = field('listing-a', 'woocommerce:primary')
    const second = field('listing-b', 'snappshop:main')
    let state = editPricingFields(createPricingWorkspaceState('workspace-1'), [
      { descriptor: second, targetValue: '130' },
      { descriptor: first, targetValue: '120' },
    ])
    state = setPricingFieldSelected(state, first.identity, false)
    const serialized = serializePricingWorkspaceState(state)
    const restored = hydratePricingWorkspaceState(serialized, 'workspace-1')

    expect(serializePricingWorkspaceState(restored)).toBe(serialized)
    expect(selectedPricingChanges(restored).map(change => change.identity.listingId)).toEqual(['listing-b'])
    expect(undoPricingWorkspace(restored).present.changes[pricingFieldKey(first.identity)]?.selectionMode).toBe('automatic')
  })

  it('uses an isolated workspace key and safely rejects corrupt or cross-workspace data', () => {
    const storage = memoryStorage()
    const descriptor = field('listing-1', 'channel:main')
    const state = editPricingField(createPricingWorkspaceState('workspace-1'), descriptor, '120')
    persistPricingWorkspaceState(storage, state)

    expect(pricingWorkspaceSummary(restorePricingWorkspaceState(storage, 'workspace-1')).changed).toBe(1)
    expect(pricingWorkspaceSummary(restorePricingWorkspaceState(storage, 'workspace-2')).changed).toBe(0)
    expect(pricingWorkspaceSummary(hydratePricingWorkspaceState('{bad json', 'workspace-1')).changed).toBe(0)

    clearPersistedPricingWorkspaceState(storage, 'workspace-1')
    expect(storage.getItem(pricingWorkspaceStorageKey('workspace-1'))).toBeNull()
  })

  it('binds persisted edits to the immutable Snapshot and Draft scope', () => {
    const storage = memoryStorage()
    const descriptor = field('listing-1', 'channel:main')
    const state = editPricingField(createPricingWorkspaceState('workspace-1', [], 'snapshot-a:draft-a'), descriptor, '120')
    persistPricingWorkspaceState(storage, state)

    expect(pricingWorkspaceSummary(restorePricingWorkspaceState(storage, 'workspace-1', 'snapshot-a:draft-a')).changed).toBe(1)
    expect(pricingWorkspaceSummary(restorePricingWorkspaceState(storage, 'workspace-1', 'snapshot-b:draft-a')).changed).toBe(0)
    expect(pricingWorkspaceStorageKey('workspace-1', 'snapshot-a:draft-a')).not.toBe(pricingWorkspaceStorageKey('workspace-1', 'snapshot-b:draft-a'))
  })
})

function memoryStorage(): PricingWorkspaceStorage {
  const values = new Map<string, string>()
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value) },
    removeItem: key => { values.delete(key) },
  }
}
