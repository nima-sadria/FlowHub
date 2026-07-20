// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'
import { ApiError } from '../api/client'
import { NotificationProvider } from '../notifications/NotificationProvider'
import NotificationContainer from '../notifications/NotificationContainer'
import { ServiceProvider } from '../services/ServiceContext'
import type { Services } from '../services/ServiceContext'
import type { CommerceService } from '../services/commerce/CommerceService'
import CommerceHub from './CommerceHub'
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
          { key: 'token_refresh_expired_at', label: 'Token refresh expiration', required: false, secret: false },
          { key: 'token', label: 'Authorization token', required: true, secret: true },
          { key: 'webhook_token', label: 'Webhook token', required: false, secret: true },
        ]),
      ],
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
        channel('digikala:main', 'Digikala', true),
        channel('technolife:main', 'Technolife', true),
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
              <CommerceHub key={initialEntries[0]} />
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

describe('CommerceHub', () => {
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
    expect(c.textContent).toContain('Snapp Shop')
    expect(c.textContent).toContain('Tapsi Shop')
    expect(c.textContent).toContain('Coming Soon')
    expect(c.textContent).toContain('Read-only mode')
    expect(c.textContent).toContain('Writes blocked')
    expect(c.textContent).toContain('Add channel')
    expect(c.textContent).not.toContain('Apply')
  })

  it('shows configuration actions only for implemented channels', async () => {
    const c = await renderPage()

    expect(Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Refresh product cache')).toHaveLength(1)
    expect(Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Settings')).toHaveLength(0)
    expect(Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Configure')).toHaveLength(3)
    expect(c.textContent).toContain('Cached products: 2')
    expect(c.textContent).toContain('Cached variations: 2')
    expect(c.textContent).toContain('Refresh status: Completed')
    expect(c.querySelector('button [data-icon="edit"]')).not.toBeNull()
    expect(c.querySelector('button [data-icon="testConnection"]')).not.toBeNull()
    expect(c.querySelector('button [data-icon="refresh"]')).not.toBeNull()

    const sources = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])

    expect(sources.textContent).not.toContain('Refresh product cache')
    expect(Array.from(sources.querySelectorAll('button')).filter(button => button.textContent === 'Read now')).toHaveLength(1)
  })

  it('shows Settings for configured marketplaces and no Configure action for planned channels', async () => {
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
    expect(Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Refresh product cache')).toHaveLength(2)
    for (const planned of ['Digikala', 'Technolife', 'Shopify']) {
      const card = Array.from(c.querySelectorAll('h3')).find(item => item.textContent === planned)?.closest('.fh-card')
      expect(Array.from(card?.querySelectorAll('button') ?? [])).toHaveLength(0)
    }
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
    const configure = resourceAction(c, 'Snapp Shop', 'Configure')
    await act(async () => {
      configure.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Configure Snapp Shop')
    expect(c.textContent).toContain('Agent identifier')
    expect(c.textContent).toContain('Agent header name')
    expect(c.textContent).toContain('Request timeout seconds')
    const advanced = c.querySelector('details') as HTMLDetailsElement
    expect(advanced.open).toBe(false)
    const timeout = c.querySelector('input[type="number"]') as HTMLInputElement
    expect(timeout.step).toBe('1')
    expect(timeout.min).toBe('1')
    expect(timeout.value).toBe('20')
    timeout.value = '29'
    expect(timeout.checkValidity()).toBe(true)
    const token = c.querySelector('input[type="password"]') as HTMLInputElement
    expect(token.value).toBe('')
    expect(c.textContent).toContain('Configured; leave blank to keep unchanged.')

    const test = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')
    expect((test as HTMLButtonElement).disabled).toBe(false)
    await act(async () => {
      test?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })
    expect(testedPayload?.settings.agent_identifier).toBe('flowhub-agent')
    expect(testedPayload?.secrets.token).toBeUndefined()
    const vendorSelect = Array.from(c.querySelectorAll('select')).find(select => select.required) as HTMLSelectElement
    expect(vendorSelect.value).toBe('vendor-1')
    expect(vendorSelect.textContent).toContain('Primary Vendor')
    expect(c.textContent).toContain('Channel connected successfully')
    expect(c.textContent).toContain('SnappShop is ready to use.')
    expect(c.querySelector('[role="alert"] [data-icon="success"]')).not.toBeNull()
  })

  it('requires explicit vendor selection when multiple active SnappShop vendors are discovered', async () => {
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
    const configure = resourceAction(c, 'Snapp Shop', 'Configure')
    await act(async () => {
      configure.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })
    await act(async () => {
      Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })

    const vendorSelect = Array.from(c.querySelectorAll('select')).find(select => select.required) as HTMLSelectElement
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
    const configure = resourceAction(c, 'Tapsi Shop', 'Configure')
    await act(async () => {
      configure.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
      await Promise.resolve()
    })

    const secretInputs = Array.from(c.querySelectorAll('input[type="password"]')) as HTMLInputElement[]
    expect(secretInputs).toHaveLength(2)
    expect(secretInputs.every(input => input.value === '')).toBe(true)
    expect(c.textContent).toContain('Webhook registration')
    expect(c.textContent).toContain('Webhook credential: Configured')
    expect((inputByLabel(c, 'Webhook URL')).value).toContain('/api/v2/webhooks/tapsishop/tapsishop%3Amain')
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
    const configure = resourceAction(c, 'Snapp Shop', 'Configure')
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
      .find(button => button.textContent === 'Refresh product cache')

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
        .find(button => button.textContent === 'Refresh product cache')
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
    expect(c.textContent).not.toContain('Snapp Shop')
    expect(c.textContent).not.toContain('Tapsi Shop')
  })

  it('shows Nextcloud source Test connection action but not planned source test actions', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])

    const testButtons = Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Test connection')
    expect(testButtons).toHaveLength(1)
    const readButtons = Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Read now')
    expect(readButtons).toHaveLength(1)
    const settingsButtons = Array.from(c.querySelectorAll('button')).filter(button => button.textContent === 'Settings')
    expect(settingsButtons).toHaveLength(1)
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
        return tested
          ? { ...original, items: [refreshedSource, ...original.items.slice(1)] }
          : original
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
    expect(c.textContent).toContain('Please verify your credentials and try again.')
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
    expect(c.textContent).toContain('choose product ID, price, stock, and status columns separately for every Channel')
    expect(c.textContent).toContain('Read Policy')
    expect(c.textContent).not.toContain('snapp-secret-value')
  })

  it('saves connector read settings without persisting a second global Source mapping', async () => {
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
      }],
    })

    await act(async () => {
      inputByLabel(c, 'Selected worksheet').dispatchEvent(new MouseEvent('click', { bubbles: true }))
      setInputValue(inputByLabel(c, 'Worksheet name'), 'Prices')
      setInputValue(inputByLabel(c, 'Max reads per 24 hours'), '5')
    })
    await act(async () => {
      Array.from(c.querySelectorAll('button'))
        .find(button => button.textContent === 'Save configuration')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(captured.payload).toBeTruthy()
    if (!captured.payload) throw new Error('saveSource payload was not captured')
    expect(captured.payload.settings).not.toHaveProperty('source_mapping')
    expect(captured.payload.settings.worksheet_mode).toBe('selected')
    expect(captured.payload.settings.worksheet_name).toBe('Prices')
    expect(captured.payload.settings.source_read_policy).toMatchObject({
      enabled: true,
      max_reads_per_24h: 5,
      manual_read_allowed: true,
    })
    expect(c.textContent).toContain('Source configured successfully')
    expect(c.textContent).toContain('The source is ready to use.')
    expect(c.querySelector('[data-notification-type="success"] .fh-notification-icon [data-icon="success"]')).not.toBeNull()
  })

  it('renders visible centralized icons with labels on source workflow actions', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])

    const configure = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Settings')
    const test = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Test connection')
    const read = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Read now')
    const add = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Add source')

    expect(configure?.querySelector('[data-icon="settings"]')).not.toBeNull()
    expect(test?.querySelector('[data-icon="testConnection"]')).not.toBeNull()
    expect(read?.querySelector('[data-icon="sync"]')).not.toBeNull()
    expect(add?.querySelector('[data-icon="add"]')).not.toBeNull()
    expect(configure?.textContent).toContain('Settings')
    expect(test?.textContent).toContain('Test connection')
    expect(read?.textContent).toContain('Read now')
    expect(add?.textContent).toContain('Add source')
  })

  it('runs Read now for Nextcloud and renders the read result', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])

    await act(async () => {
      Array.from(c.querySelectorAll('button'))
        .find(button => button.textContent === 'Read now')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await Promise.resolve()
    })

    expect(c.textContent).toContain('Source refreshed successfully')
    expect(c.textContent).toContain('1 row loaded.')
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
    expect(c.textContent).toContain('Please verify your credentials and try again.')
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
  })

  it('opens Nextcloud file picker, renders directories and spreadsheet files, and selects a path', async () => {
    const c = await renderPage(adminUser, commerce, ['/commerce?tab=sources'])
    await openNextcloudSourceForm(c)
    fillNextcloudCredentials(c)

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
