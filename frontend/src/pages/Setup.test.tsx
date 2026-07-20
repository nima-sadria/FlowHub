// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { DirectionProvider } from '../direction'
import { ThemeProvider } from '../theme/ThemeProvider'
import Setup, { SearchableListbox, validateSetupEmail } from './Setup'

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
})
