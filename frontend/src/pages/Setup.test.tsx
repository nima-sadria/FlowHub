// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { SearchableListbox, validateSetupEmail } from './Setup'

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

    const input = container.querySelector('input')
    expect(input?.value).toBe('IRR - Iranian Rial')
    expect(container.textContent).not.toContain('Selected:')
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
