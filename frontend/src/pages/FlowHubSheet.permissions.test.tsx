// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { FlowHubSheetPage } from '../features/sourceWorkspace/types'
import { NotificationProvider } from '../notifications/NotificationProvider'
import FlowHubSheet from './FlowHubSheet'

const sheet: FlowHubSheetPage = {
  id: 'sheet-1',
  sourceId: 'source-1',
  name: 'Daily prices',
  version: 2,
  revisionId: 'revision-2',
  columns: [{ columnKey: 'price', name: 'Price', position: 1, dataType: 'number' }],
  rows: [{
    rowKey: 'row-1',
    position: 1,
    cells: { price: { raw: '100', value: '100', formula: null, error: null } },
  }],
  total: 1,
  page: 1,
  pageSize: 200,
}

function auth(permissions: Record<string, boolean>): AuthContextValue {
  return {
    user: { username: 'user', role: 'viewer', is_admin: false, is_super_admin: false, permissions },
    status: 'authenticated',
    refreshUser: async () => {},
    clearAuth: () => {},
    logout: async () => {},
    authFetch: fetch,
  }
}

describe('FlowHub Sheet permissions', () => {
  let container: HTMLDivElement
  let root: ReturnType<typeof createRoot>

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    vi.spyOn(sourceWorkspaceApi, 'getSheet').mockResolvedValue(sheet)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.restoreAllMocks()
  })

  async function renderPage(value: AuthContextValue) {
    await act(async () => {
      root.render(
        <AuthContext.Provider value={value}>
          <NotificationProvider>
            <MemoryRouter initialEntries={['/sheets/sheet-1']}>
              <Routes><Route path="/sheets/:sheetId" element={<FlowHubSheet />} /></Routes>
            </MemoryRouter>
          </NotificationProvider>
        </AuthContext.Provider>,
      )
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  it('keeps a read-only Sheet visible without exposing revision actions', async () => {
    await renderPage(auth({ 'workspace.read': true }))

    expect(container.textContent).toContain('You can view this Sheet')
    expect(container.textContent).not.toContain('Save Revision')
    expect(container.textContent).not.toContain('Add 20 rows')
    expect(Array.from(container.querySelectorAll('.fh-sheet-cell')).every(input => (input as HTMLInputElement).disabled)).toBe(true)
  })

  it('enables Sheet editing for a user with Draft save permission', async () => {
    await renderPage(auth({ 'workspace.read': true, 'draft.save': true }))

    expect(container.textContent).toContain('Save Revision')
    expect(container.textContent).toContain('Add 20 rows')
    expect((container.querySelector('.fh-sheet-cell') as HTMLInputElement).disabled).toBe(false)
  })
})
