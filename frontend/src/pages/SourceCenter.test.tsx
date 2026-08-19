// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceLifecycleImpact, SourceProfile } from '../features/sourceWorkspace/types'
import NotificationContainer from '../notifications/NotificationContainer'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { CommerceService } from '../services/commerce/CommerceService'
import type { CommerceSource } from '../services/types'
import SourceCenter from './SourceCenter'

const source: SourceProfile = { id: 'source-1', name: 'Synthetic prices', sourceKind: 'flowhub_sheet', externalSourceId: null, worksheetMode: 'selected', worksheetName: 'Sheet1', dataStartRow: 2, status: 'active', version: 3, mappingVersion: 2, mappingReadiness: 'ready', sheetId: 'sheet-1', createdAt: null, updatedAt: null }
const admin: AuthContextValue = { user: { id: 1, username: 'admin', email: 'admin@example.com', role: 'admin', is_admin: true, is_super_admin: false, permissions: {} }, status: 'authenticated', refreshUser: async () => {}, clearAuth: () => {}, logout: async () => {}, authFetch: fetch }
const viewer: AuthContextValue = { ...admin, user: { id: 2, username: 'viewer', email: 'viewer@example.com', role: 'user', is_admin: false, is_super_admin: false, permissions: { can_access_site: true, 'workspace.read': true } } }
const operator: AuthContextValue = { ...admin, user: { id: 3, username: 'operator', email: 'operator@example.com', role: 'operator', is_admin: false, is_super_admin: false, permissions: { 'workspace.read': true, 'workspace.create': true } } }
const commerce = {
  getSources: vi.fn(),
} as unknown as CommerceService
const products = {
  getProducts: vi.fn(),
} as unknown as Services['products']
const services: Services = {
  commerce,
  products,
  health: {} as Services['health'],
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

function LocationProbe() {
  const location = useLocation()
  return <span data-testid="location-probe">{location.pathname}{location.search}</span>
}

function commerceSource(
  id: string,
  name: string,
  options: {
    placeholder?: boolean
    healthy?: boolean
    configured?: boolean
    connectionConfigured?: boolean
    enabled?: boolean
    configurationState?: CommerceSource['configuration_state']
    healthStatus?: string
  } = {},
): CommerceSource {
  const placeholder = options.placeholder ?? false
  const configured = options.configured ?? !placeholder
  const connectionConfigured = options.connectionConfigured ?? configured
  return {
    id,
    provider: id.split(':')[0],
    name,
    type: 'Source',
    status: placeholder ? 'future' : configured ? 'configured' : 'not_configured',
    implemented: !placeholder,
    placeholder,
    credential_status: connectionConfigured ? 'configured' : 'not_configured',
    connection_configured: connectionConfigured,
    configuration_state: options.configurationState ?? (configured ? 'configured' : 'not_configured'),
    enabled: options.enabled ?? true,
    last_health_check: options.healthy ? '2026-07-15T10:00:00Z' : null,
    data_role: 'Spreadsheet price input',
    action_label: 'Manage',
    action_href: '/commerce?tab=sources',
    health: { status: options.healthStatus ?? (options.healthy ? 'healthy' : 'unknown'), message: '', latency_ms: null, error_code: null },
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
    vi.mocked(products.getProducts).mockReset()
    vi.mocked(products.getProducts).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 1 })
    vi.spyOn(sourceWorkspaceApi, 'listSources').mockResolvedValue({ items: [source] })
    vi.spyOn(sourceWorkspaceApi, 'source').mockResolvedValue({ ...source, mapping: null })
    vi.spyOn(sourceWorkspaceApi, 'sourceLifecycle').mockResolvedValue({ sourceId: source.id, sourceName: source.name, sourceVersion: source.version, sourceStatus: 'active', action: 'archive', blockers: {}, protectedHistory: { mappingRevisions: 1 } })
    vi.spyOn(sourceWorkspaceApi, 'deleteSource').mockResolvedValue({ sourceId: source.id, sourceName: source.name, outcome: 'archived', source: { ...source, status: 'archived', archivedAt: '2026-08-13T08:30:00Z', version: 4 }, impact: { sourceId: source.id, sourceName: source.name, sourceVersion: source.version, sourceStatus: 'active', action: 'archive', blockers: {}, protectedHistory: { mappingRevisions: 1 } } })
    vi.spyOn(sourceWorkspaceApi, 'archiveSource').mockResolvedValue({ sourceId: source.id, sourceName: source.name, outcome: 'archived', source: { ...source, status: 'archived', archivedAt: '2026-08-13T08:30:00Z', version: 4 }, impact: { sourceId: source.id, sourceName: source.name, sourceVersion: source.version, sourceStatus: 'active', action: 'archive', blockers: {}, protectedHistory: { mappingRevisions: 1 } } })
  })
  afterEach(() => { act(() => root.unmount()); container.remove(); vi.restoreAllMocks() })

  async function render(auth = admin, initialEntry = '/sources') {
    await act(async () => {
      root.render(<AuthContext.Provider value={auth}><NotificationProvider><MemoryRouter initialEntries={[initialEntry]}><ServiceProvider services={services}><SourceCenter /></ServiceProvider><LocationProbe /></MemoryRouter><NotificationContainer /></NotificationProvider></AuthContext.Provider>)
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    })
  }

  async function deleteTrigger(sourceId = source.id): Promise<HTMLButtonElement> {
    const menu = container.querySelector(`[data-source-menu-trigger="${sourceId}"]`) as HTMLButtonElement
    await act(async () => menu.click())
    return Array.from(container.querySelectorAll(`[data-source-card="${sourceId}"] [role="menu"] button`))
      .find(item => item.textContent?.includes('Delete Source')) as HTMLButtonElement
  }

  async function archiveTrigger(sourceId = source.id): Promise<HTMLButtonElement> {
    const menu = container.querySelector(`[data-source-menu-trigger="${sourceId}"]`) as HTMLButtonElement
    await act(async () => menu.click())
    return Array.from(container.querySelectorAll(`[data-source-card="${sourceId}"] [role="menu"] button`))
      .find(item => item.textContent?.includes('Archive Source')) as HTMLButtonElement
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

  it('archives explicitly while preserving the Source identity', async () => {
    await render()
    const trigger = await archiveTrigger()
    await act(async () => { trigger.click(); await Promise.resolve(); await Promise.resolve() })
    const dialog = container.querySelector('[role="dialog"]') as HTMLElement
    const confirmation = dialog.querySelector('input[name="source-delete-confirmation"]') as HTMLInputElement
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(confirmation, source.name)
      confirmation.dispatchEvent(new Event('input', { bubbles: true }))
    })
    const confirm = Array.from(dialog.querySelectorAll('button')).find(item => item.textContent?.includes('Archive Source')) as HTMLButtonElement
    await act(async () => { confirm.click(); await Promise.resolve(); await Promise.resolve() })
    expect(sourceWorkspaceApi.archiveSource).toHaveBeenCalledWith(source, source.name)
    expect(container.textContent).toContain('Archived')
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
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Delete Source Permanently')

    await act(async () => {
      resolveFirst({ sourceId: source.id, sourceName: source.name, sourceVersion: source.version, sourceStatus: 'active', action: 'archive', blockers: {}, protectedHistory: { mappingRevisions: 1 } })
      await Promise.resolve()
    })
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Other prices')
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Delete Source Permanently')
    expect(container.querySelector('[role="dialog"]')?.textContent).not.toContain('Archive Source')
  })

  it('does not expose the destructive control to an unauthorized viewer', async () => {
    await render(viewer)
    expect(container.textContent).not.toContain('Delete Source')
  })

  it('does not expose Source creation to a read-only viewer', async () => {
    await render(viewer)
    expect(Array.from(container.querySelectorAll('button')).some(item => item.textContent?.trim() === 'Add source')).toBe(false)
  })

  it('keeps admin-only external connector setup hidden from an operator', async () => {
    await render(operator)
    const add = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Add source') as HTMLButtonElement
    await act(async () => add.click())

    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Create Sheet')
    expect(container.querySelector('[role="dialog"]')?.textContent).not.toContain('Manage external Sources')
  })

  it('reports Sheet creation failure without navigating', async () => {
    vi.spyOn(sourceWorkspaceApi, 'createSheet').mockRejectedValueOnce(new Error('create failed'))
    await render(admin)
    const add = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Add source') as HTMLButtonElement
    await act(async () => add.click())
    const create = Array.from(container.querySelectorAll('[role="dialog"] button')).find(item => item.textContent?.includes('Create Sheet')) as HTMLButtonElement
    await act(async () => { create.click(); await Promise.resolve(); await Promise.resolve() })

    expect(container.textContent).toContain('Sheet could not be created')
    expect(container.textContent).toContain('Check Sources before trying again')
  })

  it('creates a new Sheet named FlowSheet', async () => {
    const created = { id: 'sheet-new', sourceId: 'source-new', name: 'FlowSheet', version: 1, revisionId: null, columns: [], rows: [], total: 0, page: 1, pageSize: 200 }
    vi.spyOn(sourceWorkspaceApi, 'createSheet').mockResolvedValueOnce(created)
    await render(admin)
    const add = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Add source') as HTMLButtonElement
    await act(async () => add.click())
    const create = Array.from(container.querySelectorAll('[role="dialog"] button')).find(item => item.textContent?.includes('Create Sheet')) as HTMLButtonElement
    await act(async () => { create.click(); await Promise.resolve(); await Promise.resolve() })

    expect(sourceWorkspaceApi.createSheet).toHaveBeenCalledWith('FlowSheet')
  })

  it('shows retry when both authoritative Source lists fail', async () => {
    vi.mocked(sourceWorkspaceApi.listSources).mockRejectedValueOnce(new Error('managed offline'))
    vi.mocked(commerce.getSources).mockRejectedValueOnce(new Error('commerce offline'))
    await render(admin)

    expect(container.querySelector('[role="alert"]')?.textContent).toContain('Sources could not be loaded')
    const retry = Array.from(container.querySelectorAll('button')).find(item => item.textContent === 'Retry') as HTMLButtonElement
    await act(async () => { retry.click(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })

    expect(container.querySelector('[data-source-card="source-1"]')).not.toBeNull()
  })

  it('groups managed Sources consistently and sorts display names inside each group', async () => {
    const activeZebra = { ...source, id: 'source-z', name: 'Zebra prices' }
    const activeAlpha = { ...source, id: 'source-a', name: 'Alpha prices' }
    const disabledBeta = { ...source, id: 'source-b', name: 'Beta paused', status: 'disabled', sheetId: null }
    const archivedGamma = { ...source, id: 'source-c', name: 'Gamma history', status: 'archived', archivedAt: '2026-08-13T08:30:00Z' }
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({
      items: [archivedGamma, disabledBeta, activeZebra, activeAlpha],
    })

    await render()

    expect(Array.from(container.querySelectorAll('[data-resource-id]')).map(item => item.getAttribute('data-resource-id')))
      .toEqual(['source-a', 'source-z', 'source-b', 'source-c'])
    const sections = Array.from(container.querySelectorAll('[data-resource-section]')).map(item => item.getAttribute('data-resource-section'))
    expect([...new Set(sections)]).toEqual(['connected', 'disabled', 'archived'])
    expect(container.querySelector('[data-resource-id="source-a"]')?.textContent).toContain('Connected')
    expect(container.querySelector('[data-resource-id="source-b"]')?.textContent).toContain('Disabled')
    const archivedCard = container.querySelector('[data-source-card="source-c"]') as HTMLElement
    expect(archivedCard.getAttribute('data-resource-state')).toBe('archived')
    expect(archivedCard.textContent).toContain('Archived')
    expect(archivedCard.textContent).toContain('View Data Sheet')
    expect(archivedCard.textContent).not.toContain('Edit Source')
    expect(archivedCard.querySelector('[data-source-menu-trigger]')).not.toBeNull()
    expect(container.querySelector('.fh-kpi-card-value')?.textContent).toBe('2')
    expect(sections).not.toContain('comingSoon')
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
    expect(container.querySelector('[data-source-card="source-1"]')?.textContent).toContain('Configured')
    expect(container.querySelector('[data-source-card="source-1"] [data-source-icon]')?.getAttribute('data-source-icon')?.toLowerCase()).toContain('nextcloud.webp')
    const comingSoonCard = container.querySelector('[data-source-card="integration:gsheets:price-list"]')
    expect(comingSoonCard?.textContent).toContain('Coming Soon')
    expect(comingSoonCard?.querySelectorAll('button')).toHaveLength(0)
    expect(container.querySelector('.fh-kpi-card-value')?.textContent).toBe('1')
    const sections = Array.from(container.querySelectorAll('[data-resource-section]')).map(item => item.getAttribute('data-resource-section'))
    expect([...new Set(sections)]).toEqual(['connected', 'comingSoon'])
    expect(container.querySelector('[data-testid="source-card-groups"] .fh-sources-grid')).not.toBeNull()
  })

  it('shows persisted Source setup states as Add now, connected incomplete, and configured', async () => {
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [
        commerceSource('nextcloud:empty', 'Empty Source', {
          configured: false,
          connectionConfigured: false,
          configurationState: 'not_configured',
        }),
        commerceSource('nextcloud:partial', 'Partial Source', {
          configured: false,
          connectionConfigured: true,
          configurationState: 'setup_required',
        }),
        commerceSource('nextcloud:ready', 'Ready Source', {
          configured: true,
          connectionConfigured: true,
          configurationState: 'configured',
        }),
        commerceSource('nextcloud:ready-warning', 'Ready Source with warning', {
          configured: true,
          connectionConfigured: true,
          configurationState: 'configured',
          healthStatus: 'unhealthy',
        }),
      ],
    })

    await render()

    const empty = container.querySelector('[data-source-card="integration:nextcloud:empty"]') as HTMLElement
    const partial = container.querySelector('[data-source-card="integration:nextcloud:partial"]') as HTMLElement
    const ready = container.querySelector('[data-source-card="integration:nextcloud:ready"]') as HTMLElement
    const readyWarning = container.querySelector('[data-source-card="integration:nextcloud:ready-warning"]') as HTMLElement
    expect(empty.querySelector('.fh-badge-warning')?.textContent).toBe('Add now')
    expect(partial.querySelector('.fh-badge-info')?.textContent).toBe('Connected • Setup required')
    expect(ready.querySelector('.fh-badge-success')?.textContent).toBe('Configured')
    expect(readyWarning.querySelector('.fh-badge-warning')?.textContent).toBe('Needs Attention')
  })

  it('does not present pending or blocked identity validation as a configured Source', async () => {
    const pending: SourceProfile = { ...source, id: 'source-pending', name: 'Pending identity', mappingReadiness: 'identity_validation_pending' }
    const blocked: SourceProfile = { ...source, id: 'source-blocked', name: 'Blocked identity', mappingReadiness: 'identity_validation_blocked' }
    const omitted: SourceProfile = { ...source, id: 'source-omitted', name: 'Readiness omitted', mappingReadiness: undefined }
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [pending, blocked, omitted] })

    await render()

    const pendingCard = container.querySelector('[data-source-card="source-pending"]') as HTMLElement
    const blockedCard = container.querySelector('[data-source-card="source-blocked"]') as HTMLElement
    const omittedCard = container.querySelector('[data-source-card="source-omitted"]') as HTMLElement
    expect(pendingCard.getAttribute('data-resource-state')).toBe('setupRequired')
    expect(blockedCard.getAttribute('data-resource-state')).toBe('setupRequired')
    expect(omittedCard.getAttribute('data-resource-state')).toBe('setupRequired')
    expect(pendingCard.textContent).toContain('Identity validation pending')
    expect(blockedCard.textContent).toContain('Identity validation blocked')
    expect(omittedCard.textContent).toContain('Identity validation pending')
    expect(pendingCard.textContent).not.toContain('Configured')
    expect(blockedCard.textContent).not.toContain('Configured')
  })

  it('groups actual Source failures under Needs Attention and excludes disabled historical failures from that KPI', async () => {
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [
        commerceSource('nextcloud:attention', 'Connection needs attention', {
          configured: true,
          connectionConfigured: true,
          healthStatus: 'unhealthy',
        }),
        commerceSource('nextcloud:disabled', 'Disabled historical failure', {
          configured: true,
          connectionConfigured: true,
          enabled: false,
          healthStatus: 'unhealthy',
        }),
      ],
    })

    await render()

    const attention = container.querySelector('[data-source-card="integration:nextcloud:attention"]') as HTMLElement
    const disabled = container.querySelector('[data-source-card="integration:nextcloud:disabled"]') as HTMLElement
    expect(attention.getAttribute('data-resource-state')).toBe('needsAttention')
    expect(disabled.getAttribute('data-resource-state')).toBe('disabled')
    expect(container.querySelector('[data-resource-section="needsAttention"]')).not.toBeNull()
    expect(container.querySelector('[data-resource-section="connected"]')).toBeNull()

    const attentionKpi = Array.from(container.querySelectorAll('.fh-kpi-card'))
      .find(card => card.textContent?.includes('Needs Attention'))
    expect(attentionKpi?.textContent).toContain('1')

    const filter = container.querySelector('select') as HTMLSelectElement
    await act(async () => {
      filter.value = 'attention'
      filter.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(container.querySelector('[data-source-card="integration:nextcloud:attention"]')).not.toBeNull()
    expect(container.querySelector('[data-source-card="integration:nextcloud:disabled"]')).toBeNull()
  })

  it('keeps a linked source in Disabled rather than Setup required when its saved connector is disabled', async () => {
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
      items: [commerceSource('nextcloud:primary', 'Nextcloud', { healthy: true, enabled: false })],
    })

    await render()

    const card = container.querySelector('[data-source-card="source-1"]') as HTMLElement
    expect(card.getAttribute('data-resource-state')).toBe('disabled')
    expect(card.textContent).toContain('Disabled')
    expect(card.textContent).not.toContain('Setup Source')
    expect(Array.from(container.querySelectorAll('[data-resource-section]')).map(item => item.getAttribute('data-resource-section')))
      .toContain('disabled')
  })

  it('does not show an unfinished external Source as connected by default', async () => {
    const unfinishedNextcloud: SourceProfile = {
      ...source,
      id: 'nextcloud-draft',
      name: 'Nextcloud',
      sourceKind: 'external',
      externalSourceId: 'nextcloud:primary',
      mappingVersion: 0,
      sheetId: null,
    }
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [unfinishedNextcloud] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [
        commerceSource('nextcloud:primary', 'Nextcloud', { healthy: true }),
        commerceSource('gsheets:price-list', 'Google Sheets', { placeholder: true }),
      ],
    })

    await render()

    const unfinishedCard = container.querySelector('[data-source-card="nextcloud-draft"]')
    expect(unfinishedCard?.textContent).toContain('Setup required')
    expect(unfinishedCard?.textContent).toContain('Setup Source')
    expect(container.querySelector('[data-source-card="integration:nextcloud:primary"]')).toBeNull()
    expect(container.querySelector('[data-source-card="integration:gsheets:price-list"]')?.textContent).toContain('Coming Soon')
    expect(container.querySelector('.fh-kpi-card-value')?.textContent).toBe('0')
  })

  it('routes Setup Source to connection settings when an external Source credential set is incomplete', async () => {
    const incompleteNextcloud: SourceProfile = {
      ...source,
      id: 'nextcloud-draft',
      name: 'Nextcloud',
      sourceKind: 'external',
      externalSourceId: 'nextcloud:primary',
      mappingVersion: 0,
      sheetId: null,
    }
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [incompleteNextcloud] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [commerceSource('nextcloud:primary', 'Nextcloud', { configured: false })],
    })

    await render()
    const setup = Array.from(container.querySelectorAll('[data-source-card="nextcloud-draft"] button'))
      .find(item => item.textContent?.trim() === 'Setup Source') as HTMLButtonElement
    await act(async () => setup.click())

    expect(container.querySelector('[data-testid="location-probe"]')?.textContent)
      .toBe('/commerce?tab=sources&resource=nextcloud%3Aprimary')
  })

  it('routes a connected but incomplete Source back through setup instead of Data Sheet', async () => {
    const incompleteNextcloud: SourceProfile = {
      ...source,
      id: 'nextcloud-draft',
      name: 'Nextcloud',
      sourceKind: 'external',
      externalSourceId: 'nextcloud:primary',
      mappingVersion: 0,
      sheetId: null,
    }
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [incompleteNextcloud] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [commerceSource('nextcloud:primary', 'Nextcloud', {
        configured: false,
        connectionConfigured: true,
        configurationState: 'setup_required',
      })],
    })

    await render()
    const setup = Array.from(container.querySelectorAll('[data-source-card="nextcloud-draft"] button'))
      .find(item => item.textContent?.trim() === 'Setup Source') as HTMLButtonElement
    await act(async () => setup.click())

    expect(container.querySelector('[data-testid="location-probe"]')?.textContent)
      .toBe('/commerce?tab=sources&resource=nextcloud%3Aprimary')
  })

  it('exposes the implemented Excel / CSV import once, outside Coming Soon, and routes setup to the existing import wizard', async () => {
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [commerceSource('csv:import', 'Excel / CSV', { configured: false })],
    })

    await render()

    const card = container.querySelector('[data-source-card="integration:csv:import"]') as HTMLElement
    expect(card.textContent).toContain('Excel / CSV')
    expect(card.textContent).not.toContain('Coming Soon')
    expect(container.querySelector('[data-resource-section="comingSoon"]')).toBeNull()
    const setup = Array.from(card.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Setup Source') as HTMLButtonElement
    await act(async () => setup.click())
    expect(container.querySelector('[data-testid="location-probe"]')?.textContent).toBe('/sources/import')
  })

  it('uses the same available Excel / CSV setup path from Add source without listing unavailable providers as available', async () => {
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [
        commerceSource('csv:import', 'Excel / CSV', { configured: false }),
        commerceSource('gsheets:price-list', 'Google Sheets', { placeholder: true }),
        commerceSource('erp:api-import', 'ERP / API Import', { placeholder: true }),
      ],
    })

    await render()

    expect(container.querySelectorAll('[data-source-card="integration:csv:import"]')).toHaveLength(1)
    expect(container.querySelector('[data-source-card="integration:gsheets:price-list"]')?.textContent).toContain('Coming Soon')
    expect(container.querySelector('[data-source-card="integration:erp:api-import"]')?.textContent).toContain('Coming Soon')
    expect(container.querySelector('[data-resource-section="setupRequired"]')?.textContent).toContain('Available Sources')
    const add = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Add source') as HTMLButtonElement
    await act(async () => add.click())
    const importAction = Array.from(container.querySelectorAll('[role="dialog"] button')).find(item => item.textContent?.includes('Import your spreadsheet')) as HTMLButtonElement
    expect(importAction).toBeTruthy()
    expect(container.querySelector('[role="dialog"]')?.textContent).not.toContain('Google Sheets')
    expect(container.querySelector('[role="dialog"]')?.textContent).not.toContain('ERP / API Import')
    await act(async () => importAction.click())
    expect(container.querySelector('[data-testid="location-probe"]')?.textContent).toBe('/sources/import')
  })

  it('shows an actionable onboarding state when only future integrations are available', async () => {
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [commerceSource('gsheets:price-list', 'Google Sheets', { placeholder: true })],
    })

    await render()

    const onboarding = container.querySelector('[data-testid="sources-onboarding-empty-state"]')
    expect(onboarding?.textContent).toContain('No managed Source yet')
    expect(onboarding?.textContent).toContain('Recommended for easier column setup')
    expect(onboarding?.querySelector('button')?.textContent).toContain('Add source')
    expect(container.querySelector('[data-source-card="integration:gsheets:price-list"]')?.textContent).toContain('Coming Soon')
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

  it('uses provider-specific copy for the ERP and API Import integration', async () => {
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [commerceSource('erp:api-import', 'ERP / API Import', { placeholder: true })],
    })

    await render()

    const card = container.querySelector('[data-source-card="integration:erp:api-import"]') as HTMLElement
    expect(card.title).toContain('Structured business data from an ERP system or external API.')
    expect(card.textContent).not.toContain('External spreadsheet Source')
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

    const filterSelect = container.querySelector('.fh-chip-select select') as HTMLSelectElement
    const selectValueSetter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')?.set
    await act(async () => {
      selectValueSetter?.call(filterSelect, 'disabled')
      filterSelect.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(Array.from(container.querySelectorAll('[data-source-card]')).map(item => item.getAttribute('data-source-card')))
      .toEqual(['source-b'])

    await act(async () => {
      selectValueSetter?.call(filterSelect, 'all')
      filterSelect.dispatchEvent(new Event('change', { bubbles: true }))
    })
    const search = container.querySelector('input[type="search"]') as HTMLInputElement
    const valueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    await act(async () => {
      valueSetter?.call(search, 'zebra')
      search.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(Array.from(container.querySelectorAll('[data-source-card]')).map(item => item.getAttribute('data-source-card')))
      .toEqual(['source-z'])
  })

  it('distinguishes a filtered no-results state from the onboarding empty state', async () => {
    await render()

    const search = container.querySelector('input[type="search"]') as HTMLInputElement
    const valueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    await act(async () => {
      valueSetter?.call(search, 'does-not-exist')
      search.dispatchEvent(new Event('input', { bubbles: true }))
    })

    const emptyState = container.querySelector('[data-testid="sources-filter-empty-state"]') as HTMLElement
    expect(emptyState.textContent).toContain('No sources found')
    expect(emptyState.textContent).not.toContain('No managed Source yet')
    const clear = Array.from(emptyState.querySelectorAll('button')).find(item => item.textContent?.includes('Clear filters')) as HTMLButtonElement
    await act(async () => clear.click())
    expect(container.querySelector('[data-source-card="source-1"]')).not.toBeNull()
  })

  it('exposes isolated development-only connected and partial-failure QA states', async () => {
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce({
      ...emptyCommerceSources,
      items: [commerceSource('nextcloud:primary', 'Nextcloud', { configured: false })],
    })
    await render(admin, '/sources?qa=connected')
    expect(container.querySelector('[data-source-card="qa-connected-source"]')?.textContent).toContain('Connected')
    expect(vi.mocked(sourceWorkspaceApi.source).mock.calls.some(([sourceId]) => sourceId === 'qa-connected-source')).toBe(false)

    act(() => root.unmount())
    root = createRoot(container)
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [source] })
    vi.mocked(commerce.getSources).mockResolvedValueOnce(emptyCommerceSources)
    await render(admin, '/sources?qa=partial')
    expect(container.textContent).toContain('Some Source information is unavailable')
  })

  it('opens a focused Add Source panel with the three supported entry paths', async () => {
    await render()
    const add = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.trim() === 'Add source') as HTMLButtonElement
    await act(async () => add.click())

    const dialog = container.querySelector('[role="dialog"]') as HTMLElement
    expect(dialog.textContent).toContain('FlowHub Sheet')
    expect(dialog.textContent).toContain('Import your spreadsheet')
    expect(dialog.textContent).toContain('Keep an external Source linked')
  })
})
