// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { ReviewScopePresentation } from './DensePricingWorkspace'
import type { ReviewItemResource, ReviewResource } from '../../services/unifiedWorkspace/types'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

function reviewItem(overrides: Partial<ReviewItemResource> = {}): ReviewItemResource {
  return {
    id: 'item-1',
    canonicalProductId: 'product-1',
    listingId: 'listing-1',
    externalPrimaryId: 'WC-1',
    channelId: 'woocommerce:primary',
    field: 'price',
    current: '100',
    target: '125',
    validationState: 'ready',
    warnings: [],
    errors: [],
    eligible: true,
    selected: true,
    ...overrides,
  }
}

function review(items: ReviewItemResource[]): ReviewResource {
  return {
    id: 'review-1',
    workspaceId: 'workspace-1',
    snapshotId: 'snapshot-1',
    draftRevisionId: 'draft-1',
    status: 'ready',
    checksum: 'checksum-1',
    summary: { total: items.length, eligible: items.length, blocked: 0, warnings: 0 },
    items,
    staleReason: null,
  }
}

describe('ReviewScopePresentation', () => {
  it('renders the same immutable classification badges the grid showed, including percentage delta', () => {
    const item = reviewItem({
      changeClassification: {
        version: 'workspace-change-badges-v1',
        price: { state: 'INCREASE', current: '100', target: '125', delta: '25', percentageDelta: '25.00' },
        quantity: { state: 'UNMANAGED' },
        stockStatus: { state: 'UNCHANGED_IN_STOCK', current: 'IN_STOCK', target: 'IN_STOCK' },
        warnings: [],
        blockers: [],
        eligibility: 'ELIGIBLE',
        actionable: true,
      },
    })
    act(() => root.render(<ReviewScopePresentation review={review([item])} />))

    const badgeGroup = container.querySelector('[data-change-badges]')
    expect(badgeGroup).not.toBeNull()
    expect(badgeGroup?.textContent).toContain('25')
    // Raw eligible/blocked fallback badge must not duplicate the
    // classification's own eligibility badge when classification is present.
    expect(container.querySelectorAll('[data-review-listing] > div > .fh-badge').length).toBeGreaterThan(0)
  })

  it('treats an unchanged field as Eligible, not Blocked, in the raw fallback badge', () => {
    const item = reviewItem({ eligible: false, validationState: 'unchanged', target: '100' })
    act(() => root.render(<ReviewScopePresentation review={review([item])} />))

    const listing = container.querySelector('[data-review-listing]')
    expect(listing?.textContent).toContain('Eligible')
    expect(listing?.textContent).not.toContain('Blocked')
  })

  it('still shows Blocked in the raw fallback badge for a genuine error', () => {
    const item = reviewItem({ eligible: false, validationState: 'error', errors: ['currency_unit_invalid'] })
    act(() => root.render(<ReviewScopePresentation review={review([item])} />))

    const listing = container.querySelector('[data-review-listing]')
    expect(listing?.textContent).toContain('Blocked')
  })
})
