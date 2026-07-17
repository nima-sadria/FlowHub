import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SecretField from './SecretField'

describe('SecretField', () => {
  let container: HTMLDivElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
  })

  afterEach(() => {
    container.remove()
  })

  function render(value = '', configured = true, onChange = vi.fn()) {
    const root = createRoot(container)
    act(() => root.render(
      <SecretField
        label="Consumer secret"
        value={value}
        configured={configured}
        onChange={onChange}
        configuredHint="Configured; leave blank to keep unchanged."
        revealLabel="Show entered secret"
        concealLabel="Hide entered secret"
        copyLabel="Copy entered secret"
      />,
    ))
    return { root, onChange }
  }

  it('represents a stored secret without putting it in the DOM', () => {
    const { root } = render()
    const input = container.querySelector('input') as HTMLInputElement
    expect(input.value).toBe('')
    expect(input.placeholder).toBe('••••••••')
    expect(container.textContent).toContain('Configured; leave blank to keep unchanged.')
    expect(Array.from(container.querySelectorAll('button')).every(button => button.disabled)).toBe(true)
    act(() => root.unmount())
  })

  it('reveals and copies only a value entered in the current form session', async () => {
    const { root } = render('replacement-secret')
    const [reveal, copy] = Array.from(container.querySelectorAll('button'))
    const input = container.querySelector('input') as HTMLInputElement

    expect(input.type).toBe('password')
    act(() => reveal.click())
    expect(input.type).toBe('text')
    expect(reveal.getAttribute('aria-label')).toBe('Hide entered secret')

    await act(async () => copy.click())
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('replacement-secret')
    act(() => root.unmount())
  })
})
