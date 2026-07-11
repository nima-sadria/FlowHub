// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import type { ReactNode } from 'react'
import LocalizedText, { containsPersianScript } from './LocalizedText'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

describe('LocalizedText', () => {
  it('marks mixed Persian and English text without changing direction globally', () => {
    const { container, unmount } = render(<LocalizedText text="WooCommerce فروشگاه" className="truncate" />)
    const span = container.querySelector('span')

    expect(span?.textContent).toBe('WooCommerce فروشگاه')
    expect(span?.getAttribute('lang')).toBe('fa')
    expect(span?.getAttribute('dir')).toBe('auto')
    expect(span?.className).toContain('fh-persian-text')
    expect(document.documentElement.lang).not.toBe('fa')
    expect(document.documentElement.dir).not.toBe('rtl')
    unmount()
  })

  it('keeps English technical text on the existing typography path', () => {
    const { container, unmount } = render(<LocalizedText text="SKU-100" className="fh-text-mono" />)
    const span = container.querySelector('span')

    expect(span?.getAttribute('lang')).toBeNull()
    expect(span?.getAttribute('dir')).toBeNull()
    expect(span?.className).not.toContain('fh-persian-text')
    expect(span?.className).toContain('fh-text-mono')
    unmount()
  })

  it('detects Persian script in mixed labels used by data panels', () => {
    expect(containsPersianScript('SKU محصول')).toBe(true)
    expect(containsPersianScript('EUR 120.00')).toBe(false)
  })
})

function render(node: ReactNode) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(node)
  })
  return {
    container,
    unmount() {
      act(() => root.unmount())
      container.remove()
    },
  }
}
