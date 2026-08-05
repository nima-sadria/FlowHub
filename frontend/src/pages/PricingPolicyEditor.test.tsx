// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import PricingPolicyEditor from './PricingPolicyEditor'
import { changeLocale } from '../i18n'
import { ServiceProvider } from '../services/ServiceContext'
import type { CommerceService } from '../services/commerce/CommerceService'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

const stubCommerce = {
  getChannels: async () => ({ items: [{ id: 'woocommerce:primary', name: 'WooCommerce' }] }),
  getSources: async () => ({ items: [] }),
} as unknown as CommerceService

const existingRevision = {
  id: 'rev-1', policyId: 'pol-1', revisionNumber: 1, name: 'Retail EUR',
  computationCurrency: 'EUR', basisStrategy: 'min', roundOrder: 'surcharge_then_round',
  maxQuoteAgeDays: 30, minQuoteCount: 1, evaluationTimezone: 'UTC',
  arithmeticVersion: 'a1', unitRegistryVersion: 'u1', checksum: 'sum-1', createdAt: '2026-08-05T00:00:00Z',
  rules: [{
    channelId: 'woocommerce:primary', productRef: null, productGroupRevisionId: null,
    rateMode: 'percent_bp', rateValue: 1000, fixedAddendMinor: 0, roundMode: 'floor',
    roundStepMinor: 100, surchargeMinor: 0, guards: {},
  }],
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

function stubFetch(handler: (url: string, method: string) => Response | Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => handler(String(input), init?.method ?? 'GET')))
}

async function renderNew() {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/settings/pricing/policies/new']}>
        <ServiceProvider services={{ commerce: stubCommerce } as never}>
          <Routes>
            <Route path="/settings/pricing/policies/new" element={<PricingPolicyEditor />} />
          </Routes>
        </ServiceProvider>
      </MemoryRouter>,
    )
  })
  await act(async () => { await Promise.resolve() })
  await settle()
  return container
}

async function renderNextRevision() {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/settings/pricing/policies/rev-1/new-revision']}>
        <ServiceProvider services={{ commerce: stubCommerce } as never}>
          <Routes>
            <Route path="/settings/pricing/policies/:revisionId/new-revision" element={<PricingPolicyEditor />} />
          </Routes>
        </ServiceProvider>
      </MemoryRouter>,
    )
  })
  await settle()
  return container
}

async function settle() {
  for (let i = 0; i < 4; i += 1) {
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
  }
}

function setValue(el: Element | null, value: string) {
  const input = el as HTMLInputElement | HTMLSelectElement
  const proto = input.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')!.set!
  setter.call(input, value)
  input.dispatchEvent(new Event('change', { bubbles: true }))
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

describe('PricingPolicyEditor', () => {
  it('creates a new policy revision and shows a success state with navigation actions', async () => {
    stubFetch((url, method) => {
      if (method === 'POST' && url.endsWith('/pricing-matrix/policies')) return json({ ...existingRevision, revisionNumber: 1 })
      return json({ items: [] })
    })
    const c = await renderNew()
    expect(c.querySelector('[data-testid="pricing-policy-editor"]')).not.toBeNull()

    setValue(c.querySelector('#policy-name'), 'Retail EUR')
    setValue(c.querySelector('#policy-currency'), 'EUR')

    const submit = c.querySelector('[data-testid="pricing-policy-editor-submit"]') as HTMLButtonElement
    await act(async () => { submit.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()

    expect(c.querySelector('[data-testid="pricing-policy-editor-success"]')).not.toBeNull()
    expect(c.textContent).toContain('View in Pricing Matrix')
    expect(c.textContent).toContain('Create next revision')
  })

  it('prefills from an existing revision when creating the next one, explaining reuse', async () => {
    stubFetch((url, method) => {
      if (method === 'GET' && url.endsWith('/pricing-matrix/policies/rev-1')) return json(existingRevision)
      return json({ items: [] })
    })
    const c = await renderNextRevision()

    expect(c.textContent).toContain('reuses the existing policy identity')
    expect((c.querySelector('#policy-name') as HTMLInputElement).value).toBe('Retail EUR')
    expect((c.querySelector('[data-testid="pricing-policy-editor-policy-id"]') as HTMLInputElement).disabled).toBe(true)
  })

  it('lets a rule target a product only, and only shows the product-ref field', async () => {
    stubFetch(() => json({ items: [] }))
    const c = await renderNew()
    const addRule = c.querySelector('[data-testid="pricing-policy-editor-add-rule"]') as HTMLButtonElement
    await act(async () => { addRule.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    setValue(c.querySelector('[data-testid="pricing-policy-editor-rule-0-target-kind"]'), 'product')
    await settle()
    expect(c.querySelector('[data-testid="pricing-policy-editor-rule-0-product-ref"]')).not.toBeNull()
    expect(c.querySelector('[data-testid="pricing-policy-editor-rule-0-group"]')).toBeNull()
  })

  it('lets a rule target a product group revision only, and only shows the group field', async () => {
    stubFetch(() => json({ items: [] }))
    const c = await renderNew()
    const addRule = c.querySelector('[data-testid="pricing-policy-editor-add-rule"]') as HTMLButtonElement
    await act(async () => { addRule.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    setValue(c.querySelector('[data-testid="pricing-policy-editor-rule-0-target-kind"]'), 'group')
    await settle()
    expect(c.querySelector('[data-testid="pricing-policy-editor-rule-0-group"]')).not.toBeNull()
    expect(c.querySelector('[data-testid="pricing-policy-editor-rule-0-product-ref"]')).toBeNull()
  })

  it('flags a duplicate rule scope (same channel + target) across two rules', async () => {
    stubFetch(() => json({ items: [] }))
    const c = await renderNew()
    setValue(c.querySelector('#policy-name'), 'X')
    setValue(c.querySelector('#policy-currency'), 'EUR')

    for (let i = 0; i < 2; i += 1) {
      const addRule = c.querySelector('[data-testid="pricing-policy-editor-add-rule"]') as HTMLButtonElement
      await act(async () => { addRule.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
      await settle()
    }
    setValue(c.querySelector('[data-testid="pricing-policy-editor-rule-0-channel"]'), 'woocommerce:primary')
    setValue(c.querySelector('[data-testid="pricing-policy-editor-rule-1-channel"]'), 'woocommerce:primary')
    await settle()

    expect(c.querySelector('[data-testid="pricing-policy-editor-rule-1-duplicate-error"]')).not.toBeNull()
    const submit = c.querySelector('[data-testid="pricing-policy-editor-submit"]') as HTMLButtonElement
    expect(submit.disabled).toBe(true)
  })

  it('shows a distinct permission-denied state and preserves entered data on a 403', async () => {
    stubFetch((url, method) => {
      if (method === 'POST' && url.endsWith('/pricing-matrix/policies')) return json({ detail: { code: 'forbidden', message: 'no' } }, 403)
      return json({ items: [] })
    })
    const c = await renderNew()
    setValue(c.querySelector('#policy-name'), 'Kept Name')
    setValue(c.querySelector('#policy-currency'), 'EUR')

    const submit = c.querySelector('[data-testid="pricing-policy-editor-submit"]') as HTMLButtonElement
    await act(async () => { submit.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()

    expect(c.querySelector('[data-testid="pricing-permission-denied"]')).not.toBeNull()
    expect((c.querySelector('#policy-name') as HTMLInputElement).value).toBe('Kept Name')
  })

  it('shows a distinct unavailable state on a network/server failure', async () => {
    stubFetch((url, method) => {
      if (method === 'POST' && url.endsWith('/pricing-matrix/policies')) return json({ detail: 'down' }, 500)
      return json({ items: [] })
    })
    const c = await renderNew()
    setValue(c.querySelector('#policy-name'), 'X')
    setValue(c.querySelector('#policy-currency'), 'EUR')
    const submit = c.querySelector('[data-testid="pricing-policy-editor-submit"]') as HTMLButtonElement
    await act(async () => { submit.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    expect(c.querySelector('[data-testid="pricing-unavailable"]')).not.toBeNull()
  })

  it('fails closed to a contract-mismatch state on prefill with an unknown enum', async () => {
    stubFetch((url, method) => {
      if (method === 'GET' && url.endsWith('/pricing-matrix/policies/rev-1')) return json({ ...existingRevision, roundOrder: 'sideways' })
      return json({ items: [] })
    })
    const c = await renderNextRevision()
    expect(c.querySelector('[data-testid="pricing-policy-editor-prefill-error"]')).not.toBeNull()
    expect(c.querySelector('[data-testid="pricing-contract-mismatch"]')).not.toBeNull()
  })

  it('prevents a duplicate submit while saving', async () => {
    let policyPostCalls = 0
    stubFetch((url, method) => {
      if (method === 'POST' && url.endsWith('/pricing-matrix/policies')) {
        policyPostCalls += 1
        return json({ ...existingRevision })
      }
      return json({ items: [] })
    })
    const c = await renderNew()
    setValue(c.querySelector('#policy-name'), 'X')
    setValue(c.querySelector('#policy-currency'), 'EUR')
    const submit = c.querySelector('[data-testid="pricing-policy-editor-submit"]') as HTMLButtonElement
    await act(async () => {
      submit.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      submit.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await settle()
    expect(policyPostCalls).toBeLessThanOrEqual(1)
  })

  it('localizes the editor in Persian', async () => {
    await changeLocale('fa')
    stubFetch(() => json({ items: [] }))
    const c = await renderNew()
    expect(c.textContent).toContain('ایجاد بازنگری سیاست')
  })

  it('preserves a large exact-integer rate value as text through the rules table input', async () => {
    stubFetch(() => json({ items: [] }))
    const c = await renderNew()
    const addRule = c.querySelector('[data-testid="pricing-policy-editor-add-rule"]') as HTMLButtonElement
    await act(async () => { addRule.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    const bigValue = '9007199254740993000'
    setValue(c.querySelector('[data-testid="pricing-policy-editor-rule-0-rate-value"]'), bigValue)
    await settle()
    expect((c.querySelector('[data-testid="pricing-policy-editor-rule-0-rate-value"]') as HTMLInputElement).value).toBe(bigValue)
  })
})
