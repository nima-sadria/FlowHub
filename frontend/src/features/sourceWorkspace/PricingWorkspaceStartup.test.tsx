// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import PricingWorkspaceStartup from './PricingWorkspaceStartup'

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

describe('PricingWorkspaceStartup', () => {
  it('uses the Workspace title on first paint and keeps every loading filter labeled', () => {
    act(() => root.render(<PricingWorkspaceStartup />))

    expect(container.querySelector('h1')?.textContent).toBe('Workspace')
    expect(container.querySelectorAll('.fh-chip-select-skeleton')).toHaveLength(0)
    expect([...container.querySelectorAll<HTMLSelectElement>('.fh-chip-select select')].map(select => select.value)).toEqual([
      'All statuses',
      'All Channels',
      'Saved Views',
    ])
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(3)
  })
})
