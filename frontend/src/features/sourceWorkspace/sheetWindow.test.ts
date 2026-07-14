import { describe, expect, it } from 'vitest'
import { sheetWindow } from './sheetWindow'

describe('FlowHub Sheet virtualization', () => {
  it('keeps a 10,000-product Sheet bounded to a small rendered window', () => {
    const initial = sheetWindow(10_000, 0, 520, 38, 6)
    const middle = sheetWindow(10_000, 190_000, 520, 38, 6)
    expect(initial).toEqual({ start: 0, end: 20 })
    expect(middle.end - middle.start).toBeLessThan(30)
    expect(middle.start).toBeGreaterThan(4_000)
  })

  it('clamps empty and final windows safely', () => {
    expect(sheetWindow(0, 0, 520, 38, 6)).toEqual({ start: 0, end: 0 })
    expect(sheetWindow(100, 10_000, 520, 38, 6).end).toBe(100)
  })
})
