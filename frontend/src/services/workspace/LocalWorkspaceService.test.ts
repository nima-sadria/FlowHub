// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest'
import { LocalWorkspaceService } from './LocalWorkspaceService'

beforeEach(() => {
  sessionStorage.clear()
})

describe('LocalWorkspaceService', () => {
  it('initial state is idle when sessionStorage is empty', async () => {
    const svc = new LocalWorkspaceService()
    const state = await svc.getState()
    expect(state).toBe('idle')
  })

  it('startPreview returns a preview with 4 changes', async () => {
    const svc = new LocalWorkspaceService()
    const preview = await svc.startPreview('src-001')
    expect(preview.totalChanges).toBe(4)
    expect(preview.changes.length).toBe(4)
    expect(preview.state).toBe('preview_ready')
  })

  it('getState returns preview_ready after startPreview', async () => {
    const svc = new LocalWorkspaceService()
    await svc.startPreview('src-001')
    const state = await svc.getState()
    expect(state).toBe('preview_ready')
  })

  it('cancelPreview returns state to idle', async () => {
    const svc = new LocalWorkspaceService()
    const preview = await svc.startPreview('src-001')
    await svc.cancelPreview(preview.id)
    const state = await svc.getState()
    expect(state).toBe('idle')
  })

  it('cancelPreview removes sessionStorage entry', async () => {
    const svc = new LocalWorkspaceService()
    const preview = await svc.startPreview('src-001')
    expect(sessionStorage.getItem('wp_local_workspace')).not.toBeNull()
    await svc.cancelPreview(preview.id)
    expect(sessionStorage.getItem('wp_local_workspace')).toBeNull()
  })

  it('preview changes include WHP-001, UCH-002, MON-004, CMK-009', async () => {
    const svc = new LocalWorkspaceService()
    const preview = await svc.startPreview('src-001')
    const skus = preview.changes.map(c => c.sku)
    expect(skus).toContain('WHP-001')
    expect(skus).toContain('UCH-002')
    expect(skus).toContain('MON-004')
    expect(skus).toContain('CMK-009')
  })
})
