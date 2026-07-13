import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import Handsontable from 'handsontable'
import { registerAllModules } from 'handsontable/registry'
import { sanitizeGridHtml, sourceRecordAtVisualRow } from './handsontableIdentity'

registerAllModules()

class TestResizeObserver implements ResizeObserver {
  disconnect() {}
  observe() {}
  unobserve() {}
}

const originalResizeObserver = globalThis.ResizeObserver
const originalIntersectionObserver = globalThis.IntersectionObserver
beforeAll(() => {
  globalThis.ResizeObserver = TestResizeObserver
  globalThis.IntersectionObserver = class {
    readonly root = null
    readonly rootMargin = ''
    readonly thresholds = []
    disconnect() {}
    observe() {}
    takeRecords() { return [] }
    unobserve() {}
  } as unknown as typeof IntersectionObserver
})
afterAll(() => {
  globalThis.ResizeObserver = originalResizeObserver
  globalThis.IntersectionObserver = originalIntersectionObserver
})

const instances: Handsontable[] = []
afterEach(() => {
  for (const hot of instances.splice(0)) hot.destroy()
  document.body.replaceChildren()
})

function createGrid(afterChange?: Handsontable.GridSettings['afterChange']) {
  const root = document.createElement('div')
  document.body.append(root)
  const hot = new Handsontable(root, {
    data: [
      { listingId: 'listing-a', name: 'A', selected: false, price: 10 },
      { listingId: 'listing-b', name: 'B', selected: false, price: 20 },
    ],
    columns: [
      { data: 'listingId', readOnly: true },
      { data: 'name' },
      { data: 'selected', type: 'checkbox' },
      { data: 'price', type: 'numeric' },
    ],
    columnSorting: true,
    filters: true,
    height: 160,
    licenseKey: 'non-commercial-and-evaluation',
    sanitizer: sanitizeGridHtml,
    afterChange,
  })
  instances.push(hot)
  return hot
}

describe('stable Handsontable Listing identity', () => {
  it('resolves edits and checkbox selection after descending sort', () => {
    const seen: string[] = []
    const hot = createGrid((changes, source) => {
      if (!changes || source === 'loadData') return
      for (const [visualRow] of changes) {
        const identity = sourceRecordAtVisualRow(hot, visualRow)
        if (identity) seen.push(identity.listingId)
      }
    })
    hot.getPlugin('columnSorting').sort({ column: 1, sortOrder: 'desc' })
    expect(sourceRecordAtVisualRow(hot, 0)?.listingId).toBe('listing-b')
    hot.setDataAtCell(0, 3, 99, 'edit')
    hot.setDataAtRowProp(0, 'selected', true, 'edit')
    expect(seen.length).toBeGreaterThan(0)
    expect(new Set(seen)).toEqual(new Set(['listing-b']))
  }, 15_000)

  it('resolves filtered and clipboard-style changes by physical source row', () => {
    const seen: string[] = []
    const hot = createGrid((changes, source) => {
      if (!changes || source === 'loadData') return
      for (const [visualRow] of changes) {
        const identity = sourceRecordAtVisualRow(hot, visualRow)
        if (identity) seen.push(`${source}:${identity.listingId}`)
      }
    })
    const filters = hot.getPlugin('filters')
    filters.addCondition(1, 'eq', ['B'])
    filters.filter()
    expect(sourceRecordAtVisualRow(hot, 0)?.listingId).toBe('listing-b')
    hot.runHooks('afterChange', [[0, 'price', 20, 125]], 'CopyPaste.paste')
    expect(seen[seen.length - 1]).toBe('CopyPaste.paste:listing-b')
  })

  it('virtualizes a 500-row server window for a 10,000-row dataset', () => {
    const root = document.createElement('div')
    document.body.append(root)
    const hot = new Handsontable(root, {
      data: Array.from({ length: 500 }, (_, index) => ({ listingId: `listing-${index}` })),
      columns: [{ data: 'listingId' }],
      height: 300,
      licenseKey: 'non-commercial-and-evaluation',
      sanitizer: sanitizeGridHtml,
    })
    instances.push(hot)
    expect(hot.countSourceRows()).toBe(500)
    expect(hot.countSourceRows()).toBeLessThan(10_000)
    expect(root.querySelectorAll('tbody tr').length).toBeLessThanOrEqual(500)
  })
})
