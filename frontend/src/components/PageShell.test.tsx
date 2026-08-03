// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import PageShell from './PageShell'

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

describe('PageShell', () => {
  it('places every page on the shared twelve-column layout primitive', () => {
    act(() => root.render(<PageShell><section>Content</section></PageShell>))

    const inner = container.querySelector('.fh-page-inner')
    expect(inner?.className).toContain('fh-grid-12')
    expect(inner?.querySelector('section')?.textContent).toBe('Content')
  })
})
