// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { DirectionProvider } from '../direction'
import { ThemeProvider } from '../theme/ThemeProvider'
import Setup, { SearchableListbox, validateSetupEmail } from './Setup'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  localStorage.clear()
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

async function renderSetup() {
  await act(async () => {
    root.render(
      <ThemeProvider>
        <DirectionProvider>
          <Setup onComplete={() => undefined} />
        </DirectionProvider>
      </ThemeProvider>,
    )
  })
  await act(async () => { await Promise.resolve() })
}

afterEach(() => {
  act(() => { root.unmount() })
  container.remove()
})

describe('SearchableListbox', () => {
  it('shows the selected value inside the field without a separate selected line', () => {
    act(() => {
      root.render(
        <SearchableListbox
          label="Currency"
          options={[
            { value: 'IRR', label: 'IRR - Iranian Rial' },
            { value: 'IRT', label: 'IRT - Iranian Toman' },
          ]}
          value="IRR"
          onChange={() => {}}
        />
      )
    })

    const trigger = container.querySelector('button')
    expect(trigger?.textContent).toContain('IRR - Iranian Rial')
    expect(container.textContent).not.toContain('Selected:')
  })

  it('opens options only after the field is clicked', () => {
    act(() => {
      root.render(
        <SearchableListbox
          label="Timezone"
          options={[
            { value: 'UTC', label: 'UTC' },
            { value: 'Asia/Tehran', label: 'Asia/Tehran' },
          ]}
          value="UTC"
          onChange={() => {}}
        />
      )
    })

    expect(container.querySelector('[role="listbox"]')).toBeNull()

    const trigger = container.querySelector('button')
    act(() => {
      trigger?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(container.querySelector('[role="listbox"]')).not.toBeNull()
    expect(container.textContent).toContain('Asia/Tehran')
  })
})

describe('validateSetupEmail', () => {
  it('accepts a valid email after trimming whitespace', () => {
    expect(validateSetupEmail(' admin@example.com ')).toBeNull()
  })

  it('rejects malformed email addresses', () => {
    const invalid = [
      '',
      'adminexample.com',
      'admin@',
      'admin@example',
      'admin@@example.com',
      'admin @example.com',
      'admin@example..com',
      'admin@-example.com',
      'admin@example.c',
    ]

    for (const value of invalid) {
      expect(validateSetupEmail(value)).toBe('Enter a valid email address.')
    }
  })
})

describe('Setup', () => {
  it('renders the approved four-stage workspace frame from live setup status', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ completed: false, has_admin: false }), { status: 200 }),
    )

    await renderSetup()

    expect(container.textContent).toContain('Set up your workspace')
    expect(container.textContent).toContain('Step 1 of 4')
    for (const label of ['Workspace', 'Database', 'Owner', 'Review']) {
      expect(container.textContent).toContain(label)
    }
    expect(container.textContent).toContain('Setup checklist')
    expect(container.textContent).toContain('Workspace domain')
  })

  it('keeps the existing server-profile contract when continuing', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (String(input).endsWith('/api/v2/setup/status')) {
        return new Response(JSON.stringify({ completed: false, has_admin: false }), { status: 200 })
      }
      if (String(input).endsWith('/api/v2/setup/server-profile')) {
        return new Response(JSON.stringify({ ok: true }), { status: 200 })
      }
      throw new Error(`Unexpected request: ${String(input)} ${init?.method ?? 'GET'}`)
    })

    await renderSetup()
    const continueButton = Array.from(container.querySelectorAll('button'))
      .find(button => button.textContent?.includes('Continue to database'))
    await act(async () => {
      continueButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    const request = fetchMock.mock.calls.find(([input]) => String(input).endsWith('/api/v2/setup/server-profile'))
    expect(request).toBeDefined()
    expect(request?.[1]?.method).toBe('POST')
    expect(JSON.parse(String(request?.[1]?.body))).toEqual(expect.objectContaining({
      domain: expect.any(String),
      timezone: expect.any(String),
      currency: 'USD',
    }))
    expect(container.textContent).toContain('Database readiness')
  })

  it('explains owner password requirements and enables creation only for matching valid passwords', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
      const url = String(input)
      if (url.endsWith('/api/v2/setup/status')) {
        return new Response(JSON.stringify({ completed: false, has_admin: false }), { status: 200 })
      }
      if (url.endsWith('/api/v2/setup/server-profile')) {
        return new Response(JSON.stringify({ ok: true }), { status: 200 })
      }
      if (url.endsWith('/api/v2/setup/database')) {
        return new Response(JSON.stringify({ connected: true, is_current: true }), { status: 200 })
      }
      throw new Error(`Unexpected request: ${url}`)
    })

    const findButton = async (label: string) => {
      for (let attempt = 0; attempt < 20; attempt += 1) {
        const button = Array.from(container.querySelectorAll('button'))
          .find(item => item.textContent?.includes(label)) as HTMLButtonElement | undefined
        if (button) return button
        await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
      }
      throw new Error(`Expected button containing "${label}". Page text: ${container.textContent}`)
    }
    const clickButton = async (label: string) => {
      const button = await findButton(label)
      await act(async () => {
        button.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      })
    }
    const changeInput = async (input: HTMLInputElement, value: string) => {
      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
        setter?.call(input, value)
        input.dispatchEvent(new Event('input', { bubbles: true }))
      })
    }

    await renderSetup()
    await clickButton('Continue to database')
    await clickButton('Check Database')
    await clickButton('Continue to owner')

    const email = container.querySelector('#owner-email') as HTMLInputElement
    const password = container.querySelector('#owner-password') as HTMLInputElement
    const confirm = container.querySelector('#owner-confirm') as HTMLInputElement
    const createOwner = () => Array.from(container.querySelectorAll('button'))
      .find(item => item.textContent?.includes('Create owner')) as HTMLButtonElement

    expect(container.textContent).toContain('At least 8 characters')
    await changeInput(email, 'admin@example.com')
    await changeInput(password, 'short')
    await changeInput(confirm, 'short')
    expect(container.textContent).toContain('Password must be at least 8 characters.')
    expect(createOwner().disabled).toBe(true)

    await changeInput(password, 'long-enough')
    await changeInput(confirm, 'different')
    expect(container.textContent).toContain('Passwords do not match.')
    expect(createOwner().disabled).toBe(true)

    await changeInput(confirm, 'long-enough')
    expect(container.textContent).not.toContain('Passwords do not match.')
    expect(createOwner().disabled).toBe(false)
  })

  it('saves the server profile and exits without advancing when "Save and exit" is used', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (String(input).endsWith('/api/v2/setup/status')) {
        return new Response(JSON.stringify({ completed: false, has_admin: false }), { status: 200 })
      }
      if (String(input).endsWith('/api/v2/setup/server-profile')) {
        return new Response(JSON.stringify({ ok: true }), { status: 200 })
      }
      throw new Error(`Unexpected request: ${String(input)} ${init?.method ?? 'GET'}`)
    })
    const assignSpy = vi.fn()
    const originalLocation = window.location
    Object.defineProperty(window, 'location', { value: { ...originalLocation, assign: assignSpy }, writable: true })

    try {
      await renderSetup()
      const exitButton = Array.from(container.querySelectorAll('button'))
        .find(button => button.textContent?.includes('Save and exit'))
      await act(async () => {
        exitButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      })

      const request = fetchMock.mock.calls.find(([input]) => String(input).endsWith('/api/v2/setup/server-profile'))
      expect(request).toBeDefined()
      expect(request?.[1]?.method).toBe('POST')
      expect(assignSpy).toHaveBeenCalledWith('/')
      expect(container.textContent).toContain('Workspace details')
    } finally {
      Object.defineProperty(window, 'location', { value: originalLocation, writable: true })
    }
  })
})
