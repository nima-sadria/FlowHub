// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import ChannelDocs from './ChannelDocs'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

function renderDocs(path = '/docs/channels') {
  act(() => root.render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/docs/channels" element={<ChannelDocs />} />
        <Route path="/docs/channels/:channelId" element={<ChannelDocs />} />
      </Routes>
    </MemoryRouter>,
  ))
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

describe('ChannelDocs', () => {
  it('lists all supported channel API documents', () => {
    renderDocs()

    expect(container.textContent).toContain('مستندات API کانال‌ها')
    expect(container.textContent).toContain('API اسنپ‌شاپ')
    expect(container.textContent).toContain('API تپسی‌شاپ')
    expect(container.textContent).toContain('API تکنولایف')
    expect(container.textContent).toContain('API ووکامرس')
    expect(container.textContent).toContain('API دیجی‌کالا')
  })

  it('renders the selected API document with a searchable content view', () => {
    renderDocs('/docs/channels/technolife')

    expect(container.textContent).toContain('API تکنولایف')
    expect(container.textContent).toContain('۴ — قیمت‌گذاری')
    expect(container.querySelector('input[type="search"]')?.getAttribute('aria-label')).toBe('جست‌وجو در مستندات')
  })

  it('renders the WooCommerce API v3 document', () => {
    renderDocs('/docs/channels/woocommerce')

    expect(container.textContent).toContain('API ووکامرس')
    expect(container.textContent).toContain('۱ — پیش‌نیازها و نشانی پایه')
    expect(container.textContent).toContain('۷ — وب‌هوک‌ها')
  })

  it('renders the Digikala Marketplace API document', () => {
    renderDocs('/docs/channels/digikala')

    expect(container.textContent).toContain('API دیجی‌کالا')
    expect(container.textContent).toContain('۱ — پیش‌نیازها و نشانی پایه')
    expect(container.textContent).toContain('۸ — وب‌هوک‌ها')
  })
})
