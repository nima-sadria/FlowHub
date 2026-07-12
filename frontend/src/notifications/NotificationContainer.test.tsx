// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { describe, expect, it } from 'vitest'
import NotificationContainer from './NotificationContainer'
import { NotificationProvider, useNotification } from './NotificationProvider'

function NotificationActions() {
  const notification = useNotification()
  return (
    <div>
      <button onClick={() => notification.success({ title: 'Saved successfully', description: 'Your changes have been applied.' }, 0)}>Success</button>
      <button onClick={() => notification.error({ title: 'Unable to save', description: 'Please try again.' }, 0)}>Error</button>
      <button onClick={() => notification.warning({ title: 'Review required', description: 'Check the highlighted fields.' }, 0)}>Warning</button>
      <button onClick={() => notification.info({ title: 'Update available', description: 'New information has been loaded.' }, 0)}>Information</button>
    </div>
  )
}

describe('NotificationContainer', () => {
  it('renders structured notifications with centralized semantic icons and an accessible close action', () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    act(() => {
      root.render(
        <NotificationProvider>
          <NotificationActions />
          <NotificationContainer />
        </NotificationProvider>,
      )
    })

    for (const label of ['Success', 'Error', 'Warning', 'Information']) {
      act(() => {
        Array.from(container.querySelectorAll('button'))
          .find(button => button.textContent === label)
          ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      })
    }

    expect(container.querySelector('[data-icon="success"]')).not.toBeNull()
    expect(container.querySelector('[data-icon="error"]')).not.toBeNull()
    expect(container.querySelector('[data-icon="warning"]')).not.toBeNull()
    expect(container.querySelector('[data-icon="info"]')).not.toBeNull()
    expect(container.querySelector('[data-notification-type="success"]')?.className).toContain('fh-notification-success')
    expect(container.querySelector('[data-notification-type="error"]')?.className).toContain('fh-notification-error')
    expect(container.querySelector('[data-notification-type="warning"]')?.className).toContain('fh-notification-warning')
    expect(container.querySelector('[data-notification-type="info"]')?.className).toContain('fh-notification-info')
    expect(container.querySelector('.fh-notification-icon-success [data-icon="success"]')).not.toBeNull()
    expect(container.querySelector('.fh-notification-title')?.textContent).toContain('Update available')
    expect(container.querySelector('.fh-notification-description')?.textContent).toContain('New information has been loaded.')
    expect(container.textContent).toContain('Your changes have been applied.')
    expect(container.querySelector('button[aria-label="Close notification"] [data-icon="close"]')).not.toBeNull()

    act(() => { root.unmount() })
    container.remove()
  })

  it('renders notifications when crypto.randomUUID is unavailable', () => {
    const originalCrypto = globalThis.crypto
    Object.defineProperty(globalThis, 'crypto', { value: {}, configurable: true })
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    try {
      act(() => {
        root.render(
          <NotificationProvider>
            <NotificationActions />
            <NotificationContainer />
          </NotificationProvider>,
        )
      })
      act(() => {
        Array.from(container.querySelectorAll('button'))
          .find(button => button.textContent === 'Success')
          ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      })

      expect(container.querySelector('[data-notification-type="success"]')).not.toBeNull()
      expect(container.textContent).toContain('Saved successfully')
    } finally {
      act(() => { root.unmount() })
      container.remove()
      Object.defineProperty(globalThis, 'crypto', { value: originalCrypto, configurable: true })
    }
  })
})
