// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { DataQualitySummary } from '../features/sourceWorkspace/types'
import DataQuality from './DataQuality'

const base: DataQualitySummary = { state: 'never_checked', totalIssues: 0, blockingIssues: 0, warnings: 0, affectedProducts: 0, affectedChannels: 0, affectedSources: 0, resolvedSinceLastRead: 0, trendSinceLastRead: null, productsChecked: 0, sourcesChecked: 0, checkedAt: null, scanId: null, errorCode: null, categories: [] }

describe('DataQuality summary states', () => {
  let container: HTMLDivElement
  let root: ReturnType<typeof createRoot>
  beforeEach(() => {
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container)
    vi.spyOn(sourceWorkspaceApi, 'listSources').mockResolvedValue({ items: [] })
    vi.spyOn(sourceWorkspaceApi, 'channels').mockResolvedValue({ items: [] })
    vi.spyOn(sourceWorkspaceApi, 'scanDataQuality').mockResolvedValue({ summary: { ...base, state: 'healthy' } })
  })
  afterEach(() => { act(() => root.unmount()); container.remove(); vi.restoreAllMocks() })
  async function render() { await act(async () => { root.render(<MemoryRouter><DataQuality /></MemoryRouter>); await Promise.resolve(); await Promise.resolve() }) }

  it('distinguishes never checked from a healthy scan', async () => {
    vi.spyOn(sourceWorkspaceApi, 'dataQuality').mockResolvedValue({ items: [], counts: {}, total: 0, summary: base })
    await render()
    expect(container.textContent).toContain('No check has been run yet')
    expect(container.textContent).not.toContain('No data problems found')
  })

  it('shows business summary before collapsed filters and keeps default filters unrestrictive', async () => {
    const issue = { id: 'i-1', category: 'invalid_value', severity: 'blocked', code: 'INVALID_NUMERIC_VALUE', summary: 'Invalid', recommendedAction: 'Correct', technicalDetails: { field: 'price' } }
    vi.spyOn(sourceWorkspaceApi, 'dataQuality').mockResolvedValue({ items: [issue], counts: { blocked: 1 }, total: 1, summary: { ...base, state: 'issues_found', totalIssues: 1, blockingIssues: 1, affectedProducts: 1, affectedSources: 1, categories: [{ category: 'invalid_value', count: 1 }] } })
    await render()
    const text = container.textContent ?? ''
    expect(text.indexOf('Data Quality Summary')).toBeLessThan(text.indexOf('Filters and search'))
    expect(text).toContain('Invalid value')
    expect(text).toContain('Blocked')
    expect(text).toContain('No previous read to compare')
    const request = vi.mocked(sourceWorkspaceApi.dataQuality).mock.calls[0][0]
    expect(request.has('sourceId')).toBe(false)
    expect(request.has('severity')).toBe(false)

    const blockingCard = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.includes('Blocking issues'))
    expect(blockingCard).toBeTruthy()
    await act(async () => { blockingCard!.dispatchEvent(new MouseEvent('click', { bubbles: true })); await Promise.resolve(); await Promise.resolve() })
    const calls = vi.mocked(sourceWorkspaceApi.dataQuality).mock.calls
    const filteredRequest = calls[calls.length - 1]?.[0]
    expect(filteredRequest?.get('severity')).toBe('blocked')
    expect(blockingCard?.getAttribute('aria-pressed')).toBe('true')

    const productsCard = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.includes('Affected products'))
    await act(async () => { productsCard!.dispatchEvent(new MouseEvent('click', { bubbles: true })); await Promise.resolve() })
    const filters = Array.from(container.querySelectorAll('details')).find(details => details.textContent?.includes('Filters and search'))
    expect(filters?.open).toBe(true)
    expect(document.activeElement?.getAttribute('placeholder')).toBe('Source Product name')
  })

  it('shows permission denial instead of a false healthy result', async () => {
    vi.spyOn(sourceWorkspaceApi, 'dataQuality').mockRejectedValue(new ApiError(403, 'forbidden', 'FORBIDDEN'))
    await render()
    expect(container.textContent).toContain('You cannot view this data check')
    expect(container.textContent).not.toContain('No data problems found')
  })
})
