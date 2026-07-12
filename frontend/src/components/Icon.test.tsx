// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import Icon, { routeIconMap } from './Icon'

describe('Icon', () => {
  it('renders fixed-size masked icons with optional accessible names and RTL mirroring', () => {
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
    expect(icon?.getAttribute('style')).toContain('/static/icons/angle-right.svg')

    act(() => { root.unmount() })
    container.remove()
  })

  it('keeps route icon mappings on static SVG asset paths', () => {
    const expectedAssets = [
      'grid.svg',
      'box.svg',
      'shooting-star.svg',
      'box-cube.svg',
      'task-icon.svg',
      'docs.svg',
      'pie-chart.svg',
      'user-circle.svg',
      'time.svg',
      'page.svg',
    ]

    const labels = ['Dashboard', 'Products', 'Workspace', 'Commerce Hub', 'Orders', 'Activity', 'Diagnostics', 'Settings', 'Rate Limits', 'Logs'] as const
    for (const label of labels) {
      expect(routeIconMap[label]).toBeTruthy()
    }
    for (const asset of expectedAssets) {
      expect(`/static/icons/${asset}`).toMatch(/^\/static\/icons\/.+\.svg$/)
    }
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

    expect(container.querySelector('[data-icon="success"]')?.getAttribute('style')).toContain('check-circle.svg')
    expect(container.querySelector('[data-icon="error"]')?.getAttribute('style')).toContain('info-error.svg')
    expect(container.querySelector('[data-icon="warning"]')?.getAttribute('style')).toContain('alert.svg')
    expect(container.querySelector('[data-icon="info"]')?.getAttribute('style')).toContain('info.svg')

    act(() => { root.unmount() })
    container.remove()
  })
})
