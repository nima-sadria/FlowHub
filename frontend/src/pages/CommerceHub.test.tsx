// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider } from '../services/ServiceContext'
import type { Services } from '../services/ServiceContext'
import type { CommerceService } from '../services/commerce/CommerceService'
import CommerceHub from './CommerceHub'

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
          { key: 'file_path', label: 'File/path placeholder', required: false, secret: false },
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
        typeOption('snappshop:main', 'snappshop', 'Snapp Shop', 'Channel', true, [
          { key: 'api_key', label: 'API key', required: false, secret: true },
        ]),
      ],
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
      ok: false,
      status: 'not_configured',
      message: 'No external call was performed.',
      external_call_performed: false,
      read_only: true,
      runtime_write_blocked: true,
      write_blocked: true,
    }
  },
  async getChannels() {
    return {
      items: [
        channel('woocommerce:primary', 'WooCommerce', false),
        channel('snappshop:main', 'Snapp Shop', true),
        channel('tapsishop:main', 'Tapsi Shop', true),
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
    last_health_check: null,
    health: { status: 'unknown', message: '', latency_ms: null, error_code: null },
    capabilities: { read_products: true },
    capabilities_summary: ['Product read'],
    settings_available: true,
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
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
})

async function renderPage() {
  await act(async () => {
    root.render(
      <NotificationProvider>
        <MemoryRouter initialEntries={['/commerce']}>
          <ServiceProvider services={services}>
            <CommerceHub />
          </ServiceProvider>
        </MemoryRouter>
      </NotificationProvider>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return container
}

describe('CommerceHub', () => {
  it('renders the Commerce Hub route content and Channels section', async () => {
    const c = await renderPage()
    expect(c.textContent).toContain('Commerce Hub')
    expect(c.textContent).toContain('Channels')
    expect(c.textContent).toContain('WooCommerce')
    expect(c.textContent).toContain('Snapp Shop')
    expect(c.textContent).toContain('Tapsi Shop')
    expect(c.textContent).toContain('Future channel placeholder')
    expect(c.textContent).toContain('Read-only mode')
    expect(c.textContent).toContain('Writes blocked')
    expect(c.textContent).toContain('Add Channel')
    expect(c.textContent).not.toContain('Apply')
  })

  it('renders Sources without listing marketplace channels there', async () => {
    const c = await renderPage()
    const sourceTab = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Sources')
    await act(async () => {
      sourceTab?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(c.textContent).toContain('Nextcloud')
    expect(c.textContent).toContain('CSV')
    expect(c.textContent).toContain('Google Sheets')
    expect(c.textContent).toContain('ERP / API Import')
    expect(c.textContent).toContain('Add Source')
    expect(c.textContent).toContain('Future source placeholder')
    expect(c.textContent).not.toContain('Snapp Shop')
    expect(c.textContent).not.toContain('Tapsi Shop')
  })

  it('opens Source and Channel forms without rendering secrets', async () => {
    const c = await renderPage()
    const addChannel = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Add Channel')
    await act(async () => {
      addChannel?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(c.textContent).toContain('Channel type')
    expect(c.textContent).toContain('Consumer Secret')

    const sourceTab = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Sources')
    await act(async () => {
      sourceTab?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    const addSource = Array.from(c.querySelectorAll('button')).find(button => button.textContent === 'Add Source')
    await act(async () => {
      addSource?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(c.textContent).toContain('Source type')
    expect(c.textContent).toContain('App password / token')
    expect(c.textContent).not.toContain('snapp-secret-value')
  })
})
