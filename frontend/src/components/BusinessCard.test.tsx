// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import BusinessCard from './BusinessCard'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

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

describe('BusinessCard', () => {
  it('renders the complete business decision contract with icon and text status', () => {
    act(() => {
      root.render(
        <BusinessCard
          title="Products"
          value="2,415"
          explanation="15 added today"
          meaning="Products available for daily review."
          icon="products"
          status={{ label: 'Healthy', tone: 'success', icon: 'success' }}
          recommendationLabel="Next step"
          recommendation="Review today's changes."
          testId="products"
        />,
      )
    })

    const card = container.querySelector<HTMLElement>('[data-business-card="products"]')
    expect(card).not.toBeNull()
    expect(card?.textContent).toContain('Products')
    expect(card?.textContent).toContain('2,415')
    expect(card?.textContent).toContain('15 added today')
    expect(card?.textContent).toContain('Products available for daily review.')
    expect(card?.textContent).toContain('Healthy')
    expect(card?.textContent).toContain('Next step')
    expect(card?.textContent).toContain("Review today's changes.")
    expect(card?.querySelector('[data-icon="products"]')).not.toBeNull()
    expect(card?.querySelector('.fh-badge [data-icon="success"]')).not.toBeNull()
    expect(card?.dataset.tone).toBe('success')
  })

  it('keeps the recommendation action keyboard-accessible and callable', () => {
    const onClick = vi.fn()
    act(() => {
      root.render(
        <BusinessCard
          title="Sources"
          value="No active Sources"
          explanation="No Source data is available."
          meaning="Sources provide product data."
          icon="file"
          status={{ label: 'Needs attention', tone: 'warning', icon: 'warning' }}
          recommendationLabel="Next step"
          recommendation="Connect a Source."
          action={{ label: 'Manage Sources', onClick }}
        />,
      )
    })

    const action = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.includes('Manage Sources'))
    expect(action).toBeDefined()
    act(() => action?.click())
    expect(onClick).toHaveBeenCalledTimes(1)
    expect(container.textContent).not.toMatch(/^0$/)
  })
})
