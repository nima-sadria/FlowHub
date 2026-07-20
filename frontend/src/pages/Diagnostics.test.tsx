// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { NotificationProvider } from '../notifications/NotificationProvider'
import NotificationContainer from '../notifications/NotificationContainer'
import Diagnostics from './Diagnostics'
import { changeLocale } from '../i18n'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const user: AuthUser = {
  username: 'admin',
  role: 'admin',
  is_admin: true,
  is_super_admin: false,
  permissions: { can_access_site: true, can_fetch: true, can_view_settings: true },
}

function authValue(authUser: AuthUser = user): AuthContextValue {
  return {
    user: authUser,
    status: 'authenticated',
    refreshUser: async () => undefined,
    clearAuth: () => undefined,
    logout: async () => undefined,
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
      checks: [{ category: 'database', target: 'flowhub', status: 'pass', severity: 'info' }],
      connectors: [
        { id: 'nextcloud:primary', name: 'Nextcloud', connector_type: 'nextcloud', enabled: true, status: 'operational', last_checked_at: new Date().toISOString(), last_successful_operation: new Date().toISOString() },
        { id: 'woocommerce:primary', name: 'WooCommerce duplicate', connector_type: 'woocommerce', enabled: true, status: 'operational', last_checked_at: new Date().toISOString() },
      ],
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
    orderSyncRunner: { state: 'running', lastHeartbeat: new Date().toISOString() },
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

afterEach(async () => {
  act(() => { root.unmount() })
  container.remove()
  vi.unstubAllGlobals()
  await changeLocale('en')
})

async function renderPage(authUser: AuthUser = user) {
  await act(async () => {
    root.render(
      <NotificationProvider>
        <AuthContext.Provider value={authValue(authUser)}>
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
  it.each([
    ['pass', 'Healthy'],
    ['skip', 'Not checked yet'],
    ['fail', 'Error'],
    ['unexpected', 'Not checked yet'],
  ])('derives the Database summary from a %s diagnostic check', async (databaseCheckStatus, expectedLabel) => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: databaseCheckStatus === 'pass' ? 'ok' : 'skip',
          checkedAt: new Date().toISOString(),
          checks: [{ check_name: 'database_connection', category: 'database', target: 'flowhub', status: databaseCheckStatus, severity: 'info' }],
          connectors: [],
          channelHealth: channelHealthPayload(),
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const databaseCard = Array.from(c.querySelectorAll('[data-testid="diagnostics-summary-card"]'))
      .find(card => card.textContent?.includes('Database'))

    expect(databaseCard?.textContent).toContain(expectedLabel)
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(call => String(call[0]))
    expect(calls.some(url => url.includes('/api/health'))).toBe(false)
  })

  it('shows Database as not checked when diagnostics provide no database evidence', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'ok',
          checkedAt: new Date().toISOString(),
          checks: [{ check_name: 'source_snapshot', category: 'data_layer', target: 'nextcloud', status: 'pass', severity: 'info' }],
          connectors: [],
          channelHealth: channelHealthPayload(),
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const databaseCard = Array.from(c.querySelectorAll('[data-testid="diagnostics-summary-card"]'))
      .find(card => card.textContent?.includes('Database'))

    expect(databaseCard?.textContent).toContain('Not checked yet')
    expect(databaseCard?.textContent).toContain('No database diagnostic check was reported.')
    expect(databaseCard?.textContent).not.toContain('Connected')
  })

  it('does not hide a verified failing non-database diagnostic check', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'ok',
          checkedAt: new Date().toISOString(),
          checks: [
            { category: 'database', status: 'pass' },
            { category: 'background_jobs', status: 'fail' },
          ],
          connectors: [],
          channelHealth: channelHealthPayload(),
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const systemCard = Array.from(c.querySelectorAll('[data-testid="diagnostics-summary-card"]'))
      .find(card => card.textContent?.includes('System status'))

    expect(systemCard?.textContent).toContain('Error')
  })

  it('does not hide a verified Source connection failure in the System status', async () => {
    const health = channelHealthPayload()
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'ok',
          checkedAt: new Date().toISOString(),
          checks: [{ category: 'database', status: 'pass' }],
          connectors: [{
            id: 'nextcloud:primary', name: 'Nextcloud', connector_type: 'nextcloud', enabled: true,
            status: 'unhealthy', error: 'Connection verification failed.', last_checked_at: new Date().toISOString(),
          }],
          channelHealth: {
            ...health,
            summary: { overall: 'Operational', overall_state: 'HEALTHY', counts: { Operational: 1 } },
            items: [health.items[0]],
          },
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const systemCard = Array.from(c.querySelectorAll('[data-testid="diagnostics-summary-card"]'))
      .find(card => card.textContent?.includes('System status'))

    expect(systemCard?.textContent).toContain('Error')
  })

  it('does not describe disabled or never-checked Sources as ready', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'skip',
          checkedAt: new Date().toISOString(),
          checks: [],
          connectors: [
            { id: 'nextcloud:ready', name: 'Ready Source', connector_type: 'nextcloud', enabled: true, status: 'healthy', last_checked_at: new Date().toISOString() },
            { id: 'csv:disabled', name: 'Disabled Source', connector_type: 'csv', enabled: false, status: 'disabled', last_checked_at: null },
            { id: 'gsheets:pending', name: 'Unchecked Source', connector_type: 'gsheets', enabled: true, status: 'operational', last_checked_at: null },
            { id: 'erp:pending', name: 'Pending Source', connector_type: 'erp', enabled: true, status: 'pending', last_checked_at: new Date().toISOString() },
          ],
          channelHealth: channelHealthPayload(),
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const sourceCards = Array.from(c.querySelectorAll('article'))
    const ready = sourceCards.find(card => card.textContent?.includes('Ready Source'))
    const disabled = sourceCards.find(card => card.textContent?.includes('Disabled Source'))
    const unchecked = sourceCards.find(card => card.textContent?.includes('Unchecked Source'))
    const pending = sourceCards.find(card => card.textContent?.includes('Pending Source'))

    expect(ready?.textContent).toContain('Source connection is ready.')
    expect(disabled?.textContent).toContain('This Source is disabled. Enable it before running a connection check.')
    expect(disabled?.textContent).not.toContain('Source connection is ready.')
    expect(unchecked?.textContent).toContain('No connection check has been recorded for this Source.')
    expect(unchecked?.textContent).not.toContain('Source connection is ready.')
    expect(pending?.textContent).toContain('A conclusive Source connection result is not available yet.')
    expect(pending?.textContent).not.toContain('Source connection is ready.')

    const sourcesSummary = Array.from(c.querySelectorAll('[data-testid="diagnostics-summary-card"]'))
      .find(card => card.textContent?.includes('Sources'))
    expect(sourcesSummary?.textContent).toContain('1 of 4 ready')
  })

  it('localizes truthful Source states in Persian', async () => {
    await changeLocale('fa')
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'skip',
          checkedAt: new Date().toISOString(),
          checks: [],
          connectors: [
            { id: 'csv:disabled', name: 'CSV', connector_type: 'csv', enabled: false, status: 'disabled', last_checked_at: null },
            { id: 'gsheets:pending', name: 'Google Sheets', connector_type: 'gsheets', enabled: true, status: 'degraded', last_checked_at: null },
          ],
          channelHealth: { ...channelHealthPayload(), items: [] },
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    expect(c.textContent).toContain('این منبع غیرفعال است. برای بررسی اتصال، ابتدا آن را فعال کنید.')
    expect(c.textContent).toContain('هنوز بررسی اتصالی برای این منبع ثبت نشده است.')
    expect(c.textContent).not.toContain('اتصال منبع آماده است.')
  })

  it('localizes API errors and known diagnostic prose in Persian', async () => {
    await changeLocale('fa')
    let diagnosticsCalls = 0
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/diagnostics/status') && diagnosticsCalls++ === 0) {
        return new Response(JSON.stringify({ detail: 'temporary failure' }), { status: 401 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    expect(c.textContent).toContain('بخش عیب‌یابی در دسترس نیست (HTTP 401)')
    expect(c.textContent).not.toContain('Diagnostics unavailable')
    await changeLocale('en')
  })

  it('renders normalized channel health and refreshes one channel', async () => {
    const c = await renderPage()
    expect(c.textContent).toContain('Channels')
    expect(c.textContent).toContain('WooCommerce')
    expect(c.textContent).toContain('TapsiShop')
    expect(c.textContent).toContain('Accepted webhook receipts are waiting for processing.')
    expect(c.textContent).toContain('System status')
    expect(c.textContent).toContain('Sources')
    expect(c.textContent).toContain('Database')
    expect(c.textContent).toContain('Background jobs')
    expect(c.textContent).toContain('Recent failures')
    expect(c.textContent).toContain('Nextcloud')
    expect(c.textContent).not.toContain('WooCommerce duplicate')

    const technicalDetails = c.querySelector('[data-testid="diagnostics-details-woocommerce:primary"]') as HTMLDetailsElement
    expect(technicalDetails.open).toBe(false)
    expect(c.textContent).not.toContain('About')

    const refresh = Array.from(c.querySelectorAll('button')).find(button => button.textContent?.includes('Test connection'))
    await act(async () => {
      refresh?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(call => String(call[0]))
    expect(calls.some(url => url.includes('/api/v2/diagnostics/channels/health/refresh'))).toBe(true)
  })

  it('orders Source and Channel diagnostics with the shared policy', async () => {
    const health = channelHealthPayload()
    const disabledChannel = {
      ...health.items[0],
      channelId: 'snappshop:main',
      channelType: 'snappshop',
      enabled: false,
      status: 'Disabled',
      summary: 'SnappShop is disabled.',
    }
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'skip',
          checkedAt: new Date().toISOString(),
          checks: [],
          connectors: [
            { id: 'nextcloud:disabled', name: 'Nextcloud', connector_type: 'nextcloud', enabled: false, status: 'disabled', last_checked_at: null },
            { id: 'erp:warning', name: 'ERP', connector_type: 'erp', enabled: true, status: 'degraded', last_checked_at: new Date().toISOString() },
            { id: 'gsheets:healthy', name: 'Google Sheets', connector_type: 'gsheets', enabled: true, status: 'operational', last_checked_at: new Date().toISOString(), last_successful_operation: new Date().toISOString() },
            { id: 'csv:healthy', name: 'CSV', connector_type: 'csv', enabled: true, status: 'healthy', last_checked_at: new Date().toISOString(), last_successful_operation: new Date().toISOString() },
          ],
          channelHealth: { ...health, items: [disabledChannel, health.items[1], health.items[0]] },
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const channelSection = c.querySelector('#diagnostics-channels')?.closest('section')
    const sourceSection = c.querySelector('#diagnostics-sources')?.closest('section')
    const resourceIds = (scope: Element | null | undefined) => Array.from(scope?.querySelectorAll<HTMLElement>('[data-resource-id]') ?? [])
      .map(element => element.dataset.resourceId)

    expect(resourceIds(channelSection)).toEqual([
      'woocommerce:primary',
      'tapsishop:main',
      'snappshop:main',
    ])
    expect(resourceIds(sourceSection)).toEqual([
      'csv:healthy',
      'gsheets:healthy',
      'erp:warning',
      'nextcloud:disabled',
    ])
    expect(channelSection?.querySelectorAll('[data-resource-section="comingSoon"]')).toHaveLength(0)
    expect(sourceSection?.querySelectorAll('[data-resource-section="comingSoon"]')).toHaveLength(0)
  })

  it('uses evidence semantics for Source badges instead of treating a missing check as warning', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'skip',
          checkedAt: new Date().toISOString(),
          checks: [{ category: 'database', status: 'pass' }],
          connectors: [{
            id: 'nextcloud:primary',
            name: 'Nextcloud',
            connector_type: 'nextcloud',
            enabled: true,
            status: 'degraded',
            last_checked_at: null,
          }],
          channelHealth: channelHealthPayload(),
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const sourceStatus = c.querySelector('[data-testid="diagnostics-source-status-nextcloud:primary"]')

    expect(sourceStatus?.getAttribute('data-diagnostic-state')).toBe('NOT_CHECKED')
    expect(sourceStatus?.textContent).toContain('Not checked yet')
    expect(sourceStatus?.textContent).not.toContain('Needs attention')
  })

  it('presents practical rate-limit information before technical details', async () => {
    const c = await renderPage()

    expect(c.textContent).toContain('Requests available now')
    expect(c.textContent).toContain('Available now')
    expect(c.textContent).toContain('Requests allowed per minute')
    expect(c.textContent).toContain('60 read / 30 write')
    expect(c.textContent).toContain('No wait expected')
    expect(c.textContent).toContain('No throttling recorded')

    const rateDetails = Array.from(c.querySelectorAll('details')).find(details => details.textContent?.includes('Technical rate details'))
    expect(rateDetails?.open).toBe(false)
  })

  it('explains unavailable rate-limit evidence instead of showing healthy zero values', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'skip',
          checkedAt: new Date().toISOString(),
          checks: [],
          connectors: [],
          channelHealth: channelHealthPayload(),
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()

    expect(c.textContent).toContain('Rate-limit data has not been reported yet.')
    expect(c.textContent).not.toContain('0 read / 0 write')
    expect(c.textContent).not.toContain('No wait expected')
    expect(c.textContent).not.toContain('No throttling recorded')
  })

  it('does not expose the admin-only provider refresh action to a non-admin viewer', async () => {
    const viewer: AuthUser = {
      ...user,
      role: 'user',
      is_admin: false,
    }

    const c = await renderPage(viewer)
    const refreshButtons = Array.from(c.querySelectorAll('button')).filter(button => button.textContent?.trim() === 'Refresh')

    expect(refreshButtons).toHaveLength(0)
    expect(c.textContent).toContain('WooCommerce')
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
      .filter(alert => alert.textContent?.includes('Diagnostics updated'))
    expect(refreshedToasts).toHaveLength(1)
  })

  it('renders neutral missing, unused, and disabled evidence without warning leakage', async () => {
    const health = channelHealthPayload()
    const channel = {
      ...health.items[0],
      state: 'NOT_CHECKED',
      status: 'Not checked',
      reason_code: 'credentials_not_checked',
      checked_at: null,
      evidence_source: 'connector_health',
      is_actionable: true,
      recommended_action: 'Run connection test',
      lastSuccessfulVerification: null,
      lastSuccessfulSyncOrRead: health.items[0].lastSuccessfulOperation,
      dimensions: {
        configuration: {
          status: 'Operational', state: 'HEALTHY', reason_code: 'configuration_complete', checked_at: health.items[0].lastChecked,
          evidence_source: 'connector_settings', is_actionable: false, recommended_action: '', message: 'Required configuration is present.',
        },
        credentials: {
          status: 'Not checked', state: 'NOT_CHECKED', reason_code: 'credentials_not_checked', checked_at: null,
          evidence_source: 'connector_health', is_actionable: true, recommended_action: 'Run connection test', message: 'No credential verification has been recorded.',
        },
        externalApi: {
          status: 'Not applicable', state: 'NOT_APPLICABLE', reason_code: 'external_api_probe_not_applicable', checked_at: null,
          evidence_source: 'connector_registry', is_actionable: false, recommended_action: '', message: 'This connector does not provide a separate API health probe.',
        },
        webhookReceipt: {
          status: 'Not applicable', state: 'NOT_APPLICABLE', reason_code: 'webhook_not_applicable', checked_at: null,
          evidence_source: 'connector_registry', is_actionable: false, recommended_action: '', message: 'This Channel does not use webhooks.',
        },
        polling: {
          status: 'Disabled', state: 'DISABLED', reason_code: 'polling_disabled', checked_at: null,
          evidence_source: 'connector_settings', is_actionable: false, recommended_action: '', message: 'Order polling is turned off.',
        },
      },
    }
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'ok', checkedAt: health.checkedAt, checks: [{ category: 'database', status: 'pass' }], connectors: [],
          channelHealth: { ...health, summary: { overall: 'Not checked', overall_state: 'NOT_CHECKED', counts: {}, state_counts: { NOT_CHECKED: 1 } }, items: [channel] },
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const card = c.querySelector('[data-testid="diagnostics-channel-woocommerce:primary"]')
    expect(card?.querySelector('[data-testid="diagnostics-channel-status-woocommerce:primary"]')?.getAttribute('data-diagnostic-state')).toBe('NOT_CHECKED')
    expect(card?.textContent).toContain('Not checked yet')
    expect(card?.textContent).toContain('No credential verification has been recorded.')
    expect(card?.textContent).toContain('Run connection test')
    expect(card?.textContent).not.toContain('Warning')
    expect(card?.textContent).not.toContain('Unable to check')

    const details = c.querySelector('[data-testid="diagnostics-details-woocommerce:primary"]') as HTMLDetailsElement
    details.open = true
    expect(details.textContent).toContain('Connection')
    expect(details.textContent).toContain('Background processing')
    expect(details.querySelector('[data-testid="diagnostics-check-woocommerce:primary-externalApi"] [data-diagnostic-state="NOT_APPLICABLE"]')).not.toBeNull()
    expect(details.querySelector('[data-testid="diagnostics-check-woocommerce:primary-polling"] [data-diagnostic-state="DISABLED"]')).not.toBeNull()
  })

  it('keeps optional unsupported checks from lowering a healthy Channel', async () => {
    const health = channelHealthPayload()
    const channel = {
      ...health.items[0],
      state: 'HEALTHY',
      reason_code: 'channel_core_checks_healthy',
      evidence_source: 'channel_diagnostics',
      is_actionable: false,
      recommended_action: '',
      lastSuccessfulVerification: health.items[0].lastChecked,
      dimensions: {
        credentials: { status: 'Operational', state: 'HEALTHY', reason_code: 'credentials_verified', checked_at: health.items[0].lastChecked, evidence_source: 'connector_health', is_actionable: false, recommended_action: '', message: 'Credential verification passed.' },
        tokenRefresh: { status: 'Not applicable', state: 'NOT_APPLICABLE', reason_code: 'token_refresh_not_applicable', checked_at: null, evidence_source: 'connector_registry', is_actionable: false, recommended_action: '', message: 'This authentication method does not require token refresh.' },
        queueDeadLetter: { status: 'Not applicable', state: 'NOT_APPLICABLE', reason_code: 'dead_letter_queue_not_applicable', checked_at: null, evidence_source: 'connector_registry', is_actionable: false, recommended_action: '', message: 'This Channel does not use a dead-letter queue.' },
      },
    }
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'ok', checkedAt: health.checkedAt, checks: [{ category: 'database', status: 'pass' }], connectors: [],
          channelHealth: { ...health, summary: { overall: 'Operational', overall_state: 'HEALTHY', counts: {}, state_counts: { HEALTHY: 1 } }, items: [channel] },
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const card = c.querySelector('[data-testid="diagnostics-channel-woocommerce:primary"]')
    expect(card?.querySelector('[data-diagnostic-state="HEALTHY"]')).not.toBeNull()
    expect(card?.textContent).toContain('No action required')
    expect(card?.textContent).not.toContain('Needs attention')
  })

  it('localizes the seven-state Channel presentation in Persian without changing technical evidence IDs', async () => {
    await changeLocale('fa')
    const health = channelHealthPayload()
    const channel = {
      ...health.items[0], state: 'NOT_CHECKED', status: 'Not checked', reason_code: 'credentials_not_checked', checked_at: null,
      evidence_source: 'connector_health', is_actionable: true, recommended_action: 'Run connection test', lastSuccessfulVerification: null,
      dimensions: { credentials: { status: 'Not checked', state: 'NOT_CHECKED', reason_code: 'credentials_not_checked', checked_at: null, evidence_source: 'connector_health', is_actionable: true, recommended_action: 'Run connection test', message: '' } },
    }
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({ overall_status: 'ok', checkedAt: health.checkedAt, checks: [{ category: 'database', status: 'pass' }], connectors: [], channelHealth: { ...health, summary: { overall: 'Not checked', overall_state: 'NOT_CHECKED', counts: {} }, items: [channel] }, rateLimiter: null }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const card = c.querySelector('[data-testid="diagnostics-channel-woocommerce:primary"]')
    expect(card?.textContent).toContain('هنوز بررسی نشده')
    expect(card?.textContent).toContain('آزمایش اتصال را اجرا کنید')
    expect(card?.textContent).toContain('connector_health')
    expect(card?.textContent).not.toContain('Not checked')
    expect(card?.textContent).not.toContain('Run connection test')
  })

  it('clears a page-wide error after a successful Re-check', async () => {
    let diagnosticsCalls = 0
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/diagnostics/status')) {
        diagnosticsCalls += 1
        if (diagnosticsCalls === 1) {
          return new Response(JSON.stringify({ detail: 'temporary failure' }), { status: 500 })
        }
      }
      return responseFor(input as RequestInfo | URL)
    }))
    const c = await renderPage()
    expect(c.textContent).toContain('Diagnostics unavailable (HTTP 500)')

    const recheck = Array.from(c.querySelectorAll('button')).find(button => button.textContent?.includes('Re-check'))
    await act(async () => {
      recheck?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(c.querySelector('.fh-alert-danger')).toBeNull()
    expect(c.textContent).toContain('Channels')
    expect(c.textContent).toContain('WooCommerce')
  })
})
