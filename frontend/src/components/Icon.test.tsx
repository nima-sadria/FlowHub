// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import Icon, { routeIconMap } from './Icon'

describe('Icon', () => {
  it('renders fixed-size centralized icons with optional accessible names and RTL mirroring', () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    act(() => {
      root.render(<Icon name="next" label="Next page" mirrorRtl />)
    })

    const icon = container.querySelector('[data-icon="next"]')
    expect(icon?.getAttribute('role')).toBe('img')
    expect(icon?.getAttribute('aria-label')).toBe('Next page')
    expect(icon?.getAttribute('data-rtl-mirror')).toBe('true')
    expect(icon?.className).toContain('fh-svg-icon')
    expect(icon?.className).not.toContain('fh-inline-svg-icon')
    expect(icon?.getAttribute('style')).toBeNull()
    expect(icon?.querySelector('svg')?.getAttribute('stroke-width')).toBe('2')
    expect(icon?.querySelector('svg path')).not.toBeNull()

    act(() => { root.unmount() })
    container.remove()
  })

  it('keeps every route on the centralized inline icon system', () => {
    const labels = ['Dashboard', 'Products', 'Workspace', 'Commerce Hub', 'Orders', 'Activity', 'Diagnostics', 'Settings', 'Rate Limits', 'Logs'] as const
    for (const label of labels) {
      expect(routeIconMap[label]).toBeTruthy()
    }
    expect(Object.values(routeIconMap)).not.toContain('')
  })

  it('resolves all notification states through the centralized icon assets', () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    act(() => {
      root.render(
        <>
          <Icon name="success" />
          <Icon name="error" />
          <Icon name="warning" />
          <Icon name="info" />
        </>,
      )
    })

    expect(container.querySelectorAll('[data-icon]')).toHaveLength(4)
    expect(container.querySelectorAll('[data-icon] svg[stroke="currentColor"]')).toHaveLength(4)
    expect(container.querySelector('[style*="--fh-icon-url"]')).toBeNull()

    act(() => { root.unmount() })
    container.remove()
  })
})
