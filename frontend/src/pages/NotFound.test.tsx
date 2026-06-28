// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import NotFound from './NotFound'

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

describe('NotFound', () => {
  it('shows 404 text', () => {
    act(() => {
      root.render(<MemoryRouter><NotFound /></MemoryRouter>)
    })
    expect(container.textContent).toContain('404')
  })

  it('shows a Return to Dashboard button', () => {
    act(() => {
      root.render(<MemoryRouter><NotFound /></MemoryRouter>)
    })
    const btn = container.querySelector('button')
    expect(btn?.textContent).toContain('Return to Dashboard')
  })
})
