import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import NotificationContainer from '../notifications/NotificationContainer'
import { NotificationProvider } from '../notifications/NotificationProvider'
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
    const field = (currentValue: string) => (
      <NotificationProvider>
        <SecretField
          label="Consumer secret"
          value={currentValue}
          configured={configured}
          onChange={onChange}
          configuredHint="Configured; leave blank to keep unchanged."
          revealLabel="Show entered secret"
          concealLabel="Hide entered secret"
          copyLabel="Copy entered secret"
          copiedLabel="Entered secret copied."
          emptySecretHint="Saved secret is hidden for security — type a new one to reveal or copy it."
          placeholder="Type your password"
          configuredMask="••••••••••••"
        />
        <NotificationContainer />
      </NotificationProvider>
    )
    act(() => root.render(field(value)))
    return {
      root,
      onChange,
      rerender: (currentValue: string) => act(() => root.render(field(currentValue))),
    }
  }

  it('represents a stored secret without putting it in the DOM', () => {
    const { root } = render()
    const input = container.querySelector('input') as HTMLInputElement
    expect(input.value).toBe('')
    expect(input.getAttribute('value')).toBe('')
    expect(input.placeholder).toBe('')
    expect(container.querySelector('[data-testid="configured-secret-mask"]')?.textContent).toBe('••••••••••••')
    expect(container.querySelector('[data-testid="configured-secret-mask"]')?.getAttribute('aria-hidden')).toBe('true')
    expect(container.textContent).toContain('Configured; leave blank to keep unchanged.')
    const reveal = container.querySelector<HTMLButtonElement>('[aria-label="Show entered secret"]')
    const copy = container.querySelector<HTMLButtonElement>('[aria-label="Copy entered secret"]')
    expect(reveal?.disabled).toBe(true)
    expect(copy?.disabled).toBe(true)
    expect(reveal?.title).toBe('Saved secret is hidden for security — type a new one to reveal or copy it.')
    expect(copy?.title).toBe('Saved secret is hidden for security — type a new one to reveal or copy it.')
    act(() => root.unmount())
  })

  it('shows the real placeholder instead of the decorative saved mask while focused', () => {
    const { root } = render()
    const input = container.querySelector('input') as HTMLInputElement
    const mask = container.querySelector('[data-testid="configured-secret-mask"]')

    expect(mask?.className).toContain('text-text-muted')
    act(() => input.focus())
    expect(container.querySelector('[data-testid="configured-secret-mask"]')).toBeNull()
    expect(input.placeholder).toBe('Type your password')

    act(() => input.blur())
    expect(container.querySelector('[data-testid="configured-secret-mask"]')).not.toBeNull()
    act(() => root.unmount())
  })

  it('reveals and copies only a value entered in the current form session', async () => {
    const { root } = render('replacement-secret')
    const [reveal, copy] = Array.from(container.querySelectorAll('button'))
    const input = container.querySelector('input') as HTMLInputElement

    expect(input.type).toBe('password')
    expect(container.querySelector('[data-testid="configured-secret-mask"]')).toBeNull()
    expect(reveal.disabled).toBe(false)
    expect(copy.disabled).toBe(false)
    expect(reveal.title).toBe('Show entered secret')
    expect(copy.title).toBe('Copy entered secret')
    act(() => reveal.click())
    expect(input.type).toBe('text')
    expect(reveal.getAttribute('aria-label')).toBe('Hide entered secret')
    expect(reveal.title).toBe('Hide entered secret')

    await act(async () => copy.click())
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('replacement-secret')
    expect(container.textContent).toContain('Entered secret copied.')
    act(() => root.unmount())
  })

  it('returns to the configured disabled state when the local replacement is cleared', () => {
    const { root, rerender } = render('replacement-secret')
    const input = container.querySelector('input') as HTMLInputElement
    const reveal = container.querySelector<HTMLButtonElement>('[aria-label="Show entered secret"]') as HTMLButtonElement

    act(() => reveal.click())
    expect(input.type).toBe('text')
    rerender('')

    expect(input.type).toBe('password')
    expect(container.querySelector<HTMLButtonElement>('[aria-label="Show entered secret"]')?.disabled).toBe(true)
    expect(container.querySelector<HTMLButtonElement>('[aria-label="Copy entered secret"]')?.disabled).toBe(true)
    expect(container.querySelector('[data-testid="configured-secret-mask"]')).not.toBeNull()
    expect(container.textContent).toContain('Configured; leave blank to keep unchanged.')
    act(() => root.unmount())
  })
})
