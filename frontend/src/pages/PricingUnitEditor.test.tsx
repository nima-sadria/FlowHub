// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { MemoryRouter } from 'react-router'
import PricingUnitEditor from './PricingUnitEditor'
import { changeLocale } from '../i18n'
import { ServiceProvider } from '../services/ServiceContext'
import type { CommerceService } from '../services/commerce/CommerceService'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

const stubCommerce = {
  getSources: async () => ({ items: [{ id: 'nextcloud:primary', name: 'Nextcloud' }] }),
  getChannels: async () => ({ items: [{ id: 'woocommerce:primary', name: 'WooCommerce' }] }),
} as unknown as CommerceService

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

async function renderPage() {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/settings/pricing/units/new']}>
        <ServiceProvider services={{ commerce: stubCommerce } as never}>
          <PricingUnitEditor />
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

describe('PricingUnitEditor', () => {
  it('offers only Source and Channel scopes, never Global', async () => {
    stubFetch(() => json({ scope: 'channel', scopeReference: 'x', status: 'unresolved', currency: null, unit: null }))
    const c = await renderPage()
    const options = Array.from(c.querySelectorAll('[data-testid="pricing-unit-editor-scope"] option')).map(o => o.textContent)
    expect(options.sort()).toEqual(['Channel', 'Source'])
    expect(options.join(',')).not.toMatch(/global/i)
  })

  it('declares an IRR + RIAL unit explicitly', async () => {
    stubFetch((_url, method) => {
      if (method === 'PUT') return json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'resolved', canonicalCurrency: 'IRR', canonicalUnit: 'RIAL', canonicalFactor: '1', currencyProfileId: 'cp-1', version: 'v1' })
      return json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null })
    })
    const c = await renderPage()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-scope-reference"]'), 'woocommerce:primary')
    await settle()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-currency"]'), 'IRR')
    setValue(c.querySelector('[data-testid="pricing-unit-editor-unit"]'), 'RIAL')
    setValue(c.querySelector('[data-testid="pricing-unit-editor-connector-config-version"]'), 'v1')

    const submit = c.querySelector('[data-testid="pricing-unit-editor-submit"]') as HTMLButtonElement
    await act(async () => { submit.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()

    expect(c.querySelector('[data-testid="pricing-unit-editor-success"]')).not.toBeNull()
    expect(c.textContent).toContain('RIAL')
  })

  it('declares an IRR + TOMAN unit explicitly', async () => {
    stubFetch((_url, method) => {
      if (method === 'PUT') return json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'resolved', canonicalCurrency: 'IRR', canonicalUnit: 'TOMAN', canonicalFactor: '10', currencyProfileId: 'cp-1', version: 'v1' })
      return json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null })
    })
    const c = await renderPage()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-scope-reference"]'), 'woocommerce:primary')
    await settle()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-currency"]'), 'IRR')
    setValue(c.querySelector('[data-testid="pricing-unit-editor-unit"]'), 'TOMAN')
    setValue(c.querySelector('[data-testid="pricing-unit-editor-connector-config-version"]'), 'v1')
    const submit = c.querySelector('[data-testid="pricing-unit-editor-submit"]') as HTMLButtonElement
    await act(async () => { submit.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    expect(c.querySelector('[data-testid="pricing-unit-editor-success"]')).not.toBeNull()
    expect(c.textContent).toContain('TOMAN')
  })

  it('requires an explicit IRR unit choice and never defaults it (no magnitude inference)', async () => {
    stubFetch(() => json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null }))
    const c = await renderPage()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-scope-reference"]'), 'woocommerce:primary')
    await settle()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-currency"]'), 'IRR')
    await settle()
    expect((c.querySelector('[data-testid="pricing-unit-editor-unit"]') as HTMLSelectElement).value).toBe('')
    expect(c.querySelector('[data-testid="pricing-unit-editor-unit-error"]')?.textContent).toContain('explicitly')
    const submit = c.querySelector('[data-testid="pricing-unit-editor-submit"]') as HTMLButtonElement
    expect(submit.disabled).toBe(true)
  })

  it('auto-fills the unit for a supported non-IRR currency without treating it as inference', async () => {
    stubFetch(() => json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null }))
    const c = await renderPage()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-scope-reference"]'), 'woocommerce:primary')
    await settle()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-currency"]'), 'USD')
    await settle()
    expect((c.querySelector('[data-testid="pricing-unit-editor-unit"]') as HTMLInputElement).value).toBe('USD')
  })

  it('rejects an unsupported currency/unit pair before submit', async () => {
    stubFetch(() => json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null }))
    const c = await renderPage()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-scope-reference"]'), 'woocommerce:primary')
    await settle()
    // SUPPORTED_CURRENCIES only lists supported codes, so simulate an out-of-list value directly.
    const currencySelect = c.querySelector('[data-testid="pricing-unit-editor-currency"]') as HTMLSelectElement
    const option = document.createElement('option')
    option.value = 'GBP'
    currencySelect.appendChild(option)
    setValue(currencySelect, 'GBP')
    await settle()
    const submit = c.querySelector('[data-testid="pricing-unit-editor-submit"]') as HTMLButtonElement
    expect(submit.disabled).toBe(true)
  })

  it('shows the current resolved/unresolved state before editing', async () => {
    stubFetch(() => json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null }))
    const c = await renderPage()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-scope-reference"]'), 'woocommerce:primary')
    await settle()
    expect(c.querySelector('[data-testid="pricing-unit-editor-current-state"]')?.textContent).toContain('Unresolved')
  })

  it('shows a distinct permission-denied state on 403', async () => {
    stubFetch((_url, method) => {
      if (method === 'PUT') return json({ detail: { code: 'forbidden' } }, 403)
      return json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null })
    })
    const c = await renderPage()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-scope-reference"]'), 'woocommerce:primary')
    await settle()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-currency"]'), 'USD')
    setValue(c.querySelector('[data-testid="pricing-unit-editor-connector-config-version"]'), 'v1')
    const submit = c.querySelector('[data-testid="pricing-unit-editor-submit"]') as HTMLButtonElement
    await act(async () => { submit.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    expect(c.querySelector('[data-testid="pricing-permission-denied"]')).not.toBeNull()
  })

  it('localizes the editor in Persian', async () => {
    await changeLocale('fa')
    stubFetch(() => json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null }))
    const c = await renderPage()
    expect(c.textContent).toContain('اعلام واحد ارزی')
  })
})

// -- UI Stage 5: RTL, responsive, theme, accessibility, keyboard ---------------

describe('PricingUnitEditor — RTL, responsive, and accessibility (UI Stage 5)', () => {
  it('sets document direction to rtl in Persian', async () => {
    await changeLocale('fa')
    stubFetch(() => json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null }))
    await renderPage()
    expect(document.documentElement.dir).toBe('rtl')
  })

  it('lays out the declaration fields as a responsive two-column grid from tablet up', async () => {
    stubFetch(() => json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null }))
    const c = await renderPage()
    const grid = c.querySelector('[data-testid="pricing-unit-editor-scope"]')?.closest('.fh-form-grid')
    expect(grid?.className).toContain('md:grid-cols-2')
  })

  it('keeps the submit action bar wrappable instead of clipped', async () => {
    stubFetch(() => json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null }))
    const c = await renderPage()
    const actions = c.querySelector('[data-testid="pricing-unit-editor-actions"]')
    expect(actions?.className).toContain('flex-wrap')
  })

  it('associates the scope-reference, currency, unit, and connector-config-version errors with their fields', async () => {
    stubFetch(() => json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null }))
    const c = await renderPage()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-scope-reference"]'), 'woocommerce:primary')
    await settle()
    setValue(c.querySelector('[data-testid="pricing-unit-editor-currency"]'), 'IRR')
    await settle()

    const unitSelect = c.querySelector('[data-testid="pricing-unit-editor-unit"]') as HTMLSelectElement
    expect(unitSelect.getAttribute('aria-invalid')).toBe('true')
    const describedBy = unitSelect.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    expect(c.querySelector(`[id="${describedBy}"]`)?.textContent).toBeTruthy()
  })

  it('does not show "required" errors on a pristine, untouched form (UI Stage 6 fix)', async () => {
    stubFetch(() => json({ scope: 'channel', scopeReference: 'woocommerce:primary', status: 'unresolved', currency: null, unit: null }))
    const c = await renderPage()
    expect(c.textContent).not.toContain('This field is required')
    const submit = c.querySelector('[data-testid="pricing-unit-editor-submit"]') as HTMLButtonElement
    expect(submit.disabled).toBe(true)
  })
})
