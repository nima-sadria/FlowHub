// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { changeLocale } from '../i18n'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { ActivityEvent } from '../services/types'
import Activity from './Activity'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

describe('Activity business history', () => {
  let container: HTMLDivElement
  let root: ReturnType<typeof createRoot>
  const getEvents = vi.fn()

  beforeEach(async () => {
    await changeLocale('en')
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    const events: ActivityEvent[] = [
      { id: 'failure', timestamp: new Date(), kind: 'user_action', level: 'error', category: 'products', actor: 'owner', action: 'preview_failed', detail: 'fixture failure' },
      { id: 'token-1', timestamp: new Date(), kind: 'system_log', level: 'debug', category: 'system', actor: 'owner', action: 'token_refreshed', detail: null },
      { id: 'token-2', timestamp: new Date(), kind: 'system_log', level: 'debug', category: 'system', actor: 'owner', action: 'token_refreshed', detail: null },
    ]
    getEvents.mockResolvedValue({ items: events, total: 3, page: 1, pageSize: 30 })
  })

  afterEach(async () => {
    act(() => root.unmount())
    container.remove()
    getEvents.mockReset()
    await changeLocale('en')
  })

  async function render(path = '/activity') {
    const services = {
      activity: { getEvents },
      health: {}, products: {}, sources: {}, workspace: {}, settings: {},
      commerce: {}, writePipeline: {}, orders: {},
    } as unknown as Services
    await act(async () => {
      root.render(<MemoryRouter initialEntries={[path]}><ServiceProvider services={services}><Activity /></ServiceProvider></MemoryRouter>)
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  it('puts important business events first and groups repetitive token refresh entries', async () => {
    await render()
    expect(container.textContent).toContain('Important activity')
    expect(container.textContent).toContain('Product preview failed')
    expect(container.textContent).toContain('Routine system activity (1)')
    expect(container.textContent).toContain('2 successful routine events')
    expect(container.querySelectorAll('article')).toHaveLength(2)
    expect(getEvents.mock.calls[0][0].includeDebug).toBe(false)
  })

  it('reads a user filter from navigation and exposes categorized filters', async () => {
    await render('/activity?user=operator')
    expect(getEvents.mock.calls[0][0].username).toBe('operator')
    const category = Array.from(container.querySelectorAll('select')).find(select => select.textContent?.includes('Authentication'))
    expect(category).toBeTruthy()
    expect(container.textContent).toContain('Show routine and debug events')
    expect(container.textContent).toContain('Technical details')
  })
})
