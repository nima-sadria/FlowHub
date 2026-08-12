// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { changeLocale, translate } from '../i18n'
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

beforeEach(async () => {
  await changeLocale('en')
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(async () => {
  act(() => root.unmount())
  container.remove()
  await changeLocale('en')
})

describe('ChannelDocs', () => {
  it('lists all supported channel API documents', () => {
    renderDocs()

    expect(container.textContent).toContain('Channel API documentation')
    expect(container.textContent).toContain('SnappShop API')
    expect(container.textContent).toContain('TapsiShop API')
    expect(container.textContent).toContain('Technolife API')
    expect(container.textContent).toContain('WooCommerce API')
    expect(container.textContent).toContain('Digikala API')

    const digikala = container.querySelector('[data-testid="channel-docs-digikala"]')
    expect(digikala?.textContent).toContain('Coming Soon')
    expect(digikala?.textContent).toContain('Implementation unverified')
    expect(digikala?.textContent).toContain('no live Products or Orders sync')
    expect(digikala?.querySelector('img[alt="Digikala"]')).not.toBeNull()
  })

  it('renders the selected API document with a searchable content view', () => {
    renderDocs('/docs/channels/technolife')

    expect(container.textContent).toContain('Technolife API')
    expect(container.querySelector('input[type="search"]')?.getAttribute('aria-label')).toBe('Search documentation')
    expect(container.querySelectorAll('.fh-docs-section')).not.toHaveLength(0)
  })

  it('renders the WooCommerce API v3 document', () => {
    renderDocs('/docs/channels/woocommerce')

    expect(container.textContent).toContain('WooCommerce API')
    expect(container.querySelectorAll('.fh-docs-section')).not.toHaveLength(0)
  })

  it('renders the Digikala Marketplace API document without making it operational', () => {
    renderDocs('/docs/channels/digikala')

    expect(container.textContent).toContain('Digikala API')
    expect(container.textContent).toContain('Coming Soon')
    expect(container.querySelector('[data-testid="channel-configuration-dialog"]')).toBeNull()
    expect(container.querySelector('[data-testid="channel-docs-coming-soon-disclaimer"]')?.textContent).toContain('Implementation unverified')
    expect(container.querySelector('[data-testid="channel-docs-coming-soon-disclaimer"]')?.textContent).toContain('no live Products or Orders sync')
    expect(container.querySelector('img[alt="Digikala"]')).not.toBeNull()
    expect(container.querySelectorAll('.fh-docs-section')).not.toHaveLength(0)
    expect(container.textContent).not.toContain('Test connection')
    expect(container.textContent).not.toContain('Configure')
  })

  it('localizes the documentation shell while retaining all provider documentation', async () => {
    await changeLocale('fa')
    renderDocs()

    expect(container.textContent).toContain(translate('commerce:commerceHub.channelDocs.indexTitle'))
    expect(container.textContent).toContain(translate('commerce:commerceHub.channelDocs.digikala.title'))
    expect(container.textContent).toContain(translate('commerce:commerceHub.channelDocs.digikala.description'))
    expect(container.textContent).toContain(translate('commerce:commerceHub.channelDocs.digikala.disclaimer'))
  })
})
