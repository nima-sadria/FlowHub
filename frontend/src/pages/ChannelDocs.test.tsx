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
  })

  it('renders the selected API document with a searchable content view', () => {
    renderDocs('/docs/channels/technolife')

    expect(container.textContent).toContain('API تکنولایف')
    expect(container.textContent).toContain('۴ — قیمت‌گذاری')
    expect(container.querySelector('input[type="search"]')?.getAttribute('aria-label')).toBe('جست‌وجو در مستندات')
  })
})
