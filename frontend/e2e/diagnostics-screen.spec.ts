import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/Diagnostics hierarchy: header
// with Re-check, a compact 4-card KPI row (Overall State / Healthy Services /
// Channel Checks / Source Checks), and two side-by-side panels ("System
// health" with an urgent-item banner, and "Recent checks"). Captures 1440x900
// evidence for Light/Dark and LTR/RTL. All network traffic is mocked inside
// this spec; nothing leaves the isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'diagnostics-screen')
mkdirSync(screenshotRoot, { recursive: true })

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

const NOW = new Date()
function minutesAgoIso(minutes: number): string {
  return new Date(NOW.getTime() - minutes * 60_000).toISOString()
}

function canonicalStateModel() {
  const now = minutesAgoIso(1)
  const capability = (freshness: string, required = true) => ({ support: 'SUPPORTED_ENABLED', freshness, schedule: { mode: 'SCHEDULED', enabled: true, intervalSeconds: 3600, jitterSeconds: 0, policySource: 'visual-test' }, lastAttemptAt: now, lastSuccessAt: now, lastOutcome: 'SUCCESSFUL', nextExpectedAt: now, required, policy: { freshnessTtlSeconds: 7200, source: 'visual-test' }, evidenceKey: 'visual_test' })
  const channel = {
    id: 'woocommerce:primary', kind: 'CHANNEL', provider: 'woocommerce', displayName: 'WooCommerce', lifecycle: 'ACTIVE', enabled: true, configured: true, denominatorEligible: true,
    connectivity: { state: 'HEALTHY', freshness: 'FRESH', lastVerifiedAt: now, lastCheckedAt: now }, readiness: { state: 'NEEDS_ATTENTION', reasonCode: 'product_sync_stale' }, freshness: { state: 'STALE' }, overallState: 'NEEDS_ATTENTION', reasonCode: 'product_sync_stale', recommendedAction: { code: 'NEXT_PRODUCT_SYNC_SCHEDULED', scheduledAt: now, actionable: true }, latestRelevantAt: now,
    capabilities: { connectionVerification: capability('FRESH'), productSynchronization: capability('STALE'), productCache: { ...capability('STALE'), cachedItemCount: 7597 }, orderSynchronization: capability('FRESH'), webhookProcessing: { ...capability('NOT_APPLICABLE', false), support: 'NOT_SUPPORTED' }, providerAcquisition: { ...capability('NOT_APPLICABLE', false), support: 'NOT_SUPPORTED' } },
    advancedEvidence: [{ key: 'data_layer_health', label: 'Connection health record', value: 'healthy', recordedAt: now }],
  }
  const source = { ...channel, id: 'source-price-list', connectorId: 'nextcloud:primary', kind: 'SOURCE', provider: 'nextcloud', displayName: 'Nextcloud — Primary catalog', readiness: { state: 'READY', reasonCode: 'source_ready' }, freshness: { state: 'FRESH' }, overallState: 'HEALTHY', reasonCode: 'source_ready', recommendedAction: { code: 'NO_ACTION_REQUIRED', scheduledAt: null, actionable: false } }
  const archived = { ...source, id: 'source-legacy', connectorId: 'nextcloud:legacy', displayName: 'Nextcloud — Archived legacy', lifecycle: 'ARCHIVED', enabled: false, denominatorEligible: false, connectivity: { state: 'NOT_APPLICABLE', freshness: 'NOT_APPLICABLE', lastVerifiedAt: null, lastCheckedAt: null }, readiness: { state: 'ARCHIVED', reasonCode: 'source_archived' }, freshness: { state: 'NOT_APPLICABLE' }, overallState: 'ARCHIVED', reasonCode: 'source_archived' }
  const comingSoon = { ...channel, id: 'digikala:main', provider: 'digikala', displayName: 'Digikala', lifecycle: 'COMING_SOON', enabled: false, denominatorEligible: false, connectivity: { state: 'NOT_APPLICABLE', freshness: 'NOT_APPLICABLE', lastVerifiedAt: null, lastCheckedAt: null }, readiness: { state: 'COMING_SOON', reasonCode: 'channel_coming_soon' }, freshness: { state: 'NOT_APPLICABLE' }, overallState: 'COMING_SOON', reasonCode: 'channel_coming_soon', recommendedAction: { code: 'NO_ACTION_REQUIRED', scheduledAt: null, actionable: false } }
  return { schemaVersion: 'diagnostics-state-v1', generatedAt: now, overallState: 'NEEDS_ATTENTION', summary: { overallState: 'NEEDS_ATTENTION', channels: { ready: 0, operational: 1, needsAttention: 1, blocked: 0, disabled: 0, comingSoon: 1 }, sources: { ready: 1, active: 1, needsAttention: 0, blocked: 0, disabled: 0, archived: 1 } }, resources: [channel, source, archived, comingSoon], backgroundJobs: [{ id: 'flowhub:order-sync-runner', displayName: 'Integration background runner', state: 'IDLE', health: 'HEALTHY', required: true, lastHeartbeatAt: now, heartbeatTtlSeconds: 180, runnerId: 'visual-runner', lastSuccessfulJobAt: now, queueDepth: 0, lastFailureAt: null, lastFailureCode: null }], recentChecks: [{ id: channel.id, kind: channel.kind, displayName: channel.displayName, provider: channel.provider, lifecycle: channel.lifecycle, connectivity: 'HEALTHY', readiness: 'NEEDS_ATTENTION', freshness: 'STALE', state: 'NEEDS_ATTENTION', reasonCode: 'product_sync_stale', recordedAt: now }], consumerStates: { diagnostics: 'NEEDS_ATTENTION', dashboard: 'NEEDS_ATTENTION', sidebar: 'NEEDS_ATTENTION' }, externalCallPerformed: false }
}

async function installDiagnosticsMocks(page: Page, audit: TrafficAudit) {
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    if (url.hostname === 'static.userback.io') {
      return route.fulfill({ status: 200, contentType: 'application/javascript', body: 'window.Userback={identify:function(){}}' })
    }
    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      audit.externalRequests.push(`${method} ${url.href}`)
      return route.abort('blockedbyclient')
    }
    if (url.pathname.startsWith('/static/logos/')) {
      return route.fulfill({ path: path.resolve('..', decodeURIComponent(url.pathname.slice(1))) })
    }
    if (!url.pathname.startsWith('/api/')) return route.continue()

    if (url.pathname === '/api/auth/me' && method === 'GET') {
      return json(route, {
        username: 'diagnostics-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'diagnostics-visual-mock' })
    if (url.pathname === '/api/v2/exchange-rates/me' && method === 'GET') return json(route, { selections: [], rates: [] })

    if (url.pathname === '/api/v2/diagnostics/status' && method === 'GET') {
      const stateModel = canonicalStateModel()
      return json(route, {
        overall_status: stateModel.overallState,
        stateModel,
        checkedAt: minutesAgoIso(1),
        checks: [{ check_name: 'database_connection', category: 'database', target: 'flowhub', status: 'pass', severity: 'info' }],
        connectors: [
          { id: 'gsheets:warehouse', name: 'Warehouse inventory', connector_type: 'gsheets', enabled: true, status: 'degraded', last_checked_at: minutesAgoIso(12), last_successful_operation: minutesAgoIso(180) },
          { id: 'nextcloud:primary', name: 'Primary catalog', connector_type: 'nextcloud', enabled: true, status: 'healthy', last_checked_at: minutesAgoIso(5), last_successful_operation: minutesAgoIso(5) },
        ],
        channelHealth: {
          stateModel,
          checkedAt: minutesAgoIso(1),
          summary: { overall: 'Warning', overall_state: 'WARNING', counts: { Operational: 1, Warning: 1 } },
          external_call_performed: false,
          orderSyncRunner: { state: 'running', lastHeartbeat: minutesAgoIso(2) },
          items: [
            {
              channelId: 'woocommerce:primary', channelType: 'woocommerce', enabled: true, accessMode: 'read_write',
              status: 'Operational', summary: 'All channel checks passed.', lastChecked: minutesAgoIso(2),
              latency: 80, lastSuccessfulOperation: minutesAgoIso(2), lastErrorCategory: null,
              capabilityState: { read_products: true, write_prices: true }, nextRecommendedAction: 'No immediate action required.',
              dimensions: { credentials: { status: 'Operational', message: 'Credential validation passed.' } },
              lastProductRead: minutesAgoIso(2), lastProductWrite: null, lastOrderSync: minutesAgoIso(2),
              polling: { cursor: null, lastRunAt: null },
              webhooks: { supported: false, received: 0, queued: 0, processed: 0, deadLetter: 0, lastReceivedAt: null, lastProcessedAt: null },
            },
            {
              channelId: 'snappshop:main', channelType: 'snappshop', enabled: true, accessMode: 'read_write',
              status: 'Warning', summary: 'Rate limit elevated.', lastChecked: minutesAgoIso(8),
              latency: 340, lastSuccessfulOperation: minutesAgoIso(45), lastErrorCategory: 'rate_limit',
              capabilityState: { read_products: true, write_prices: true }, nextRecommendedAction: 'Review the connection details',
              dimensions: { externalApi: { status: 'Warning', message: 'The API health check found a condition that needs review.' } },
              lastProductRead: minutesAgoIso(45), lastProductWrite: null, lastOrderSync: minutesAgoIso(45),
              polling: { cursor: null, lastRunAt: null },
              webhooks: { supported: false, received: 0, queued: 0, processed: 0, deadLetter: 0, lastReceivedAt: null, lastProcessedAt: null },
            },
          ],
        },
        rateLimiter: null,
      })
    }
    if (url.pathname === '/api/v2/diagnostics/channels/health/refresh' && method === 'POST') {
      return json(route, { checkedAt: minutesAgoIso(0), summary: { overall: 'Warning' }, items: [] })
    }

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('wp_token', 'diagnostics-visual-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

async function assertFigmaDiagnosticsHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'Diagnostics' : 'عیب‌یابی'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    await expect(page.getByRole('button', { name: /Re-check/ })).toBeVisible()
    await expect(page.getByText('Overall State', { exact: true })).toBeVisible()
    await expect(page.getByText('Channel Checks', { exact: true })).toBeVisible()
    await expect(page.getByText('Source Checks', { exact: true })).toBeVisible()
    await expect(page.getByText('Operational resources', { exact: true })).toBeVisible()
    await expect(page.getByText('Recent checks', { exact: true })).toBeVisible()
    await expect(page.getByText('WooCommerce').first()).toBeVisible()
    await expect(page.getByText('Nextcloud — Primary catalog').first()).toBeVisible()
    await expect(page.getByText('Historical Sources', { exact: false })).toBeVisible()
    await expect(page.getByText('Non-operational Channels', { exact: true })).toBeVisible()
  } else {
    await expect(page.getByRole('button', { name: /بررسی دوباره/ })).toBeVisible()
  }
}

test('diagnostics matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installDiagnosticsMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/diagnostics')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await expect(page.locator('#operational-resources')).toBeVisible()
    await assertFigmaDiagnosticsHierarchy(page, variant.locale)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({
      path: path.join(screenshotRoot, `diagnostics-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Diagnostics API request must be explicitly mocked').toEqual([])
})

test('canonical diagnostics remains usable at 390x844 in LTR light and RTL dark', async ({ page }) => {
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installDiagnosticsMocks(page, audit)
  await page.setViewportSize({ width: 390, height: 844 })
  for (const variant of [{ locale: 'en', theme: 'light', dir: 'ltr' }, { locale: 'fa', theme: 'dark', dir: 'rtl' }] as const) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/diagnostics')
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    await expect(page.locator('#operational-resources')).toBeVisible()
    await expect(page.locator('[data-canonical-resource="woocommerce:primary"]')).toBeVisible()
    expect(await page.locator('body').evaluate(element => element.scrollWidth <= window.innerWidth)).toBe(true)
  }
  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
})
