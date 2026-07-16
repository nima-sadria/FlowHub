import path from 'node:path'
import { mkdirSync, readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'sources-worksheet-redesign')
mkdirSync(screenshotRoot, { recursive: true })

const mockLogo = readFileSync(path.resolve('public', 'flowhub-logo.png'))
const nextcloudLogo = readFileSync(path.resolve('..', 'static', 'logos', 'brands', 'nextcloud.webp'))
const microsoftOfficeLogo = readFileSync(path.resolve('..', 'static', 'logos', 'brands', 'microsoft-office.webp'))

const overviewViewports = [
  { width: 1280, height: 720 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
  { width: 1024, height: 768 },
  { width: 768, height: 900 },
] as const

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
  interceptedWrites: string[]
  previewRequests: number
  savedMappings: Array<Record<string, unknown>>
}

const sourceProfiles = [
  sourceProfile('source-logitech', 'Logitech Pricing Workbook', 'active', 'imported_sheet', 7),
  sourceProfile('source-flowhub', 'Daily Pricing Sheet', 'active', 'flowhub_sheet', 3, 'sheet-daily'),
  sourceProfile('source-archive', 'Archived CSV', 'disabled', 'imported_sheet', 2),
]

const channels = [
  sourceChannel('woocommerce:primary', 'WooCommerce', true, true, 'implemented'),
  sourceChannel('snappshop:main', 'SnappShop', true, true, 'implemented'),
  sourceChannel('tapsishop:main', 'TapsiShop', true, true, 'implemented'),
  sourceChannel('digikala:future', 'Digikala', false, false, 'coming_soon'),
]

const integrations = [
  commerceSource('nextcloud:primary', 'nextcloud', 'Nextcloud', 'configured', 'healthy'),
  commerceSource('csv:archive', 'csv', 'CSV', 'disabled', 'unknown'),
  commerceSource('shopify:future', 'shopify', 'Shopify', 'planned', 'unknown', false, true),
]

const worksheetRules = [
  worksheetRule('Logitech', 2, 'A', [
    channelRule('woocommerce:primary', 'D', 'B', 'C'),
    channelRule('snappshop:main', 'G', 'E', 'F'),
    channelRule('tapsishop:main', 'J', 'H', 'I'),
  ]),
  worksheetRule('Surface', 3, 'B', [
    channelRule('woocommerce:primary', 'F', 'C', 'D'),
    channelRule('snappshop:main', 'J', 'G', 'H'),
    channelRule('tapsishop:main', 'N', 'K', 'L'),
  ]),
  { ...worksheetRule('Notes', 1, 'A', []), enabled: false },
]

const sourceConfiguration = {
  ...sourceProfiles[0],
  mapping: {
    id: 'mapping-logitech-7',
    version: 7,
    checksum: 'a'.repeat(64),
    worksheetMode: 'all',
    worksheetName: null,
    dataStartRow: 1,
    valuePolicy: valuePolicy(),
    worksheetRuleMode: 'per_worksheet',
    selectedWorksheetNames: ['Logitech', 'Surface'],
    duplicateProductPolicy: 'block',
    worksheetRules,
    sourceFields: [],
    channels: [],
  },
  legacyMapping: null,
}

function sourceProfile(
  id: string,
  name: string,
  status: string,
  sourceKind: 'flowhub_sheet' | 'imported_sheet' | 'external',
  mappingVersion: number,
  sheetId: string | null = null,
) {
  return {
    id,
    name,
    sourceKind,
    externalSourceId: null,
    worksheetMode: 'all',
    worksheetName: null,
    dataStartRow: 1,
    status,
    version: 4,
    mappingVersion,
    sheetId,
  }
}

function sourceChannel(
  channelId: string,
  name: string,
  enabled: boolean,
  available: boolean,
  implementationState: string,
) {
  return {
    channelId,
    name,
    connectorType: channelId.split(':')[0],
    capabilityVersion: 'source-redesign-v1',
    capabilities: { products_read: available, price_write: available, stock_write: available },
    enabled,
    implementationState,
    available,
  }
}

function commerceSource(
  id: string,
  provider: string,
  name: string,
  status: string,
  healthStatus: string,
  implemented = true,
  placeholder = false,
) {
  return {
    id,
    provider,
    name,
    type: 'Source',
    status,
    implemented,
    placeholder,
    credential_status: implemented && !placeholder ? 'configured' : 'not_configured',
    last_health_check: implemented ? '2026-07-16T07:00:00Z' : null,
    data_role: implemented ? 'synthetic_source_role_v9' : 'planned_integration_v9',
    action_label: implemented ? 'Manage' : 'Coming Soon',
    action_href: '',
    health: {
      status: healthStatus,
      message: implemented ? 'Synthetic local health' : 'Not implemented',
      latency_ms: implemented ? 11 : null,
      error_code: null,
    },
    read_policy: {
      enabled: implemented,
      max_reads_per_24h: 20,
      manual_read_allowed: implemented,
      reads_used_last_24h: implemented ? 1 : 0,
      reads_remaining: implemented ? 19 : 0,
      reset_at: null,
      last_read_at: implemented ? '2026-07-16T06:45:00Z' : null,
    },
    read_status: {
      enabled: implemented,
      max_reads_per_24h: 20,
      manual_read_allowed: implemented,
      reads_used_last_24h: implemented ? 1 : 0,
      reads_remaining: implemented ? 19 : 0,
      reset_at: null,
      last_read_at: implemented ? '2026-07-16T06:45:00Z' : null,
      last_read_status: implemented ? 'completed' : null,
      last_row_count: implemented ? 1035 : null,
      last_warning_count: 0,
      last_error_count: 0,
    },
    read_only: true,
    runtime_write_blocked: true,
    settings_available: implemented,
  }
}

function valuePolicy() {
  return {
    blank: 'no_change',
    x: 'unavailable',
    dash: 'no_change',
    zero: 'explicit_zero',
    formula: 'calculated_value',
    invalid: 'blocked',
  }
}

function field(fieldName: string, referenceValue: string | null, required = false) {
  return {
    field: fieldName,
    referenceType: referenceValue ? 'column_letter' : 'disabled',
    referenceValue,
    required,
  }
}

function channelRule(channelId: string, externalId: string, price: string, stock: string) {
  return {
    channelId,
    worksheetName: 'Logitech',
    enabled: true,
    fields: [
      field('external_id', externalId),
      field('price', price),
      field('stock', stock),
      field('status', null),
    ],
  }
}

function worksheetRule(
  worksheetName: string,
  dataStartRow: number,
  productNameColumn: string,
  channelMappings: ReturnType<typeof channelRule>[],
) {
  return {
    worksheetName,
    enabled: true,
    dataStartRow,
    valuePolicy: valuePolicy(),
    sourceFields: [
      field('name', productNameColumn, true),
      field('source_key', null),
      field('category', null),
      field('brand', null),
      field('cost', null),
    ],
    channels: channelMappings.map(mapping => ({ ...mapping, worksheetName })),
  }
}

function sourcePreview() {
  return {
    items: [
      {
        rowKey: 'Logitech:4',
        rowNumber: 4,
        worksheetName: 'Logitech',
        recognized: true,
        hasIssues: false,
        ready: true,
        sourceProduct: { name: 'LOGITECH-MX-MASTER4-GRY', source_key: null },
        channels: [
          { channelId: 'woocommerce:primary', fields: { external_id: '51550', price: '32200000', stock: '29', status: null } },
          { channelId: 'snappshop:main', fields: { external_id: '1826345203', price: '36550000', stock: '41', status: null } },
          { channelId: 'tapsishop:main', fields: { external_id: '7785746738', price: '32950000', stock: '17', status: null } },
        ],
        valuePolicy: valuePolicy(),
        issues: [],
      },
      {
        rowKey: 'Surface:3',
        rowNumber: 3,
        worksheetName: 'Surface',
        recognized: true,
        hasIssues: true,
        ready: false,
        sourceProduct: { name: 'SURFACE-PRO-KEYBOARD', source_key: null },
        channels: [
          { channelId: 'woocommerce:primary', fields: { external_id: '9001', price: '21000000', stock: '8', status: null } },
          { channelId: 'snappshop:main', fields: { external_id: null, price: '21800000', stock: '7', status: null } },
          { channelId: 'tapsishop:main', fields: { external_id: 'TPS-9001', price: '21500000', stock: '6', status: null } },
        ],
        valuePolicy: valuePolicy(),
        issues: [{ category: 'missing_identifier', severity: 'blocked', channelId: 'snappshop:main', message: 'Product identifier is missing.' }],
      },
    ],
    total: 2,
    recognized: 2,
    ignored: 0,
    issues: [{ category: 'missing_identifier', severity: 'blocked', channelId: 'snappshop:main', count: 1 }],
    businessSummary: {
      productsFound: 2,
      productsReady: 1,
      priceChanges: null,
      stockChanges: null,
      unchanged: null,
      needsAttention: 1,
      channelsReady: 2,
      channelsNotConfigured: 1,
    },
    sheetRevisionId: 'sheet-revision-logitech-9',
    mappingRevisionId: 'mapping-logitech-7',
  }
}

async function installStrictMockApi(page: Page, audit: TrafficAudit, locale: 'en' | 'fa') {
  await page.addInitScript(({ selectedLocale }) => {
    localStorage.setItem('wp_token', 'sources-redesign-isolated-token')
    localStorage.setItem('flowhub.locale', selectedLocale)
  }, { selectedLocale: locale })

  await page.route('**/*', async (route: Route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) {
      audit.externalRequests.push(`${request.method()} ${request.url()}`)
      await route.abort('blockedbyclient')
      return
    }
    if (url.pathname === '/static/logos/brands/nextcloud.webp') {
      await route.fulfill({ status: 200, contentType: 'image/webp', body: nextcloudLogo })
      return
    }
    if (url.pathname === '/static/logos/brands/microsoft-office.webp') {
      await route.fulfill({ status: 200, contentType: 'image/webp', body: microsoftOfficeLogo })
      return
    }
    if (url.pathname.startsWith('/static/')) {
      await route.fulfill({ status: 200, contentType: 'image/png', body: mockLogo })
      return
    }
    if (!url.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }

    const json = (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
    const pathname = url.pathname

    if (request.method() === 'PUT' && pathname === '/api/v2/sources/source-logitech/mappings') {
      audit.interceptedWrites.push(`PUT ${pathname}`)
      const payload = request.postDataJSON() as Record<string, unknown>
      audit.savedMappings.push(payload)
      return json(sourceConfiguration.mapping)
    }
    if (request.method() !== 'GET') {
      audit.interceptedWrites.push(`${request.method()} ${pathname}`)
      return json({ code: 'MOCK_WRITE_BLOCKED', message: 'All writes are blocked by the isolated Sources redesign fixture.' }, 405)
    }

    if (pathname === '/api/v2/setup/status') return json({ completed: true })
    if (pathname === '/api/auth/me') return json({
      username: 'sources-redesign-owner',
      role: 'admin',
      is_admin: true,
      is_super_admin: false,
      permissions: {
        can_access_site: true,
        can_fetch: true,
        can_view_logs: true,
        can_view_settings: true,
        'workspace.admin': true,
      },
      maintenance: { enabled: false, message: '' },
    })
    if (pathname === '/api/health') return json({ status: 'ok', version: 'sources-redesign-isolated' })
    if (pathname === '/api/v2/source-profiles') return json({ items: sourceProfiles })
    if (pathname === '/api/v2/source-profiles/channels') return json({ items: channels })
    if (pathname === '/api/v2/commerce/sources') return json({
      items: integrations,
      relationship_map: {
        nodes: ['Source', 'FlowHub / Data Layer', 'Channel'],
        example: ['Nextcloud', 'Data Layer', 'WooCommerce'],
        runtime_write_blocked: true,
        read_only: true,
      },
    })
    if (pathname === '/api/v2/commerce/source-types' || pathname === '/api/v2/commerce/channel-types') return json({ items: [] })
    if (pathname === '/api/v2/sources/source-logitech/configuration') return json(sourceConfiguration)
    if (pathname === '/api/v2/sources/source-logitech/worksheets') return json({
      sourceId: 'source-logitech',
      sourceRevisionId: 'source-revision-logitech-9',
      items: [
        { name: 'Logitech', rowCount: 261 },
        { name: 'Surface', rowCount: 396 },
        { name: 'Notes', rowCount: 12 },
      ],
    })
    if (pathname === '/api/v2/sources/source-logitech/preview') {
      audit.previewRequests += 1
      return json(sourcePreview())
    }

    audit.unhandledApiRequests.push(`${request.method()} ${request.url()}`)
    return json({ code: 'UNHANDLED_ISOLATED_MOCK', message: 'The isolated Sources redesign fixture does not implement this request.' }, 501)
  })
}

function expectSafeTraffic(audit: TrafficAudit, expectedMappingWrites = 0) {
  expect(audit.externalRequests).toEqual([])
  expect(audit.unhandledApiRequests).toEqual([])
  expect(audit.interceptedWrites).toEqual(expectedMappingWrites === 1
    ? ['PUT /api/v2/sources/source-logitech/mappings']
    : [])
}

test.describe.serial('Sources integrations and per-worksheet Channel rules', () => {
  test('Sources overview is responsive, grouped, local-only, and bilingual', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [], interceptedWrites: [], previewRequests: 0, savedMappings: [] }
    await installStrictMockApi(page, audit, 'en')

    for (const viewport of overviewViewports) {
      await page.setViewportSize(viewport)
      await page.goto('/sources')
      await expect(page.getByRole('heading', { name: 'Sources', exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Add Source' })).toBeVisible()
      await expect(page.locator('[data-source-card]')).toHaveCount(6)
      await expect(page.locator('[data-resource-id="integration:shopify:future"]')).toContainText('Coming Soon')
      await expect(page.locator('[data-resource-id="integration:shopify:future"] button')).toHaveCount(0)

      const cards = await page.locator('[data-source-card]').evaluateAll(elements => elements.map(element => {
        const box = element.getBoundingClientRect()
        return { left: Math.round(box.left), top: Math.round(box.top), right: Math.round(box.right) }
      }))
      expect(cards.every(card => card.left >= 0 && card.right <= viewport.width)).toBe(true)
      const firstGroupRowCount = new Set(cards.filter(card => card.top === cards[0].top).map(card => card.left)).size
      expect(firstGroupRowCount).toBe(viewport.width >= 1280 ? 3 : viewport.width >= 1024 ? 2 : 1)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      await page.screenshot({ path: path.join(screenshotRoot, `sources-overview-en-${viewport.width}x${viewport.height}.png`), fullPage: true })
    }

    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/sources')
    await page.getByRole('button', { name: 'Add Source' }).click()
    await expect(page.getByRole('dialog')).toContainText('FlowHub Sheet')
    await expect(page.getByRole('dialog')).toContainText('Import your spreadsheet')
    await expect(page.getByRole('dialog')).toContainText('Keep an external Source linked')
    await page.screenshot({ path: path.join(screenshotRoot, 'add-source-en.png'), fullPage: true })
    await page.getByRole('button', { name: 'Close' }).click()

    expect(audit.previewRequests).toBe(0)
    expectSafeTraffic(audit)
  })

  test('Sources overview uses the same safe cards in Persian RTL', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [], interceptedWrites: [], previewRequests: 0, savedMappings: [] }
    await installStrictMockApi(page, audit, 'fa')
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/sources')
    await expect(page.locator('html')).toHaveAttribute('lang', 'fa')
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
    await expect(page.getByRole('heading', { name: 'منابع', exact: true })).toBeVisible()
    await expect(page.getByText('Shopify', { exact: true })).toBeVisible()
    await expect(page.getByText('منبع صفحه‌گسترده خارجی', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('synthetic_source_role_v9')).toHaveCount(0)
    await expect(page.locator('[data-resource-id="integration:shopify:future"] button')).toHaveCount(0)
    await page.screenshot({ path: path.join(screenshotRoot, 'sources-overview-fa-1440x900.png'), fullPage: true })

    await page.goto('/sources/source-logitech')
    await expect(page.locator('html')).toHaveAttribute('lang', 'fa')
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
    await expect(page.getByText('قواعد برگه‌ها', { exact: true })).toBeVisible()
    await page.locator('summary').filter({ hasText: 'ستون‌های برگه‌ها' }).click()
    const persianLogitechRule = page.locator('[data-worksheet-rule="Logitech"]')
    if (!await persianLogitechRule.evaluate(element => (element as HTMLDetailsElement).open)) await persianLogitechRule.locator('summary').first().click()
    await expect(persianLogitechRule.getByText('نام محصول', { exact: true }).first()).toBeVisible()
    await expect(persianLogitechRule.getByText('ستون‌های هر کانال', { exact: true }).first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: path.join(screenshotRoot, 'source-configuration-fa-1440x900.png'), fullPage: true })
    expectSafeTraffic(audit)
  })

  test('Source configuration stays usable without horizontal page clipping at every required viewport', async ({ page }) => {
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [], interceptedWrites: [], previewRequests: 0, savedMappings: [] }
    await installStrictMockApi(page, audit, 'en')

    for (const viewport of overviewViewports) {
      await page.setViewportSize(viewport)
      await page.goto('/sources/source-logitech')
      await page.locator('summary').filter({ hasText: 'Worksheet columns' }).click()
      const logitechRule = page.locator('[data-worksheet-rule="Logitech"]')
      await expect(logitechRule).toHaveAttribute('open', '')
      await expect(logitechRule.getByLabel('Source Product Name column reference')).toBeEnabled()
      await expect(page.getByTestId('source-configuration-actions')).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      await page.screenshot({ path: path.join(screenshotRoot, `source-configuration-en-${viewport.width}x${viewport.height}.png`), fullPage: true })
    }

    expectSafeTraffic(audit)
  })

  test('Logitech A-J columns remain independent, explicit copies are confirmed, and preview reads once', async ({ page }) => {
    test.setTimeout(90_000)
    const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [], interceptedWrites: [], previewRequests: 0, savedMappings: [] }
    await installStrictMockApi(page, audit, 'en')
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/sources/source-logitech')

    await expect(page.getByRole('heading', { name: 'Logitech Pricing Workbook' })).toBeVisible()
    await expect(page.locator('input[name="worksheet-rule-mode"][value="per_worksheet"]')).toBeChecked()
    await page.locator('summary').filter({ hasText: 'Worksheet rules' }).click()
    await page.locator('input[name="worksheet-rule-mode"][value="shared"]').check()
    await expect(page.locator('input[name="worksheet-rule-mode"][value="shared"]')).toBeChecked()
    await page.screenshot({ path: path.join(screenshotRoot, 'worksheet-shared-rules.png'), fullPage: true })
    await page.locator('input[name="worksheet-rule-mode"][value="per_worksheet"]').check()
    await expect(page.locator('input[name="worksheet-rule-mode"][value="per_worksheet"]')).toBeChecked()
    await page.screenshot({ path: path.join(screenshotRoot, 'worksheet-independent-rules.png'), fullPage: true })
    await page.locator('summary').filter({ hasText: 'Worksheet columns' }).click()
    await expect(page.getByText('Logitech', { exact: true }).first()).toBeVisible()
    await page.getByRole('button', { name: 'Test connection' }).first().click()
    await expect(page.getByText('261 rows', { exact: true })).toBeVisible()
    const logitechRule = page.locator('[data-worksheet-rule="Logitech"]')
    await expect(logitechRule).toHaveAttribute('open', '')
    await expect(logitechRule.getByText('Digikala', { exact: true })).toBeVisible()
    await expect(logitechRule.getByRole('heading', { name: 'Coming Soon', exact: true })).toBeVisible()
    const digikalaSummary = logitechRule.locator('summary').filter({ hasText: 'Digikala' }).first()
    await expect(digikalaSummary.getByRole('checkbox')).toBeDisabled()
    await page.screenshot({ path: path.join(screenshotRoot, 'source-configuration-en.png'), fullPage: true })
    await expect(logitechRule.getByText('Source Product Name', { exact: true })).toHaveCount(1)
    await expect(logitechRule.getByLabel('Source Product Name column reference')).toHaveValue('A')

    const expectedColumns: Record<string, { external: string; price: string; stock: string }> = {
      WooCommerce: { external: 'D', price: 'B', stock: 'C' },
      SnappShop: { external: 'G', price: 'E', stock: 'F' },
      TapsiShop: { external: 'J', price: 'H', stock: 'I' },
    }
    for (const [channelName, values] of Object.entries(expectedColumns)) {
      const channelSummary = logitechRule.locator('summary').filter({ hasText: channelName }).first()
      const channelDetails = channelSummary.locator('..')
      if (!await channelDetails.evaluate(element => (element as HTMLDetailsElement).open)) await channelSummary.click()
      await expect(channelDetails).toHaveAttribute('open', '')
      await expect(channelDetails.getByLabel('Product identifier column reference')).toHaveValue(values.external)
      await expect(channelDetails.getByLabel('Price column reference')).toHaveValue(values.price)
      await expect(channelDetails.getByLabel('Stock column reference')).toHaveValue(values.stock)
      await expect(channelDetails.getByLabel('Status column reference')).toBeDisabled()
      await channelDetails.scrollIntoViewIfNeeded()
      await page.waitForTimeout(100)
      await page.screenshot({ path: path.join(screenshotRoot, `worksheet-logitech-${channelName.toLowerCase()}.png`), animations: 'disabled' })
    }
    await page.setViewportSize({ width: 1920, height: 2160 })
    await logitechRule.locator('[data-worksheet-channel-columns="Logitech"]').scrollIntoViewIfNeeded()
    await page.waitForTimeout(100)
    await page.screenshot({ path: path.join(screenshotRoot, 'worksheet-logitech-a-j.png'), animations: 'disabled' })
    await page.setViewportSize({ width: 1440, height: 900 })

    await logitechRule.getByRole('button', { name: 'Copy shared product fields' }).click()
    const copyDialog = page.getByRole('dialog', { name: 'Copy shared product fields' })
    await expect(copyDialog).toContainText('Source worksheet: Logitech')
    await expect(copyDialog).toContainText('Surface')
    await expect(copyDialog).toContainText('A')
    await page.screenshot({ path: path.join(screenshotRoot, 'copy-shared-fields-confirmation.png'), fullPage: true })
    expect(audit.savedMappings).toHaveLength(0)
    await copyDialog.getByRole('button', { name: 'Confirm copy' }).click()

    const wooSummary = logitechRule.locator('summary').filter({ hasText: 'WooCommerce' }).first()
    const wooDetails = wooSummary.locator('..')
    await expect(wooDetails).toHaveAttribute('open', '')
    const wooIdentifierMethod = wooDetails.getByLabel('Product identifier reference type')
    await wooIdentifierMethod.selectOption('disabled')
    await expect(wooDetails.getByText('Choose the Product identifier column for each enabled Channel.')).toBeVisible()
    await wooDetails.scrollIntoViewIfNeeded()
    await page.waitForTimeout(100)
    await page.screenshot({ path: path.join(screenshotRoot, 'worksheet-validation-error.png'), animations: 'disabled' })
    await wooIdentifierMethod.selectOption('column_letter')
    await wooDetails.getByLabel('Product identifier column reference').fill('D')
    await wooSummary.click()

    await page.getByRole('button', { name: 'Preview recognized rows' }).click()
    await expect(page.getByText('LOGITECH-MX-MASTER4-GRY', { exact: true })).toBeVisible()
    const previewArticle = page.locator('article').filter({ hasText: 'LOGITECH-MX-MASTER4-GRY' })
    await expect(previewArticle).toContainText('51550')
    await expect(previewArticle).toContainText('32200000')
    await expect(previewArticle).toContainText('29')
    await expect(previewArticle).toContainText('1826345203')
    await expect(previewArticle).toContainText('36550000')
    await expect(previewArticle).toContainText('41')
    await expect(previewArticle).toContainText('7785746738')
    await expect(previewArticle).toContainText('32950000')
    await expect(previewArticle).toContainText('17')
    expect(audit.previewRequests).toBe(1)
    await previewArticle.scrollIntoViewIfNeeded()
    await previewArticle.screenshot({ path: path.join(screenshotRoot, 'worksheet-preview-independent-values.png'), animations: 'disabled' })

    await page.getByTestId('source-configuration-actions').getByRole('button', { name: 'Save column setup', exact: true }).click()
    await expect.poll(() => audit.savedMappings.length).toBe(1)
    const saved = audit.savedMappings[0]
    expect(saved.worksheet_rule_mode).toBe('per_worksheet')
    const savedRules = saved.worksheet_rules as Array<{ worksheet_name: string; source_fields: Array<{ field: string; reference_value: string | null }>; channel_mappings: Array<{ channel_id: string; fields: Array<{ field: string; reference_value: string | null }> }> }>
    const savedLogitech = savedRules.find(rule => rule.worksheet_name === 'Logitech')
    expect(savedLogitech?.source_fields.find(item => item.field === 'name')?.reference_value).toBe('A')
    expect(savedLogitech?.channel_mappings.map(item => item.channel_id).sort()).toEqual([
      'woocommerce:primary',
      'snappshop:main',
      'tapsishop:main',
    ].sort())
    const savedChannelFields = Object.fromEntries((savedLogitech?.channel_mappings ?? []).map(item => [
      item.channel_id,
      Object.fromEntries(item.fields.map(mapped => [mapped.field, mapped.reference_value])),
    ]))
    expect(savedChannelFields).toEqual({
      'woocommerce:primary': { external_id: 'D', price: 'B', stock: 'C', status: null },
      'snappshop:main': { external_id: 'G', price: 'E', stock: 'F', status: null },
      'tapsishop:main': { external_id: 'J', price: 'H', stock: 'I', status: null },
    })

    expect(audit.previewRequests).toBe(1)
    expectSafeTraffic(audit, 1)
  })
})
