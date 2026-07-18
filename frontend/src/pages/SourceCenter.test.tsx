// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceLifecycleImpact, SourceProfile } from '../features/sourceWorkspace/types'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { CommerceService } from '../services/commerce/CommerceService'
import type { CommerceSource } from '../services/types'
import SourceCenter from './SourceCenter'

const source: SourceProfile = { id: 'source-1', name: 'Synthetic prices', sourceKind: 'flowhub_sheet', externalSourceId: null, worksheetMode: 'selected', worksheetName: 'Sheet1', dataStartRow: 2, status: 'active', version: 3, mappingVersion: 2, sheetId: 'sheet-1' }
const admin: AuthContextValue = { user: { username: 'admin', role: 'admin', is_admin: true, is_super_admin: false, permissions: {} }, status: 'authenticated', refreshUser: async () => {}, clearAuth: () => {}, authFetch: fetch }
const viewer: AuthContextValue = { ...admin, user: { username: 'viewer', role: 'user', is_admin: false, is_super_admin: false, permissions: { can_access_site: true, 'workspace.read': true } } }
const commerce = {
  getSources: vi.fn(),
} as unknown as CommerceService
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

const emptyCommerceSources = {
  items: [],
  relationship_map: { nodes: [], example: [], runtime_write_blocked: true, read_only: true },
}

function commerceSource(
  id: string,
  name: string,
  options: { placeholder?: boolean; healthy?: boolean; configured?: boolean } = {},
): CommerceSource {
  const placeholder = options.placeholder ?? false
  const configured = options.configured ?? !placeholder
  return {
    id,
    provider: id.split(':')[0],
    name,
    type: 'Source',
    status: placeholder ? 'future' : configured ? 'configured' : 'not_configured',
    implemented: !placeholder,
    placeholder,
    credential_status: configured ? 'configured' : 'not_configured',
    last_health_check: options.healthy ? '2026-07-15T10:00:00Z' : null,
    data_role: 'Spreadsheet price input',
    action_label: 'Manage',
    action_href: '/commerce?tab=sources',
    health: { status: options.healthy ? 'healthy' : 'unknown', message: '', latency_ms: null, error_code: null },
    read_status: options.healthy ? {
      enabled: true,
      max_reads_per_24h: 10,
      manual_read_allowed: true,
      reads_used_last_24h: 1,
      reads_remaining: 9,
      reset_at: null,
      last_read_at: '2026-07-15T09:30:00Z',
      last_read_status: 'completed',
      last_row_count: 25,
      last_warning_count: 0,
      last_error_count: 0,
    } : undefined,
    read_only: true,
    runtime_write_blocked: true,
    settings_available: !placeholder,
  }
}

describe('SourceCenter safe lifecycle', () => {
  let container: HTMLDivElement
  let root: ReturnType<typeof createRoot>
  beforeEach(() => {
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container)
    vi.mocked(commerce.getSources).mockReset()
    vi.mocked(commerce.getSources).mockResolvedValue(emptyCommerceSources)
    vi.spyOn(sourceWorkspaceApi, 'listSources').mockResolvedValue({ items: [source] })
    vi.spyOn(sourceWorkspaceApi, 'sourceLifecycle').mockResolvedValue({ sourceId: source.id, sourceName: source.name, sourceVersion: source.version, sourceStatus: 'active', action: 'archive', blockers: {}, protectedHistory: { mappingRevisions: 1 } })
    vi.spyOn(sourceWorkspaceApi, 'deleteSource').mockResolvedValue({ sourceId: source.id, sourceName: source.name, outcome: 'archived', source: { ...source, status: 'disabled', version: 4 }, impact: { sourceId: source.id, sourceName: source.name, sourceVersion: source.version, sourceStatus: 'active', action: 'archive', blockers: {}, protectedHistory: { mappingRevisions: 1 } } })
  })
  afterEach(() => { act(() => root.unmount()); container.remove(); vi.restoreAllMocks() })

  async function render(auth = admin) {
    await act(async () => {
      root.render(<AuthContext.Provider value={auth}><NotificationProvider><MemoryRouter><ServiceProvider services={services}><SourceCenter /></ServiceProvider></MemoryRouter></NotificationProvider></AuthContext.Provider>)
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    })
  }

  async function deleteTrigger(sourceId = source.id): Promise<HTMLButtonElement> {
    const menu = container.querySelector(`[data-source-menu-trigger="${sourceId}"]`) as HTMLButtonElement
    await act(async () => menu.click())
    return Array.from(container.querySelectorAll(`[data-source-card="${sourceId}"] [role="menu"] button`))
      .find(item => item.textContent?.includes('Delete Source')) as HTMLButtonElement
  }

  it('requires explicit named confirmation and cancellation sends no request', async () => {
    await render()
    const trigger = await deleteTrigger()
    await act(async () => { trigger.click(); await Promise.resolve(); await Promise.resolve() })
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Synthetic prices')
    const cancel = Array.from(container.querySelectorAll('[role="dialog"] button')).find(item => item.textContent?.includes('Cancel')) as HTMLButtonElement
    await act(async () => cancel.click())
    expect(sourceWorkspaceApi.deleteSource).not.toHaveBeenCalled()
  })

  it('moves focus into the dialog, closes with Escape, and restores trigger focus', async () => {
    await render()
    const menuTrigger = container.querySelector('[data-source-menu-trigger="source-1"]') as HTMLButtonElement
    const trigger = await deleteTrigger()
    trigger.focus()
    await act(async () => { trigger.click(); await Promise.resolve(); await Promise.resolve() })
    const dialog = container.querySelector('[role="dialog"]') as HTMLElement
    const cancel = Array.from(dialog.querySelectorAll('button')).find(item => item.textContent?.includes('Cancel')) as HTMLButtonElement
    expect(document.activeElement).toBe(cancel)

    await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))

    expect(container.querySelector('[role="dialog"]')).toBeNull()
    expect(document.activeElement).toBe(menuTrigger)
    expect(sourceWorkspaceApi.deleteSource).not.toHaveBeenCalled()
  })

  it('shows archive result while preserving the Source identity', async () => {
    await render()
    const trigger = await deleteTrigger()
    await act(async () => { trigger.click(); await Promise.resolve(); await Promise.resolve() })
    const confirm = Array.from(container.querySelectorAll('[role="dialog"] button')).find(item => item.textContent?.includes('Archive Source')) as HTMLButtonElement
    await act(async () => { confirm.click(); await Promise.resolve(); await Promise.resolve() })
    expect(sourceWorkspaceApi.deleteSource).toHaveBeenCalledWith(source)
    expect(container.textContent).toContain('Disabled')
    expect(container.textContent).toContain('Synthetic prices')
  })

  it('shows the active Workspace blocker and cannot confirm removal', async () => {
    vi.mocked(sourceWorkspaceApi.sourceLifecycle).mockResolvedValueOnce({ sourceId: source.id, sourceName: source.name, sourceVersion: source.version, sourceStatus: 'active', action: 'blocked', blockers: { activeWorkspaces: 1 }, protectedHistory: { workspaceSnapshots: 1 } })
    await render()
    const trigger = await deleteTrigger()
    await act(async () => { trigger.click(); await Promise.resolve(); await Promise.resolve() })
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Cannot delete')
    const destructive = Array.from(container.querySelectorAll('[role="dialog"] button')).find(item => item.textContent?.includes('Delete Source')) as HTMLButtonElement
    expect(destructive.disabled).toBe(true)
    expect(sourceWorkspaceApi.deleteSource).not.toHaveBeenCalled()
  })

  it('ignores an out-of-order lifecycle response from a previously closed Source dialog', async () => {
    const other: SourceProfile = { ...source, id: 'source-2', name: 'Other prices', version: 5 }
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValue({ items: [source, other] })
    let resolveFirst: (impact: SourceLifecycleImpact) => void = () => {}
    const firstImpact = new Promise<SourceLifecycleImpact>(resolve => { resolveFirst = resolve })
    vi.mocked(sourceWorkspaceApi.sourceLifecycle).mockImplementation(sourceId => sourceId === source.id
      ? firstImpact
      : Promise.resolve({ sourceId: other.id, sourceName: other.name, sourceVersion: other.version, sourceStatus: 'active', action: 'delete', blockers: {}, protectedHistory: {} }))
    await render()

    const firstMenuTrigger = container.querySelector('[data-source-menu-trigger="source-1"]') as HTMLButtonElement
    const firstTrigger = await deleteTrigger('source-1')
    await act(async () => { firstTrigger.click(); await Promise.resolve() })
    const cancel = Array.from(container.querySelectorAll('[role="dialog"] button')).find(item => item.textContent?.includes('Cancel')) as HTMLButtonElement
    await act(async () => { cancel.click(); await Promise.resolve() })
    expect(document.activeElement).toBe(firstMenuTrigger)

    const secondTrigger = await deleteTrigger('source-2')
    await act(async () => { secondTrigger.click(); await Promise.resolve(); await Promise.resolve() })
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Other prices')
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Delete unused Source')

    await act(async () => {
      resolveFirst({ sourceId: source.id, sourceName: source.name, sourceVersion: source.version, sourceStatus: 'active', action: 'archive', blockers: {}, protectedHistory: { mappingRevisions: 1 } })
      await Promise.resolve()
    })
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Other prices')
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Delete unused Source')
    expect(container.querySelector('[role="dialog"]')?.textContent).not.toContain('Archive Source')
  })

  it('does not expose the destructive control to an unauthorized viewer', async () => {
    await render(viewer)
    expect(container.textContent).not.toContain('Delete Source')
  })

  it('groups managed Sources consistently and sorts display names inside each group', async () => {
    const activeZebra = { ...source, id: 'source-z', name: 'Zebra prices' }
    const activeAlpha = { ...source, id: 'source-a', name: 'Alpha prices' }
    const disabledBeta = { ...source, id: 'source-b', name: 'Beta archive', status: 'disabled', sheetId: null }
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({
      items: [disabledBeta, activeZebra, activeAlpha],
    })

    await render()

    expect(Array.from(container.querySelectorAll('[data-resource-id]')).map(item => item.getAttribute('data-resource-id')))
      .toEqual(['source-a', 'source-z', 'source-b'])
    expect(Array.from(container.querySelectorAll('[data-resource-section]')).map(item => item.getAttribute('data-resource-section')))
      .toEqual(['active', 'disabled'])
    expect(container.querySelector('[data-resource-id="source-a"]')?.textContent).toContain('Configured')
    expect(container.querySelector('[data-resource-id="source-b"]')?.textContent).toContain('Disabled')
    expect(container.querySelector('[data-resource-section="comingSoon"]')).toBeNull()
  })

  it('renders responsive integration cards, merges linked Commerce metadata, and keeps Coming Soon last', async () => {
    const linked: SourceProfile = {
      ...source,
      name: 'Nextcloud prices',
      sourceKind: 'external',
      externalSourceId: 'nextcloud:primary',
      sheetId: null,
    }
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [linked] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [
        commerceSource('gsheets:price-list', 'Google Sheets', { placeholder: true }),
        commerceSource('nextcloud:primary', 'Nextcloud', { healthy: true }),
      ],
    })

    await render()

    expect(container.querySelectorAll('[data-source-card]')).toHaveLength(2)
    expect(container.querySelector('[data-source-card="source-1"]')?.textContent).toContain('Healthy')
    expect(container.querySelector('[data-source-card="source-1"] [data-source-icon]')?.getAttribute('data-source-icon')?.toLowerCase()).toContain('nextcloud.webp')
    expect(container.querySelector('[data-source-card="integration:gsheets:price-list"]')?.textContent).toContain('Coming Soon')
    expect(Array.from(container.querySelectorAll('[data-resource-section]')).map(item => item.getAttribute('data-resource-section')))
      .toEqual(['active', 'comingSoon'])
    const cardGridClass = container.querySelector('[data-testid="source-card-groups"] section > div')?.className ?? ''
    expect(cardGridClass).toContain('lg:grid-cols-2')
    expect(cardGridClass).toContain('xl:grid-cols-3')
  })

  it('merges a legacy managed Source with Commerce metadata when their stable IDs match', async () => {
    const legacyImported: SourceProfile = {
      ...source,
      id: 'csv:primary',
      name: 'Imported CSV prices',
      sourceKind: 'imported_sheet',
      externalSourceId: null,
    }
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [legacyImported] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [commerceSource('csv:primary', 'CSV', { healthy: true })],
    })

    await render()

    expect(container.querySelectorAll('[data-source-card]')).toHaveLength(1)
    expect(container.querySelector('[data-source-card="csv:primary"]')?.textContent).toContain('Healthy')
    expect(container.querySelector('[data-source-card="integration:csv:primary"]')).toBeNull()
  })

  it('keeps a managed Source linked to an unavailable integration non-actionable and in Coming Soon', async () => {
    const linked: SourceProfile = {
      ...source,
      sourceKind: 'external',
      externalSourceId: 'shopify:future',
      sheetId: null,
    }
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [linked] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [commerceSource('shopify:future', 'Shopify', { placeholder: true })],
    })

    await render()

    const card = container.querySelector('[data-source-card="source-1"]') as HTMLElement
    expect(card.textContent).toContain('Coming Soon')
    expect(card.querySelectorAll('button')).toHaveLength(0)
    expect(container.querySelector('[data-resource-section="comingSoon"]')).not.toBeNull()
  })

  it('uses a localized safe description instead of exposing an unknown technical data role', async () => {
    const integration = commerceSource('custom-erp:primary', 'Custom ERP', { healthy: true })
    integration.data_role = 'synthetic_source_role_v9'
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [integration],
    })

    await render()

    const card = container.querySelector('[data-source-card="integration:custom-erp:primary"]') as HTMLElement
    expect(card.title).toContain('External spreadsheet Source')
    expect(card.textContent).not.toContain('synthetic_source_role_v9')
  })

  it('searches managed Sources and filters cards by shared resource state', async () => {
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({
      items: [
        { ...source, id: 'source-z', name: 'Zebra prices' },
        { ...source, id: 'source-a', name: 'Alpha prices' },
        { ...source, id: 'source-b', name: 'Beta archive', status: 'disabled', sheetId: null },
      ],
    })
    await render()

    const disabledFilter = Array.from(container.querySelectorAll('button')).find(item => item.textContent === 'Disabled') as HTMLButtonElement
    await act(async () => disabledFilter.click())
    expect(Array.from(container.querySelectorAll('[data-source-card]')).map(item => item.getAttribute('data-source-card')))
      .toEqual(['source-b'])

    const allFilter = Array.from(container.querySelectorAll('button')).find(item => item.textContent === 'All Sources') as HTMLButtonElement
    await act(async () => allFilter.click())
    const search = container.querySelector('input[type="search"]') as HTMLInputElement
    const valueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    await act(async () => {
      valueSetter?.call(search, 'zebra')
      search.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(Array.from(container.querySelectorAll('[data-source-card]')).map(item => item.getAttribute('data-source-card')))
      .toEqual(['source-z'])
  })

  it('opens a focused Add Source panel with the three supported entry paths', async () => {
    await render()
    const add = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Add Source') as HTMLButtonElement
    await act(async () => add.click())

    const dialog = container.querySelector('[role="dialog"]') as HTMLElement
    expect(dialog.textContent).toContain('FlowHub Sheet')
    expect(dialog.textContent).toContain('Import your spreadsheet')
    expect(dialog.textContent).toContain('Keep an external Source linked')
  })
})
