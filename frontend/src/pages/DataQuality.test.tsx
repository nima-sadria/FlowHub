// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { DataQualitySummary, SourceChannel, SourceProfile } from '../features/sourceWorkspace/types'
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
    const issue = { id: 'i-1', sourceId: 'source-1', channelId: 'woocommerce:primary', category: 'invalid_value', severity: 'blocked', code: 'INVALID_NUMERIC_VALUE', summary: 'Invalid', recommendedAction: 'Correct', technicalDetails: { field: 'price' } }
    vi.spyOn(sourceWorkspaceApi, 'dataQuality').mockResolvedValue({ items: [issue], counts: { blocked: 1 }, total: 1, summary: { ...base, state: 'issues_found', totalIssues: 1, blockingIssues: 1, affectedProducts: 1, affectedSources: 1, productsChecked: 10, categories: [{ category: 'invalid_value', count: 1 }] } })
    await render()
    const text = container.textContent ?? ''
    expect(text.indexOf('Data Quality Summary')).toBeLessThan(text.indexOf('Filters and search'))
    expect(text).toContain('Invalid value')
    expect(text).toContain('Blocked')
    expect(text).toContain('Recommended actions')
    expect(text).toContain('Ready9')
    expect(text).toContain('No previous read to compare')
    expect(container.querySelector('a[href^="/products?dataQualityIssue=INVALID_NUMERIC_VALUE"]')).not.toBeNull()
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

  it('routes Source setup issues to the affected Source instead of a technical dead end', async () => {
    vi.spyOn(sourceWorkspaceApi, 'dataQuality').mockResolvedValue({
      items: [{
        id: 'mapping-issue',
        sourceId: 'source/with space',
        worksheet: 'Retail',
        category: 'mapping_not_configured',
        severity: 'blocked',
        code: 'SOURCE_MAPPING_REQUIRED',
        summary: 'Columns are missing',
        recommendedAction: 'Choose columns',
        technicalDetails: {},
      }],
      counts: { blocked: 1 },
      total: 1,
      summary: { ...base, state: 'issues_found', totalIssues: 1, blockingIssues: 1 },
    })

    await render()

    const links = Array.from(container.querySelectorAll<HTMLAnchorElement>('a'))
      .filter(link => link.textContent?.includes('Open'))
    expect(links.length).toBeGreaterThan(0)
    expect(links[0].getAttribute('href')).toContain('/sources/source%2Fwith%20space?')
    expect(links[0].getAttribute('href')).toContain('worksheet=Retail')
  })

  it('shows permission denial instead of a false healthy result', async () => {
    vi.spyOn(sourceWorkspaceApi, 'dataQuality').mockRejectedValue(new ApiError(403, 'forbidden', 'FORBIDDEN'))
    await render()
    expect(container.textContent).toContain('You cannot view this data check')
    expect(container.textContent).not.toContain('No data problems found')
  })

  it('keeps All filters explicit while grouping and ordering Source and Channel options', async () => {
    const source = (id: string, name: string, status = 'active'): SourceProfile => ({
      id, name, status, sourceKind: 'flowhub_sheet', externalSourceId: null,
      worksheetMode: 'selected', worksheetName: 'Sheet1', dataStartRow: 2,
      version: 1, mappingVersion: 1, sheetId: null,
    })
    const channel = (
      channelId: string,
      name: string,
      enabled: boolean,
      implementationState: string = 'implemented',
    ): SourceChannel => ({
      channelId, name, enabled, implementationState, available: enabled,
      connectorType: channelId.split(':')[0], capabilityVersion: '1', capabilities: {},
    })
    vi.mocked(sourceWorkspaceApi.listSources).mockResolvedValueOnce({ items: [
      source('disabled-source', 'Beta archive', 'disabled'),
      source('z-source', 'Zebra prices'),
      source('a-source', 'Alpha prices'),
    ] })
    vi.mocked(sourceWorkspaceApi.channels).mockResolvedValueOnce({ items: [
      channel('future:main', 'Future Market', false, 'coming_soon'),
      channel('woo:main', 'WooCommerce', true),
      channel('snap:main', 'SnappShop', true),
      channel('disabled:main', 'Disabled Market', false),
    ] })
    vi.spyOn(sourceWorkspaceApi, 'dataQuality').mockResolvedValue({
      items: [{ id: 'i-1', category: 'invalid_value', severity: 'blocked', code: 'INVALID_NUMERIC_VALUE', summary: 'Invalid', recommendedAction: 'Correct', technicalDetails: {} }],
      counts: { blocked: 1 }, total: 1,
      summary: { ...base, state: 'issues_found', totalIssues: 1 },
    })

    await render()

    const selects = Array.from(container.querySelectorAll('select'))
    const sourceSelect = selects.find(select => select.querySelector('option[value="a-source"]')) as HTMLSelectElement
    const channelSelect = selects.find(select => select.querySelector('option[value="woo:main"]')) as HTMLSelectElement
    expect(sourceSelect.value).toBe('')
    expect(channelSelect.value).toBe('')
    expect(Array.from(sourceSelect.options).map(option => option.value)).toEqual(['', 'a-source', 'z-source', 'disabled-source'])
    expect(Array.from(channelSelect.options).map(option => option.value)).toEqual(['', 'snap:main', 'woo:main', 'disabled:main', 'future:main'])
    expect(Array.from(channelSelect.querySelectorAll('optgroup')).map(group => group.label)).toEqual(['Active', 'Disabled', 'Coming Soon'])
  })
})
