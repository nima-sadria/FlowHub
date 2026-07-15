// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceLifecycleImpact, SourceProfile } from '../features/sourceWorkspace/types'
import { NotificationProvider } from '../notifications/NotificationProvider'
import SourceCenter from './SourceCenter'

const source: SourceProfile = { id: 'source-1', name: 'Synthetic prices', sourceKind: 'flowhub_sheet', externalSourceId: null, worksheetMode: 'selected', worksheetName: 'Sheet1', dataStartRow: 2, status: 'active', version: 3, mappingVersion: 2, sheetId: 'sheet-1' }
const admin: AuthContextValue = { user: { username: 'admin', role: 'admin', is_admin: true, is_super_admin: false, permissions: {} }, status: 'authenticated', refreshUser: async () => {}, clearAuth: () => {}, authFetch: fetch }
const viewer: AuthContextValue = { ...admin, user: { username: 'viewer', role: 'user', is_admin: false, is_super_admin: false, permissions: { can_access_site: true, 'workspace.read': true } } }

describe('SourceCenter safe lifecycle', () => {
  let container: HTMLDivElement
  let root: ReturnType<typeof createRoot>
  beforeEach(() => {
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container)
    vi.spyOn(sourceWorkspaceApi, 'listSources').mockResolvedValue({ items: [source] })
    vi.spyOn(sourceWorkspaceApi, 'sourceLifecycle').mockResolvedValue({ sourceId: source.id, sourceName: source.name, sourceVersion: source.version, sourceStatus: 'active', action: 'archive', blockers: {}, protectedHistory: { mappingRevisions: 1 } })
    vi.spyOn(sourceWorkspaceApi, 'deleteSource').mockResolvedValue({ sourceId: source.id, sourceName: source.name, outcome: 'archived', source: { ...source, status: 'disabled', version: 4 }, impact: { sourceId: source.id, sourceName: source.name, sourceVersion: source.version, sourceStatus: 'active', action: 'archive', blockers: {}, protectedHistory: { mappingRevisions: 1 } } })
  })
  afterEach(() => { act(() => root.unmount()); container.remove(); vi.restoreAllMocks() })

  async function render(auth = admin) {
    await act(async () => { root.render(<AuthContext.Provider value={auth}><NotificationProvider><MemoryRouter><SourceCenter /></MemoryRouter></NotificationProvider></AuthContext.Provider>); await Promise.resolve(); await Promise.resolve() })
  }

  it('requires explicit named confirmation and cancellation sends no request', async () => {
    await render()
    const trigger = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.includes('Delete Source')) as HTMLButtonElement
    await act(async () => { trigger.click(); await Promise.resolve(); await Promise.resolve() })
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain('Synthetic prices')
    const cancel = Array.from(container.querySelectorAll('[role="dialog"] button')).find(item => item.textContent?.includes('Cancel')) as HTMLButtonElement
    await act(async () => cancel.click())
    expect(sourceWorkspaceApi.deleteSource).not.toHaveBeenCalled()
  })

  it('moves focus into the dialog, closes with Escape, and restores trigger focus', async () => {
    await render()
    const trigger = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.includes('Delete Source')) as HTMLButtonElement
    trigger.focus()
    await act(async () => { trigger.click(); await Promise.resolve(); await Promise.resolve() })
    const dialog = container.querySelector('[role="dialog"]') as HTMLElement
    const cancel = Array.from(dialog.querySelectorAll('button')).find(item => item.textContent?.includes('Cancel')) as HTMLButtonElement
    expect(document.activeElement).toBe(cancel)

    await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))

    expect(container.querySelector('[role="dialog"]')).toBeNull()
    expect(document.activeElement).toBe(trigger)
    expect(sourceWorkspaceApi.deleteSource).not.toHaveBeenCalled()
  })

  it('shows archive result while preserving the Source identity', async () => {
    await render()
    const trigger = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.includes('Delete Source')) as HTMLButtonElement
    await act(async () => { trigger.click(); await Promise.resolve(); await Promise.resolve() })
    const confirm = Array.from(container.querySelectorAll('[role="dialog"] button')).find(item => item.textContent?.includes('Archive Source')) as HTMLButtonElement
    await act(async () => { confirm.click(); await Promise.resolve(); await Promise.resolve() })
    expect(sourceWorkspaceApi.deleteSource).toHaveBeenCalledWith(source)
    expect(container.textContent).toContain('Archived')
    expect(container.textContent).toContain('Synthetic prices')
  })

  it('shows the active Workspace blocker and cannot confirm removal', async () => {
    vi.mocked(sourceWorkspaceApi.sourceLifecycle).mockResolvedValueOnce({ sourceId: source.id, sourceName: source.name, sourceVersion: source.version, sourceStatus: 'active', action: 'blocked', blockers: { activeWorkspaces: 1 }, protectedHistory: { workspaceSnapshots: 1 } })
    await render()
    const trigger = Array.from(container.querySelectorAll('button')).find(item => item.textContent?.includes('Delete Source')) as HTMLButtonElement
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

    const triggers = Array.from(container.querySelectorAll('button')).filter(item => item.textContent?.includes('Delete Source')) as HTMLButtonElement[]
    await act(async () => { triggers[0].click(); await Promise.resolve() })
    const cancel = Array.from(container.querySelectorAll('[role="dialog"] button')).find(item => item.textContent?.includes('Cancel')) as HTMLButtonElement
    await act(async () => { cancel.click(); await Promise.resolve() })
    expect(document.activeElement).toBe(triggers[0])

    await act(async () => { triggers[1].click(); await Promise.resolve(); await Promise.resolve() })
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
})
