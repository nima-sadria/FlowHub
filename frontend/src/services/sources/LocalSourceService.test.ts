// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest'
import { LocalSourceService } from './LocalSourceService'

beforeEach(() => {
  sessionStorage.clear()
})

describe('LocalSourceService', () => {
  it('returns default source list (1 source)', async () => {
    const svc = new LocalSourceService()
    const sources = await svc.getSources()
    expect(sources.length).toBe(1)
    expect(sources[0].name).toBe('Nextcloud Price List')
    expect(sources[0].status).toBe('active')
  })

  it('testConnection always succeeds', async () => {
    const svc = new LocalSourceService()
    const result = await svc.testConnection({
      name: 'Test',
      type: 'nextcloud_excel',
      url: 'https://cloud.example.com',
      username: 'user',
      password: 'pass',
      filePath: '/prices.xlsx',
    })
    expect(result.success).toBe(true)
    expect(result.discoveredProductCount).toBe(12)
  })

  it('createSource adds to list', async () => {
    const svc = new LocalSourceService()
    await svc.createSource({
      name: 'New Source',
      type: 'nextcloud_excel',
      url: 'https://cloud.example.com',
      username: 'user',
      password: 'pass',
      filePath: '/prices.xlsx',
    })
    const sources = await svc.getSources()
    expect(sources.length).toBe(2)
    expect(sources[1].name).toBe('New Source')
  })

  it('createSource persists to sessionStorage', async () => {
    const svc = new LocalSourceService()
    await svc.createSource({
      name: 'Persisted',
      type: 'nextcloud_excel',
      url: 'https://cloud.example.com',
      username: 'user',
      password: 'pass',
      filePath: '/prices.xlsx',
    })
    expect(sessionStorage.getItem('wp_local_sources')).not.toBeNull()
  })
})
