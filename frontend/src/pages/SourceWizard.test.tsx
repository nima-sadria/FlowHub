// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { NotificationProvider } from '../notifications/NotificationProvider'
import NotificationContainer from '../notifications/NotificationContainer'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import SourceWizard from './SourceWizard'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

function services(): Services {
  return {
    sources: {
      getSources: async () => [],
      testConnection: async () => ({ success: true, message: 'Connection verified successfully.' }),
      createSource: async config => ({
        id: 'source-1',
        name: config.name,
        type: config.type,
        displayUrl: config.url,
        status: 'active',
        lastSynced: null,
        productCount: 0,
      }),
    },
    health: {} as Services['health'],
    products: {} as Services['products'],
    workspace: {} as Services['workspace'],
    settings: {} as Services['settings'],
    activity: {} as Services['activity'],
    commerce: {} as Services['commerce'],
    writePipeline: {} as Services['writePipeline'],
  }
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

function inputByLabel(labelText: string): HTMLInputElement {
  const label = Array.from(container.querySelectorAll('label'))
    .find(item => item.textContent?.toLowerCase().includes(labelText.toLowerCase()))
  const input = label?.parentElement?.querySelector('input')
  expect(input).toBeTruthy()
  return input as HTMLInputElement
}

async function clickButton(text: string) {
  const button = Array.from(container.querySelectorAll('button'))
    .find(item => item.textContent?.includes(text))
  expect(button).toBeTruthy()
  await act(async () => {
    button?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await Promise.resolve()
  })
  return button as HTMLButtonElement
}

describe('SourceWizard', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => { root.unmount() })
    container.remove()
    vi.restoreAllMocks()
  })

  it('keeps source wizard actions labeled and backed by centralized icons', async () => {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <ServiceProvider services={services()}>
            <NotificationProvider>
              <SourceWizard />
              <NotificationContainer />
            </NotificationProvider>
          </ServiceProvider>
        </MemoryRouter>,
      )
      await Promise.resolve()
    })

    await clickButton('Nextcloud Excel')

    expect(container.querySelector('button [data-icon="previous"]')).not.toBeNull()
    expect(container.querySelector('button [data-icon="testConnection"]')).not.toBeNull()
    expect(container.textContent).toContain('Back')
    expect(container.textContent).toContain('Test Connection')

    setInputValue(inputByLabel('Source name'), 'Nextcloud')
    setInputValue(inputByLabel('Nextcloud URL'), 'https://cloud.example.com')
    setInputValue(inputByLabel('Username'), 'admin')
    setInputValue(inputByLabel('Password'), 'secret')
    setInputValue(inputByLabel('File path'), '/Price_List.xlsx')

    await clickButton('Test Connection')

    expect(container.querySelector('.fh-alert-success [data-icon="success"]')).not.toBeNull()
    expect(container.querySelector('button [data-icon="save"]')).not.toBeNull()
    expect(container.textContent).toContain('Save Source')

    await clickButton('Save Source')

    expect(container.querySelector('button [data-icon="products"]')).not.toBeNull()
    expect(container.querySelector('button [data-icon="previous"]')).not.toBeNull()
    expect(container.textContent).toContain('View Products')
    expect(container.textContent).toContain('Back to Sources')
    expect(container.querySelector('[data-notification-type="success"] [data-icon="success"]')).not.toBeNull()
  })
})
