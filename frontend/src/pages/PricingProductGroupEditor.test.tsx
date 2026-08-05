// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import PricingProductGroupEditor from './PricingProductGroupEditor'
import { changeLocale } from '../i18n'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

const existingRevision = {
  id: 'grp-rev-1', productGroupId: 'grp-1', revisionNumber: 1, name: 'Mobile accessories',
  canonicalProductIds: ['prod-1', 'prod-2'], checksum: 'sum-1', createdAt: '2026-08-05T00:00:00Z',
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
      <MemoryRouter initialEntries={['/settings/pricing/product-groups/new']}>
        <Routes>
          <Route path="/settings/pricing/product-groups/new" element={<PricingProductGroupEditor />} />
        </Routes>
      </MemoryRouter>,
    )
  })
  await settle()
  return container
}

async function renderNextRevision() {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/settings/pricing/product-groups/grp-rev-1/new-revision']}>
        <Routes>
          <Route path="/settings/pricing/product-groups/:revisionId/new-revision" element={<PricingProductGroupEditor />} />
        </Routes>
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
  const input = el as HTMLInputElement
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
  setter.call(input, value)
  input.dispatchEvent(new Event('change', { bubbles: true }))
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

describe('PricingProductGroupEditor', () => {
  it('creates a new product group revision and shows a success state', async () => {
    stubFetch((url, method) => {
      if (method === 'POST' && url.endsWith('/pricing-matrix/product-groups')) return json({ ...existingRevision, revisionNumber: 1 })
      return json({ items: [] })
    })
    const c = await renderNew()
    setValue(c.querySelector('#group-name'), 'Mobile accessories')
    setValue(c.querySelector('[data-testid="pricing-product-group-editor-member-0"]'), 'prod-1')

    const submit = c.querySelector('[data-testid="pricing-product-group-editor-submit"]') as HTMLButtonElement
    await act(async () => { submit.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()

    expect(c.querySelector('[data-testid="pricing-product-group-editor-success"]')).not.toBeNull()
    expect(c.textContent).toContain('Create next revision')
  })

  it('prefills members from an existing revision, explaining reuse', async () => {
    stubFetch((url, method) => {
      if (method === 'GET' && url.endsWith('/pricing-matrix/product-groups/grp-rev-1')) return json(existingRevision)
      return json({ items: [] })
    })
    const c = await renderNextRevision()
    expect(c.textContent).toContain('reuses the existing product group identity')
    expect((c.querySelector('[data-testid="pricing-product-group-editor-member-0"]') as HTMLInputElement).value).toBe('prod-1')
    expect((c.querySelector('[data-testid="pricing-product-group-editor-member-1"]') as HTMLInputElement).value).toBe('prod-2')
    expect((c.querySelector('[data-testid="pricing-product-group-editor-group-id"]') as HTMLInputElement).disabled).toBe(true)
  })

  it('flags a duplicate canonical product identifier and preserves both entries', async () => {
    stubFetch(() => json({ items: [] }))
    const c = await renderNew()
    setValue(c.querySelector('#group-name'), 'X')
    const addMember = c.querySelector('[data-testid="pricing-product-group-editor-add-member"]') as HTMLButtonElement
    await act(async () => { addMember.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    setValue(c.querySelector('[data-testid="pricing-product-group-editor-member-0"]'), 'prod-1')
    setValue(c.querySelector('[data-testid="pricing-product-group-editor-member-1"]'), 'prod-1')
    await settle()

    expect(c.querySelector('[data-testid="pricing-product-group-editor-member-1-error"]')).not.toBeNull()
    const submit = c.querySelector('[data-testid="pricing-product-group-editor-submit"]') as HTMLButtonElement
    expect(submit.disabled).toBe(true)
    expect((c.querySelector('[data-testid="pricing-product-group-editor-member-0"]') as HTMLInputElement).value).toBe('prod-1')
    expect((c.querySelector('[data-testid="pricing-product-group-editor-member-1"]') as HTMLInputElement).value).toBe('prod-1')
  })

  it('shows a distinct not-found state (404)', async () => {
    stubFetch((url, method) => {
      if (method === 'GET' && url.endsWith('/pricing-matrix/product-groups/grp-rev-1')) return json({ detail: { code: 'product_group_revision_not_found' } }, 404)
      return json({ items: [] })
    })
    const c = await renderNextRevision()
    expect(c.querySelector('[data-testid="pricing-not-found"]')).not.toBeNull()
  })

  it('shows a distinct unavailable state and preserves entered members after a 500', async () => {
    stubFetch((url, method) => {
      if (method === 'POST' && url.endsWith('/pricing-matrix/product-groups')) return json({ detail: 'down' }, 500)
      return json({ items: [] })
    })
    const c = await renderNew()
    setValue(c.querySelector('#group-name'), 'X')
    setValue(c.querySelector('[data-testid="pricing-product-group-editor-member-0"]'), 'prod-kept')
    const submit = c.querySelector('[data-testid="pricing-product-group-editor-submit"]') as HTMLButtonElement
    await act(async () => { submit.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    expect(c.querySelector('[data-testid="pricing-unavailable"]')).not.toBeNull()
    expect((c.querySelector('[data-testid="pricing-product-group-editor-member-0"]') as HTMLInputElement).value).toBe('prod-kept')
  })

  it('prevents a duplicate submit while saving', async () => {
    let postCalls = 0
    stubFetch((url, method) => {
      if (method === 'POST' && url.endsWith('/pricing-matrix/product-groups')) {
        postCalls += 1
        return json(existingRevision)
      }
      return json({ items: [] })
    })
    const c = await renderNew()
    setValue(c.querySelector('#group-name'), 'X')
    setValue(c.querySelector('[data-testid="pricing-product-group-editor-member-0"]'), 'prod-1')
    const submit = c.querySelector('[data-testid="pricing-product-group-editor-submit"]') as HTMLButtonElement
    await act(async () => {
      submit.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      submit.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await settle()
    expect(postCalls).toBeLessThanOrEqual(1)
  })

  it('localizes the editor in Persian', async () => {
    await changeLocale('fa')
    stubFetch(() => json({ items: [] }))
    const c = await renderNew()
    expect(c.textContent).toContain('ایجاد بازنگری گروه محصول')
  })
})

// -- UI Stage 5: RTL, responsive, theme, accessibility, keyboard ---------------

describe('PricingProductGroupEditor — RTL, responsive, and accessibility (UI Stage 5)', () => {
  it('sets document direction to rtl in Persian', async () => {
    await changeLocale('fa')
    stubFetch(() => json({ items: [] }))
    await renderNew()
    expect(document.documentElement.dir).toBe('rtl')
  })

  it('lays out the identity fields as a responsive two-column grid from tablet up', async () => {
    stubFetch(() => json({ items: [] }))
    const c = await renderNew()
    const grid = c.querySelector('#group-name')?.closest('.fh-form-grid')
    expect(grid?.className).toContain('md:grid-cols-2')
  })

  it('keeps the submit action bar wrappable instead of clipped', async () => {
    stubFetch(() => json({ items: [] }))
    const c = await renderNew()
    const actions = c.querySelector('[data-testid="pricing-product-group-editor-actions"]')
    expect(actions?.className).toContain('flex-wrap')
  })

  it('associates the name field and each member field with its error via aria-describedby', async () => {
    stubFetch(() => json({ items: [] }))
    const c = await renderNew()
    const addMember = c.querySelector('[data-testid="pricing-product-group-editor-add-member"]') as HTMLButtonElement
    await act(async () => { addMember.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    setValue(c.querySelector('[data-testid="pricing-product-group-editor-member-0"]'), 'dup')
    setValue(c.querySelector('[data-testid="pricing-product-group-editor-member-1"]'), 'dup')
    await settle()

    const member1 = c.querySelector('[data-testid="pricing-product-group-editor-member-1"]') as HTMLInputElement
    expect(member1.getAttribute('aria-invalid')).toBe('true')
    const describedBy = member1.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    expect(c.querySelector(`[id="${describedBy}"]`)?.textContent).toBeTruthy()
  })

  it('preserves a very long English and Persian product group name without clipping', async () => {
    stubFetch(() => json({ items: [] }))
    const c = await renderNew()
    const longEnglish = 'Mobile Accessories Retail Bundle '.repeat(10).trim()
    setValue(c.querySelector('#group-name'), longEnglish)
    expect((c.querySelector('#group-name') as HTMLInputElement).value).toBe(longEnglish)

    await changeLocale('fa')
    const longPersian = 'بسته‌ی لوازم جانبی موبایل برای فروش خرده‌فروشی '.repeat(3).trim()
    setValue(c.querySelector('#group-name'), longPersian)
    expect((c.querySelector('#group-name') as HTMLInputElement).value).toBe(longPersian)
  })
})
