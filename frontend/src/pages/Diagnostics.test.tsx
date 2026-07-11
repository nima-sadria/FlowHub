// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { NotificationProvider } from '../notifications/NotificationProvider'
import NotificationContainer from '../notifications/NotificationContainer'
import Diagnostics from './Diagnostics'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const user: AuthUser = {
  username: 'admin',
  role: 'admin',
  is_admin: true,
  is_super_admin: false,
  permissions: { can_access_site: true, can_fetch: true, can_view_settings: true },
}

function authValue(): AuthContextValue {
  return {
    user,
    status: 'authenticated',
    refreshUser: async () => undefined,
    clearAuth: () => undefined,
    authFetch: fetch,
  }
}

function responseFor(input: RequestInfo | URL): Response {
  const url = String(input)
  if (url.includes('/api/health')) {
    return new Response(JSON.stringify({ status: 'ok', version: '1.0.0' }), { status: 200 })
  }
  if (url.includes('/api/v2/diagnostics/status')) {
    return new Response(JSON.stringify({
      overall_status: 'ok',
      checkedAt: new Date().toISOString(),
      connectors: [],
      channelHealth: channelHealthPayload(),
      rateLimiter: {
        settings: {
          read_requests_per_minute: 60,
          write_requests_per_minute: 30,
          read_delay_ms: 1000,
          write_delay_ms: 2000,
        },
        queue_length: 0,
        average_request_duration_ms: null,
        average_latency_ms: null,
        estimated_completion_seconds: null,
      },
    }), { status: 200 })
  }
  if (url.includes('/api/v2/diagnostics/channels/health/refresh')) {
    return new Response(JSON.stringify(channelHealthPayload()), { status: 200 })
  }
  return new Response('{}', { status: 404 })
}

function channelHealthPayload() {
  return {
    checkedAt: new Date().toISOString(),
    summary: { overall: 'Warning', counts: { Operational: 1, Warning: 1, Error: 0, 'Unable to check': 0, Disabled: 1 } },
    external_call_performed: false,
    items: [
      {
        channelId: 'woocommerce:primary',
        channelType: 'woocommerce',
        enabled: true,
        accessMode: 'read_only',
        status: 'Operational',
        summary: 'WooCommerce is operational.',
        lastChecked: new Date().toISOString(),
        latency: 12,
        lastSuccessfulOperation: new Date().toISOString(),
        lastErrorCategory: null,
        capabilityState: { read_products: true, write_prices: true },
        nextRecommendedAction: 'No immediate action required.',
        dimensions: { credentials: { status: 'Operational', message: 'Credential validation passed.' } },
        lastProductRead: new Date().toISOString(),
        lastProductWrite: null,
        lastOrderSync: new Date().toISOString(),
        polling: { cursor: null, lastRunAt: null },
        webhooks: { supported: false, received: 0, queued: 0, processed: 0, deadLetter: 0, lastReceivedAt: null, lastProcessedAt: null },
      },
      {
        channelId: 'tapsishop:main',
        channelType: 'tapsishop',
        enabled: true,
        accessMode: 'read_only',
        status: 'Warning',
        summary: 'Accepted webhook receipts are waiting for processing.',
        lastChecked: new Date().toISOString(),
        latency: 24,
        lastSuccessfulOperation: new Date().toISOString(),
        lastErrorCategory: null,
        capabilityState: { read_products: true, write_prices: true, webhook: true },
        nextRecommendedAction: 'Review queued webhook receipts.',
        dimensions: { webhookProcessing: { status: 'Warning', message: 'Accepted webhook receipts are waiting for processing.' } },
        lastProductRead: new Date().toISOString(),
        lastProductWrite: null,
        lastOrderSync: new Date().toISOString(),
        polling: { cursor: null, lastRunAt: null },
        webhooks: { supported: true, received: 1, queued: 1, processed: 0, deadLetter: 0, lastReceivedAt: new Date().toISOString(), lastProcessedAt: null },
      },
    ],
  }
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  vi.stubGlobal('fetch', vi.fn(async input => responseFor(input as RequestInfo | URL)))
})

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
  vi.unstubAllGlobals()
})

async function renderPage() {
  await act(async () => {
    root.render(
      <NotificationProvider>
        <AuthContext.Provider value={authValue()}>
          <Diagnostics />
          <NotificationContainer />
        </AuthContext.Provider>
      </NotificationProvider>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return container
}

describe('Diagnostics', () => {
  it('renders normalized channel health and refreshes one channel', async () => {
    const c = await renderPage()
    expect(c.textContent).toContain('Channel Health')
    expect(c.textContent).toContain('WooCommerce')
    expect(c.textContent).toContain('TapsiShop')
    expect(c.textContent).toContain('Accepted webhook receipts are waiting for processing.')

    const refresh = Array.from(c.querySelectorAll('button')).find(button => button.textContent?.includes('Refresh'))
    await act(async () => {
      refresh?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(call => String(call[0]))
    expect(calls.some(url => url.includes('/api/v2/diagnostics/channels/health/refresh'))).toBe(true)
  })

  it('does not stack duplicate refreshed success toasts', async () => {
    const c = await renderPage()
    const recheck = Array.from(c.querySelectorAll('button')).find(button => button.textContent?.includes('Re-check'))

    await act(async () => {
      recheck?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })
    await act(async () => {
      recheck?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    const refreshedToasts = Array.from(c.querySelectorAll('[role="alert"]'))
      .filter(alert => alert.textContent?.includes('Diagnostics refreshed'))
    expect(refreshedToasts).toHaveLength(1)
  })
})
