// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import Alert, { type AlertVariant } from './Alert'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

describe('Alert Design System component', () => {
  it('derives the tone, icon, and announcement role from the variant', () => {
    const variants: AlertVariant[] = ['success', 'warning', 'error', 'info']
    act(() => root.render(<>{variants.map(variant => (
      <Alert key={variant} variant={variant} title={`${variant} title`} message={`${variant} message`} />
    ))}</>))

    const alerts = Array.from(container.querySelectorAll<HTMLElement>('.fh-alert'))
    expect(alerts).toHaveLength(4)
    expect(alerts.find(alert => alert.textContent?.includes('success title'))?.className).toContain('fh-alert-success')
    expect(alerts.find(alert => alert.textContent?.includes('warning title'))?.querySelector('[data-icon="warning"]')).not.toBeNull()
    expect(alerts.find(alert => alert.textContent?.includes('error title'))?.getAttribute('role')).toBe('alert')
    expect(alerts.find(alert => alert.textContent?.includes('info title'))?.getAttribute('role')).toBe('status')
    expect(alerts.every(alert => alert.querySelector('[data-icon]')?.getAttribute('aria-hidden') === 'true')).toBe(true)
  })

  it('renders an optional link with a context-specific accessible name', () => {
    act(() => root.render(
      <Alert
        variant="info"
        title="API documentation"
        message="Review the connection requirements."
        linkHref="/docs/channels"
        linkText="Learn more"
        linkAriaLabel="Learn more about channel connection requirements"
      />,
    ))

    const link = container.querySelector<HTMLAnchorElement>('.fh-alert-link')
    expect(link?.getAttribute('href')).toBe('/docs/channels')
    expect(link?.getAttribute('aria-label')).toBe('Learn more about channel connection requirements')
  })
})
