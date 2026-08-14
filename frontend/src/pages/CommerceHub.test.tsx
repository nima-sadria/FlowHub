// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { ApiError } from '../api/client'
import { NotificationProvider } from '../notifications/NotificationProvider'
import NotificationContainer from '../notifications/NotificationContainer'
import { ServiceProvider } from '../services/ServiceContext'
import type { Services } from '../services/ServiceContext'
import type { CommerceService } from '../services/commerce/CommerceService'
import CommerceHub, { CommerceHubContent, ConfigPanel } from './CommerceHub'
import { changeLocale, translate } from '../i18n'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const commerce: CommerceService = {
  async getSources() {
    return {
      relationship_map: {
        nodes: ['Source', 'FlowHub / Data Layer', 'Channel'],
        example: ['Nextcloud', 'Data Layer', 'WooCommerce'],
        runtime_write_blocked: true,
        read_only: true,
      },
      items: [
        {
          id: 'nextcloud:primary',
          provider: 'nextcloud',
          name: 'Nextcloud',
          type: 'Source',
          status: 'not_configured',
          implemented: true,
          placeholder: false,
          credential_status: 'not_configured',
          connection_configured: false,
          configuration_state: 'not_configured',
          last_health_check: null,
          data_role: 'Spreadsheet price input',
          action_label: 'Manage',
          action_href: '/commerce?tab=sources',
          health: { status: 'unknown', message: '', latency_ms: null, error_code: null },
          read_only: true,
          runtime_write_blocked: true,
          settings_available: true,
        },
        {
          id: 'csv:import',
          provider: 'csv',
          name: 'CSV',
          type: 'Source',
          status: 'future',
          implemented: false,
          placeholder: true,
          credential_status: 'not_required',
          last_health_check: null,
          data_role: 'File import input',
          action_label: 'Manage',
          action_href: '/commerce?tab=sources',
          health: { status: 'unknown', message: '', latency_ms: null, error_code: null },
          read_only: true,
          runtime_write_blocked: true,
          settings_available: true,
        },
        {
          id: 'gsheets:price-list',
          provider: 'gsheets',
          name: 'Google Sheets',
          type: 'Source',
          status: 'future',
          implemented: false,
          placeholder: true,
          credential_status: 'not_configured',
          last_health_check: null,
          data_role: 'Spreadsheet price input',
          action_label: 'Manage',
          action_href: '/commerce?tab=sources',
          health: { status: 'unknown', message: '', latency_ms: null, error_code: null },
          read_only: true,
          runtime_write_blocked: true,
          settings_available: true,
        },
        {
          id: 'erp:api-import',
          provider: 'erp',
          name: 'ERP / API Import',
          type: 'Source',
          status: 'future',
          implemented: false,
          placeholder: true,
          credential_status: 'not_configured',
          last_health_check: null,
          data_role: 'System import input',
          action_label: 'Manage',
          action_href: '/commerce?tab=sources',
          health: { status: 'unknown', message: '', latency_ms: null, error_code: null },
          read_only: true,
          runtime_write_blocked: true,
          settings_available: true,
        },
      ],
    }
  },
  async getSourceTypes() {
    return {
      items: [
        typeOption('nextcloud:primary', 'nextcloud', 'Nextcloud', 'Source', false, [
          { key: 'url', label: 'Nextcloud URL', required: true, secret: false },
          { key: 'username', label: 'Username', required: true, secret: false },
          { key: 'password', label: 'Password', required: true, secret: true },
          { key: 'spreadsheet_path', label: 'Spreadsheet path', required: true, secret: false },
        ]),
        typeOption('csv:import', 'csv', 'CSV', 'Source', true, [
          { key: 'file_path', label: 'File path', required: false, secret: false },
        ]),
      ],
    }
  },
  async getChannelTypes() {
    return {
      items: [
        typeOption('woocommerce:primary', 'woocommerce', 'WooCommerce', 'Channel', false, [
          { key: 'url', label: 'Store URL', required: true, secret: false },
          { key: 'key', label: 'Consumer key', required: true, secret: true },
          { key: 'secret', label: 'Consumer secret', required: true, secret: true },
        ]),
        typeOption('snappshop:main', 'snappshop', 'Snapp Shop', 'Channel', false, [
          { key: 'base_url', label: 'Base URL', required: false, secret: false },
          { key: 'agent_identifier', label: 'Agent identifier', required: true, secret: false },
          { key: 'agent_header_name', label: 'Agent header name', required: false, secret: false },
          { key: 'request_timeout', label: 'Request timeout seconds', required: false, secret: false },
          { key: 'vendor_id', label: 'Vendor ID', required: false, secret: false },
          { key: 'token', label: 'Bearer token', required: true, secret: true },
        ]),
        typeOption('tapsishop:main', 'tapsishop', 'Tapsi Shop', 'Channel', false, [
          { key: 'base_url', label: 'Base URL', required: false, secret: false },
          { key: 'request_timeout', label: 'Request timeout seconds', required: false, secret: false },
          { key: 'selected_vendor_id', label: 'Selected vendor/store ID', required: false, secret: false },
          { key: 'token_refresh_enabled', label: 'Token refresh enabled', required: false, secret: false },
          { key: 'token_refresh_name', label: 'Token refresh name', required: false, secret: false },
          { key: 'revoke_current_token', label: 'Revoke current token on refresh', required: false, secret: false },
          { key: 'token', label: 'Authorization token', required: true, secret: true },
          { key: 'webhook_token', label: 'Webhook token', required: false, secret: true },
        ]),
        {
          ...typeOption('digikala:main', 'digikala', 'Digikala', 'Channel', true, [
            { key: 'access_token', label: 'Access token', required: true, secret: true },
            { key: 'refresh_token', label: 'Refresh token', required: false, secret: true },
          ]),
          implemented: true,
          implementation_status: 'IMPLEMENTED_UNVERIFIED',
        },
        typeOption('technolife:main', 'technolife', 'Technolife', 'Channel', false, [
          { key: 'base_url', label: 'Base URL', required: false, secret: false },
          { key: 'request_timeout', label: 'Request timeout seconds', required: false, secret: false },
          { key: 'api_key', label: 'API key', required: true, secret: true },
          { key: 'encryption_secret', label: 'Encryption secret', required: true, secret: true },
        ]),
      ],
    }
  },
  async getSourceConfiguration(sourceId) {
    const provider = sourceId.split(':')[0]
    const schemas = (await this.getSourceTypes()).items
    const option = schemas.find(item => item.id === sourceId)
    return {
      source_id: sourceId,
      provider,
      display_name: option?.name ?? sourceId,
      configured: false,
      enabled: false,
      access_mode: 'read_only' as const,
      settings: Object.fromEntries((option?.settings_schema ?? [])
        .filter(field => !field.secret && field.default !== undefined)
        .map(field => [field.key, field.default])),
      secrets: {},
      settings_schema: option?.settings_schema ?? [],
      credentials_returned: false as const,
      currency_profile: { status: 'resolved' as const, currency: 'IRR', unit: 'RIAL' },
    }
  },
  async getChannelConfiguration(channelId) {
    const provider = channelId.split(':')[0]
    const schemas = (await this.getChannelTypes()).items
    const option = schemas.find(item => item.id === channelId)
    return {
      channel_id: channelId,
      provider,
      display_name: option?.name ?? channelId,
      configured: false,
      enabled: false,
      access_mode: 'read_only' as const,
      settings: Object.fromEntries((option?.settings_schema ?? [])
        .filter(field => !field.secret && field.default !== undefined)
        .map(field => [field.key, field.default])),
      secrets: {},
      token_configured: false,
      webhook_token_configured: false,
      settings_schema: option?.settings_schema ?? [],
      webhook_path: provider === 'tapsishop' ? `/api/v2/webhooks/tapsishop/${channelId}` : null,
      credentials_returned: false as const,
      currency_profile: { status: 'resolved' as const, currency: 'IRR', unit: 'RIAL' },
    }
  },
  async saveSource() {
    return {
      settings: {},
      secrets: { password: { status: 'configured', replaced_at: null } },
      read_only: true,
      runtime_write_blocked: true,
      write_blocked: true,
    }
  },
  async createSource(_sourceTypeId, payload) {
    return {
      ...(await this.saveSource('nextcloud:test-replacement', payload)),
      source_id: 'nextcloud:test-replacement',
    }
  },
  async saveChannel() {
    return {
      settings: {},
      secrets: { secret: { status: 'configured', replaced_at: null } },
      read_only: true,
      runtime_write_blocked: true,
      write_blocked: true,
    }
  },
  async testSource() {
    return {
      ok: true,
      status: 'operational',
      message: 'Connection successful. Spreadsheet found.',
      external_call_performed: true,
      read_only: true,
      runtime_write_blocked: true,
      write_blocked: true,
      webdav_reachable: true,
      spreadsheet_found: true,
      normalized_base_url: 'https://softpple.business',
      normalized_webdav_url: 'https://softpple.business/remote.php/dav/files/woo/',
      checked_at: '2026-07-09T10:00:00Z',
    }
  },
  async testSourceType(sourceTypeId, payload) {
    return this.testSource(sourceTypeId, payload)
  },
  async readSource() {
    return {
      ok: true,
      rows_read: 1,
      valid_rows: 1,
      warning_rows: 0,
      error_rows: 0,
      last_read_at: '2026-07-09T10:00:00Z',
      remaining_reads_today: 9,
      reads_used_last_24h: 1,
      reads_remaining: 9,
      reset_at: null,
      warnings: [],
      errors: [],
      source_id: 'nextcloud:primary',
      source_type: 'nextcloud_spreadsheet',
      spreadsheet_path: '/prices.xlsx',
      external_call_performed: true,
      read_only: true,
      source_write: false,
      write_blocked: true,
    }
  },
  async getChannels() {
    return {
      items: [
        channel('woocommerce:primary', 'WooCommerce', false),
        channel('snappshop:main', 'Snapp Shop', false),
        channel('tapsishop:main', 'Tapsi Shop', false),
        {
          ...channel('digikala:main', 'Digikala', true),
          implemented: true,
          status: 'coming_soon',
          implementation_status: 'IMPLEMENTED_UNVERIFIED',
          settings_available: false,
        },
        channel('technolife:main', 'Technolife', false),
        channel('shopify:main', 'Shopify', true),
      ],
    }
  },
  async testChannel() {
    return {
      ok: false,
      status: 'not_configured',
      message: 'No external call was performed.',
      external_call_performed: false,
      read_only: true,
      runtime_write_blocked: true,
      write_blocked: true,
    }
  },
  async refreshChannelCache() {
    return {
      ok: true,
      status: 'completed',
      products_read: 2,
      variable_products_read: 1,
      variations_read: 2,
      cache_rows_upserted: 4,
      warnings: [],
      errors: [],
      started_at: '2026-07-10T10:00:00Z',
      completed_at: '2026-07-10T10:00:01Z',
      read_only: true,
      external_write: false,
      stock_write: false,
      source_write: false,
      dry_run_created: false,
      approval_created: false,
      apply_executed: false,
      credentials_returned: false,
    }
  },
  async browseNextcloud() {
    return {
      path: '/',
      directories: [
        {
          name: 'Reports',
          path: '/Reports',
          type: 'directory' as const,
          extension: '',
          modified_at: null,
          size: null,
          supported: true,
        },
      ],
      files: [
        {
          name: 'prices.xlsx',
          path: '/prices.xlsx',
          type: 'file' as const,
          extension: '.xlsx',
          modified_at: null,
          size: 1234,
          supported: true,
        },
        {
          name: 'legacy.csv',
          path: '/legacy.csv',
          type: 'file' as const,
          extension: '.csv',
          modified_at: null,
          size: 512,
          supported: false,
        },
      ],
      read_only: true,
      write_blocked: true,
      external_call_performed: true,
      credentials_returned: false,
    }
  },
}

function typeOption(
  id: string,
  provider: string,
  name: string,
  type: 'Source' | 'Channel',
  placeholder: boolean,
  settings_schema: Array<{ key: string; label: string; required: boolean; secret: boolean }>,
) {
  return {
    id,
    provider,
    name,
    type,
    implemented: !placeholder,
    placeholder,
    read_only: true,
    write_blocked: type === 'Channel',
    runtime_write_blocked: true,
    settings_schema,
  }
}

function channel(id: string, name: string, placeholder: boolean) {
  return {
    id,
    provider: id.split(':')[0],
    name,
    type: 'Channel' as const,
    status: placeholder ? 'not_configured' : 'configured',
    implemented: !placeholder,
    placeholder,
    enabled: !placeholder,
    read_only: true,
    write_blocked: true,
    runtime_write_blocked: true,
    credential_status: 'not_configured',
    token_configured: false,
    webhook_token_configured: false,
    last_health_check: null,
    health: { status: 'unknown', message: '', latency_ms: null, error_code: null },
    capabilities: { read_products: true },
    capabilities_summary: ['Product read'],
    settings_available: true,
    cached_products: id === 'woocommerce:primary' ? 2 : 0,
    cached_variations: id === 'woocommerce:primary' ? 2 : 0,
    last_cache_refresh: id === 'woocommerce:primary' ? '2026-07-10T10:00:01Z' : null,
    cache_refresh_status: id === 'woocommerce:primary' ? 'completed' : 'not_run',
  }
}

const services: Services = {
  commerce,
  health: {} as Services['health'],
  products: {} as Services['products'],
  sources: {} as Services['sources'],
  workspace: {} as Services['workspace'],
  settings: {} as Services['settings'],
  activity: {} as Services['activity'],
  writePipeline: {} as Services['writePipeline'],
}

const adminUser: AuthUser = {
  username: 'admin',
  role: 'admin',
  is_admin: true,
  is_super_admin: false,
  permissions: { can_access_site: true, can_fetch: true, can_view_settings: true },
}

const viewerUser: AuthUser = {
  username: 'viewer',
  role: 'viewer',
  is_admin: false,
  is_super_admin: false,
  permissions: { can_access_site: true, can_fetch: true, can_view_settings: false },
}

function authValue(user: AuthUser): AuthContextValue {
  return {
    user,
    status: 'authenticated',
    refreshUser: async () => undefined,
    clearAuth: () => undefined,
    logout: async () => undefined,
    authFetch: fetch,
  }
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(async () => {
  act(() => { root.unmount() })
  container.remove()
  await changeLocale('en')
  vi.restoreAllMocks()
})

async function renderPage(user = adminUser, commerceOverride: CommerceService = commerce, initialEntries: string[] = ['/commerce']) {
  await act(async () => {
    root.render(
      <NotificationProvider>
        <AuthContext.Provider value={authValue(user)}>
          <MemoryRouter key={initialEntries[0]} initialEntries={initialEntries}>
            <ServiceProvider services={{ ...services, commerce: commerceOverride }}>
              <CommerceHubContent key={initialEntries[0]} />
            </ServiceProvider>
            <NotificationContainer />
          </MemoryRouter>
        </AuthContext.Provider>
      </NotificationProvider>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return container
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

function inputByLabel(c: HTMLElement, labelText: string): HTMLInputElement {
  const label = Array.from(c.querySelectorAll('label'))
    .find(item => item.textContent?.toLowerCase().includes(labelText.toLowerCase()))
  const input = label?.querySelector('input')
  expect(input).toBeTruthy()
  return input as HTMLInputElement
}

function LocationProbe() {
  const location = useLocation()
  return <p data-testid="redirect-location">{location.pathname}{location.search}</p>
}

async function renderLegacyRedirect(initialEntry: string) {
  await act(async () => {
    root.render(
      <NotificationProvider>
        <AuthContext.Provider value={authValue(adminUser)}>
          <MemoryRouter initialEntries={[initialEntry]}>
            <ServiceProvider services={services}>
              <Routes>
                <Route path="/commerce" element={<CommerceHub />} />
                <Route path="/channels" element={<LocationProbe />} />
              </Routes>
            </ServiceProvider>
          </MemoryRouter>
        </AuthContext.Provider>
      </NotificationProvider>,
    )
    await Promise.resolve()
  })
}

function selectByLabel(c: HTMLElement, labelText: string): HTMLSelectElement {
  const label = Array.from(c.querySelectorAll('label'))
    .find(item => item.textContent?.toLowerCase().includes(labelText.toLowerCase()))
  const select = label?.querySelector('select')
  expect(select).toBeTruthy()
  return select as HTMLSelectElement
}

function resourceAction(c: HTMLElement, resourceName: string, actionName: string): HTMLButtonElement {
  const card = Array.from(c.querySelectorAll('h3'))
    .find(item => item.textContent === resourceName)
    ?.closest('.fh-card')
  const action = Array.from(card?.querySelectorAll('button') ?? [])
    .find(button => button.textContent === actionName)
  expect(action).toBeTruthy()
  return action as HTMLButtonElement
}

async function openNextcloudSourceForm(c: HTMLElement) {
  await act(async () => {
    Array.from(c.querySelectorAll('button'))
      .find(button => button.textContent === 'Add source')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
  await act(async () => {
    const unit = selectByLabel(c, 'Price unit')
    unit.value = 'RIAL'
    unit.dispatchEvent(new Event('change', { bubbles: true }))
    inputByLabel(c, 'Enabled').click()
  })
  expect(inputByLabel(c, 'Enabled').checked).toBe(true)
}

function fillNextcloudCredentials(c: HTMLElement, baseUrl = 'https://softpple.business', username: string | null = 'owner') {
  act(() => {
    setInputValue(inputByLabel(c, 'Nextcloud server URL'), baseUrl)
    if (username !== null) {
      setInputValue(inputByLabel(c, 'Username'), username)
    }
    setInputValue(c.querySelector('input[type="password"]') as HTMLInputElement, 'app-password-value')
  })
}

async function saveNextcloudConnection(c: HTMLElement) {
  const saveConnection = Array.from(c.querySelectorAll('button'))
    .find(button => button.textContent === 'Save connection') as HTMLButtonElement
  expect(saveConnection.disabled).toBe(false)
  await act(async () => {
    saveConnection.click()
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function testSavedNextcloudConnection(c: HTMLElement) {
  const testConnection = Array.from(c.querySelectorAll('button'))
    .find(button => button.textContent === 'Test connection') as HTMLButtonElement
  expect(testConnection.disabled).toBe(false)
  await act(async () => {
    testConnection.click()
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function selectNextcloudSpreadsheet(c: HTMLElement) {
  let browse = Array.from(c.querySelectorAll('button'))
    .find(button => button.textContent === 'Browse Nextcloud') as HTMLButtonElement
  if (browse.disabled) {
    await saveNextcloudConnection(c)
    browse = Array.from(c.querySelectorAll('button'))
      .find(button => button.textContent === 'Browse Nextcloud') as HTMLButtonElement
  }
  if (browse.disabled) {
    await testSavedNextcloudConnection(c)
    browse = Array.from(c.querySelectorAll('button'))
      .find(button => button.textContent === 'Browse Nextcloud') as HTMLButtonElement
  }
  expect(browse.disabled).toBe(false)
  await act(async () => { browse.click(); await Promise.resolve(); await Promise.resolve() })
  const file = Array.from(c.querySelectorAll('button'))
    .find(button => button.textContent?.includes('prices.xlsx')) as HTMLButtonElement
  expect(file).toBeTruthy()
  await act(async () => file.click())
}

describe('CommerceHub', () => {
  it('presents an archived linked Source without enable, edit, or provider actions', async () => {
    const original = await commerce.getSources()
    const archivedCommerce: CommerceService = {
      ...commerce,
      async getSources() {
        return {
          ...original,
          items: [{
            ...original.items[0],
            status: 'archived',
            lifecycle_status: 'archived',
            source_profile_id: 'source-archived',
            archived_at: '2026-08-13T08:30:00Z',
            enabled: false,
            credential_status: 'configured',
            connection_configured: true,
            configuration_state: 'configured',
          }],
        }
      },
    }

    const c = await renderPage(adminUser, archivedCommerce, ['/commerce?tab=sources'])
    const card = c.querySelector('[data-source-id="nextcloud:primary"]') as HTMLElement
    expect(card.textContent).toContain('Archived')
    expect(card.textContent).toContain('View Data Sheet')
    expect(Array.from(card.querySelectorAll('button')).some(button => button.textContent === 'Edit connection')).toBe(false)
    expect(Array.from(card.querySelectorAll('button')).some(button => button.textContent === 'Test connection')).toBe(false)
    expect(c.querySelector('[data-resource-section="archived"]')).not.toBeNull()
  })

  it('creates and tests a fresh connector instead of reusing an archived Nextcloud identity', async () => {
    const createSource = vi.fn(async (_sourceTypeId, payload) => ({
      ...(await commerce.saveSource('nextcloud:replacement-1', payload)),
      source_id: 'nextcloud:replacement-1',
      connection_configured: true,
      configuration_state: 'setup_required' as const,
    }))
    const saveSource = vi.fn(async () => {
      throw new Error('the archived connector must not receive the new configuration')
    })
    const testSource = vi.fn((sourceId, payload) => commerce.testSource(sourceId, payload))
    const testSourceType = vi.fn((sourceTypeId, payload) => commerce.testSourceType(sourceTypeId, payload))
    const replacementCommerce: CommerceService = {
      ...commerce,
      createSource,
      saveSource,
      testSource,
      testSourceType,
    }
    const c = await renderPage(adminUser, replacementCommerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    fillNextcloudCredentials(c, 'https://replacement.example.test', 'replacement-owner')

    await saveNextcloudConnection(c)
    expect(createSource).toHaveBeenCalledWith(
      'nextcloud:primary',
      expect.objectContaining({
        settings: expect.objectContaining({
          url: 'https://replacement.example.test',
          username: 'replacement-owner',
        }),
        secrets: { password: 'app-password-value' },
      }),
    )
    expect(saveSource).not.toHaveBeenCalled()

    await testSavedNextcloudConnection(c)
    expect(testSource).toHaveBeenCalledWith(
      'nextcloud:replacement-1',
      expect.any(Object),
    )
    expect(testSourceType).not.toHaveBeenCalled()
  })

  it('renders the three persisted Source setup states with Owner-approved semantics', async () => {
    const original = await commerce.getSources()
    const base = original.items[0]
    const stateCommerce: CommerceService = {
      ...commerce,
      async getSources() {
        return {
          ...original,
          items: [
            {
              ...base,
              id: 'nextcloud:empty',
              name: 'Empty Source',
              credential_status: 'not_configured',
              connection_configured: false,
              configuration_state: 'not_configured',
            },
            {
              ...base,
              id: 'nextcloud:partial',
              name: 'Partial Source',
              credential_status: 'configured',
              connection_configured: true,
              configuration_state: 'setup_required',
            },
            {
              ...base,
              id: 'nextcloud:ready',
              name: 'Ready Source',
              credential_status: 'configured',
              connection_configured: true,
              configuration_state: 'configured',
            },
          ],
        }
      },
    }

    const c = await renderPage(adminUser, stateCommerce, ['/commerce?tab=sources'])
    const empty = c.querySelector('[data-source-id="nextcloud:empty"]') as HTMLElement
    const partial = c.querySelector('[data-source-id="nextcloud:partial"]') as HTMLElement
    const ready = c.querySelector('[data-source-id="nextcloud:ready"]') as HTMLElement

    expect(empty.querySelector('.fh-badge-warning')?.textContent).toBe('Add now')
    expect(partial.querySelector('.fh-badge-info')?.textContent).toBe('Connected • Setup required')
    expect(ready.querySelector('.fh-badge-success')?.textContent).toBe('Configured')
    expect(Array.from(empty.querySelectorAll('button')).some(button => button.textContent === 'Configure Data')).toBe(false)
    expect(Array.from(partial.querySelectorAll('button')).some(button => button.textContent === 'Configure Data')).toBe(false)
    expect(Array.from(ready.querySelectorAll('button')).some(button => button.textContent === 'Configure Data')).toBe(true)
    expect(Array.from(empty.querySelectorAll('button')).some(button => button.textContent === 'Test connection')).toBe(false)
    expect(Array.from(partial.querySelectorAll('button')).some(button => button.textContent === 'Test connection')).toBe(true)
    expect(Array.from(ready.querySelectorAll('button')).some(button => button.textContent === 'Test connection')).toBe(true)
  })

  it('redirects legacy Channel URLs to the canonical Channels workflow', async () => {
    await renderLegacyRedirect('/commerce?tab=channels&resource=woocommerce%3Aprimary')
    expect(container.querySelector('[data-testid="redirect-location"]')?.textContent)
      .toBe('/channels?setup=woocommerce%3Aprimary')
  })

  it('redirects a legacy Commerce landing URL without rendering duplicate Channel cards', async () => {
    await renderLegacyRedirect('/commerce')
    expect(container.querySelector('[data-testid="redirect-location"]')?.textContent).toBe('/channels')
    expect(container.querySelectorAll('[data-channel-card]')).toHaveLength(0)
  })

  it('localizes channel statuses and capabilities in Persian', async () => {
    await changeLocale('fa')
    const c = await renderPage()

    expect(c.textContent).toContain('کانال')
    expect(c.textContent).toContain(translate('common:resourceBadge.warning'))
    expect(c.textContent).toContain('خواندن محصولات')
    expect(c.textContent).toContain('حالت فقط‌خواندنی')
    expect(c.textContent).not.toContain('Product read')
    expect(c.textContent).not.toContain('Not Configured')
    await changeLocale('en')
  })

  it('renders the Commerce Hub route content and Channels section', async () => {
    const c = await renderPage()
    expect(c.textContent).toContain('Manage connected sales channels')
    expect(c.textContent).toContain('Channels')
    expect(c.textContent).toContain('WooCommerce')
    expect(c.textContent).toContain('SnappShop')
    expect(c.textContent).toContain('TapsiShop')
    expect(c.textContent).toContain('Coming Soon')
    expect(c.textContent).toContain('Read-only mode')
    expect(c.textContent).toContain('Writes blocked')
    expect(c.textContent).toContain('Add channel')
    expect(c.textContent).not.toContain('Apply')
  })

  it('shows configuration actions only for implemented channels', async () => {
    const c = await renderPage()

    expect(Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Refresh cache')).toHaveLength(1)
    expect(Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Settings')).toHaveLength(0)
    expect(Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Configure')).toHaveLength(3)
    expect(c.textContent).toContain('Cached products: 2')
    expect(c.textContent).toContain('Cached variations: 2')
    expect(c.textContent).toContain('Refresh status: Completed')
    expect(c.querySelector('button [data-icon="edit"]')).not.toBeNull()
    expect(c.querySelector('button [data-icon="testConnection"]')).not.toBeNull()
    expect(c.querySelector('button [data-icon="refresh"]')).not.toBeNull()

    const sources = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])

    expect(sources.textContent).not.toContain('Refresh cache')
    expect(Array.from(sources.querySelectorAll('button')).filter(button => button.textContent === 'Read now')).toHaveLength(0)
    expect(Array.from(sources.querySelectorAll('button')).filter(button => button.textContent === 'Edit Connection')).toHaveLength(1)
  })

  it('shows Settings for configured marketplaces and keeps planned channels non-actionable', async () => {
    const configuredCommerce: CommerceService = {
      ...commerce,
      async getChannels() {
        const original = await commerce.getChannels()
        return {
          ...original,
          items: original.items.map(item => item.provider === 'snappshop'
            ? { ...item, credential_status: 'configured', token_configured: true }
            : item),
        }
      },
    }
    const c = await renderPage(adminUser, configuredCommerce)

    expect(Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Settings')).toHaveLength(1)
    expect(Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Configure')).toHaveLength(2)
    expect(Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Refresh cache')).toHaveLength(2)
    const digikala = Array.from(c.querySelectorAll('h3')).find(item => item.textContent === 'Digikala')?.closest('.fh-card')
    expect(digikala?.textContent).toContain('Coming Soon')
    expect(Array.from(digikala?.querySelectorAll('button') ?? [])).toHaveLength(0)
    const shopify = Array.from(c.querySelectorAll('h3')).find(item => item.textContent === 'Shopify')?.closest('.fh-card')
    expect(Array.from(shopify?.querySelectorAll('button') ?? [])).toHaveLength(0)
  })

  it('does not load a legacy configuration panel for an implemented-but-Coming-Soon Digikala type', async () => {
    const getChannelConfiguration = vi.fn()
    const digikalaCommerce: CommerceService = {
      ...commerce,
      getChannelConfiguration,
    }
    const types = (await commerce.getChannelTypes()).items

    await act(async () => {
      root.render(
        <NotificationProvider>
          <AuthContext.Provider value={authValue(adminUser)}>
            <MemoryRouter>
              <ServiceProvider services={{ ...services, commerce: digikalaCommerce }}>
                <ConfigPanel
                  kind="channel"
                  types={types}
                  initialResourceId="digikala:main"
                  onCancel={vi.fn()}
                  onSaved={vi.fn()}
                />
              </ServiceProvider>
            </MemoryRouter>
          </AuthContext.Provider>
        </NotificationProvider>,
      )
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(container.querySelector('[data-testid="configuration-coming-soon"]')).not.toBeNull()
    expect(container.textContent).toContain('Coming Soon')
    expect(container.textContent).not.toContain('Access token')
    expect(container.textContent).not.toContain('Test connection')
    expect(getChannelConfiguration).not.toHaveBeenCalled()
  })

  it('loads sanitized SnappShop settings, masks the token, and discovers vendors from unsaved test values', async () => {
    let testedPayload: Parameters<CommerceService['testChannel']>[1]
    const snappCommerce: CommerceService = {
      ...commerce,
      async getChannelConfiguration(channelId) {
        const base = await commerce.getChannelConfiguration(channelId)
        return {
          ...base,
          display_name: 'Primary SnappShop',
          settings: {
            base_url: 'https://apix.snappshop.ir/automation/v1',
            agent_identifier: 'flowhub-agent',
            agent_header_name: 'User-Agent',
            request_timeout: '20',
            vendor_id: '',
          },
          secrets: { token: { status: 'configured', replaced_at: '2026-07-12T00:00:00Z' } },
          token_configured: true,
        }
      },
      async testChannel(_channelId, payload) {
        testedPayload = payload
        return {
          ok: true,
          status: 'credentials_verified',
          message: 'Connected to SnappShop.',
          external_call_performed: true,
          read_only: true,
          runtime_write_blocked: true,
          write_blocked: true,
          vendors: [{ id: 'vendor-1', name: 'Primary Vendor', title: 'فروشگاه اصلی', title_en: 'Primary Vendor', status: 'ACTIVE' }],
          suggested_vendor_id: 'vendor-1',
        }
      },
    }
    const c = await renderPage(adminUser, snappCommerce)
    const configure = resourceAction(c, 'SnappShop', 'Configure')
    await act(async () => {
      configure.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Configure SnappShop')
    expect(c.textContent).toContain('Agent identifier')
    expect(c.textContent).not.toContain('Agent header name')
    expect(c.textContent).not.toContain('Request timeout seconds')
    const token = c.querySelector('input[type="password"]') as HTMLInputElement
    expect(token.value).toBe('')
    expect(c.textContent).toContain('Configured; leave blank to keep unchanged.')
    const accessMode = selectByLabel(c, 'Access mode')
    expect(Array.from(accessMode.options).map(option => option.value))
      .toEqual(['read_only', 'write_enabled'])
    await act(async () => {
      accessMode.value = 'write_enabled'
      accessMode.dispatchEvent(new Event('change', { bubbles: true }))
    })
    const form = accessMode.closest('form') as HTMLFormElement
    expect(form.textContent).toContain('Write enabled')
    expect(form.textContent).not.toContain('Read-only mode')
    expect(form.textContent).not.toContain('Writes blocked')

    const test = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')
    expect((test as HTMLButtonElement).disabled).toBe(false)
    await act(async () => {
      test?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })
    expect(testedPayload?.settings.agent_identifier).toBe('flowhub-agent')
    expect(testedPayload?.secrets.token).toBeUndefined()
    const vendorSelect = selectByLabel(c, 'Vendor / store')
    expect(vendorSelect.value).toBe('vendor-1')
    expect(vendorSelect.textContent).toContain('Primary Vendor')
    expect(c.textContent).toContain('Channel connection verified')
    expect(c.textContent).toContain('This connection test used unsaved values. Save the configuration before the channel is ready to use.')
    expect(c.textContent).not.toContain('SnappShop is ready to use.')
    expect(c.querySelector('[role="alert"] [data-icon="success"]')).not.toBeNull()
  })

  it('allows credentials to be saved before discovery and requires a vendor after discovery', async () => {
    const snappCommerce: CommerceService = {
      ...commerce,
      async getChannelConfiguration(channelId) {
        const base = await commerce.getChannelConfiguration(channelId)
        return {
          ...base,
          settings: { agent_identifier: 'flowhub-agent', request_timeout: 30, vendor_id: '' },
          secrets: { token: { status: 'configured', replaced_at: null } },
          token_configured: true,
        }
      },
      async testChannel() {
        return {
          ok: true,
          status: 'credentials_verified',
          message: 'Verified',
          external_call_performed: true,
          read_only: true,
          runtime_write_blocked: true,
          write_blocked: true,
          vendors: [
            { id: 'vendor-1', name: 'Vendor One', status: 'ACTIVE' },
            { id: 'vendor-2', name: 'Vendor Two', status: 'ACTIVE' },
            { id: 'vendor-3', name: 'Vendor Three', status: 'INACTIVE' },
          ],
          suggested_vendor_id: null,
        }
      },
    }
    const c = await renderPage(adminUser, snappCommerce)
    const configure = resourceAction(c, 'SnappShop', 'Configure')
    await act(async () => {
      configure.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })
    const saveBeforeDiscovery = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Save configuration') as HTMLButtonElement
    expect(saveBeforeDiscovery.disabled).toBe(false)

    await act(async () => {
      Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })

    const vendorSelect = selectByLabel(c, 'Vendor / store')
    const save = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Save configuration') as HTMLButtonElement
    expect(vendorSelect.value).toBe('')
    expect(save.disabled).toBe(true)
    expect(Array.from(vendorSelect.options).find(option => option.value === 'vendor-3')?.disabled).toBe(true)

    await act(async () => {
      vendorSelect.value = 'vendor-2'
      vendorSelect.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(save.disabled).toBe(false)
  })

  it('renders separate TapsiShop secrets and the webhook registration URL', async () => {
    const tapsiCommerce: CommerceService = {
      ...commerce,
      async getChannelConfiguration(channelId) {
        const base = await commerce.getChannelConfiguration(channelId)
        return {
          ...base,
          settings: { base_url: 'https://vendorgw.tapsi.shop/Web/Hub/vendors/v1', request_timeout: '30' },
          secrets: {
            token: { status: 'configured', replaced_at: null },
            webhook_token: { status: 'configured', replaced_at: null },
          },
          token_configured: true,
          webhook_token_configured: true,
        }
      },
    }
    const c = await renderPage(adminUser, tapsiCommerce)
    const configure = resourceAction(c, 'TapsiShop', 'Configure')
    await act(async () => {
      configure.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })

    const secretInputs = Array.from(c.querySelectorAll('input[type="password"]')) as HTMLInputElement[]
    expect(secretInputs).toHaveLength(2)
    expect(secretInputs.every(input => input.value === '')).toBe(true)
    expect(c.textContent).not.toContain('TapsiShop API URL')
    expect(c.textContent).toContain('TapsiShop authorization token')
    expect(c.textContent).toContain('Webhook registration')
    expect(c.textContent).toContain('Webhook credential: Configured')
    expect(c.textContent).toContain('Dry Run, Review, Approval, Apply')
    expect(c.textContent).toContain('Variations, listing creation, categories, attributes, discounts, and courier review are unavailable')
    expect((inputByLabel(c, 'Webhook URL')).value).toContain('/api/v2/webhooks/tapsishop/tapsishop%3Amain')
    const accessMode = selectByLabel(c, 'Access mode')
    expect(Array.from(accessMode.options).map(option => option.value)).toEqual(['read_only', 'write_enabled'])
    expect(accessMode.value).toBe('read_only')
  })

  it('refreshes a marketplace card from Configure to Settings after save', async () => {
    let saved = false
    const savingCommerce: CommerceService = {
      ...commerce,
      async getChannels() {
        const original = await commerce.getChannels()
        return {
          ...original,
          items: original.items.map(item => saved && item.provider === 'snappshop'
            ? { ...item, credential_status: 'configured', token_configured: true }
            : item),
        }
      },
      async getChannelConfiguration(channelId) {
        const base = await commerce.getChannelConfiguration(channelId)
        return {
          ...base,
          settings: { agent_identifier: 'flowhub-agent', vendor_id: 'vendor-1' },
          secrets: { token: { status: 'configured', replaced_at: null } },
          token_configured: true,
        }
      },
      async saveChannel(channelId, payload) {
        saved = true
        return commerce.saveChannel(channelId, payload)
      },
    }
    const c = await renderPage(adminUser, savingCommerce)
    const configure = resourceAction(c, 'SnappShop', 'Configure')
    await act(async () => {
      configure.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })
    await act(async () => {
      Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Save configuration')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(Array.from(c.querySelectorAll('button')).some(button => button.textContent === 'Settings')).toBe(true)
  })

  it('shows cache refresh loading, success, and refreshed channel counts', async () => {
    let refreshed = false
    let resolveRefresh: ((value: Awaited<ReturnType<CommerceService['refreshChannelCache']>>) => void) | undefined
    const refreshCommerce: CommerceService = {
      ...commerce,
      async getChannels() {
        const original = await commerce.getChannels()
        const items = [...original.items]
        if (refreshed) {
          items[0] = {
            ...items[0],
            cached_products: 7,
            cached_variations: 3,
            cache_refresh_status: 'completed',
            last_cache_refresh: '2026-07-10T11:00:01Z',
          }
        }
        return { ...original, items }
      },
      async refreshChannelCache() {
        return new Promise(resolve => {
          resolveRefresh = resolve
        })
      },
    }
    const c = await renderPage(adminUser, refreshCommerce)
    const refreshButton = Array.from(c.querySelectorAll('button'))
      .find(button => button.textContent === 'Refresh cache')

    await act(async () => {
      refreshButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Refreshing')
    expect((Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Refreshing') as HTMLButtonElement).disabled).toBe(true)

    await act(async () => {
      refreshed = true
      resolveRefresh?.(await commerce.refreshChannelCache('woocommerce:primary'))
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Product cache refreshed successfully')
    expect(c.textContent).toContain('The latest product information has been loaded.')
    expect(c.textContent).toContain('Cached products: 7')
    expect(c.textContent).toContain('Cached variations: 3')
  })

  it('renders a safe cache refresh failure reason', async () => {
    const failingCommerce: CommerceService = {
      ...commerce,
      async refreshChannelCache() {
        return {
          ...await commerce.refreshChannelCache('woocommerce:primary'),
          ok: false,
          status: 'failed',
          errors: ['WooCommerce authentication failed.'],
        }
      },
    }
    const c = await renderPage(adminUser, failingCommerce)

    await act(async () => {
      Array.from(c.querySelectorAll('button'))
        .find(button => button.textContent === 'Refresh cache')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Unable to refresh the product cache')
    expect(c.textContent).toContain('Please try again.')
    expect(c.textContent).not.toContain('ck_live_secret')
    expect(c.textContent).not.toContain('cs_live_secret')
  })

  it('renders Sources without listing marketplace channels there', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])

    expect(c.textContent).toContain('Nextcloud')
    expect(c.textContent).toContain('CSV')
    expect(c.textContent).toContain('Google Sheets')
    expect(c.textContent).toContain('ERP / API Import')
    expect(c.textContent).toContain('Add source')
    expect(c.textContent).toContain('Coming Soon')
    expect(c.textContent).not.toContain('SnappShop')
    expect(c.textContent).not.toContain('TapsiShop')
  })

  it('shows Nextcloud connection actions without bypassing setup gating', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])

    const testButtons = Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Test connection')
    expect(testButtons).toHaveLength(0)
    const readButtons = Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Read now')
    expect(readButtons).toHaveLength(0)
    const editConnectionButtons = Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Edit Connection')
    expect(editConnectionButtons).toHaveLength(1)
    expect(Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Configure Data')).toHaveLength(0)
    expect(c.textContent).toContain('Nextcloud')
    expect(c.textContent).toContain('CSV')
    expect(c.textContent).toContain('Google Sheets')
  })

  it('tests Nextcloud source connection, shows loading, renders success, and refreshes source health', async () => {
    let resolveTest: ((value: Awaited<ReturnType<CommerceService['testSource']>>) => void) | undefined
    let tested = false
    const refreshedSource = {
      id: 'nextcloud:primary',
      provider: 'nextcloud',
      name: 'Nextcloud',
      type: 'Source' as const,
      status: 'healthy',
      implemented: true,
      placeholder: false,
      credential_status: 'configured',
      connection_configured: true,
      configuration_state: 'configured' as const,
      last_health_check: '2026-07-09T10:00:00Z',
      data_role: 'Spreadsheet price input',
      action_label: 'Manage',
      action_href: '/commerce?tab=sources',
      health: { status: 'healthy', message: 'Connection successful. Spreadsheet found.', latency_ms: 12, error_code: null },
      read_only: true,
      runtime_write_blocked: true,
      settings_available: true,
    }
    const testCommerce: CommerceService = {
      ...commerce,
      async getSources() {
        const original = await commerce.getSources()
        const savedSource = {
          ...original.items[0],
          credential_status: 'configured' as const,
          connection_configured: true,
          configuration_state: 'setup_required' as const,
        }
        return tested
          ? { ...original, items: [refreshedSource, ...original.items.slice(1)] }
          : { ...original, items: [savedSource, ...original.items.slice(1)] }
      },
      async testSource() {
        return new Promise(resolve => {
          resolveTest = resolve
        })
      },
    }
    const c = await renderPage(adminUser, testCommerce, ['/commerce?tab=sources'])
    const testButton = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')

    await act(async () => {
      testButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })
    expect(c.textContent).toContain('Testing')

    await act(async () => {
      tested = true
      resolveTest?.({
        ok: true,
        status: 'operational',
        message: 'Connection successful. Spreadsheet found.',
        external_call_performed: true,
        read_only: true,
        runtime_write_blocked: true,
        write_blocked: true,
      })
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Source connected successfully')
    expect(c.textContent).toContain('Nextcloud is ready to use.')
    expect(c.textContent).not.toContain('Channel connected successfully')
    expect(c.querySelector('[data-notification-type="success"] .fh-notification-icon [data-icon="success"]')).not.toBeNull()
    expect(c.textContent).toContain('Healthy')
    expect(c.textContent).toContain('Configured')
  })

  it('renders Nextcloud source connection failure message', async () => {
    const failingCommerce: CommerceService = {
      ...commerce,
      async getSources() {
        const original = await commerce.getSources()
        return {
          ...original,
          items: original.items.map(item => item.id === 'nextcloud:primary'
            ? {
                ...item,
                credential_status: 'configured',
                connection_configured: true,
                configuration_state: 'setup_required',
              }
            : item),
        }
      },
      async testSource() {
        return {
          ok: false,
          status: 'error',
          message: 'Authentication failed.',
          external_call_performed: true,
          read_only: true,
          runtime_write_blocked: true,
          write_blocked: true,
        }
      },
    }
    const c = await renderPage(adminUser, failingCommerce, ['/commerce?tab=sources'])
    const testButton = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')

    await act(async () => {
      testButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Unable to connect to the source')
    expect(c.textContent).toContain('Nextcloud rejected the username or app password.')
    expect(c.textContent).not.toContain('Unable to connect to the channel')
  })

  it('opens Source and Channel forms without rendering secrets', async () => {
    const c = await renderPage()
    const addChannel = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Add channel')
    await act(async () => {
      addChannel?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(c.textContent).toContain('Channel type')
    expect(c.textContent).toContain('Bearer token')

    const sourcesScreen = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])
    const addSource = Array.from(sourcesScreen.querySelectorAll('button')).find(button => button.textContent === 'Add source')
    await act(async () => {
      addSource?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(c.textContent).toContain('Source type')
    expect(c.textContent).toContain('App password / token')
    expect(c.textContent).toContain('Columns for each Channel')
    expect(c.textContent).toContain('Column mapping and read limits now live on the Data Sheet page.')
    expect(c.textContent).not.toContain('Read Policy')
    expect(c.textContent).not.toContain('snapp-secret-value')
  })

  it('gives any spreadsheet-backed source connector the same resource, worksheet, and Configure Data UX as Nextcloud', async () => {
    const spreadsheetCommerce: CommerceService = {
      ...commerce,
      async getSourceTypes() {
        return {
          items: [
            typeOption('nextcloud:primary', 'nextcloud', 'Nextcloud', 'Source', false, [
              { key: 'url', label: 'Nextcloud URL', required: true, secret: false },
              { key: 'username', label: 'Username', required: true, secret: false },
              { key: 'password', label: 'Password', required: true, secret: true },
              { key: 'spreadsheet_path', label: 'Spreadsheet path', required: true, secret: false },
            ]),
            typeOption('gsheets:test', 'gsheets', 'Test Sheets', 'Source', false, [
              { key: 'auth_token', label: 'Auth token', required: true, secret: true },
              { key: 'spreadsheet_path', label: 'Spreadsheet path', required: true, secret: false },
            ]),
          ],
        }
      },
    }
    const c = await renderPage(adminUser, spreadsheetCommerce, ['/commerce?tab=sources'])
    const add = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Add source')
    await act(async () => { add?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })

    const typeSelect = selectByLabel(c, 'Source type')
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set?.call(typeSelect, 'gsheets:test')
      typeSelect.dispatchEvent(new Event('change', { bubbles: true }))
    })

    expect(c.textContent).toContain('Auth token')
    expect(Array.from(c.querySelectorAll('label')).some(label => label.textContent?.includes('Spreadsheet path'))).toBe(false)

    const genericPathInput = Array.from(c.querySelectorAll('label'))
      .find(label => label.textContent?.includes('Selected file'))
      ?.querySelector('input') as HTMLInputElement
    expect(genericPathInput).toBeTruthy()
    expect(Array.from(c.querySelectorAll('button')).some(button => button.textContent === 'Browse Nextcloud')).toBe(false)
    expect(c.textContent).toContain('Worksheet')
    expect(c.textContent).toContain('All worksheets')
    expect(c.textContent).toContain('Selected worksheet')
    expect(c.textContent).toContain('Save the connection first, then configure worksheets, mapping, and read limits on the Data Sheet page.')
  })

  it('saves connector worksheet settings without persisting a second global Source mapping', async () => {
    const captured: { payload: Parameters<CommerceService['saveSource']>[1] | null } = { payload: null }
    const savingCommerce: CommerceService = {
      ...commerce,
      async saveSource(_sourceId, nextPayload) {
        captured.payload = nextPayload
        return commerce.saveSource(_sourceId, nextPayload)
      },
    }
    const c = await renderPage(adminUser, savingCommerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    fillNextcloudCredentials(c)
    await selectNextcloudSpreadsheet(c)
    vi.spyOn(sourceWorkspaceApi, 'listSources').mockResolvedValue({
      items: [{
        id: 'managed-nextcloud',
        name: 'Nextcloud',
        sourceKind: 'external',
        externalSourceId: 'nextcloud:primary',
        worksheetMode: 'selected',
        worksheetName: 'Prices',
        dataStartRow: 2,
        status: 'active',
        version: 1,
        mappingVersion: 0,
        sheetId: null,
        createdAt: null,
        updatedAt: null,
      }],
    })

    await act(async () => {
      inputByLabel(c, 'Selected worksheet').dispatchEvent(new MouseEvent('click', { bubbles: true }))
      setInputValue(inputByLabel(c, 'Worksheet name'), 'Prices')
      setInputValue(inputByLabel(c, 'Display name'), 'Owner workbook')
      setInputValue(inputByLabel(c, 'Description optional'), 'Saved before Data Sheet')
    })
    await act(async () => {
      const openDataSheet = Array.from(c.querySelectorAll('button'))
        .find(button => button.textContent?.includes('Save and open Data Sheet')) as HTMLButtonElement
      expect(openDataSheet.disabled).toBe(true)
      expect(c.querySelector('[data-setup-step="data-sheet"]')?.textContent)
        .toContain('Save the selected spreadsheet, then test the saved connection before opening the Data Sheet.')
      const saveConfiguration = Array.from(c.querySelectorAll('button'))
        .find(button => button.textContent === 'Save configuration') as HTMLButtonElement
      expect(saveConfiguration.disabled).toBe(false)
      saveConfiguration.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(captured.payload).toBeTruthy()
    if (!captured.payload) throw new Error('saveSource payload was not captured')
    expect(captured.payload.settings).not.toHaveProperty('source_mapping')
    expect(captured.payload.settings.worksheet_mode).toBe('selected')
    expect(captured.payload.settings.worksheet_name).toBe('Prices')
    expect(captured.payload.display_name).toBe('Owner workbook')
    expect(captured.payload.description).toBe('Saved before Data Sheet')
    expect(captured.payload.enabled).toBe(true)
    expect(c.textContent).toContain('Source configured successfully')
    expect(c.querySelector('[data-notification-type="success"] .fh-notification-icon [data-icon="success"]')).not.toBeNull()
  })

  it('requires a changed saved connection to be saved and verified before normal setup Save', async () => {
    const listSources = vi.spyOn(sourceWorkspaceApi, 'listSources').mockResolvedValue({ items: [] })
    const createSource = vi.spyOn(sourceWorkspaceApi, 'createSource')
    const browseNextcloud = vi.fn((sourceId, request) => commerce.browseNextcloud(sourceId, request))
    const saveSource = vi.fn(async () => ({
      settings: {
        url: 'https://new.softpple.business/remote.php/dav/files/owner',
        username: 'owner',
        spreadsheet_path: '/prices.xlsx',
        worksheet_mode: 'all',
      },
      secrets: { password: { status: 'configured', replaced_at: null } },
      configured: false,
      connection_configured: true,
      configuration_state: 'setup_required' as const,
      read_only: true,
      runtime_write_blocked: true,
      write_blocked: true,
    }))
    const setupRequiredCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          configured: false,
          enabled: true,
          connection_configured: true,
          last_test: {
            status: 'healthy',
            message: 'Connection successful. Spreadsheet found.',
            error_code: null,
            latency_ms: 42,
            checked_at: '2026-08-10T10:30:00Z',
          },
          settings: {
            url: 'https://softpple.business/remote.php/dav/files/owner',
            username: 'owner',
            spreadsheet_path: '/prices.xlsx',
            worksheet_mode: 'all',
            worksheet_name: '',
          },
          secrets: { password: { status: 'configured', replaced_at: null } },
        }
      },
      saveSource,
      browseNextcloud,
    }
    const c = await renderPage(adminUser, setupRequiredCommerce, ['/commerce?tab=sources&resource=nextcloud%3Aprimary'])
    await act(async () => { await Promise.resolve(); await Promise.resolve() })

    const save = Array.from(c.querySelectorAll('button'))
      .find(button => button.textContent === 'Save configuration') as HTMLButtonElement
    act(() => setInputValue(
      inputByLabel(c, 'Nextcloud server URL'),
      'https://new.softpple.business/remote.php/dav/files/owner',
    ))
    expect(save.disabled).toBe(true)
    await saveNextcloudConnection(c)
    expect(saveSource).toHaveBeenCalledTimes(1)
    expect(save.disabled).toBe(true)
    await testSavedNextcloudConnection(c)
    expect(save.disabled).toBe(false)
    await act(async () => {
      save.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(saveSource).toHaveBeenCalledTimes(2)
    expect(listSources).not.toHaveBeenCalled()
    expect(createSource).not.toHaveBeenCalled()
    expect(c.textContent).toContain('Source settings updated successfully')
    expect(c.textContent).toContain('Your changes have been saved.')
    expect(c.textContent).not.toContain('The Source is ready to use')
    expect(c.textContent).not.toContain('Opening the Data Sheet')
    expect(c.textContent).toContain('Configure Nextcloud')

    const browse = Array.from(c.querySelectorAll('button'))
      .find(button => button.textContent === 'Browse Nextcloud') as HTMLButtonElement
    expect(browse.disabled).toBe(false)
    await act(async () => {
      browse.click()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(browseNextcloud).toHaveBeenCalledWith(
      'nextcloud:primary',
      expect.objectContaining({
        settings: expect.objectContaining({
          url: 'https://new.softpple.business/remote.php/dav/files/owner',
          username: 'owner',
        }),
        secrets: {},
      }),
    )
  })

  it('opens a saved Source connection in the editable settings form', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])
    const settings = resourceAction(c, 'Nextcloud', 'Edit Connection')

    await act(async () => {
      settings.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Configure Nextcloud')
    expect(selectByLabel(c, 'Source type').value).toBe('nextcloud:primary')
    expect(selectByLabel(c, 'Source type').disabled).toBe(true)
    expect(inputByLabel(c, 'Nextcloud server URL').name).toBe('commerce.source.nextcloud.url')
    expect(inputByLabel(c, 'Nextcloud server URL').autocomplete).toBe('url')
    expect(inputByLabel(c, 'Username').name).toBe('commerce.source.nextcloud.username')
    expect(inputByLabel(c, 'Username').autocomplete).toBe('username')
    expect(c.textContent).toContain('Connection Settings')
    expect(c.textContent).toContain('Save configuration')
  })

  it('keeps saved Nextcloud evidence scoped to its connection identity without returning the secret', async () => {
    const savedSecret = 'never-return-this-app-password'
    const configuredCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          display_name: 'Owner price source',
          description: 'Daily owner workbook',
          configured: true,
          enabled: true,
          connection_configured: true,
          last_test: {
            status: 'healthy',
            message: 'Connection successful.',
            error_code: null,
            latency_ms: 42,
            checked_at: '2026-08-10T10:30:00Z',
          },
          settings: {
            url: 'https://softpple.business/remote.php/dav/files/woo',
            username: 'woo',
            spreadsheet_path: '/Reports/prices.xlsx',
            worksheet_mode: 'selected',
            worksheet_name: 'Prices',
          },
          secrets: { password: { status: 'configured', replaced_at: '2026-08-10T10:00:00Z' } },
        }
      },
      async testSource() {
        return {
          ok: false,
          status: 'timeout',
          code: 'timeout',
          message: 'Draft target timed out.',
          external_call_performed: true,
          read_only: true,
          runtime_write_blocked: true,
          write_blocked: true,
        }
      },
    }

    const c = await renderPage(adminUser, configuredCommerce, ['/commerce?tab=sources&resource=nextcloud%3Aprimary'])
    await act(async () => { await Promise.resolve(); await Promise.resolve() })

    expect(inputByLabel(c, 'Display name').value).toBe('Owner price source')
    expect(inputByLabel(c, 'Description optional').value).toBe('Daily owner workbook')
    expect(inputByLabel(c, 'Nextcloud server URL').value).toBe('https://softpple.business/remote.php/dav/files/woo')
    expect(inputByLabel(c, 'Username').value).toBe('woo')
    const savedCredential = c.querySelector('input[type="password"]') as HTMLInputElement
    expect(savedCredential.value).toBe('')
    expect(c.querySelector('[data-testid="configured-secret-mask"]')?.textContent).toBe('••••••••••••')
    expect(savedCredential.parentElement?.querySelector('button')?.disabled).toBe(true)
    expect(c.textContent).toContain('Saved credential ✓ — leave blank to keep unchanged.')
    expect(c.textContent).not.toContain(savedSecret)
    expect(c.textContent).toContain('/Reports/prices.xlsx')
    expect(c.querySelector('[data-testid="nextcloud-last-test"]')?.textContent).toContain('Healthy')
    expect(c.querySelector('[data-testid="nextcloud-last-test"]')?.textContent).toContain('Connection successful.')
    expect(inputByLabel(c, 'Selected worksheet').checked).toBe(true)
    expect(inputByLabel(c, 'Worksheet name').value).toBe('Prices')
    expect(Array.from(c.querySelectorAll('[data-setup-step]')).map(section => section.getAttribute('data-setup-step')))
      .toEqual(['general', 'connection', 'spreadsheet', 'worksheet', 'data-sheet', 'monetary-unit'])
    expect((c.querySelector('[data-setup-step="spreadsheet"] button') as HTMLButtonElement).disabled).toBe(false)
    expect((c.querySelector('[data-setup-step="data-sheet"] button') as HTMLButtonElement).disabled).toBe(false)

    act(() => setInputValue(inputByLabel(c, 'Worksheet name'), 'Updated Prices'))
    expect((c.querySelector('[data-setup-step="data-sheet"] button') as HTMLButtonElement).disabled).toBe(false)

    act(() => setInputValue(inputByLabel(c, 'Nextcloud server URL'), 'https://changed.example.test'))
    expect(c.querySelector('[data-testid="nextcloud-last-test"]')?.textContent).toContain('Not tested')
    expect(c.querySelector('[data-testid="nextcloud-last-test"]')?.textContent).not.toContain('Healthy')
    expect((c.querySelector('[data-setup-step="spreadsheet"] button') as HTMLButtonElement).disabled).toBe(true)
    expect((c.querySelector('[data-setup-step="worksheet"] fieldset') as HTMLFieldSetElement).disabled).toBe(true)
    expect((c.querySelector('[data-setup-step="data-sheet"] button') as HTMLButtonElement).disabled).toBe(true)
    expect((c.querySelector('[data-setup-step="monetary-unit"] fieldset') as HTMLFieldSetElement).disabled).toBe(false)
    expect(Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Save configuration')?.disabled).toBe(true)
    expect(c.querySelector('[data-setup-step="worksheet"]')?.textContent)
      .toContain('Save and test the changed Connection Settings before continuing.')

    const replacementSecret = c.querySelector('input[type="password"]') as HTMLInputElement
    act(() => setInputValue(replacementSecret, 'replacement-pending-save'))
    expect((c.querySelector('[data-setup-step="worksheet"] fieldset') as HTMLFieldSetElement).disabled).toBe(true)
    expect((c.querySelector('[data-setup-step="data-sheet"] button') as HTMLButtonElement).disabled).toBe(true)
    expect((c.querySelector('[data-setup-step="monetary-unit"] fieldset') as HTMLFieldSetElement).disabled).toBe(false)
    act(() => setInputValue(replacementSecret, ''))

    await act(async () => {
      Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')?.click()
      await Promise.resolve()
      await Promise.resolve()
    })
    act(() => setInputValue(
      inputByLabel(c, 'Nextcloud server URL'),
      'https://softpple.business/remote.php/dav/files/woo',
    ))
    const persistedEvidence = c.querySelector('[data-testid="nextcloud-last-test"]')?.textContent ?? ''
    expect(persistedEvidence).toContain('Healthy')
    expect(persistedEvidence).toContain('Connection successful.')
    expect(persistedEvidence).not.toContain('timed out')
  })

  it('edits and reloads Worksheet and Monetary Policy after a healthy saved connection without a spreadsheet', async () => {
    const savedPayloads: NonNullable<Parameters<CommerceService['saveSource']>[1]>[] = []
    const persistedSettings: Record<string, unknown> = {
      url: 'https://softpple.business',
      username: 'woo',
      worksheet_mode: 'all',
      worksheet_name: '',
    }
    let persistedUnit = 'RIAL'
    const configuredCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          configured: false,
          enabled: true,
          connection_configured: true,
          configuration_state: 'setup_required',
          last_test: {
            status: 'healthy',
            message: 'Connection successful.',
            error_code: null,
            latency_ms: 42,
            checked_at: '2026-08-10T10:30:00Z',
          },
          settings: { ...persistedSettings },
          secrets: { password: { status: 'configured', replaced_at: null } },
          currency_profile: { status: 'resolved', currency: 'IRR', unit: persistedUnit },
        }
      },
      async saveSource(sourceId, payload) {
        savedPayloads.push(payload)
        Object.assign(persistedSettings, payload.settings)
        persistedUnit = payload.currency_unit ?? persistedUnit
        return {
          ...(await commerce.saveSource(sourceId, payload)),
          configured: false,
          connection_configured: true,
          configuration_state: 'setup_required',
        }
      },
    }
    const types = (await configuredCommerce.getSourceTypes()).items
    const renderConfiguration = async (key: string) => {
      await act(async () => {
        root.render(
          <NotificationProvider>
            <AuthContext.Provider value={authValue(adminUser)}>
              <MemoryRouter>
                <ServiceProvider services={{ ...services, commerce: configuredCommerce }}>
                  <ConfigPanel
                    key={key}
                    kind="source"
                    types={types}
                    initialResourceId="nextcloud:primary"
                    onCancel={vi.fn()}
                    onSaved={vi.fn()}
                  />
                </ServiceProvider>
              </MemoryRouter>
            </AuthContext.Provider>
          </NotificationProvider>,
        )
        await Promise.resolve()
        await Promise.resolve()
      })
    }

    await renderConfiguration('initial')

    const spreadsheet = container.querySelector('[data-setup-step="spreadsheet"]') as HTMLElement
    const worksheet = container.querySelector('[data-setup-step="worksheet"]') as HTMLElement
    const dataSheet = container.querySelector('[data-setup-step="data-sheet"]') as HTMLElement
    const monetary = container.querySelector('[data-setup-step="monetary-unit"]') as HTMLElement
    expect(spreadsheet.getAttribute('aria-disabled')).toBe('false')
    expect(worksheet.getAttribute('aria-disabled')).toBe('false')
    expect(monetary.getAttribute('aria-disabled')).toBe('false')
    expect(worksheet.classList.contains('opacity-70')).toBe(false)
    expect(monetary.classList.contains('opacity-70')).toBe(false)
    expect((worksheet.querySelector('fieldset') as HTMLFieldSetElement).disabled).toBe(false)
    expect((monetary.querySelector('fieldset') as HTMLFieldSetElement).disabled).toBe(false)
    expect(dataSheet.getAttribute('aria-disabled')).toBe('true')
    expect((dataSheet.querySelector('button') as HTMLButtonElement).disabled).toBe(true)

    act(() => {
      inputByLabel(container, 'Selected worksheet').click()
      setInputValue(inputByLabel(container, 'Worksheet name'), 'Prices')
      const unit = selectByLabel(container, 'Price unit')
      unit.value = 'TOMAN'
      unit.dispatchEvent(new Event('change', { bubbles: true }))
    })

    const save = Array.from(container.querySelectorAll('button'))
      .find(button => button.textContent === 'Save configuration') as HTMLButtonElement
    expect(save.disabled).toBe(false)
    await act(async () => {
      save.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(savedPayloads).toHaveLength(1)
    expect(savedPayloads[0].settings).toMatchObject({
      worksheet_mode: 'selected',
      worksheet_name: 'Prices',
    })
    expect(savedPayloads[0].settings).not.toHaveProperty('spreadsheet_path')
    expect(savedPayloads[0]).toMatchObject({ currency: 'IRR', currency_unit: 'TOMAN' })
    expect((container.querySelector('[data-setup-step="worksheet"] fieldset') as HTMLFieldSetElement).disabled).toBe(false)
    expect((container.querySelector('[data-setup-step="monetary-unit"] fieldset') as HTMLFieldSetElement).disabled).toBe(false)

    await renderConfiguration('reopened')
    expect(inputByLabel(container, 'Selected worksheet').checked).toBe(true)
    expect(inputByLabel(container, 'Worksheet name').value).toBe('Prices')
    expect(selectByLabel(container, 'Currency').value).toBe('IRR')
    expect(selectByLabel(container, 'Price unit').value).toBe('TOMAN')
    expect((container.querySelector('[data-setup-step="worksheet"] fieldset') as HTMLFieldSetElement).disabled).toBe(false)
    expect((container.querySelector('[data-setup-step="data-sheet"] button') as HTMLButtonElement).disabled).toBe(true)
    expect((container.querySelector('[data-setup-step="monetary-unit"] fieldset') as HTMLFieldSetElement).disabled).toBe(false)
  })

  it('locks connection-dependent steps after a failed saved-connection test without clearing policy values', async () => {
    const failedCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          configured: true,
          enabled: true,
          connection_configured: true,
          configuration_state: 'configured',
          last_test: {
            status: 'unhealthy',
            message: 'Authentication failed.',
            error_code: 'authentication_failed',
            latency_ms: 42,
            checked_at: '2026-08-10T10:30:00Z',
          },
          settings: {
            url: 'https://softpple.business',
            username: 'woo',
            spreadsheet_path: '/Reports/prices.xlsx',
            worksheet_mode: 'selected',
            worksheet_name: 'Prices',
          },
          secrets: { password: { status: 'configured', replaced_at: null } },
          currency_profile: { status: 'resolved', currency: 'IRR', unit: 'TOMAN' },
        }
      },
    }

    const c = await renderPage(adminUser, failedCommerce, ['/commerce?tab=sources&resource=nextcloud%3Aprimary'])
    await act(async () => { await Promise.resolve(); await Promise.resolve() })

    for (const step of ['spreadsheet', 'worksheet', 'monetary-unit']) {
      const section = c.querySelector(`[data-setup-step="${step}"]`) as HTMLElement
      expect(section.getAttribute('aria-disabled')).toBe('true')
      expect(section.classList.contains('opacity-70')).toBe(true)
    }
    expect((c.querySelector('[data-setup-step="spreadsheet"] button') as HTMLButtonElement).disabled).toBe(true)
    expect((c.querySelector('[data-setup-step="worksheet"] fieldset') as HTMLFieldSetElement).disabled).toBe(true)
    expect((c.querySelector('[data-setup-step="monetary-unit"] fieldset') as HTMLFieldSetElement).disabled).toBe(true)
    expect(inputByLabel(c, 'Selected worksheet').checked).toBe(true)
    expect(inputByLabel(c, 'Worksheet name').value).toBe('Prices')
    expect(selectByLabel(c, 'Currency').value).toBe('IRR')
    expect(selectByLabel(c, 'Price unit').value).toBe('TOMAN')
    expect(c.querySelector('[data-setup-step="worksheet"]')?.textContent)
      .toContain('Save and successfully test Connection Settings to continue.')
    expect(c.querySelector('[data-setup-step="monetary-unit"]')?.textContent)
      .toContain('Save and successfully test Connection Settings to continue.')
  })

  it('keeps Worksheet and Monetary Policy editable while Data Sheet waits for a spreadsheet', async () => {
    const savedPayloads: NonNullable<Parameters<CommerceService['saveSource']>[1]>[] = []
    const configuredCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          configured: true,
          enabled: true,
          connection_configured: true,
          configuration_state: 'configured',
          last_test: {
            status: 'healthy',
            message: 'Connection successful.',
            error_code: null,
            latency_ms: 42,
            checked_at: '2026-08-10T10:30:00Z',
          },
          settings: {
            url: 'https://softpple.business',
            username: 'woo',
            worksheet_mode: 'selected',
            worksheet_name: 'Prices',
          },
          secrets: { password: { status: 'configured', replaced_at: null } },
          currency_profile: { status: 'resolved', currency: 'IRR', unit: 'RIAL' },
        }
      },
      async saveSource(sourceId, payload) {
        savedPayloads.push(payload)
        return commerce.saveSource(sourceId, payload)
      },
    }
    const types = (await configuredCommerce.getSourceTypes()).items
    const openDataSheet = vi.fn()

    await act(async () => {
      root.render(
        <NotificationProvider>
          <AuthContext.Provider value={authValue(adminUser)}>
            <MemoryRouter>
              <ServiceProvider services={{ ...services, commerce: configuredCommerce }}>
                <ConfigPanel
                  kind="source"
                  types={types}
                  initialResourceId="nextcloud:primary"
                  onCancel={vi.fn()}
                  onSaved={vi.fn()}
                  onConfigureData={openDataSheet}
                />
              </ServiceProvider>
            </MemoryRouter>
          </AuthContext.Provider>
        </NotificationProvider>,
      )
      await Promise.resolve()
      await Promise.resolve()
    })

    const worksheet = container.querySelector('[data-setup-step="worksheet"] fieldset') as HTMLFieldSetElement
    const dataSheet = container.querySelector('[data-setup-step="data-sheet"] button') as HTMLButtonElement
    const monetary = container.querySelector('[data-setup-step="monetary-unit"] fieldset') as HTMLFieldSetElement
    expect(worksheet.disabled).toBe(false)
    expect(dataSheet.disabled).toBe(true)
    expect(monetary.disabled).toBe(false)

    const currencyUnit = selectByLabel(container, translate('commerce:commerceHub.currencyUnit'))
    act(() => {
      currencyUnit.value = 'TOMAN'
      currencyUnit.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(currencyUnit.value).toBe('TOMAN')

    await act(async () => {
      Array.from(container.querySelectorAll('button')).find(item => item.textContent === 'Save configuration')?.click()
      await Promise.resolve()
    })
    expect(savedPayloads).toHaveLength(1)
    expect(savedPayloads[0].currency_unit).toBe('TOMAN')
    expect(savedPayloads[0].settings).not.toHaveProperty('spreadsheet_path')

    await act(async () => dataSheet.click())
    expect(openDataSheet).not.toHaveBeenCalled()
  })

  it('localizes persisted Nextcloud test evidence instead of rendering backend English', async () => {
    await changeLocale('fa')
    const configuredCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          enabled: true,
          connection_configured: true,
          settings: { url: 'https://softpple.business', username: 'woo' },
          secrets: { password: { status: 'configured', replaced_at: null } },
          last_test: {
            status: 'healthy',
            message: 'Connection successful. Spreadsheet found.',
            error_code: null,
            latency_ms: 42,
            checked_at: '2026-08-10T10:30:00Z',
          },
        }
      },
    }

    const c = await renderPage(adminUser, configuredCommerce, ['/commerce?tab=sources&resource=nextcloud%3Aprimary'])
    await act(async () => { await Promise.resolve(); await Promise.resolve() })

    const evidence = c.querySelector('[data-testid="nextcloud-last-test"]')?.textContent ?? ''
    expect(evidence).toContain('اتصال با موفقیت برقرار شد و فایل صفحه‌گسترده پیدا شد.')
    expect(evidence).not.toContain('Connection successful')
  })

  it('keeps an existing saved secret when Save connection receives a blank replacement', async () => {
    const savedPayloads: NonNullable<Parameters<CommerceService['saveSource']>[1]>[] = []
    const configuredCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          enabled: true,
          connection_configured: true,
          last_test: {
            status: 'healthy',
            message: 'Connection successful.',
            error_code: null,
            latency_ms: 42,
            checked_at: '2026-08-10T10:30:00Z',
          },
          settings: {
            url: 'https://softpple.business',
            username: 'woo',
            spreadsheet_path: '/Reports/prices.xlsx',
            worksheet_mode: 'selected',
            worksheet_name: 'Prices',
            source_read_policy: { enabled: true, max_reads_per_24h: 7, manual_read_allowed: true },
          },
          secrets: { password: { status: 'configured', replaced_at: null } },
        }
      },
      async saveSource(sourceId, payload) {
        savedPayloads.push(payload)
        return commerce.saveSource(sourceId, payload)
      },
    }
    const c = await renderPage(adminUser, configuredCommerce, ['/commerce?tab=sources&resource=nextcloud%3Aprimary'])
    await act(async () => { await Promise.resolve(); await Promise.resolve() })

    await saveNextcloudConnection(c)

    expect(savedPayloads).toHaveLength(1)
    expect(savedPayloads[0].secrets).toEqual({})
    expect(savedPayloads[0].settings).toMatchObject({ url: 'https://softpple.business', username: 'woo' })
    expect(savedPayloads[0].settings).not.toHaveProperty('spreadsheet_path')
    expect(savedPayloads[0].settings).not.toHaveProperty('worksheet_mode')
    expect(savedPayloads[0].settings).not.toHaveProperty('worksheet_name')
    expect(savedPayloads[0].settings).not.toHaveProperty('source_read_policy')
    expect(c.querySelector('[data-testid="nextcloud-last-test"]')?.textContent).toContain('Healthy')
    expect((c.querySelector('[data-setup-step="worksheet"] fieldset') as HTMLFieldSetElement).disabled).toBe(false)
    expect((c.querySelector('[data-setup-step="data-sheet"] button') as HTMLButtonElement).disabled).toBe(false)
    expect((c.querySelector('[data-setup-step="monetary-unit"] fieldset') as HTMLFieldSetElement).disabled).toBe(false)
  })

  it('keeps a newly selected spreadsheet unsaved when only Connection Settings are saved', async () => {
    const savedPayloads: NonNullable<Parameters<CommerceService['saveSource']>[1]>[] = []
    const configuredCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          configured: true,
          enabled: true,
          connection_configured: true,
          last_test: {
            status: 'healthy',
            message: 'Connection successful.',
            error_code: null,
            latency_ms: 42,
            checked_at: '2026-08-10T10:30:00Z',
          },
          settings: {
            url: 'https://softpple.business',
            username: 'woo',
            spreadsheet_path: '/Reports/prices.xlsx',
            worksheet_mode: 'selected',
            worksheet_name: 'Prices',
          },
          secrets: { password: { status: 'configured', replaced_at: null } },
        }
      },
      async saveSource(sourceId, payload) {
        savedPayloads.push(payload)
        return commerce.saveSource(sourceId, payload)
      },
    }
    const c = await renderPage(adminUser, configuredCommerce, ['/commerce?tab=sources&resource=nextcloud%3Aprimary'])
    await act(async () => { await Promise.resolve(); await Promise.resolve() })

    await selectNextcloudSpreadsheet(c)
    expect(c.querySelector('[data-testid="nextcloud-selected-file"]')?.textContent)
      .toContain('Selected — save to keep')
    const dataSheet = c.querySelector('[data-setup-step="data-sheet"] button') as HTMLButtonElement
    expect(dataSheet.disabled).toBe(true)
    expect(c.querySelector('[data-setup-step="data-sheet"]')?.textContent)
      .toContain('Save the selected spreadsheet, then test the saved connection before opening the Data Sheet.')

    await saveNextcloudConnection(c)

    expect(savedPayloads).toHaveLength(1)
    expect(savedPayloads[0].settings).not.toHaveProperty('spreadsheet_path')
    expect(c.querySelector('[data-testid="nextcloud-selected-file"]')?.textContent)
      .toContain('/prices.xlsx')
    expect(c.querySelector('[data-testid="nextcloud-selected-file"]')?.textContent)
      .toContain('Selected — save to keep')
    expect(dataSheet.disabled).toBe(true)
  })

  it('uses a replacement secret for Test without persisting it until Save connection', async () => {
    const testedSecrets: Array<Record<string, string>> = []
    const savedSecrets: Array<Record<string, string>> = []
    const configuredCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          enabled: true,
          connection_configured: true,
          settings: { url: 'https://softpple.business', username: 'woo' },
          secrets: { password: { status: 'configured', replaced_at: null } },
        }
      },
      async testSource(sourceId, payload) {
        testedSecrets.push(payload?.secrets ?? {})
        return commerce.testSource(sourceId, payload)
      },
      async saveSource(sourceId, payload) {
        savedSecrets.push(payload.secrets)
        return commerce.saveSource(sourceId, payload)
      },
    }
    const c = await renderPage(adminUser, configuredCommerce, ['/commerce?tab=sources&resource=nextcloud%3Aprimary'])
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    const secretInput = c.querySelector('input[type="password"]') as HTMLInputElement
    act(() => setInputValue(secretInput, 'replacement-app-password'))

    await act(async () => {
      Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')?.click()
      await Promise.resolve()
    })

    expect(testedSecrets).toEqual([{ password: 'replacement-app-password' }])
    expect(savedSecrets).toHaveLength(0)
    await saveNextcloudConnection(c)
    expect(savedSecrets).toEqual([{ password: 'replacement-app-password' }])
    expect((c.querySelector('input[type="password"]') as HTMLInputElement).value).toBe('')
    expect(c.textContent).not.toContain('replacement-app-password')
  })

  it('keeps an unconfigured routed Nextcloud Source in first-time setup mode', async () => {
    const bootstrapCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          enabled: null,
          connection_configured: false,
          configured: false,
        }
      },
    }

    const c = await renderPage(
      adminUser,
      bootstrapCommerce,
      ['/commerce?tab=sources&resource=nextcloud%3Aprimary'],
    )
    await act(async () => { await Promise.resolve(); await Promise.resolve() })

    const general = c.querySelector('[data-setup-step="general"]')
    expect(general?.textContent).toContain('Step 1')
    expect(general?.textContent).toContain('Define the connector type')
    expect(general?.textContent).not.toContain("Manage this Source's FlowHub identity")
    expect(c.querySelector('[data-setup-step="worksheet"]')).toBeTruthy()
  })

  it('locks each remote-dependent setup step until the saved connection is healthy', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    const browse = c.querySelector('[data-setup-step="spreadsheet"] button') as HTMLButtonElement
    const worksheet = c.querySelector('[data-setup-step="worksheet"] fieldset') as HTMLFieldSetElement
    const dataSheet = c.querySelector('[data-setup-step="data-sheet"] button') as HTMLButtonElement
    const monetary = c.querySelector('[data-setup-step="monetary-unit"] fieldset') as HTMLFieldSetElement

    expect(browse.disabled).toBe(true)
    expect(worksheet.disabled).toBe(true)
    expect(dataSheet.disabled).toBe(true)
    expect(monetary.disabled).toBe(true)
    expect(c.querySelector('[data-setup-step="data-sheet"]')?.textContent).toContain('Columns for each Channel')
    expect(c.querySelector('[data-testid="nextcloud-source-enabled-state"]')?.textContent)
      .toContain('Save and successfully test Connection Settings to continue.')
    expect(c.querySelector('[data-testid="nextcloud-source-enabled-state"]')?.textContent)
      .not.toContain('This Source is enabled.')

    fillNextcloudCredentials(c)
    await act(async () => {
      Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')?.click()
      await Promise.resolve()
    })
    expect(browse.disabled).toBe(true)

    await saveNextcloudConnection(c)
    expect(browse.disabled).toBe(true)
    expect(worksheet.disabled).toBe(true)
    expect(monetary.disabled).toBe(true)

    await testSavedNextcloudConnection(c)
    expect(browse.disabled).toBe(false)
    expect(worksheet.disabled).toBe(false)
    expect(monetary.disabled).toBe(false)
    expect(dataSheet.disabled).toBe(true)

    await selectNextcloudSpreadsheet(c)
    expect(worksheet.disabled).toBe(false)
    expect(monetary.disabled).toBe(false)
    expect(dataSheet.disabled).toBe(true)
    expect(c.querySelector('[data-setup-step="data-sheet"]')?.textContent)
      .toContain('Save the selected spreadsheet, then test the saved connection before opening the Data Sheet.')
  })

  it('verifies the unsaved Source credentials entered in Connection Settings', async () => {
    const captured: { payload: Parameters<CommerceService['testSource']>[1] | null } = { payload: null }
    const verifyingCommerce: CommerceService = {
      ...commerce,
      async testSource(_sourceId, payload) {
        captured.payload = payload ?? null
        return commerce.testSource(_sourceId, payload)
      },
    }
    const c = await renderPage(adminUser, verifyingCommerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    fillNextcloudCredentials(c, 'https://draft.example.test', 'draft-user')
    const testButton = Array.from(c.querySelectorAll('button')).find(item => item.textContent === 'Test connection')

    await act(async () => {
      testButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(captured.payload?.settings).toMatchObject({
      url: 'https://draft.example.test',
      username: 'draft-user',
    })
    expect(captured.payload?.secrets).toEqual({ password: 'app-password-value' })
    expect(c.textContent).toContain('Connection details verified')
    expect(c.textContent).toContain('These connection details are valid. Save them to continue.')
    expect(c.querySelector('.fh-alert-success')).not.toBeNull()
  })

  it('labels a successful saved Nextcloud connection as verified rather than asking the Owner to save again', async () => {
    const savedCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          configured: true,
          enabled: true,
          connection_configured: true,
          last_test: {
            status: 'healthy',
            message: 'Connection successful.',
            error_code: null,
            latency_ms: 42,
            checked_at: '2026-08-10T10:30:00Z',
          },
          settings: {
            url: 'https://softpple.business',
            username: 'woo',
            spreadsheet_path: '/Reports/prices.xlsx',
            worksheet_mode: 'selected',
            worksheet_name: 'Prices',
          },
          secrets: { password: { status: 'configured', replaced_at: null } },
        }
      },
      async testSource() {
        return {
          ok: true,
          status: 'operational',
          message: 'Connection successful.',
          configuration_matches_saved: true,
          external_call_performed: true,
          read_only: true,
          runtime_write_blocked: true,
          write_blocked: true,
          checked_at: '2026-08-10T11:00:00Z',
        }
      },
    }
    const c = await renderPage(adminUser, savedCommerce, ['/commerce?tab=sources&resource=nextcloud%3Aprimary'])
    await act(async () => { await Promise.resolve(); await Promise.resolve() })

    await testSavedNextcloudConnection(c)

    expect(c.textContent).toContain('Saved connection verified')
    expect(c.textContent).toContain('The saved connection is healthy. You can continue editing this Source.')
    expect(c.textContent).not.toContain('Save them to continue.')
  })

  it('keeps saved evidence intact and skips the refresh when the API rejects a test for a disabled Source', async () => {
    let configurationReads = 0
    const disabledResultCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        configurationReads += 1
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          configured: true,
          enabled: true,
          connection_configured: true,
          last_test: {
            status: 'healthy',
            message: 'Connection successful.',
            error_code: null,
            latency_ms: 42,
            checked_at: '2026-08-10T10:30:00Z',
          },
          settings: {
            url: 'https://softpple.business',
            username: 'woo',
            spreadsheet_path: '/Reports/prices.xlsx',
            worksheet_mode: 'selected',
            worksheet_name: 'Prices',
          },
          secrets: { password: { status: 'configured', replaced_at: null } },
        }
      },
      async testSource() {
        return {
          ok: false,
          status: 'disabled',
          code: 'SOURCE_DISABLED',
          message: 'Source disabled.',
          configuration_matches_saved: true,
          external_call_performed: false,
          read_only: true,
          runtime_write_blocked: true,
          write_blocked: true,
        }
      },
    }
    const c = await renderPage(adminUser, disabledResultCommerce, ['/commerce?tab=sources&resource=nextcloud%3Aprimary'])
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(configurationReads).toBe(1)

    await testSavedNextcloudConnection(c)

    expect(configurationReads).toBe(1)
    expect(c.textContent).toContain('This Source is disabled. Enable and save it before testing the connection.')
    expect(c.querySelector('[data-testid="nextcloud-last-test"]')?.textContent).toContain('Healthy')
  })

  it.each([
    {
      status: 'timeout',
      code: 'connection_timeout',
      message: 'The external service did not respond in time.',
      expected: 'The external service did not respond in time.',
    },
    {
      status: 'authentication_failed',
      code: 'authentication_failed',
      message: 'Authentication failed.',
      expected: 'Nextcloud rejected the username or app password.',
    },
    {
      status: 'blocked',
      code: 'unsafe_destination',
      message: 'Destination blocked.',
      expected: 'The configured source destination is blocked by the Source network safety policy.',
    },
    {
      status: 'error',
      code: 'not_configured',
      message: 'Nextcloud is not configured.',
      expected: 'Save the required Nextcloud connection settings before testing.',
    },
    {
      status: 'error',
      code: 'spreadsheet_unsupported',
      message: 'Unsupported spreadsheet.',
      expected: 'The selected file must be a supported .xlsx spreadsheet.',
    },
    {
      status: 'error',
      code: 'connection_failed',
      message: 'WebDAV not reachable.',
      expected: 'The Nextcloud server could not be reached from FlowHub.',
    },
  ])('shows a specific Nextcloud $status test failure', async ({ status, code, message, expected }) => {
    const failingCommerce: CommerceService = {
      ...commerce,
      async testSource() {
        return {
          ok: false,
          status,
          code,
          message,
          external_call_performed: true,
          read_only: true,
          runtime_write_blocked: true,
          write_blocked: true,
        }
      },
    }
    const c = await renderPage(adminUser, failingCommerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    fillNextcloudCredentials(c)

    await act(async () => {
      Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')?.click()
      await Promise.resolve()
    })

    expect(c.textContent).toContain(expected)
    expect(c.querySelector('.fh-alert-danger')).not.toBeNull()
  })

  it('does not mislabel a FlowHub authorization failure as rejected Nextcloud credentials', async () => {
    const failingCommerce: CommerceService = {
      ...commerce,
      async testSource() {
        throw new ApiError(403, JSON.stringify({ detail: 'Admin permission required.' }))
      },
    }
    const c = await renderPage(adminUser, failingCommerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    fillNextcloudCredentials(c)

    await act(async () => {
      Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')?.click()
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Admin permission required.')
    expect(c.textContent).not.toContain('Nextcloud rejected the username or app password.')
  })

  it('uses the same specific timeout message from the Source card Test connection action', async () => {
    const failingCommerce: CommerceService = {
      ...commerce,
      async getSources() {
        const original = await commerce.getSources()
        return {
          ...original,
          items: original.items.map(item => item.id === 'nextcloud:primary'
            ? {
                ...item,
                credential_status: 'configured',
                connection_configured: true,
                configuration_state: 'setup_required',
              }
            : item),
        }
      },
      async testSource() {
        return {
          ok: false,
          status: 'timeout',
          code: 'connection_timeout',
          message: 'Request timed out.',
          external_call_performed: true,
          read_only: true,
          runtime_write_blocked: true,
          write_blocked: true,
        }
      },
    }
    const c = await renderPage(adminUser, failingCommerce, ['/commerce?tab=sources'])

    await act(async () => {
      resourceAction(c, 'Nextcloud', 'Test connection').click()
      await Promise.resolve()
    })

    expect(c.textContent).toContain('The external service did not respond in time.')
  })

  it('reopens an incomplete Nextcloud connection and lets the stored credentials be corrected before file selection', async () => {
    const editableCommerce: CommerceService = {
      ...commerce,
      async getSourceConfiguration(sourceId) {
        const base = await commerce.getSourceConfiguration(sourceId)
        return {
          ...base,
          display_name: 'Nextcloud prices',
          enabled: true,
          settings: {
            url: 'https://wrong.example.test',
            username: 'wrong-user',
            spreadsheet_path: '',
          },
          secrets: { password: { status: 'configured', replaced_at: null } },
        }
      },
    }

    const c = await renderPage(adminUser, editableCommerce, ['/commerce?tab=sources&resource=nextcloud%3Aprimary'])
    await act(async () => { await Promise.resolve(); await Promise.resolve() })

    expect(inputByLabel(c, 'Nextcloud server URL').value).toBe('https://wrong.example.test')
    expect(inputByLabel(c, 'Username').value).toBe('wrong-user')
    expect(c.textContent).toContain('Saved credential ✓ — leave blank to keep unchanged.')
    const saveConnection = Array.from(c.querySelectorAll('button'))
      .find(item => item.textContent === 'Save connection') as HTMLButtonElement
    const save = Array.from(c.querySelectorAll('button'))
      .find(item => item.textContent === 'Save configuration') as HTMLButtonElement
    expect(saveConnection.disabled).toBe(false)
    expect(save.disabled).toBe(true)

    const browse = Array.from(c.querySelectorAll('button'))
      .find(button => button.textContent === 'Browse Nextcloud') as HTMLButtonElement
    expect(browse.disabled).toBe(true)
    await testSavedNextcloudConnection(c)
    expect(browse.disabled).toBe(false)
    await act(async () => { browse.click(); await Promise.resolve(); await Promise.resolve() })
    const file = Array.from(c.querySelectorAll('button'))
      .find(button => button.textContent?.includes('prices.xlsx')) as HTMLButtonElement
    expect(file).toBeTruthy()
    await act(async () => file.click())

    expect(c.textContent).toContain('/prices.xlsx')
    expect(save.disabled).toBe(false)
  })

  it('hides the source card list while editing and separates connection Save from full configuration Save', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources&resource=nextcloud%3Aprimary'])
    await act(async () => { await Promise.resolve(); await Promise.resolve() })

    expect(c.textContent).toContain('Configure Nextcloud')
    expect(c.querySelector('[data-resource-section]')).toBeNull()
    expect(Array.from(c.querySelectorAll('button')).filter(item => item.textContent === 'Edit Connection')).toHaveLength(0)
    const configureData = c.querySelector('[data-setup-step="data-sheet"] button') as HTMLButtonElement
    expect(configureData).toBeTruthy()
    expect(configureData.disabled).toBe(true)
    expect(Array.from(c.querySelectorAll('button')).filter(item => item.textContent === 'Test connection')).toHaveLength(1)
    expect(Array.from(c.querySelectorAll('button')).filter(item => item.textContent === 'Save configuration')).toHaveLength(1)
    expect(Array.from(c.querySelectorAll('button')).filter(item => item.textContent === 'Save connection')).toHaveLength(1)

    const cancel = Array.from(c.querySelectorAll('button')).find(item => item.textContent === 'Close') as HTMLButtonElement
    await act(async () => { cancel.click(); await Promise.resolve() })
    expect(c.querySelector('[data-resource-section]')).not.toBeNull()
  })

  it('saves Nextcloud credentials explicitly before a spreadsheet is selected without requiring a test', async () => {
    const captured: { payload: Parameters<CommerceService['saveSource']>[1] | null } = { payload: null }
    let testCalls = 0
    const savingCommerce: CommerceService = {
      ...commerce,
      async testSource() {
        testCalls += 1
        return {
          ...(await commerce.testSource('nextcloud:primary')),
          spreadsheet_found: null,
          message: 'Connection successful. Select a spreadsheet file to enable preview.',
        }
      },
      async saveSource(sourceId, payload) {
        captured.payload = payload
        return commerce.saveSource(sourceId, payload)
      },
    }
    vi.spyOn(sourceWorkspaceApi, 'listSources').mockResolvedValue({
      items: [{
        id: 'managed-nextcloud',
        name: 'Nextcloud',
        sourceKind: 'external',
        externalSourceId: 'nextcloud:primary',
        worksheetMode: 'selected',
        worksheetName: 'Sheet1',
        dataStartRow: 2,
        status: 'active',
        version: 1,
        mappingVersion: 0,
        sheetId: null,
        createdAt: null,
        updatedAt: null,
      }],
    })
    const c = await renderPage(adminUser, savingCommerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    fillNextcloudCredentials(c)
    const save = Array.from(c.querySelectorAll('button'))
      .find(item => item.textContent === 'Save connection') as HTMLButtonElement

    expect(save.disabled).toBe(false)
    await act(async () => {
      save.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(captured.payload?.settings.spreadsheet_path).toBeUndefined()
    expect(captured.payload).not.toHaveProperty('currency')
    expect(captured.payload).not.toHaveProperty('currency_unit')
    expect(testCalls).toBe(0)
    expect(c.textContent).toContain('Connection settings saved')
    expect(c.textContent).toContain('You can now choose a Nextcloud spreadsheet file.')
  })

  it('keeps Test Connection separate from Save and does not test implicitly', async () => {
    let saveCalls = 0
    let testCalls = 0
    const failingCommerce: CommerceService = {
      ...commerce,
      async testSource() {
        testCalls += 1
        return {
          ok: false,
          status: 'authentication_failed',
          message: 'Authentication failed.',
          external_call_performed: true,
          read_only: true,
          runtime_write_blocked: true,
          write_blocked: true,
        }
      },
      async saveSource(sourceId, payload) {
        saveCalls += 1
        return commerce.saveSource(sourceId, payload)
      },
    }
    const c = await renderPage(adminUser, failingCommerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    fillNextcloudCredentials(c)
    const saveButton = Array.from(c.querySelectorAll('button'))
      .find(item => item.textContent === 'Save connection')

    await act(async () => {
      saveButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(testCalls).toBe(0)
    expect(saveCalls).toBe(1)
    expect(c.textContent).toContain('Connection settings saved')
    expect(c.querySelector('.fh-alert-danger')).toBeNull()
  })

  it('renders visible centralized icons with labels on source workflow actions', async () => {
    const configuredCommerce: CommerceService = {
      ...commerce,
      async getSources() {
        const original = await commerce.getSources()
        return {
          ...original,
          items: original.items.map(item => item.id === 'nextcloud:primary'
            ? {
                ...item,
                credential_status: 'configured',
                connection_configured: true,
                configuration_state: 'configured',
              }
            : item),
        }
      },
    }
    const c = await renderPage(adminUser, configuredCommerce, ['/commerce?tab=sources'])

    const configure = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Edit Connection')
    const configureColumns = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Configure Data')
    const test = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')
    const add = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Add source')

    expect(configure?.querySelector('[data-icon="settings"]')).not.toBeNull()
    expect(configureColumns?.querySelector('[data-icon="workspace"]')).not.toBeNull()
    expect(test?.querySelector('[data-icon="testConnection"]')).not.toBeNull()
    expect(add?.querySelector('[data-icon="add"]')).not.toBeNull()
    expect(configure?.textContent).toContain('Edit Connection')
    expect(configureColumns?.textContent).toContain('Configure Data')
    expect(test?.textContent).toContain('Test connection')
    expect(add?.textContent).toContain('Add source')
  })

  it('keeps channel management controls admin-only', async () => {
    const c = await renderPage(viewerUser)

    expect(c.textContent).toContain('Channels')
    expect(c.textContent).toContain('WooCommerce')
    expect(c.textContent).toContain('Admin permission required')
    expect(c.textContent).not.toContain('Add channel')
    expect(c.textContent).not.toContain('Test connection')

    const sources = await renderPage(viewerUser, commerce, ['/commerce?tab=sources'])

    expect(sources.textContent).toContain('Nextcloud')
    expect(sources.textContent).not.toContain('Add source')
  })

  it('shows a user-facing channel test error without backend detail', async () => {
    const failingCommerce: CommerceService = {
      ...commerce,
      async getChannels() {
        const original = await commerce.getChannels()
        return {
          ...original,
          items: original.items.map((item, index) => index === 0 ? { ...item, credential_status: 'configured' } : item),
        }
      },
      async testChannel() {
        throw new ApiError(403, JSON.stringify({ detail: 'Admin permission required.' }))
      },
    }
    const c = await renderPage(adminUser, failingCommerce)
    const testButton = resourceAction(c, 'WooCommerce', 'Test connection')

    await act(async () => {
      testButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Unable to connect to the channel')
    expect(c.textContent).toContain('The external service denied access for the saved credentials.')
    expect(c.textContent).not.toContain('Admin permission required.')
  })

  it('shows a user-facing save error without rendering secret values', async () => {
    const failingCommerce: CommerceService = {
      ...commerce,
      async saveChannel() {
        throw new ApiError(400, JSON.stringify({
          detail: 'Invalid credential: consumer_secret=cs_live_secret api_key=snapp-secret-value Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.private.signature https://user:pass@example.test/path',
        }))
      },
    }
    const c = await renderPage(adminUser, failingCommerce)
    const addChannel = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Add channel')
    await act(async () => {
      addChannel?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    const channelType = Array.from(c.querySelectorAll('label'))
      .find(label => label.textContent?.includes('Channel type'))
      ?.querySelector('select') as HTMLSelectElement
    await act(async () => {
      channelType.value = 'woocommerce:primary'
      channelType.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await act(async () => {
      const unit = selectByLabel(c, 'Price unit')
      unit.value = 'RIAL'
      unit.dispatchEvent(new Event('change', { bubbles: true }))
    })
    act(() => {
      setInputValue(inputByLabel(c, 'Store URL'), 'https://shop.example.test')
      const secrets = Array.from(c.querySelectorAll('input[type="password"]')) as HTMLInputElement[]
      setInputValue(secrets[0], 'consumer-key')
      setInputValue(secrets[1], 'consumer-secret')
    })
    const save = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Save configuration')

    await act(async () => {
      save?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Unable to save channel settings')
    expect(c.textContent).toContain('Please review your changes and try again.')
    expect(c.textContent).not.toContain('Invalid credential')
    expect(c.textContent).not.toContain('cs_live_secret')
    expect(c.textContent).not.toContain('snapp-secret-value')
    expect(c.textContent).not.toContain('eyJhbGci')
    expect(c.textContent).not.toContain('user:pass')
    expect(c.textContent).not.toContain('Unable to save channel configuration')
  })

  it('shows Nextcloud browser controls for configured source input', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)

    expect(c.textContent).toContain('Browse Nextcloud')
    expect(c.textContent).toContain('Nextcloud spreadsheet file')
    expect(c.textContent).toContain('Selected file')
    expect(c.textContent).toContain('No spreadsheet file selected')
    expect(c.textContent).not.toContain('Spreadsheet path')
    const fileRow = c.querySelector('[data-testid="nextcloud-file-control-row"]') as HTMLElement
    const browse = Array.from(fileRow.querySelectorAll('button'))
      .find(button => button.textContent === 'Browse Nextcloud') as HTMLButtonElement
    expect(fileRow.className).toContain('md:items-end')
    expect(fileRow.children).toHaveLength(2)
    expect(browse.parentElement).toBe(fileRow)
    expect(fileRow.textContent).toContain('Selected file')
  })

  it('opens Nextcloud file picker, renders directories and spreadsheet files, and selects a path', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    fillNextcloudCredentials(c)
    await saveNextcloudConnection(c)
    await testSavedNextcloudConnection(c)

    await act(async () => {
      Array.from(c.querySelectorAll('button'))
        .find(button => button.textContent === 'Browse Nextcloud')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Reports')
    expect(c.textContent).toContain('prices.xlsx')
    expect(c.textContent).toContain('legacy.csv')
    expect(c.textContent).toContain('Unsupported')

    await act(async () => {
      Array.from(c.querySelectorAll('button'))
        .find(button => button.textContent?.includes('prices.xlsx'))
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(c.textContent).toContain('/prices.xlsx')
  })

  it('rejects public share links as Nextcloud Base URL input', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    fillNextcloudCredentials(c, 'https://softpple.business/index.php/s/xxxxx')

    expect(c.textContent).toContain('Public share links are not supported. Use the Nextcloud root URL or your personal WebDAV files URL.')
  })

  it('accepts an authenticated Nextcloud WebDAV files URL as source input', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    fillNextcloudCredentials(c, 'https://softpple.business/remote.php/dav/files/woo', null)

    const textInputs = Array.from(c.querySelectorAll('input[type="text"]')) as HTMLInputElement[]
    expect(textInputs[1].value).toBe('woo')
    expect(c.textContent).not.toContain('Use the Nextcloud root URL or the WebDAV files URL shown in Nextcloud Files settings.')
    expect(c.textContent).not.toContain('WebDAV URL username does not match configured username.')
  })

  it('browses Nextcloud with a WebDAV URL and keeps the selected file as a relative path', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    fillNextcloudCredentials(c, 'https://softpple.business/remote.php/dav/files/woo', null)
    await saveNextcloudConnection(c)
    await testSavedNextcloudConnection(c)

    await act(async () => {
      Array.from(c.querySelectorAll('button'))
        .find(button => button.textContent === 'Browse Nextcloud')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    await act(async () => {
      Array.from(c.querySelectorAll('button'))
        .find(button => button.textContent?.includes('prices.xlsx'))
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(c.textContent).toContain('/prices.xlsx')
    expect(c.textContent).not.toContain('https://softpple.business/remote.php/dav/files/woo/prices.xlsx')
  })

  it('groups Channel cards and orders healthy, warning, disabled, then Coming Soon resources', async () => {
    const orderedCommerce: CommerceService = {
      ...commerce,
      async getChannels() {
        return {
          items: [
            channel('future:main', 'Future Market', true),
            { ...channel('disabled:main', 'Disabled Market', false), enabled: false },
            channel('warning:main', 'Warning Market', false),
            {
              ...channel('healthy:main', 'Healthy Market', false),
              status: 'healthy',
              credential_status: 'configured',
              health: { status: 'healthy', message: '', latency_ms: 4, error_code: null },
            },
          ],
        }
      },
    }

    const c = await renderPage(adminUser, orderedCommerce)

    expect(Array.from(c.querySelectorAll('[data-resource-id]')).map(item => item.getAttribute('data-resource-id')))
      .toEqual(['healthy:main', 'warning:main', 'disabled:main', 'future:main'])
    expect(Array.from(c.querySelectorAll('[data-resource-section]')).map(item => item.getAttribute('data-resource-section')))
      .toEqual(['active', 'disabled', 'comingSoon'])
    expect(c.querySelector('[data-resource-id="healthy:main"]')?.textContent).toContain('Healthy')
    expect(c.querySelector('[data-resource-id="warning:main"]')?.textContent).toContain('Warning')
    expect(c.querySelector('[data-resource-id="disabled:main"]')?.textContent).toContain('Disabled')
    expect(c.querySelector('[data-resource-id="future:main"]')?.textContent).toContain('Coming Soon')
  })

  it('groups Source cards and sorts Coming Soon items by display name', async () => {
    const c = await renderPage()
    await act(async () => {
      Array.from(c.querySelectorAll('button'))
        .find(button => button.textContent === 'Sources')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(Array.from(c.querySelectorAll('[data-resource-id]')).map(item => item.getAttribute('data-resource-id')))
      .toEqual(['nextcloud:primary', 'csv:import', 'erp:api-import', 'gsheets:price-list'])
    expect(Array.from(c.querySelectorAll('[data-resource-section]')).map(item => item.getAttribute('data-resource-section')))
      .toEqual(['active', 'comingSoon'])
  })

  it('initializes the first Nextcloud Data Sheet from the saved worksheet policy', async () => {
    const listSources = vi.spyOn(sourceWorkspaceApi, 'listSources').mockResolvedValue({ items: [] })
    const createSource = vi.spyOn(sourceWorkspaceApi, 'createSource').mockResolvedValue({
      id: 'managed-nextcloud',
      name: 'Nextcloud',
      sourceKind: 'external',
      externalSourceId: 'nextcloud:primary',
      worksheetMode: 'all',
      worksheetName: null,
      dataStartRow: 2,
      status: 'active',
      version: 1,
      mappingVersion: 0,
      sheetId: null,
      createdAt: null,
      updatedAt: null,
    })
    const policyCommerce: CommerceService = {
      ...commerce,
      async getSources() {
        const data = await commerce.getSources()
        return {
          ...data,
          items: data.items.map(item => item.id === 'nextcloud:primary'
            ? {
                ...item,
                enabled: true,
                status: 'healthy',
                credential_status: 'configured',
                connection_configured: true,
                configuration_state: 'configured',
                health: { status: 'healthy', message: '', latency_ms: 12, error_code: null },
              }
            : item),
        }
      },
      async getSourceConfiguration(sourceId) {
        const configuration = await commerce.getSourceConfiguration(sourceId)
        return {
          ...configuration,
          enabled: true,
          configured: true,
          connection_configured: true,
          settings: {
            ...configuration.settings,
            worksheet_mode: 'all',
            worksheet_name: '',
          },
        }
      },
    }

    const c = await renderPage(adminUser, policyCommerce, ['/commerce?tab=sources'])
    await act(async () => {
      resourceAction(c, 'Nextcloud', 'Configure Data').click()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(listSources).toHaveBeenCalledTimes(1)
    expect(createSource).toHaveBeenCalledWith(expect.objectContaining({
      external_source_id: 'nextcloud:primary',
      worksheet_mode: 'all',
      worksheet_name: null,
    }))
  })

  it('prefers the first Active configuration type and preserves an explicit edit selection', async () => {
    const typesCommerce: CommerceService = {
      ...commerce,
      async getSourceTypes() {
        return {
          items: [
            typeOption('csv:import', 'csv', 'CSV', 'Source', true, []),
            typeOption('nextcloud:primary', 'nextcloud', 'Nextcloud', 'Source', false, []),
          ],
        }
      },
      async getChannels() {
        const original = await commerce.getChannels()
        return {
          ...original,
          items: original.items.map(item => item.provider === 'woocommerce'
            ? { ...item, credential_status: 'configured' }
            : item),
        }
      },
    }
    const c = await renderPage(adminUser, typesCommerce)

    await act(async () => {
      Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Sources')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(async () => {
      Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Add source')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    const sourceTypeSelect = Array.from(c.querySelectorAll('label')).find(label => label.textContent?.includes('Source type'))?.querySelector('select') as HTMLSelectElement
    expect(sourceTypeSelect.value).toBe('nextcloud:primary')
    expect(Array.from(sourceTypeSelect.querySelectorAll('optgroup')).map(group => group.label)).toEqual(['Active', 'Coming Soon'])

    await act(async () => {
      Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Channels')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(async () => {
      Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Settings')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })
    const channelTypeSelect = Array.from(c.querySelectorAll('label')).find(label => label.textContent?.includes('Channel type'))?.querySelector('select') as HTMLSelectElement
    expect(channelTypeSelect.value).toBe('woocommerce:primary')
    expect(channelTypeSelect.disabled).toBe(true)
  })
})
