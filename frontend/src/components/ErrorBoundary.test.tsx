// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import ErrorBoundary from './ErrorBoundary'

function ThrowError(): ReactNode { throw new Error('test error') }

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

describe('ErrorBoundary', () => {
  it('renders children when there is no error', () => {
    act(() => {
      root.render(
        <ErrorBoundary>
          <span>safe content</span>
        </ErrorBoundary>
      )
    })
    expect(container.textContent).toContain('safe content')
  })

  it('renders default fallback when child throws', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    act(() => {
      root.render(
        <ErrorBoundary>
          <ThrowError />
        </ErrorBoundary>
      )
    })
    expect(container.textContent).toContain('Something went wrong')
    expect(container.textContent).toContain('Try again')
    consoleSpy.mockRestore()
  })

  it('renders custom fallback when provided', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    act(() => {
      root.render(
        <ErrorBoundary fallback={<div>custom fallback</div>}>
          <ThrowError />
        </ErrorBoundary>
      )
    })
    expect(container.textContent).toContain('custom fallback')
    consoleSpy.mockRestore()
  })
})
