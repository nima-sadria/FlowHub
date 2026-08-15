import { expect, test, type Page, type Route } from '@playwright/test'

const sourceId = 'source-nextcloud-ugreen'
const nextcloudId = 'nextcloud:primary'

const mapping = {
  id: 'mapping-nextcloud-ugreen',
  version: 1,
  checksum: 'a'.repeat(64),
  worksheetMode: 'selected',
  worksheetName: 'UGREEN',
  selectedWorksheetNames: ['UGREEN'],
  dataStartRow: 2,
  valuePolicy: {},
  worksheetRuleMode: 'shared',
  duplicateProductPolicy: 'block',
  sourceFields: [
    { field: 'name', referenceType: 'column_letter', referenceValue: 'B', required: true },
    { field: 'source_key', referenceType: 'column_letter', referenceValue: 'A', required: true },
  ],
  channels: [
    {
      channelId: 'woocommerce:primary', worksheetName: null, enabled: true,
      fields: [
        { field: 'external_id', referenceType: 'column_letter', referenceValue: 'A' },
        { field: 'price', referenceType: 'column_letter', referenceValue: 'D' },
        { field: 'stock', referenceType: 'column_letter', referenceValue: 'E' },
        { field: 'status', referenceType: 'disabled', referenceValue: null },
      ],
    },
    {
      channelId: 'snappshop:main', worksheetName: null, enabled: false,
      fields: [
        { field: 'external_id', referenceType: 'disabled', referenceValue: null },
        { field: 'price', referenceType: 'disabled', referenceValue: null },
        { field: 'stock', referenceType: 'disabled', referenceValue: null },
        { field: 'status', referenceType: 'disabled', referenceValue: null },
      ],
    },
    {
      channelId: 'tapsishop:main', worksheetName: null, enabled: false,
      fields: [
        { field: 'external_id', referenceType: 'disabled', referenceValue: null },
        { field: 'price', referenceType: 'disabled', referenceValue: null },
        { field: 'stock', referenceType: 'disabled', referenceValue: null },
        { field: 'status', referenceType: 'disabled', referenceValue: null },
      ],
    },
  ],
  worksheetRules: [],
}

const sourceConfiguration = {
  id: sourceId,
  name: 'UGREEN Nextcloud catalog',
  sourceKind: 'external',
  externalSourceId: nextcloudId,
  worksheetMode: 'selected',
  worksheetName: 'UGREEN',
  dataStartRow: 2,
  status: 'active',
  version: 3,
  mappingVersion: 1,
  sheetId: null,
  mapping,
  legacyMapping: null,
}

const channels = [
  { channelId: 'woocommerce:primary', name: 'WooCommerce', connectorType: 'woocommerce', capabilityVersion: '1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
  { channelId: 'snappshop:main', name: 'SnappShop', connectorType: 'snappshop', capabilityVersion: '1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
  { channelId: 'tapsishop:main', name: 'TapsiShop', connectorType: 'tapsishop', capabilityVersion: '1', capabilities: {}, enabled: true, implementationState: 'implemented', available: true },
]

const preview = {
  items: [], total: 0, recognized: 0, ignored: 0, issues: [],
  identityValidation: { status: 'pass', validKeyCount: 1, missingKeyCount: 0, duplicateKeyCount: 0 },
  businessSummary: { productsFound: 0, productsReady: 0, priceChanges: null, stockChanges: null, unchanged: null, needsAttention: 0, channelsReady: 0, channelsNotConfigured: 0 },
  sheetRevisionId: 'nextcloud-ugreen-revision-1', mappingRevisionId: null,
}

async function installMocks(page: Page, savedMappings: Array<Record<string, unknown>>, previews: { count: number }) {
  await page.addInitScript(() => localStorage.setItem('wp_token', 'source-configuration-save-regression-token'))
  await page.route('**/*', async (route: Route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.pathname.startsWith('/static/')) return route.fulfill({ status: 204 })
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (request.method() === 'PUT' && url.pathname === `/api/v2/sources/${sourceId}/mappings`) {
      savedMappings.push(request.postDataJSON() as Record<string, unknown>)
      return json(mapping)
    }
    if (request.method() === 'POST' && url.pathname === `/api/v2/sources/${sourceId}/preview`) {
      previews.count += 1
      return json(preview)
    }
    if (request.method() === 'GET' && url.pathname === `/api/v2/sources/${sourceId}/configuration`) return json(sourceConfiguration)
    if (request.method() === 'GET' && url.pathname === '/api/v2/source-profiles/channels') return json({ items: channels })
    if (request.method() === 'GET' && url.pathname === `/api/v2/sources/${sourceId}/worksheets`) return json({
      sourceId, sourceRevisionId: 'nextcloud-ugreen-revision-1',
      items: [{ name: 'UGREEN', rowCount: 12, columns: [
        { id: 'A', letter: 'A', header: 'Website Product ID' }, { id: 'B', letter: 'B', header: 'Product Name' },
        { id: 'D', letter: 'D', header: 'Retail price' }, { id: 'E', letter: 'E', header: 'Stock' },
      ] }],
    })
    if (request.method() === 'GET' && url.pathname === `/api/v2/commerce/sources/${nextcloudId}/configuration`) return json({
      source_id: nextcloudId, provider: 'nextcloud', display_name: 'Nextcloud', configured: true, enabled: true,
      access_mode: 'read_only', settings: {}, secrets: {}, settings_schema: [], credentials_returned: false,
    })
    if (request.method() === 'GET' && url.pathname === '/api/auth/me') return json({
      username: 'source-regression-admin', role: 'admin', is_admin: true, is_super_admin: false,
      permissions: { can_access_site: true, can_fetch: true, can_view_logs: true, can_view_settings: true, 'workspace.admin': true }, maintenance: { enabled: false, message: '' },
    })
    if (request.method() === 'GET' && url.pathname === '/api/v2/setup/status') return json({ completed: true })
    if (request.method() === 'GET' && url.pathname === '/api/health') return json({ status: 'ok', version: 'source-configuration-save-regression' })
    return json({ code: 'UNHANDLED_TEST_REQUEST', message: `${request.method()} ${url.pathname}` }, 501)
  })
}

test('keeps visible Listing identity while Save auto-previews a valid UGREEN-only Nextcloud mapping', async ({ page }) => {
  const savedMappings: Array<Record<string, unknown>> = []
  const previews = { count: 0 }
  await installMocks(page, savedMappings, previews)
  await page.goto(`/sources/${sourceId}`)

  await expect(page.getByRole('heading', { name: 'UGREEN Nextcloud catalog' })).toBeVisible()
  await page.getByRole('button', { name: 'Detect worksheets' }).click()
  await page.locator('summary').filter({ hasText: 'Channel columns' }).click()
  const wooRow = page.locator('tr[data-channel-id="woocommerce:primary"]')
  await expect(page.getByLabel('Source Product Key column reference')).toHaveValue('A')
  await expect(wooRow.getByLabel('WooCommerce Product Identifier column reference')).toHaveValue('A')
  await expect(wooRow.getByText('WooCommerce Product Identifier', { exact: false })).toBeVisible()
  await expect(wooRow.getByText('It may use the same column as Source Product Key.', { exact: false })).toBeVisible()
  await expect(wooRow.getByLabel('WooCommerce Product Identifier column reference')).toHaveAttribute('aria-required', 'true')
  await expect(wooRow.getByLabel('Price column reference')).not.toHaveAttribute('aria-required', 'true')
  const priceCell = wooRow.locator('td').nth(4)
  await expect(priceCell.getByLabel('Price column reference')).toHaveValue('D')

  // Click the rendered controls as a browser user would. Reopening Advanced
  // must retain the controlled selection rather than restoring its old value.
  await priceCell.getByRole('button', { name: 'Advanced manual mapping' }).click()
  await priceCell.getByLabel('Price reference type').selectOption('header_name')
  await priceCell.getByLabel('Price column reference').fill('Retail price')
  await priceCell.getByRole('button', { name: 'Use discovered columns' }).click()
  await priceCell.getByRole('button', { name: 'Advanced manual mapping' }).click()
  await expect(priceCell.getByLabel('Price reference type')).toHaveValue('header_name')
  await expect(priceCell.getByLabel('Price column reference')).toHaveValue('Retail price')

  const actions = page.getByTestId('source-configuration-actions')
  await expect(actions).toContainText('Unsaved changes')
  await actions.getByRole('button', { name: 'Save column setup', exact: true }).click()

  await expect.poll(() => previews.count).toBe(1)
  await expect.poll(() => savedMappings).toHaveLength(1)
  await expect(page.getByText('Column setup saved', { exact: true })).toBeVisible()
  await expect(actions).toContainText('All changes saved')
  await expect(actions).not.toContainText('Unsaved changes')

  const payload = savedMappings[0]
  expect(payload.selected_worksheet_names).toEqual(['UGREEN'])
  const channelMappings = payload.channel_mappings as Array<{ channel_id: string; enabled: boolean; fields: Array<{ field: string; reference_type: string; reference_value: string | null }> }>
  expect(channelMappings.filter(channel => channel.enabled).map(channel => channel.channel_id)).toEqual(['woocommerce:primary'])
  expect((payload.source_fields as Array<{ field: string; reference_value: string | null }>).find(field => field.field === 'source_key')).toMatchObject({ reference_value: 'A' })
  expect(channelMappings.find(channel => channel.channel_id === 'woocommerce:primary')?.fields.find(field => field.field === 'external_id')).toMatchObject({ reference_value: 'A' })
  expect(channelMappings.find(channel => channel.channel_id === 'woocommerce:primary')?.fields.find(field => field.field === 'price')).toMatchObject({ reference_type: 'header_name', reference_value: 'Retail price' })
})
