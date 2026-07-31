// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import Badge, { type BadgeVariant } from './Badge'

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

describe('Badge semantic mapping', () => {
  it('uses one filled badge pattern for every supported semantic status', () => {
    const variants: BadgeVariant[] = ['success', 'warning', 'danger', 'info', 'neutral', 'pending', 'disabled']
    act(() => root.render(<>{variants.map(variant => <Badge dot variant={variant} key={variant}>{variant}</Badge>)}</>))

    const badges = Array.from(container.querySelectorAll('.fh-badge'))
    expect(badges).toHaveLength(variants.length)
    expect(badges.every(badge => badge.classList.contains('fh-badge'))).toBe(true)
    expect(badges.every(badge => badge.querySelector('.fh-status-dot'))).toBe(true)
    expect(badges.find(badge => badge.textContent === 'pending')?.className).toContain('fh-badge-warning')
    expect(badges.find(badge => badge.textContent === 'disabled')?.className).toContain('fh-badge-neutral')
  })
})
