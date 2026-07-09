// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { RateLimitSettings } from '../services/types'
import RateLimits from './RateLimits'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
})

const rateLimits: RateLimitSettings = {
  read_requests_per_minute: 60,
  write_requests_per_minute: 30,
  read_delay_ms: 1000,
  write_delay_ms: 2000,
  inherits_to_all_connectors: true,
  per_connector_override_available: false,
  scheduler_started: false,
  automatic_sync: false,
  runtime_write_blocked: true,
}

function services(): Services {
  return {
    settings: {
      getSettings: async () => ({
        woocommerceUrl: '',
        nextcloudUrl: '',
        syncIntervalMinutes: 60,
        timezone: 'UTC',
        currency: 'EUR',
        environment: 'production',
      }),
      updateSettings: async patch => ({
        woocommerceUrl: '',
        nextcloudUrl: '',
        syncIntervalMinutes: patch.syncIntervalMinutes ?? 60,
        timezone: patch.timezone ?? 'UTC',
        currency: patch.currency ?? 'EUR',
        environment: 'production',
      }),
      getRateLimits: async () => rateLimits,
      updateRateLimits: async patch => ({
        ...rateLimits,
        ...patch,
        read_delay_ms: 60000 / patch.read_requests_per_minute,
        write_delay_ms: 60000 / patch.write_requests_per_minute,
      }),
    },
    health: {} as Services['health'],
    products: {} as Services['products'],
    sources: {} as Services['sources'],
    workspace: {} as Services['workspace'],
    activity: {} as Services['activity'],
    commerce: {} as Services['commerce'],
    writePipeline: {} as Services['writePipeline'],
  }
}

async function renderPage() {
  await act(async () => {
    root.render(
      <NotificationProvider>
        <ServiceProvider services={services()}>
          <RateLimits />
        </ServiceProvider>
      </NotificationProvider>
    )
  })
  await act(async () => {})
  return container
}

describe('RateLimits', () => {
  it('renders global RPM settings and estimated delays', async () => {
    const c = await renderPage()

    expect(c.textContent).toContain('Global API Rate Limits')
    expect(c.textContent).toContain('Read Requests / Minute')
    expect(c.textContent).toContain('Write Requests / Minute')
    expect(c.textContent).toContain('1.00 seconds')
    expect(c.textContent).toContain('2.00 seconds')
    expect(c.textContent).toContain('Scheduler')
    expect(c.textContent).toContain('Automatic sync')
  })

  it('validates RPM range', async () => {
    const c = await renderPage()
    const input = c.querySelector('input') as HTMLInputElement
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set

    await act(async () => {
      setter?.call(input, '0')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })

    expect(c.textContent).toContain('Read Requests / Minute must be between 1 and 1000.')
  })
})
