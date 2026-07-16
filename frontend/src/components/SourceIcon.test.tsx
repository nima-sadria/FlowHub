// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  SOURCE_ICON_ASSETS,
  SOURCE_ICON_FALLBACK,
} from '../features/sourceIntegrations/sourceIconRegistry'
import SourceIcon from './SourceIcon'

describe('SourceIcon', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('renders a 48px contained brand image without recoloring or cropping it', () => {
    act(() => root.render(<SourceIcon identity={{ provider: 'nextcloud' }} />))

    const wrapper = container.querySelector('[data-source-icon]') as HTMLSpanElement
    const image = container.querySelector('img') as HTMLImageElement
    expect(wrapper.style.width).toBe('48px')
    expect(wrapper.style.height).toBe('48px')
    expect(image.src).toContain(SOURCE_ICON_ASSETS.nextcloud)
    expect(image.className).toContain('object-contain')
    expect(image.alt).toBe('')
    expect(image.getAttribute('aria-hidden')).toBe('true')
  })

  it('supports an accessible label when the icon is not decorative', () => {
    act(() => root.render(<SourceIcon identity="nextcloud" label="Nextcloud" size={44} />))

    const wrapper = container.querySelector('[data-source-icon]') as HTMLSpanElement
    const image = container.querySelector('img') as HTMLImageElement
    expect(wrapper.style.width).toBe('44px')
    expect(wrapper.style.height).toBe('44px')
    expect(image.alt).toBe('Nextcloud')
    expect(image.hasAttribute('aria-hidden')).toBe(false)
  })

  it('falls back once when a local brand asset cannot load', () => {
    act(() => root.render(<SourceIcon identity={{ fileName: 'prices.xlsx' }} />))
    const image = container.querySelector('img') as HTMLImageElement
    expect(image.src).toContain(SOURCE_ICON_ASSETS.microsoftOffice)

    act(() => image.dispatchEvent(new Event('error')))
    expect(image.src).toContain('FlowHub%20favicon.png')
    expect(container.querySelector('[data-source-icon]')?.getAttribute('data-source-icon')).toBe(SOURCE_ICON_FALLBACK)

    act(() => image.dispatchEvent(new Event('error')))
    expect(container.querySelector('[data-source-icon]')?.getAttribute('data-source-icon')).toBe(SOURCE_ICON_FALLBACK)
  })

  it('updates when the explicit Source identity changes', () => {
    act(() => root.render(<SourceIcon identity="nextcloud" />))
    expect((container.querySelector('img') as HTMLImageElement).src).toContain(SOURCE_ICON_ASSETS.nextcloud)

    act(() => root.render(<SourceIcon identity={{ sourceType: 'xlsx' }} />))
    expect((container.querySelector('img') as HTMLImageElement).src).toContain(SOURCE_ICON_ASSETS.microsoftOffice)
  })
})
