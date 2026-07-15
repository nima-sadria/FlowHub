// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { changeLocale } from '../i18n'
import { prepareResourceCollection, type ResourceOrderingSignals } from '../features/resourceOrdering/resourceOrdering'
import { ResourceOptionGroups, ResourceSectionList, ResourceStateBadge } from './ResourceOrdering'

interface Fixture {
  id: string
  name: string
  signals: Omit<ResourceOrderingSignals, 'id' | 'displayName'>
}

const resources = prepareResourceCollection<Fixture>([
  { id: 'coming-soon', name: 'Shopify', signals: { placeholder: true } },
  { id: 'disabled', name: 'CSV', signals: { enabled: false } },
  { id: 'warning', name: 'SnappShop', signals: { configured: true, healthStatus: 'warning' } },
  { id: 'active', name: 'WooCommerce', signals: { configured: true, healthStatus: 'healthy' } },
], item => ({ id: item.id, displayName: item.name, ...item.signals }))

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(async () => {
  act(() => root.unmount())
  container.remove()
  await changeLocale('en')
})

describe('ResourceOptionGroups', () => {
  it('renders non-empty groups in the shared order without disabling any resource by default', () => {
    act(() => {
      root.render(<select><ResourceOptionGroups resources={resources} /></select>)
    })

    expect(Array.from(container.querySelectorAll('optgroup')).map(group => group.label)).toEqual([
      'Active',
      'Disabled',
      'Coming Soon',
    ])
    expect(Array.from(container.querySelectorAll('option')).map(option => option.value)).toEqual([
      'active',
      'warning',
      'disabled',
      'coming-soon',
    ])
    expect(Array.from(container.querySelectorAll('option')).every(option => !option.disabled)).toBe(true)
  })

  it('lets each caller explicitly disable only options that are unavailable in its workflow', () => {
    act(() => {
      root.render(
        <select>
          <ResourceOptionGroups
            resources={resources}
            isOptionDisabled={item => item.section === 'comingSoon'}
          />
        </select>,
      )
    })

    expect(container.querySelector<HTMLOptionElement>('option[value="disabled"]')?.disabled).toBe(false)
    expect(container.querySelector<HTMLOptionElement>('option[value="coming-soon"]')?.disabled).toBe(true)
  })

  it('hides empty groups', () => {
    const activeOnly = prepareResourceCollection([{ id: 'active', name: 'WooCommerce' }], item => ({
      id: item.id,
      displayName: item.name,
      configured: true,
    }))
    act(() => {
      root.render(<select><ResourceOptionGroups resources={activeOnly} /></select>)
    })

    expect(container.querySelectorAll('optgroup')).toHaveLength(1)
    expect(container.querySelector('optgroup')?.label).toBe('Active')
  })
})

describe('ResourceSectionList', () => {
  it('shows consistent section headings and state badges', () => {
    act(() => {
      root.render(
        <ResourceSectionList
          resources={resources}
          renderItem={item => <><span>{item.displayName}</span><ResourceStateBadge badge={item.badge} /></>}
        />,
      )
    })

    expect(Array.from(container.querySelectorAll('[data-resource-section]')).map(section => (
      section.getAttribute('data-resource-section')
    ))).toEqual(['active', 'disabled', 'comingSoon'])
    expect(container.textContent).toContain('Healthy')
    expect(container.textContent).toContain('Warning')
    expect(container.textContent).toContain('Disabled')
    expect(container.textContent).toContain('Coming Soon')
  })

  it('uses translated RTL headings without changing resource identity or ordering', async () => {
    await changeLocale('fa')
    act(() => {
      root.render(<ResourceSectionList resources={resources} renderItem={item => item.displayName} />)
    })

    expect(document.documentElement.dir).toBe('rtl')
    expect(Array.from(container.querySelectorAll('[data-resource-id]')).map(item => (
      item.getAttribute('data-resource-id')
    ))).toEqual(['active', 'warning', 'disabled', 'coming-soon'])
    expect(container.textContent).not.toContain('Coming Soon')
    expect(container.querySelector('[data-resource-section="active"]')?.getAttribute('aria-label')).not.toBe('Active')
  })
})
