// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth'
import { changeLocale } from '../i18n'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { ActivityEvent } from '../services/types'
import Activity from './Activity'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const admin: AuthContextValue = { user: { username: 'owner', role: 'admin', is_admin: true, is_super_admin: false, permissions: {} }, status: 'authenticated', refreshUser: async () => {}, clearAuth: () => {}, logout: async () => {}, authFetch: vi.fn().mockRejectedValue(new Error('not mocked in this test')) }

describe('Activity business history', () => {
  let container: HTMLDivElement
  let root: ReturnType<typeof createRoot>
  const getEvents = vi.fn()
  const getChannels = vi.fn()

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
    getChannels.mockResolvedValue({ items: [], relationship_map: { nodes: [], example: [], runtime_write_blocked: true, read_only: true } })
  })

  afterEach(async () => {
    act(() => root.unmount())
    container.remove()
    getEvents.mockReset()
    getChannels.mockReset()
    await changeLocale('en')
  })

  async function render(path = '/activity') {
    const services = {
      activity: { getEvents },
      commerce: { getChannels },
      health: {}, products: {}, sources: {}, workspace: {}, settings: {},
      writePipeline: {}, orders: {},
    } as unknown as Services
    await act(async () => {
      root.render(<AuthContext.Provider value={admin}><MemoryRouter initialEntries={[path]}><ServiceProvider services={services}><Activity /></ServiceProvider></MemoryRouter></AuthContext.Provider>)
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  it('puts important business events first and groups repetitive token refresh entries', async () => {
    await render()
    expect(container.textContent).toContain('Today')
    expect(container.textContent).toContain('Product preview failed')
    expect(container.textContent).toContain('Routine system activity (1)')
    expect(container.textContent).toContain('2 successful routine events')
    expect(container.querySelectorAll('article')).toHaveLength(2)
    expect(getEvents.mock.calls[0][0].includeDebug).toBe(false)
  })

  it('renders Business Observability fields on a business event row', async () => {
    const businessEvent: ActivityEvent = {
      id: 'business:evt-1',
      timestamp: new Date(),
      kind: 'business_event',
      level: 'error',
      category: 'apply',
      actor: 'Write Pipeline',
      action: 'write_batch_partially_failed',
      detail: '2 of 5 items failed',
      businessEventId: 'evt-1',
      businessImpact: 'partial_failure',
      status: 'open',
      recommendedAction: 'Review the failed items in this batch and retry them.',
      actionUrl: '/workspace',
      retryable: true,
    }
    getEvents.mockResolvedValueOnce({ items: [businessEvent], total: 1, page: 1, pageSize: 30 })

    await render()

    expect(container.textContent).toContain('Write Pipeline')
    expect(container.textContent).toContain('Open')
    expect(container.textContent).toContain('Review the failed items in this batch and retry them.')
    const link = container.querySelector('a[href="/workspace"]')
    expect(link).toBeTruthy()
  })

  it('reads a user filter from navigation and exposes categorized filters', async () => {
    await render('/activity?user=operator')
    expect(getEvents.mock.calls[0][0].username).toBe('operator')
    const category = Array.from(container.querySelectorAll('select')).find(select => select.textContent?.includes('Authentication'))
    expect(category).toBeTruthy()
    expect(container.textContent).toContain('Show routine and debug events')
    expect(container.textContent).toContain('Technical details')
  })

  it('exports the currently loaded events as CSV', async () => {
    await render()
    const originalCreateObjectURL = URL.createObjectURL
    const originalRevokeObjectURL = URL.revokeObjectURL
    const originalAnchorClick = HTMLAnchorElement.prototype.click
    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock')
    URL.revokeObjectURL = vi.fn()
    HTMLAnchorElement.prototype.click = vi.fn()
    try {
      const exportButton = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.includes('Export')) as HTMLButtonElement
      expect(exportButton).toBeTruthy()
      expect(exportButton.disabled).toBe(false)
      exportButton.click()
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
      const blob = (URL.createObjectURL as ReturnType<typeof vi.fn>).mock.calls[0][0] as Blob
      expect(blob.type).toContain('text/csv')
    } finally {
      URL.createObjectURL = originalCreateObjectURL
      URL.revokeObjectURL = originalRevokeObjectURL
      HTMLAnchorElement.prototype.click = originalAnchorClick
    }
  })

  it('shows a retryable error when Activity cannot be loaded', async () => {
    getEvents.mockRejectedValueOnce(new Error('offline'))
    await render()

    expect(container.querySelector('[role="alert"]')?.textContent).toContain('Activity could not be loaded')
    const retry = Array.from(container.querySelectorAll('button')).find(button => button.textContent === 'Retry') as HTMLButtonElement
    await act(async () => {
      retry.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(container.textContent).toContain('Product preview failed')
  })

  it('does not skip a page after loading more fails and the activity list is retried', async () => {
    const firstPage = Array.from({ length: 30 }, (_, index): ActivityEvent => ({
      id: `page-1-${index}`,
      timestamp: new Date(),
      kind: 'user_action',
      level: 'info',
      category: 'products',
      actor: 'owner',
      action: 'preview_completed',
      detail: null,
    }))
    const secondPage: ActivityEvent[] = [{
      id: 'page-2-event',
      timestamp: new Date(),
      kind: 'user_action',
      level: 'success',
      category: 'orders',
      actor: 'owner',
      action: 'sync_completed',
      detail: null,
    }]
    let secondPageAttempts = 0
    getEvents.mockImplementation(({ page, pageSize }: { page: number; pageSize: number }) => {
      if (pageSize === 1) return Promise.resolve({ items: [], total: 0, page, pageSize })
      if (page === 1) return Promise.resolve({ items: firstPage, total: 31, page, pageSize })
      if (page === 2 && secondPageAttempts++ === 0) return Promise.reject(new Error('offline'))
      if (page === 2) return Promise.resolve({ items: secondPage, total: 31, page, pageSize })
      return Promise.reject(new Error(`unexpected page ${page}`))
    })
    await render()

    const loadMore = () => Array.from(container.querySelectorAll('button')).find(button => button.textContent?.includes('Load more')) as HTMLButtonElement
    await act(async () => {
      loadMore().click()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(container.querySelector('[role="alert"]')?.textContent).toContain('Activity could not be loaded')

    const retry = Array.from(container.querySelectorAll('button')).find(button => button.textContent === 'Retry') as HTMLButtonElement
    await act(async () => {
      retry.click()
      await Promise.resolve()
      await Promise.resolve()
    })
    await act(async () => {
      loadMore().click()
      await Promise.resolve()
      await Promise.resolve()
    })

    const loadedPages = getEvents.mock.calls
      .map(([options]) => options)
      .filter(options => options.pageSize === 30)
      .map(options => options.page)
    expect(loadedPages).toEqual([1, 2, 1, 2])
    expect(container.textContent).toContain('Sync Completed')
  })
})
