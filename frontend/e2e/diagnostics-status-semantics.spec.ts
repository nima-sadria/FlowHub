import path from 'node:path'
import { mkdirSync, readFileSync } from 'node:fs'
import { expect, test, type Locator, type Page, type Route } from '@playwright/test'

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'diagnostics-status-semantics')
mkdirSync(screenshotRoot, { recursive: true })
const mockLogo = readFileSync(path.resolve('public', 'flowhub-logo.png'))

type DiagnosticState =
  | 'HEALTHY'
  | 'INFO'
  | 'NOT_CHECKED'
  | 'NOT_APPLICABLE'
  | 'DISABLED'
  | 'WARNING'
  | 'ERROR'

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
  interceptedActions: string[]
  prohibitedWrites: string[]
}

interface DiagnosticEvidence {
  state: DiagnosticState
  status: string
  message: string
  reasonCode: string
  reason_code: string
  checkedAt: string | null
  checked_at: string | null
  evidenceSource: string
  evidence_source: string
  isActionable: boolean
  is_actionable: boolean
  recommendedAction: string | null
  recommended_action: string | null
}

const checkedAt = '2026-07-16T08:00:00Z'
const recentSync = '2026-07-16T07:45:00Z'
const staleSync = '2026-07-12T08:00:00Z'

function evidence(
  state: DiagnosticState,
  message: string,
  reasonCode: string,
  options: {
    checkedAt?: string | null
    evidenceSource?: string
    actionable?: boolean
    action?: string | null
  } = {},
): DiagnosticEvidence {
  const resultCheckedAt = options.checkedAt === undefined ? checkedAt : options.checkedAt
  const evidenceSource = options.evidenceSource ?? 'synthetic_local_fixture'
  const action = options.action ?? null
  const actionable = options.actionable ?? false
  const legacyStatus: Record<DiagnosticState, string> = {
    HEALTHY: 'Operational',
    INFO: 'Operational',
    NOT_CHECKED: 'Unable to check',
    NOT_APPLICABLE: 'Disabled',
    DISABLED: 'Disabled',
    WARNING: 'Warning',
    ERROR: 'Error',
  }
  return {
    state,
    status: legacyStatus[state],
    message,
    reasonCode,
    reason_code: reasonCode,
    checkedAt: resultCheckedAt,
    checked_at: resultCheckedAt,
    evidenceSource,
    evidence_source: evidenceSource,
    isActionable: actionable,
    is_actionable: actionable,
    recommendedAction: action,
    recommended_action: action,
  }
}

const notApplicable = (message: string, reasonCode: string) => evidence(
  'NOT_APPLICABLE',
  message,
  reasonCode,
  { checkedAt: null, evidenceSource: 'connector_capability', actionable: false },
)

function optionalDimensions() {
  return {
    lastOrderSync: notApplicable('Order synchronization is not enabled for this Channel.', 'order_sync_not_applicable'),
    webhookReceipt: notApplicable('This Channel does not use webhooks.', 'webhook_not_applicable'),
    webhookProcessing: notApplicable('This Channel does not use webhooks.', 'webhook_processing_not_applicable'),
    tokenRefresh: notApplicable('This authentication method does not require token refresh.', 'token_refresh_not_applicable'),
    polling: notApplicable('This Channel does not use polling.', 'polling_not_applicable'),
    queueDeadLetter: notApplicable('This Channel does not use a dead-letter queue.', 'dead_letter_queue_not_applicable'),
  }
}

function baseChannel(channelId: string, status: DiagnosticState) {
  const reasonCode = `CHANNEL_${status}`
  const recommendedAction = 'No action required.'
  const legacyStatus: Record<DiagnosticState, string> = {
    HEALTHY: 'Operational',
    INFO: 'Operational',
    NOT_CHECKED: 'Unable to check',
    NOT_APPLICABLE: 'Disabled',
    DISABLED: 'Disabled',
    WARNING: 'Warning',
    ERROR: 'Error',
  }
  return {
    channelId,
    channelType: channelId.split(':', 1)[0],
    enabled: status !== 'DISABLED',
    accessMode: 'read_write',
    status: legacyStatus[status],
    state: status,
    summary: '',
    lastChecked: checkedAt,
    latency: 18,
    lastSuccessfulOperation: recentSync,
    lastErrorCategory: null,
    capabilityState: { read_products: true, write_prices: true },
    nextRecommendedAction: recommendedAction,
    reasonCode,
    reason_code: reasonCode,
    checkedAt,
    checked_at: checkedAt,
    evidenceSource: 'synthetic_local_fixture',
    evidence_source: 'synthetic_local_fixture',
    isActionable: status === 'WARNING' || status === 'ERROR',
    is_actionable: status === 'WARNING' || status === 'ERROR',
    recommendedAction,
    recommended_action: recommendedAction,
    lastSuccessfulVerification: checkedAt,
    lastSuccessfulSyncOrRead: recentSync,
    dimensions: {},
    lastProductRead: recentSync,
    lastProductWrite: null,
    lastOrderSync: null,
    polling: { cursor: null, lastRunAt: null },
    webhooks: {
      supported: false,
      received: 0,
      queued: 0,
      processed: 0,
      deadLetter: 0,
      lastReceivedAt: null,
      lastProcessedAt: null,
    },
  }
}

function channelHealthPayload() {
  const healthy = {
    ...baseChannel('woocommerce:healthy', 'HEALTHY'),
    reasonCode: 'product_sync_fresh',
    reason_code: 'product_sync_fresh',
    summary: 'Verified core checks confirm normal operation.',
    dimensions: {
      configuration: evidence('HEALTHY', 'Required configuration is present.', 'configuration_complete'),
      credentials: evidence('HEALTHY', 'Credential verification succeeded.', 'credentials_verified'),
      externalApi: evidence('HEALTHY', 'The provider API health check succeeded.', 'external_api_healthy'),
      lastProductSync: evidence('HEALTHY', 'Product data was refreshed recently.', 'product_sync_fresh'),
      writeCapability: evidence('INFO', 'Price updates are supported. Review and Apply confirmation remain required.', 'write_capability_supported'),
      ...optionalDimensions(),
    },
  }

  const disabled = {
    ...baseChannel('snappshop:disabled', 'DISABLED'),
    reasonCode: 'channel_disabled',
    reason_code: 'channel_disabled',
    enabled: false,
    summary: 'This Channel is intentionally disabled.',
    lastChecked: checkedAt,
    nextRecommendedAction: 'Enable the Channel only when it should participate.',
    recommendedAction: 'Enable the Channel only when it should participate.',
    recommended_action: 'Enable the Channel only when it should participate.',
    dimensions: {
      configuration: evidence('HEALTHY', 'Saved configuration is valid.', 'configuration_complete'),
      credentials: evidence('HEALTHY', 'Historical credential verification succeeded.', 'credentials_verified'),
      externalApi: evidence('DISABLED', 'Provider checks are off while this Channel is disabled.', 'channel_disabled', { actionable: false }),
      ...optionalDimensions(),
    },
  }

  const neverChecked = {
    ...baseChannel('woocommerce:unchecked', 'NOT_CHECKED'),
    reasonCode: 'credentials_not_checked',
    reason_code: 'credentials_not_checked',
    summary: 'No connection verification has been recorded.',
    lastChecked: null,
    checked_at: null,
    lastSuccessfulVerification: null,
    lastSuccessfulOperation: null,
    lastSuccessfulSyncOrRead: null,
    lastProductRead: null,
    nextRecommendedAction: 'Run connection test.',
    isActionable: true,
    is_actionable: true,
    recommendedAction: 'Run connection test.',
    recommended_action: 'Run connection test.',
    dimensions: {
      configuration: evidence('HEALTHY', 'Required configuration is present.', 'configuration_complete'),
      credentials: evidence('NOT_CHECKED', 'No credential probe has been recorded.', 'credentials_not_checked', {
        checkedAt: null,
        actionable: true,
        action: 'Run connection test.',
      }),
      externalApi: evidence('NOT_CHECKED', 'No API health check has been recorded.', 'external_api_not_checked', {
        checkedAt: null,
        actionable: true,
        action: 'Run connection test.',
      }),
      lastProductSync: evidence('NOT_CHECKED', 'No product synchronization evidence has been recorded.', 'product_sync_not_checked', {
        checkedAt: null,
      }),
      ...optionalDimensions(),
    },
  }

  const warning = {
    ...baseChannel('snappshop:warning', 'WARNING'),
    reasonCode: 'product_sync_stale',
    reason_code: 'product_sync_stale',
    summary: 'Product data needs attention.',
    lastSuccessfulOperation: staleSync,
    lastProductRead: staleSync,
    lastErrorCategory: 'stale_sync',
    nextRecommendedAction: 'Refresh products.',
    recommendedAction: 'Refresh products.',
    recommended_action: 'Refresh products.',
    dimensions: {
      configuration: evidence('HEALTHY', 'Required configuration is present.', 'configuration_complete'),
      credentials: evidence('HEALTHY', 'Credential verification succeeded.', 'credentials_verified'),
      externalApi: evidence('HEALTHY', 'The provider API health check succeeded.', 'external_api_healthy'),
      lastProductSync: evidence(
        'WARNING',
        'Last successful product sync was 4 days ago. Expected freshness: within 24 hours.',
        'product_sync_stale',
        { checkedAt, actionable: true, action: 'Refresh products.' },
      ),
      polling: evidence('DISABLED', 'Order polling is turned off.', 'polling_disabled', { checkedAt: null }),
      webhookReceipt: notApplicable('This Channel does not use webhooks.', 'webhook_not_applicable'),
      webhookProcessing: notApplicable('This Channel does not use webhooks.', 'webhook_processing_not_applicable'),
      tokenRefresh: notApplicable('This authentication method does not require token refresh.', 'token_refresh_not_applicable'),
      queueDeadLetter: notApplicable('This Channel does not use a dead-letter queue.', 'dead_letter_queue_not_applicable'),
    },
  }

  const error = {
    ...baseChannel('tapsishop:error', 'ERROR'),
    reasonCode: 'credential_verification_failed',
    reason_code: 'credential_verification_failed',
    summary: 'Credential verification failed.',
    lastSuccessfulOperation: null,
    lastProductRead: null,
    lastErrorCategory: 'authentication_failed',
    nextRecommendedAction: 'Review credentials.',
    recommendedAction: 'Review credentials.',
    recommended_action: 'Review credentials.',
    dimensions: {
      configuration: evidence('HEALTHY', 'Required configuration is present.', 'configuration_complete'),
      credentials: evidence('ERROR', 'Credential verification failed.', 'credential_verification_failed', {
        actionable: true,
        action: 'Review credentials.',
      }),
      externalApi: evidence('ERROR', 'The provider rejected the authenticated request.', 'external_api_check_failed', {
        actionable: true,
        action: 'Review credentials.',
      }),
      lastProductSync: evidence('NOT_CHECKED', 'No verified product sync is available.', 'product_sync_not_checked', { checkedAt: null }),
      webhookReceipt: evidence('INFO', 'Webhook delivery is configured.', 'webhook_receipt_healthy'),
      webhookProcessing: evidence('HEALTHY', 'Recent webhook events were processed.', 'webhook_processing_healthy'),
      tokenRefresh: evidence('DISABLED', 'Automatic token refresh is intentionally turned off.', 'token_refresh_disabled', { checkedAt: null }),
      polling: notApplicable('This Channel does not use polling.', 'polling_not_applicable'),
      queueDeadLetter: evidence('HEALTHY', 'No failed webhook events require recovery.', 'dead_letter_queue_empty'),
      lastOrderSync: notApplicable('Order synchronization is not enabled for this Channel.', 'order_sync_not_applicable'),
    },
  }

  const optionalUnsupported = {
    ...baseChannel('woocommerce:optional', 'HEALTHY'),
    reasonCode: 'product_sync_fresh',
    reason_code: 'product_sync_fresh',
    summary: 'Verified core checks are healthy; optional capabilities do not apply.',
    dimensions: {
      configuration: evidence('HEALTHY', 'Required configuration is present.', 'configuration_complete'),
      credentials: evidence('HEALTHY', 'Credential verification succeeded.', 'credentials_verified'),
      externalApi: evidence('HEALTHY', 'The provider API health check succeeded.', 'external_api_healthy'),
      lastProductSync: evidence('HEALTHY', 'Product data was refreshed recently.', 'product_sync_fresh'),
      readCapability: evidence('INFO', 'Product reads are supported.', 'read_capability_supported'),
      ...optionalDimensions(),
    },
  }

  return {
    checkedAt,
    summary: {
      overall: 'Error',
      overall_state: 'ERROR',
      counts: {
        Operational: 2,
        Warning: 1,
        Error: 1,
        'Unable to check': 1,
        Disabled: 1,
      },
      state_counts: { HEALTHY: 2, INFO: 0, NOT_CHECKED: 1, NOT_APPLICABLE: 0, DISABLED: 1, WARNING: 1, ERROR: 1 },
    },
    items: [healthy, disabled, neverChecked, warning, error, optionalUnsupported],
    external_call_performed: false,
  }
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(body),
  })
}

async function installStrictDiagnosticsMocks(page: Page, audit: TrafficAudit) {
  await page.addInitScript(() => {
    localStorage.setItem('wp_token', 'diagnostics-semantics-isolated-token')
    if (!localStorage.getItem('flowhub.locale')) localStorage.setItem('flowhub.locale', 'en')
  })

  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()
    const requestLabel = `${method} ${url.pathname}${url.search}`

    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) {
      audit.externalRequests.push(`${method} ${url.href}`)
      return route.abort('blockedbyclient')
    }

    if (url.pathname.startsWith('/static/logos/')) {
      return route.fulfill({ status: 200, contentType: 'image/png', body: mockLogo })
    }
    if (!url.pathname.startsWith('/api/')) return route.continue()

    if (url.pathname === '/api/auth/me' && method === 'GET') {
      return json(route, {
        username: 'diagnostics-visual-owner',
        role: 'admin',
        is_admin: true,
        is_super_admin: false,
        permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true },
        maintenance: { enabled: false, message: '' },
      })
    }
    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') {
      return json(route, { status: 'ok', env: 'test', version: 'diagnostics-semantics-local-mock' })
    }
    if (url.pathname === '/api/v2/diagnostics/status' && method === 'GET') {
      return json(route, {
        overall_status: 'error',
        checkedAt,
        checks: [{
          check_name: 'database_connection',
          category: 'database',
          target: 'isolated-browser-fixture',
          status: 'pass',
          severity: 'info',
        }],
        connectors: [],
        channelHealth: channelHealthPayload(),
        rateLimiter: null,
        external_call_performed: false,
      })
    }
    if (url.pathname === '/api/v2/diagnostics/channels/health/refresh' && method === 'POST') {
      const channelId = String((request.postDataJSON() as { channelId?: string } | null)?.channelId ?? '')
      audit.interceptedActions.push(`${requestLabel} channel=${channelId}`)
      return json(route, channelHealthPayload())
    }
    if (/^\/api\/v2\/commerce\/channels\/[^/]+\/test$/.test(url.pathname) && method === 'POST') {
      audit.interceptedActions.push(requestLabel)
      return json(route, {
        status: 'not_checked',
        message: 'Synthetic local connection test completed without provider I/O.',
        checked_at: checkedAt,
        external_call_performed: false,
      })
    }

    if (method !== 'GET') audit.prohibitedWrites.push(requestLabel)
    audit.unhandledApiRequests.push(requestLabel)
    return json(route, { code: 'UNHANDLED_ISOLATED_DIAGNOSTICS_REQUEST' }, 418)
  })
}

function channel(page: Page, channelId: string): Locator {
  return page.locator(`[data-resource-id="${channelId}"]`)
}

async function expectCollapsedSemantics(page: Page, locale: 'en' | 'fa') {
  await expect(page.locator('[data-resource-id]')).toHaveCount(6)

  const healthy = channel(page, 'woocommerce:healthy')
  const disabled = channel(page, 'snappshop:disabled')
  const unchecked = channel(page, 'woocommerce:unchecked')
  const warning = channel(page, 'snappshop:warning')
  const error = channel(page, 'tapsishop:error')
  const optional = channel(page, 'woocommerce:optional')

  for (const card of [healthy, disabled, unchecked, warning, error, optional]) {
    await expect(card).toBeVisible()
    await expect(card.locator('[data-diagnostic-state]').first()).toBeVisible()
    await expect(card.locator('[data-diagnostic-state]').first().locator('[data-icon]')).toBeVisible()
    await expect(card.locator('details')).not.toHaveAttribute('open', '')
  }

  if (locale === 'en') {
    await expect(page.getByTestId('diagnostics-channel-status-woocommerce:healthy')).toHaveText('Healthy')
    await expect(page.getByTestId('diagnostics-channel-status-woocommerce:healthy')).toHaveAttribute('data-diagnostic-state', 'HEALTHY')
    await expect(healthy.getByText('No action required', { exact: true }).first()).toBeVisible()
    await expect(page.getByTestId('diagnostics-channel-status-snappshop:disabled')).toHaveText('Disabled')
    await expect(page.getByTestId('diagnostics-channel-status-snappshop:disabled')).toHaveAttribute('data-diagnostic-state', 'DISABLED')
    await expect(disabled.getByText('This Channel is disabled.', { exact: true }).first()).toBeVisible()
    await expect(page.getByTestId('diagnostics-channel-status-woocommerce:unchecked')).toHaveText('Not checked yet')
    await expect(page.getByTestId('diagnostics-channel-status-woocommerce:unchecked')).toHaveAttribute('data-diagnostic-state', 'NOT_CHECKED')
    await expect(unchecked.getByText('Run connection test', { exact: true }).first()).toBeVisible()
    await expect(unchecked.getByText(/Unable to check/i)).toHaveCount(0)
    await expect(page.getByTestId('diagnostics-channel-status-snappshop:warning')).toHaveText('Needs attention')
    await expect(page.getByTestId('diagnostics-channel-status-snappshop:warning')).toHaveAttribute('data-diagnostic-state', 'WARNING')
    await expect(warning.getByText('Refresh products', { exact: true }).first()).toBeVisible()
    await expect(page.getByTestId('diagnostics-channel-status-tapsishop:error')).toHaveText('Error')
    await expect(page.getByTestId('diagnostics-channel-status-tapsishop:error')).toHaveAttribute('data-diagnostic-state', 'ERROR')
    await expect(error.getByText('Review credentials', { exact: true }).first()).toBeVisible()
    await expect(page.getByTestId('diagnostics-channel-status-woocommerce:optional')).toHaveText('Healthy')
    await expect(page.getByTestId('diagnostics-channel-status-woocommerce:optional')).toHaveAttribute('data-diagnostic-state', 'HEALTHY')
  } else {
    await expect(page.getByTestId('diagnostics-channel-status-woocommerce:healthy')).toHaveText('سالم')
    await expect(healthy.getByText('نیازی به اقدام نیست', { exact: true }).first()).toBeVisible()
    await expect(page.getByTestId('diagnostics-channel-status-snappshop:disabled')).toHaveText('غیرفعال')
    await expect(page.getByTestId('diagnostics-channel-status-woocommerce:unchecked')).toHaveText('هنوز بررسی نشده')
    await expect(unchecked.getByText('آزمایش اتصال را اجرا کنید', { exact: true }).first()).toBeVisible()
    await expect(page.getByTestId('diagnostics-channel-status-snappshop:warning')).toHaveText('نیازمند بررسی')
    await expect(warning.getByText('محصولات را به‌روزرسانی کنید', { exact: true }).first()).toBeVisible()
    await expect(page.getByTestId('diagnostics-channel-status-tapsishop:error')).toHaveText('خطا')
  }

  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)
}

async function expandEveryChannel(page: Page) {
  for (const channelId of [
    'woocommerce:healthy',
    'snappshop:disabled',
    'woocommerce:unchecked',
    'snappshop:warning',
    'tapsishop:error',
    'woocommerce:optional',
  ]) {
    const details = page.locator(`[data-testid="diagnostics-details-${channelId}"]`)
    await details.locator('summary').click()
    await expect(details).toHaveAttribute('open', '')
  }
}

test('diagnostic evidence states are truthful, bilingual, and isolated in real Chrome', async ({ page }) => {
  test.setTimeout(90_000)

  const unsafeCredentialNames = [
    'WC_KEY',
    'WC_SECRET',
    'SNAPPSHOP_TOKEN',
    'TAPSISHOP_TOKEN',
  ]
  for (const name of unsafeCredentialNames) {
    expect(process.env[name], `${name} must remain unset during the isolated browser test`).toBeUndefined()
  }

  for (const name of ['WC_URL', 'SNAPPSHOP_BASE_URL', 'TAPSISHOP_BASE_URL']) {
    const value = process.env[name]
    if (!value) continue
    const hostname = new URL(value).hostname
    expect(
      hostname === '127.0.0.1' || hostname === 'localhost' || hostname.endsWith('.invalid'),
      `${name} must be local or use the reserved .invalid domain`,
    ).toBe(true)
  }
  const databaseUrl = process.env.DATABASE_URL
  if (databaseUrl) {
    expect(
      databaseUrl.startsWith('sqlite:') || /@(127\.0\.0\.1|localhost)(:|\/)/.test(databaseUrl),
      'DATABASE_URL must be SQLite or a loopback-only disposable database',
    ).toBe(true)
  }
  expect(process.env.FLOWHUB_ENV?.toLowerCase()).not.toBe('production')
  expect(process.env.VITE_APP_ENV?.toLowerCase()).not.toBe('production')

  const audit: TrafficAudit = {
    externalRequests: [],
    unhandledApiRequests: [],
    interceptedActions: [],
    prohibitedWrites: [],
  }
  await installStrictDiagnosticsMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  await page.goto('/diagnostics')
  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  await expectCollapsedSemantics(page, 'en')
  await page.screenshot({
    path: path.join(screenshotRoot, 'diagnostics-collapsed-en-1440x900.png'),
    fullPage: true,
    animations: 'disabled',
  })

  await expandEveryChannel(page)
  await expect(channel(page, 'woocommerce:optional').getByText('Not applicable', { exact: true }).first()).toBeVisible()
  await expect(channel(page, 'woocommerce:optional').getByText('Information', { exact: true }).first()).toBeVisible()
  await expect(channel(page, 'snappshop:warning').getByText(/older than the expected freshness window/i).first()).toBeVisible()
  await page.screenshot({
    path: path.join(screenshotRoot, 'diagnostics-expanded-en-1440x900.png'),
    fullPage: true,
    animations: 'disabled',
  })

  const warningRefresh = page.getByTestId('diagnostics-channel-action-snappshop:warning')
  await expect(warningRefresh).toHaveAttribute('href', /\/commerce\?tab=channels&channel=snappshop%3Awarning$/)
  const connectionTest = page.getByTestId('diagnostics-channel-action-woocommerce:unchecked')
  await connectionTest.click()
  await expect.poll(() => audit.interceptedActions.length).toBe(1)
  expect(audit.interceptedActions[0]).toContain('channel=woocommerce:unchecked')

  await page.evaluate(() => localStorage.setItem('flowhub.locale', 'fa'))
  await page.goto('/diagnostics')
  await expect(page.locator('html')).toHaveAttribute('lang', 'fa')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expectCollapsedSemantics(page, 'fa')
  await page.screenshot({
    path: path.join(screenshotRoot, 'diagnostics-collapsed-fa-1440x900.png'),
    fullPage: true,
    animations: 'disabled',
  })

  await expandEveryChannel(page)
  await expect(channel(page, 'woocommerce:optional').getByText('کاربرد ندارد', { exact: true }).first()).toBeVisible()
  await expect(channel(page, 'woocommerce:optional').getByText('اطلاع‌رسانی', { exact: true }).first()).toBeVisible()
  await page.screenshot({
    path: path.join(screenshotRoot, 'diagnostics-expanded-fa-1440x900.png'),
    fullPage: true,
    animations: 'disabled',
  })

  expect(audit.externalRequests, 'No request may leave the isolated localhost browser fixture').toEqual([])
  expect(audit.unhandledApiRequests, 'Every application API request must be explicitly mocked').toEqual([])
  expect(audit.prohibitedWrites, 'No Apply, Publish, Sync, cache mutation, or other write may execute').toEqual([])
})
