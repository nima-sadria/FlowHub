// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import Empty from './Empty'

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

describe('Empty', () => {
  it('renders title', () => {
    act(() => { root.render(<Empty title="No items found" />) })
    expect(container.textContent).toContain('No items found')
  })

  it('renders description when provided', () => {
    act(() => { root.render(<Empty title="Empty" description="Add something to get started." />) })
    expect(container.textContent).toContain('Add something to get started.')
  })

  it('does not render description when not provided', () => {
    act(() => { root.render(<Empty title="Empty" />) })
    expect(container.querySelector('p:last-of-type')?.textContent).not.toContain('undefined')
  })

  it('renders action button with correct label', () => {
    act(() => {
      root.render(<Empty title="Empty" action={{ label: 'Add Source', onClick: () => {} }} />)
    })
    const btn = container.querySelector('button')
    expect(btn?.textContent).toBe('Add Source')
  })

  it('calls action.onClick when button is clicked', () => {
    const onClick = vi.fn()
    act(() => {
      root.render(<Empty title="Empty" action={{ label: 'Click me', onClick }} />)
    })
    const btn = container.querySelector('button')!
    act(() => { btn.click() })
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('does not render button when action not provided', () => {
    act(() => { root.render(<Empty title="Empty" />) })
    expect(container.querySelector('button')).toBeNull()
  })
})
