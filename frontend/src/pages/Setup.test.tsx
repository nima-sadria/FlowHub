// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { SearchableListbox } from './Setup'

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
            { value: 'IRR', label: 'IRR — Iranian Rial' },
            { value: 'IRT', label: 'IRT — Iranian Toman' },
          ]}
          value="IRR"
          onChange={() => {}}
        />
      )
    })

    const input = container.querySelector('input')
    expect(input?.value).toBe('IRR — Iranian Rial')
    expect(container.textContent).not.toContain('Selected:')
  })
})
