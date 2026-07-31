// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { ThemeProvider, useTheme } from './ThemeProvider'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

function ThemeProbe() {
  const { theme, toggleTheme } = useTheme()
  return <button type="button" onClick={toggleTheme}>{theme}</button>
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.classList.remove('dark')
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  localStorage.clear()
  document.documentElement.classList.remove('dark')
})

describe('ThemeProvider', () => {
  it('applies the persisted theme to the global document before paint', () => {
    localStorage.setItem('wp_theme', 'dark')
    act(() => root.render(<ThemeProvider><ThemeProbe /></ThemeProvider>))

    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(container.textContent).toBe('dark')
  })

  it('updates the context, document class, and persistence in one toggle', () => {
    act(() => root.render(<ThemeProvider><ThemeProbe /></ThemeProvider>))
    const toggle = container.querySelector('button') as HTMLButtonElement

    act(() => toggle.click())

    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(localStorage.getItem('wp_theme')).toBe('dark')
    expect(toggle.textContent).toBe('dark')
  })

  it('synchronizes a theme change received from another browser context', () => {
    act(() => root.render(<ThemeProvider><ThemeProbe /></ThemeProvider>))

    act(() => window.dispatchEvent(new StorageEvent('storage', { key: 'wp_theme', newValue: 'dark' })))

    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(container.textContent).toBe('dark')
  })
})
