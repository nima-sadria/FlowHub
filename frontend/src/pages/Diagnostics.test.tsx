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
  id: 1,
  username: 'admin',
  email: 'admin@example.com',
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
        { id: 'nextcloud:primary', name: 'Nextcloud', connector_type: 'nextcloud', enabled: true, status: 'operational', last_checked_at: new Date().toISOString(), last_successful_operation: new Date().toISOString(), connection_test_supported: true, connection_configured: true, credentials_configured: true },
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
  if (url.includes('/api/v2/commerce/channels/') && url.includes('/test')) {
    return new Response(JSON.stringify({
      ok: true,
      status: 'connected',
      message: 'Connected.',
      external_call_performed: true,
    }), { status: 200 })
  }
  if (url.includes('/api/v2/commerce/sources/nextcloud%3Aprimary/test')) {
    return new Response(JSON.stringify({
      ok: true,
      status: 'connected',
      message: 'Connected.',
      external_call_performed: true,
    }), { status: 200 })
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
        connectionTestSupported: true,
        credentialsConfigured: true,
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
        connectionTestSupported: true,
        credentialsConfigured: true,
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

function canonicalStateModel() {
  const now = new Date().toISOString()
  const capability = (freshness: string, outcome = 'SUCCESSFUL') => ({
    support: 'SUPPORTED_ENABLED', freshness,
    schedule: { mode: 'SCHEDULED', enabled: true, intervalSeconds: 3600, jitterSeconds: 0, policySource: 'test' },
    lastAttemptAt: now, lastSuccessAt: now, lastOutcome: outcome, nextExpectedAt: now,
    required: true, policy: { freshnessTtlSeconds: 7200, source: 'test' }, evidenceKey: 'test',
  })
  const channel = {
    id: 'woocommerce:primary', kind: 'CHANNEL', provider: 'woocommerce', displayName: 'WooCommerce', lifecycle: 'ACTIVE', enabled: true, configured: true, denominatorEligible: true,
    connectivity: { state: 'HEALTHY', freshness: 'FRESH', lastVerifiedAt: now, lastCheckedAt: now },
    readiness: { state: 'NEEDS_ATTENTION', reasonCode: 'product_sync_stale' }, freshness: { state: 'STALE' }, overallState: 'NEEDS_ATTENTION', reasonCode: 'product_sync_stale',
    recommendedAction: { code: 'NEXT_PRODUCT_SYNC_SCHEDULED', scheduledAt: now, actionable: true }, latestRelevantAt: now,
    capabilities: {
      connectionVerification: capability('FRESH'),
      productSynchronization: capability('STALE'),
      productCache: { ...capability('STALE'), cachedItemCount: 7597 },
      orderSynchronization: capability('FRESH'),
      webhookProcessing: { ...capability('NOT_APPLICABLE'), support: 'NOT_SUPPORTED', required: false },
      providerAcquisition: { ...capability('NOT_APPLICABLE'), support: 'NOT_SUPPORTED', required: false },
    },
    advancedEvidence: [{ key: 'data_layer_health', label: 'Connection health record', value: 'healthy', recordedAt: now }],
  }
  const archived = {
    ...channel, id: 'source-legacy', connectorId: 'nextcloud:legacy', kind: 'SOURCE', provider: 'nextcloud', displayName: 'Nextcloud — Archived legacy source', lifecycle: 'ARCHIVED', enabled: false, denominatorEligible: false,
    connectivity: { state: 'NOT_APPLICABLE', freshness: 'NOT_APPLICABLE', lastVerifiedAt: null, lastCheckedAt: null }, readiness: { state: 'ARCHIVED', reasonCode: 'source_archived' }, freshness: { state: 'NOT_APPLICABLE' }, overallState: 'ARCHIVED', reasonCode: 'source_archived', recommendedAction: { code: 'NO_ACTION_REQUIRED', scheduledAt: null, actionable: false },
  }
  const comingSoon = {
    ...channel, id: 'digikala:main', kind: 'CHANNEL', provider: 'digikala', displayName: 'Digikala', lifecycle: 'COMING_SOON', enabled: false, denominatorEligible: false,
    connectivity: { state: 'NOT_APPLICABLE', freshness: 'NOT_APPLICABLE', lastVerifiedAt: null, lastCheckedAt: null }, readiness: { state: 'COMING_SOON', reasonCode: 'channel_coming_soon' }, freshness: { state: 'NOT_APPLICABLE' }, overallState: 'COMING_SOON', reasonCode: 'channel_coming_soon', recommendedAction: { code: 'NO_ACTION_REQUIRED', scheduledAt: null, actionable: false },
  }
  return {
    schemaVersion: 'diagnostics-state-v1', generatedAt: now, overallState: 'NEEDS_ATTENTION',
    summary: { overallState: 'NEEDS_ATTENTION', channels: { ready: 0, operational: 1, needsAttention: 1, blocked: 0, disabled: 0, comingSoon: 1 }, sources: { ready: 0, active: 0, needsAttention: 0, blocked: 0, disabled: 0, archived: 1 } },
    resources: [channel, archived, comingSoon],
    backgroundJobs: [{ id: 'flowhub:order-sync-runner', displayName: 'Integration background runner', state: 'IDLE', health: 'HEALTHY', required: true, lastHeartbeatAt: now, heartbeatTtlSeconds: 180, runnerId: 'runner', lastSuccessfulJobAt: now, queueDepth: 0, lastFailureAt: null, lastFailureCode: null }],
    recentChecks: [
      { id: channel.id, kind: channel.kind, displayName: channel.displayName, provider: channel.provider, lifecycle: channel.lifecycle, connectivity: 'HEALTHY', readiness: 'NEEDS_ATTENTION', freshness: 'STALE', state: 'NEEDS_ATTENTION', reasonCode: 'product_sync_stale', recordedAt: now },
      { id: archived.id, kind: archived.kind, displayName: archived.displayName, provider: archived.provider, lifecycle: archived.lifecycle, connectivity: 'NOT_APPLICABLE', readiness: 'ARCHIVED', freshness: 'NOT_APPLICABLE', state: 'ARCHIVED', reasonCode: 'source_archived', recordedAt: now },
      { id: comingSoon.id, kind: comingSoon.kind, displayName: comingSoon.displayName, provider: comingSoon.provider, lifecycle: comingSoon.lifecycle, connectivity: 'NOT_APPLICABLE', readiness: 'COMING_SOON', freshness: 'NOT_APPLICABLE', state: 'COMING_SOON', reasonCode: 'channel_coming_soon', recordedAt: now },
    ],
    consumerStates: { diagnostics: 'NEEDS_ATTENTION', dashboard: 'NEEDS_ATTENTION', sidebar: 'NEEDS_ATTENTION' }, externalCallPerformed: false,
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
  ])('folds the Database summary from a %s diagnostic check into the Overall State', async (databaseCheckStatus, expectedLabel) => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: databaseCheckStatus === 'pass' ? 'ok' : 'skip',
          checkedAt: new Date().toISOString(),
          checks: [{ check_name: 'database_connection', category: 'database', target: 'flowhub', status: databaseCheckStatus, severity: 'info' }],
          connectors: [],
          channelHealth: { ...channelHealthPayload(), items: [] },
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const overallCard = Array.from(c.querySelectorAll('[data-testid="diagnostics-summary-card"]'))
      .find(card => card.textContent?.includes('Overall State'))

    expect(overallCard?.textContent).toContain(expectedLabel)
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(call => String(call[0]))
    expect(calls.some(url => url.includes('/api/health'))).toBe(false)
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
    const overallCard = Array.from(c.querySelectorAll('[data-testid="diagnostics-summary-card"]'))
      .find(card => card.textContent?.includes('Overall State'))

    expect(overallCard?.textContent).toContain('Error')
  })

  it('does not hide a verified Source connection failure in the Overall State', async () => {
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
    const overallCard = Array.from(c.querySelectorAll('[data-testid="diagnostics-summary-card"]'))
      .find(card => card.textContent?.includes('Overall State'))

    expect(overallCard?.textContent).toContain('Error')
  })

  it('does not describe disabled or never-checked Sources as ready, and reflects it in Source Checks', async () => {
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
          channelHealth: { ...channelHealthPayload(), items: [] },
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
    expect(disabled?.textContent).toContain('This Source is disabled. Enable and save it before running a connection check.')
    expect(disabled?.textContent).not.toContain('Source connection is ready.')
    expect(unchecked?.textContent).toContain('No connection check has been recorded for this Source.')
    expect(unchecked?.textContent).not.toContain('Source connection is ready.')
    expect(pending?.textContent).toContain('A conclusive Source connection result is not available yet.')
    expect(pending?.textContent).not.toContain('Source connection is ready.')

    const sourcesSummary = Array.from(c.querySelectorAll('[data-testid="diagnostics-summary-card"]'))
      .find(card => card.textContent?.includes('Source Checks'))
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
    expect(c.textContent).toContain('این منبع غیرفعال است. پیش از بررسی اتصال، آن را فعال و ذخیره کنید.')
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

  it('renders normalized channel health in the unified System health list and refreshes one channel', async () => {
    const c = await renderPage()
    expect(c.textContent).toContain('System health')
    expect(c.textContent).toContain('WooCommerce')
    expect(c.textContent).toContain('TapsiShop')
    expect(c.textContent).toContain('Accepted webhook receipts are waiting for processing.')
    expect(c.textContent).toContain('Overall State')
    expect(c.textContent).toContain('Source Checks')
    expect(c.textContent).toContain('Nextcloud')
    expect(c.textContent).not.toContain('WooCommerce duplicate')

    const technicalDetails = c.querySelector('[data-testid="diagnostics-details-woocommerce:primary"]') as HTMLDetailsElement
    expect(technicalDetails.open).toBe(false)
    expect(c.textContent).not.toContain('About')

    const refresh = c.querySelector('[data-testid="diagnostics-channel-test-woocommerce:primary"]') as HTMLButtonElement
    await act(async () => {
      refresh?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(call => String(call[0]))
    expect(calls.some(url => url.includes('/api/v2/commerce/channels/woocommerce%3Aprimary/test'))).toBe(true)
  })

  it('uses canonical provider icons and tests the saved Nextcloud connection from Diagnostics', async () => {
    const c = await renderPage()

    const wooCard = c.querySelector('[data-testid="diagnostics-channel-woocommerce:primary"]')
    const sourceCard = c.querySelector('[data-resource-id="nextcloud:primary"]')
    expect(wooCard?.querySelector('[data-brand-icon="/static/logos/brands/woocommerce.webp"]')).not.toBeNull()
    expect(sourceCard?.querySelector('[data-brand-icon="/static/logos/brands/nextcloud.webp"]')).not.toBeNull()

    const sourceTest = c.querySelector('[data-testid="diagnostics-source-test-nextcloud:primary"]') as HTMLButtonElement
    expect(sourceTest.disabled).toBe(false)
    await act(async () => {
      sourceTest.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(call => String(call[0]))
    expect(calls.some(url => url.includes('/api/v2/commerce/sources/nextcloud%3Aprimary/test'))).toBe(true)
  })

  it('surfaces an HTTP-200 channel connection failure without a generic success notice', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/commerce/channels/woocommerce%3Aprimary/test')) {
        return new Response(JSON.stringify({
          ok: false,
          status: 'authentication_rejected',
          message: 'WooCommerce rejected the credentials; token=owner-secret',
          external_call_performed: true,
          read_only: true,
          runtime_write_blocked: true,
          write_blocked: true,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const testButton = c.querySelector('[data-testid="diagnostics-channel-test-woocommerce:primary"]') as HTMLButtonElement
    await act(async () => {
      testButton.click()
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    })

    const failure = c.querySelector('[data-notification-type="error"]')
    expect(failure?.textContent).toContain('Unable to connect to the channel')
    expect(failure?.textContent).toContain('The saved credentials were rejected.')
    expect(failure?.textContent).not.toContain('WooCommerce rejected the credentials')
    expect(failure?.textContent).not.toContain('token=')
    expect(failure?.textContent).not.toContain('owner-secret')
    expect(c.textContent).not.toContain('Diagnostics updated')
  })

  it('localizes an HTTP-200 connection failure in Persian without exposing backend text or secrets', async () => {
    await changeLocale('fa')
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/commerce/channels/woocommerce%3Aprimary/test')) {
        return new Response(JSON.stringify({
          ok: false,
          status: 'error',
          code: 'AUTH_FAILED',
          error_class: 'authentication',
          message: 'WooCommerce rejected the credentials; token=owner-secret',
          external_call_performed: true,
          read_only: true,
          runtime_write_blocked: true,
          write_blocked: true,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const testButton = c.querySelector('[data-testid="diagnostics-channel-test-woocommerce:primary"]') as HTMLButtonElement
    await act(async () => {
      testButton.click()
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    })

    const failure = c.querySelector('[data-notification-type="error"]')
    expect(failure?.textContent).toContain('اتصال به کانال ممکن نشد')
    expect(failure?.textContent).toContain('اطلاعات ورود ذخیره‌شده پذیرفته نشد.')
    expect(failure?.textContent).not.toContain('WooCommerce rejected the credentials')
    expect(failure?.textContent).not.toContain('owner-secret')
    expect(failure?.textContent).not.toContain('token=')
  })

  it('surfaces an HTTP-200 Source connection failure without a generic success notice', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/api/v2/commerce/sources/nextcloud%3Aprimary/test')) {
        return new Response(JSON.stringify({
          ok: false,
          status: 'resource_not_found',
          message: 'The configured Nextcloud WebDAV spreadsheet was not found.',
          external_call_performed: true,
          read_only: true,
          runtime_write_blocked: true,
          write_blocked: true,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const testButton = c.querySelector('[data-testid="diagnostics-source-test-nextcloud:primary"]') as HTMLButtonElement
    await act(async () => {
      testButton.click()
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    })

    const failure = c.querySelector('[data-notification-type="error"]')
    expect(failure?.textContent).toContain('Unable to connect to the source')
    expect(failure?.textContent).toContain('The requested remote resource was not found.')
    expect(failure?.textContent).not.toContain('The configured Nextcloud WebDAV spreadsheet was not found.')
    expect(c.textContent).not.toContain('Diagnostics updated')
  })

  it('exposes Test connection for every current provider with a real probe', async () => {
    const health = channelHealthPayload()
    const woo = health.items[0]
    const tapsi = health.items[1]
    const channels = [
      woo,
      { ...woo, channelId: 'snappshop:main', channelType: 'snappshop', summary: 'SnappShop is operational.' },
      tapsi,
      { ...woo, channelId: 'technolife:main', channelType: 'technolife', summary: 'Technolife is operational.' },
    ]
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'ok',
          checkedAt: health.checkedAt,
          checks: [{ category: 'database', status: 'pass' }],
          connectors: [],
          channelHealth: { ...health, orderSyncRunner: undefined, items: channels },
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    for (const channelId of ['woocommerce:primary', 'snappshop:main', 'tapsishop:main', 'technolife:main']) {
      const button = c.querySelector(`[data-testid="diagnostics-channel-test-${channelId}"]`) as HTMLButtonElement
      expect(button).not.toBeNull()
      expect(button.disabled).toBe(false)
    }
    expect(c.querySelector('[data-testid="diagnostics-channel-technolife:main"] [data-brand-icon="/static/logos/brands/technolife.webp"]')).not.toBeNull()
    expect(c.querySelector('[data-testid="diagnostics-channel-snappshop:main"] [data-brand-icon="/static/logos/brands/snapp-shop.webp"]')).not.toBeNull()
    expect(c.querySelector('[data-testid="diagnostics-channel-tapsishop:main"] [data-brand-icon="/static/logos/brands/tapsi-shop.webp"]')).not.toBeNull()

    await act(async () => {
      const button = c.querySelector('[data-testid="diagnostics-channel-test-technolife:main"]') as HTMLButtonElement
      button.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(call => String(call[0]))
    expect(calls.some(url => url.includes('/api/v2/commerce/channels/technolife%3Amain/test'))).toBe(true)
  })

  it('does not test a disabled Source and explains that it must be enabled and saved first', async () => {
    const health = channelHealthPayload()
    const woo = health.items[0]
    const channels = [
      { ...woo, channelId: 'snappshop:main', channelType: 'snappshop', enabled: false, credentialsConfigured: true },
      { ...woo, channelId: 'tapsishop:main', channelType: 'tapsishop', enabled: true, credentialsConfigured: false },
      { ...woo, channelId: 'shopify:main', channelType: 'shopify', enabled: true, connectionTestSupported: false, credentialsConfigured: true },
    ]
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'skip',
          checkedAt: health.checkedAt,
          checks: [{ category: 'database', status: 'pass' }],
          connectors: [{
            id: 'nextcloud:primary', name: 'Nextcloud', connector_type: 'nextcloud', enabled: false,
            status: 'disabled', connection_test_supported: true, connection_configured: true, credentials_configured: true,
          }],
          channelHealth: { ...health, orderSyncRunner: undefined, items: channels },
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    expect((c.querySelector('[data-testid="diagnostics-channel-test-snappshop:main"]') as HTMLButtonElement).disabled).toBe(false)
    expect((c.querySelector('[data-testid="diagnostics-channel-test-tapsishop:main"]') as HTMLButtonElement).disabled).toBe(true)
    expect((c.querySelector('[data-testid="diagnostics-channel-test-shopify:main"]') as HTMLButtonElement).disabled).toBe(true)
    const disabledSourceTest = c.querySelector('[data-testid="diagnostics-source-test-nextcloud:primary"]') as HTMLButtonElement
    expect(disabledSourceTest.disabled).toBe(true)
    expect(c.querySelector('[data-testid="diagnostics-source-status-nextcloud:primary"]')?.textContent).toContain('Disabled')
    expect(c.textContent).toContain('This Source is disabled. Enable and save it before running a connection check.')
    expect(c.textContent).toContain('Save the required credentials before testing this connection.')
    expect(c.textContent).toContain('This connector does not support a connection test.')

    await act(async () => {
      disabledSourceTest.click()
      await Promise.resolve()
    })
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(call => String(call[0]))
    expect(calls.some(url => url.includes('/api/v2/commerce/sources/nextcloud%3Aprimary/test'))).toBe(false)
  })

  it('keeps an archived Source distinct from Disabled and blocks Diagnostics provider actions', async () => {
    const health = channelHealthPayload()
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'ok',
          checkedAt: health.checkedAt,
          checks: [{ category: 'database', status: 'pass' }],
          connectors: [{
            id: 'nextcloud:primary', name: 'Historical Nextcloud', connector_type: 'nextcloud', enabled: false,
            status: 'disabled', source_lifecycle_status: 'archived', source_archived_at: '2026-08-13T08:30:00Z',
            connection_test_supported: true, connection_configured: true, credentials_configured: true,
          }],
          channelHealth: { ...health, orderSyncRunner: undefined, items: [] },
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const source = c.querySelector('#source-nextcloud\\:primary') as HTMLElement
    expect(source.textContent).toContain('Archived')
    expect(source.textContent).not.toContain('Disabled')
    expect(source.textContent).toContain('archived and read-only')
    const testButton = source.querySelector('[data-testid="diagnostics-source-test-nextcloud:primary"]') as HTMLButtonElement
    expect(testButton.disabled).toBe(true)
    await act(async () => { testButton.click(); await Promise.resolve() })
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(call => String(call[0]))
    expect(calls.some(url => url.includes('/api/v2/commerce/sources/nextcloud%3Aprimary/test'))).toBe(false)
  })

  it('preserves an Owner-defined channel display name while localizing system defaults', async () => {
    const health = channelHealthPayload()
    const channels = [
      { ...health.items[0], displayName: 'ووکامرس' },
      { ...health.items[1], displayName: 'فروشگاه تهران' },
    ]
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'ok', checkedAt: health.checkedAt, checks: [{ category: 'database', status: 'pass' }], connectors: [],
          channelHealth: { ...health, orderSyncRunner: undefined, items: channels }, rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    expect(c.querySelector('[data-testid="diagnostics-channel-woocommerce:primary"]')?.textContent).toContain('WooCommerce')
    expect(c.querySelector('[data-testid="diagnostics-channel-tapsishop:main"]')?.textContent).toContain('فروشگاه تهران')
  })

  it('orders the unified System health list with errors and warnings first', async () => {
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
          channelHealth: { ...health, orderSyncRunner: undefined, items: [disabledChannel, health.items[1], health.items[0]] },
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const systemHealthSection = c.querySelector('#diagnostics-system-health')?.closest('section')
    const resourceIds = Array.from(systemHealthSection?.querySelectorAll<HTMLElement>('[data-resource-id]') ?? [])
      .map(element => element.dataset.resourceId)

    // Warning/error items (tapsishop:main, erp:warning) sort before healthy and
    // disabled/not-checked items; exact ties keep the shared ordering policy.
    expect(resourceIds.indexOf('tapsishop:main')).toBeLessThan(resourceIds.indexOf('woocommerce:primary'))
    expect(resourceIds.indexOf('erp:warning')).toBeLessThan(resourceIds.indexOf('csv:healthy'))
    expect(resourceIds.indexOf('erp:warning')).toBeLessThan(resourceIds.indexOf('nextcloud:disabled'))
    // 3 channels (disabledChannel, tapsishop, woocommerce) + 4 source connectors.
    expect(resourceIds).toHaveLength(7)
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
          channelHealth: { ...channelHealthPayload(), items: [] },
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

  it('renders readable SnappShop vendor warnings without hiding independent sync evidence', async () => {
    const health = channelHealthPayload()
    const verifiedAt = '2026-08-14T09:31:13Z'
    const syncAt = '2026-08-14T12:56:00Z'
    const providerMessage = 'Connection verified. Vendor status reported by SnappShop: REVIEW_REQUIRED.'
    const channel = {
      ...health.items[0],
      channelId: 'snappshop:main',
      channelType: 'snappshop',
      state: 'WARNING',
      status: 'Warning',
      reason_code: 'external_api_degraded',
      checked_at: verifiedAt,
      summary: providerMessage,
      lastSuccessfulVerification: verifiedAt,
      lastSuccessfulSyncOrRead: syncAt,
      lastSuccessfulOperation: syncAt,
      is_actionable: true,
      recommended_action: 'Review the connection details.',
      dimensions: {
        configuration: { status: 'Operational', state: 'HEALTHY', reason_code: 'configuration_complete', checked_at: verifiedAt, evidence_source: 'connector_settings', is_actionable: false, recommended_action: '', message: 'Required configuration is present.' },
        credentials: { status: 'Operational', state: 'HEALTHY', reason_code: 'credentials_verified', checked_at: verifiedAt, evidence_source: 'data_layer_health', is_actionable: false, recommended_action: '', message: 'Credentials were verified successfully.' },
        externalApi: { status: 'Warning', state: 'WARNING', reason_code: 'external_api_degraded', checked_at: verifiedAt, evidence_source: 'data_layer_health', is_actionable: true, recommended_action: 'Review the connection details.', message: providerMessage },
      },
    }
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'ok', checkedAt: health.checkedAt, checks: [{ category: 'database', status: 'pass' }], connectors: [],
          channelHealth: { ...health, summary: { overall: 'Warning', overall_state: 'WARNING', counts: {}, state_counts: { WARNING: 1 } }, items: [channel] },
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const card = c.querySelector('[data-testid="diagnostics-channel-snappshop:main"]')
    expect(card?.querySelector('[data-diagnostic-state="WARNING"]')).not.toBeNull()
    expect(card?.textContent).toContain(providerMessage)
    expect(card?.textContent).toContain('Last successful verification')
    expect(card?.textContent).toContain('Last successful sync or read')
    expect(card?.textContent).not.toContain('The API health check failed.')
    expect(card?.textContent).not.toContain('Never verified')
    expect(card?.textContent).not.toContain('No successful activity recorded')
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
    expect(c.textContent).toContain('System health')
    expect(c.textContent).toContain('WooCommerce')
  })

  it('shows a Recent checks panel sorted by most recently checked, and an urgent-item banner', async () => {
    const health = channelHealthPayload()
    const now = Date.now()
    const stale = { ...health.items[0], lastChecked: new Date(now - 60_000).toISOString() }
    const fresh = { ...health.items[1], lastChecked: new Date(now - 1_000).toISOString() }
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: 'ok', checkedAt: health.checkedAt, checks: [{ category: 'database', status: 'pass' }], connectors: [],
          channelHealth: { ...health, orderSyncRunner: undefined, items: [stale, fresh] },
          rateLimiter: null,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const recentSection = c.querySelector('#diagnostics-recent-checks')?.closest('section')
    const recentText = recentSection?.textContent ?? ''
    expect(recentText.indexOf('TapsiShop')).toBeLessThan(recentText.indexOf('WooCommerce'))
    expect(c.querySelector('.fh-alert-warning')?.textContent).toContain('Accepted webhook receipts are waiting for processing.')
  })

  it('renders canonical readiness, freshness, denominators, lifecycle groups, and advanced evidence', async () => {
    const model = canonicalStateModel()
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: model.overallState,
          checkedAt: model.generatedAt,
          checks: [],
          connectors: [],
          channelHealth: { ...channelHealthPayload(), stateModel: model },
          stateModel: model,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()

    expect(c.textContent).toContain('0 of 1 operational Channels ready')
    expect(c.textContent).toContain('1 Coming Soon')
    expect(c.textContent).toContain('1 Archived')
    expect(c.textContent).toContain('Operational readiness')
    expect(c.textContent).toContain('Product synchronization')
    expect(c.textContent).toContain('Stale')
    expect(c.textContent).toContain('7,597')
    expect(c.textContent).toContain('Historical Sources')
    expect(c.textContent).toContain('Nextcloud — Archived legacy source')
    expect(c.textContent).toContain('Non-operational Channels')
    expect(c.textContent).toContain('Advanced evidence')
    expect(c.textContent).not.toContain('All systems operational')
  })

  it('never presents an Archived or Coming Soon resource as Healthy in Recent Checks', async () => {
    const model = canonicalStateModel()
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/api/v2/diagnostics/status')) {
        return new Response(JSON.stringify({
          overall_status: model.overallState,
          checkedAt: model.generatedAt,
          checks: [],
          connectors: [],
          channelHealth: { ...channelHealthPayload(), stateModel: model },
          stateModel: model,
        }), { status: 200 })
      }
      return responseFor(input as RequestInfo | URL)
    }))

    const c = await renderPage()
    const recentSection = c.querySelector('#diagnostics-recent-checks')?.closest('section')
    const rows = Array.from(recentSection?.querySelectorAll('[data-diagnostic-state]') ?? [])
    const archivedRow = rows.find(row => row.closest('div')?.textContent?.includes('Archived legacy source'))
    const comingSoonRow = rows.find(row => row.closest('div')?.textContent?.includes('Digikala'))

    expect(archivedRow?.getAttribute('data-diagnostic-state')).not.toBe('HEALTHY')
    expect(comingSoonRow?.getAttribute('data-diagnostic-state')).not.toBe('HEALTHY')
  })
})
