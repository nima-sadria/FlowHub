// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { MemoryRouter } from 'react-router'
import PricingMatrix from './PricingMatrix'
import { changeLocale } from '../i18n'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const CHANNEL = 'woocommerce:primary'

const policySummary = {
  id: 'rev-1', policyId: 'pol-1', revisionNumber: 1, name: 'Retail EUR',
  computationCurrency: 'EUR', basisStrategy: 'min', roundOrder: 'surcharge_then_round',
  maxQuoteAgeDays: 30, minQuoteCount: 1, evaluationTimezone: 'UTC',
  arithmeticVersion: 'a1', unitRegistryVersion: 'u1', checksum: 'sum-1',
  createdAt: '2026-08-05T00:00:00Z',
}

const policyRevision = {
  ...policySummary,
  rules: [{
    channelId: CHANNEL, productRef: null, productGroupRevisionId: null,
    rateMode: 'percent_bp', rateValue: 1000, fixedAddendMinor: 0, roundMode: 'floor',
    roundStepMinor: 100, surchargeMinor: 0, guards: {},
  }],
}

const inactiveHead = {
  channelId: CHANNEL, headVersion: 0, currentEventId: null, effectiveActivationId: null,
  status: 'inactive', policyRevisionId: null, channelConfigRevisionId: null,
  updatedAt: '2026-08-05T00:00:00Z',
}

const unresolvedUnit = { scope: 'channel', scopeReference: CHANNEL, status: 'unresolved', currency: null, unit: null }

const events = {
  items: [{
    id: 'ev-1', channelId: CHANNEL, eventKind: 'deactivate', predecessorEventId: null,
    effectiveActivationId: null, policyRevisionId: null, channelConfigRevisionId: null,
    supersedesActivationId: null, actorUserId: 'admin', reason: 'pause', occurredAt: '2026-08-05T00:00:00Z',
  }],
}

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

function defaultResponder(policies: unknown = { items: [policySummary] }) {
  return (input: RequestInfo | URL): Response => {
    const url = String(input)
    if (url.includes('/lifecycle-events')) return json(events)
    if (url.includes('/head')) return json(inactiveHead)
    if (url.includes('/units/channel/')) return json(unresolvedUnit)
    if (url.includes('/pricing-matrix/policies/')) return json(policyRevision)
    if (url.includes('/pricing-matrix/policies')) return json(policies)
    return new Response('{}', { status: 404 })
  }
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(async () => {
  act(() => { root.unmount() })
  container.remove()
  vi.unstubAllGlobals()
  await changeLocale('en')
})

async function renderPage() {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/settings/pricing']}>
        <PricingMatrix />
      </MemoryRouter>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return container
}

async function settle() {
  for (let i = 0; i < 4; i += 1) {
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
  }
}

describe('PricingMatrix (read-only surfaces)', () => {
  it('renders the read-only note and the policies list', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => defaultResponder()(input as RequestInfo | URL)))
    const c = await renderPage()
    expect(c.querySelector('[data-testid="pricing-page"]')).not.toBeNull()
    expect(c.textContent).toContain('Channel activation, pricing preview, and apply are not available')
    expect(c.querySelector('[data-testid="pricing-policy-row-rev-1"]')?.textContent).toContain('Retail EUR')
  })

  it('shows an empty state when there are no policies', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => defaultResponder({ items: [] })(input as RequestInfo | URL)))
    const c = await renderPage()
    expect(c.querySelector('[data-testid="pricing-empty"]')).not.toBeNull()
  })

  it('shows a distinct permission-denied state on 403', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/pricing-matrix/policies')) return json({ detail: { code: 'forbidden', message: 'no' } }, 403)
      return new Response('{}', { status: 404 })
    }))
    const c = await renderPage()
    expect(c.querySelector('[data-testid="pricing-permission-denied"]')).not.toBeNull()
    expect(c.querySelector('[data-testid="pricing-unavailable"]')).toBeNull()
  })

  it('shows a distinct unavailable state with the HTTP status on 500', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/pricing-matrix/policies')) return json({ detail: 'down' }, 500)
      return new Response('{}', { status: 404 })
    }))
    const c = await renderPage()
    const panel = c.querySelector('[data-testid="pricing-unavailable"]')
    expect(panel).not.toBeNull()
    expect(panel?.textContent).toContain('500')
  })

  it('fails closed to a contract-mismatch state on an unknown enum value', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/pricing-matrix/policies')) {
        return json({ items: [{ ...policySummary, roundOrder: 'sideways' }] })
      }
      return new Response('{}', { status: 404 })
    }))
    const c = await renderPage()
    expect(c.querySelector('[data-testid="pricing-contract-mismatch"]')).not.toBeNull()
  })

  it('reveals rules, channel lifecycle, and an unresolved unit when a policy is selected', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => defaultResponder()(input as RequestInfo | URL)))
    const c = await renderPage()
    const row = c.querySelector('[data-testid="pricing-policy-row-rev-1"]') as HTMLButtonElement
    await act(async () => { row.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()

    expect(c.querySelector('[data-testid="pricing-rules-table"]')).not.toBeNull()
    expect(c.querySelector('[data-testid="pricing-policy-detail"]')?.textContent).toContain('Retail EUR')

    const status = c.querySelector('[data-testid="pricing-channel-status-woocommerce:primary"]')
    expect(status?.textContent).toContain('Inactive')

    const unit = c.querySelector('[data-testid="pricing-unit-status-woocommerce:primary"]')
    expect(unit?.textContent).toContain('Unresolved')
    expect(c.querySelector('[data-testid="pricing-units-unresolved"]')).not.toBeNull()

    expect(c.querySelector('[data-testid="pricing-events-woocommerce:primary"]')?.textContent).toContain('Deactivated')
  })

  it('preserves an exact monetary rate value as text', async () => {
    const bigRate = '9007199254740993000'
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/pricing-matrix/policies/')) {
        return json({ ...policyRevision, rules: [{ ...policyRevision.rules[0], rateValue: bigRate }] })
      }
      return defaultResponder()(input as RequestInfo | URL)
    }))
    const c = await renderPage()
    const row = c.querySelector('[data-testid="pricing-policy-row-rev-1"]') as HTMLButtonElement
    await act(async () => { row.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    expect(c.querySelector('[data-testid="pricing-rule-row-0"]')?.textContent).toContain(bigRate)
  })

  it('localizes the page in Persian', async () => {
    await changeLocale('fa')
    vi.stubGlobal('fetch', vi.fn(async input => defaultResponder()(input as RequestInfo | URL)))
    const c = await renderPage()
    expect(c.textContent).toContain('ماتریس قیمت‌گذاری')
    expect(c.textContent).not.toContain('Pricing Matrix')
  })
})
