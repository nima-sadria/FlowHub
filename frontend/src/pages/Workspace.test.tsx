// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { NotificationProvider } from '../notifications/NotificationProvider'
import { ServiceProvider, type Services } from '../services/ServiceContext'
import type { WorkspacePreview, WritePipelineBatch } from '../services/types'
import Workspace from './Workspace'

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

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
  vi.restoreAllMocks()
})

describe('Workspace source-driven preview', () => {
  it('displays preview rows, warnings, unchanged rows, and blocks Dry Run when errors exist', async () => {
    const preview = makePreview({ withError: true })
    const createDryRun = vi.fn()
    await renderWorkspace(preview, createDryRun)

    await click('Start Preview')

    expect(container.textContent).toContain('Valid Product')
    expect(container.textContent).toContain('Missing Product')
    expect(container.textContent).toContain('large_price_change')
    expect(container.textContent).toContain('Unchanged')
    expect(container.textContent).toContain('blocking error')
    expect(button('Dry Run')?.hasAttribute('disabled')).toBe(true)
  })

  it('enables Dry Run for valid preview rows and sends only eligible changes', async () => {
    const preview = makePreview({ withError: false })
    const createDryRun = vi.fn(async (_previewId: string, changes) => makeBatch(changes.length, 'dry_run_ready'))
    await renderWorkspace(preview, createDryRun)

    await click('Start Preview')
    expect(button('Dry Run')?.hasAttribute('disabled')).toBe(false)

    await click('Dry Run')
    expect(createDryRun).toHaveBeenCalledTimes(1)
    expect(createDryRun.mock.calls[0][1]).toHaveLength(1)
    expect(container.textContent).toContain('Dry Run ready')
    expect(container.textContent).toContain('Approve')
    expect(container.textContent).not.toContain('Apply to WooCommerce')
  })
})

async function renderWorkspace(
  preview: WorkspacePreview,
  createDryRun: ReturnType<typeof vi.fn>,
) {
  const services = {
    settings: {
      async getSettings() {
        return {
          woocommerceUrl: 'https://store.example.test',
          nextcloudUrl: 'https://cloud.example.test',
          syncIntervalMinutes: 60,
          timezone: 'UTC',
          currency: 'EUR',
          environment: 'test',
          wcConfigured: true,
          ncConfigured: true,
        }
      },
    },
    workspace: {
      async getState() { return 'idle' as const },
      async startPreview() { return preview },
      async cancelPreview() {},
    },
    writePipeline: {
      createDryRun,
      async approve() { return makeBatch(1, 'approved') },
      async applyToWooCommerce() { return makeBatch(1, 'applied') },
      async getBatch() { return makeBatch(1, 'dry_run_ready') },
    },
    health: {},
    products: {},
    sources: {},
    activity: {},
    commerce: {},
  } as unknown as Services

  await act(async () => {
    root.render(
      <NotificationProvider>
        <ServiceProvider services={services}>
          <Workspace />
        </ServiceProvider>
      </NotificationProvider>,
    )
  })
  await flush()
}

async function click(label: string) {
  const el = button(label)
  expect(el).toBeTruthy()
  await act(async () => {
    el!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
  await flush()
}

function button(label: string): HTMLButtonElement | null {
  return Array.from(container.querySelectorAll('button')).find(item => item.textContent?.includes(label)) ?? null
}

async function flush() {
  await act(async () => {
    await Promise.resolve()
  })
}

function makePreview({ withError }: { withError: boolean }): WorkspacePreview {
  const rows = [
    {
      id: 'wp_1:Sheet1:3',
      source: sourceInfo(3, 'Valid Product'),
      matchedProduct: {
        channelId: 'woocommerce:primary',
        productId: '101',
        productType: 'simple',
        sku: 'SKU-101',
        name: 'Valid Product',
        currentPrice: 100,
        effectivePrice: 100,
        categoryNames: ['Default'],
      },
      currentPrice: 100,
      proposedPrice: 110,
      difference: 10,
      changePct: 10,
      status: 'valid_change' as const,
      errors: [],
      warnings: [],
      eligible_for_dry_run: true,
    },
    {
      id: 'wp_1:Sheet1:4',
      source: sourceInfo(4, 'Warning Product'),
      matchedProduct: null,
      currentPrice: 100,
      proposedPrice: 140,
      difference: 40,
      changePct: 40,
      status: 'warning' as const,
      errors: [],
      warnings: ['large_price_change'],
      eligible_for_dry_run: true,
    },
    {
      id: 'wp_1:Sheet1:5',
      source: sourceInfo(5, 'Same Product'),
      matchedProduct: null,
      currentPrice: 100,
      proposedPrice: 100,
      difference: 0,
      changePct: 0,
      status: 'unchanged' as const,
      errors: [],
      warnings: [],
      eligible_for_dry_run: false,
    },
    ...(withError
      ? [{
          id: 'wp_1:Sheet1:6',
          source: sourceInfo(6, 'Missing Product'),
          matchedProduct: null,
          currentPrice: null,
          proposedPrice: 120,
          difference: null,
          changePct: null,
          status: 'error' as const,
          errors: ['missing_product'],
          warnings: [],
          eligible_for_dry_run: false,
        }]
      : []),
  ]
  return {
    id: 'wp_1',
    sourceId: 'nextcloud:primary',
    sourceName: 'Nextcloud Spreadsheet: /prices.xlsx',
    state: 'preview_ready',
    totalChanges: 1,
    changes: [{
      productId: '101',
      productName: 'Valid Product',
      sku: 'SKU-101',
      currentPrice: 100,
      proposedPrice: 110,
      difference: 10,
      changePct: 10,
      currency: 'EUR',
      eligible_for_dry_run: true,
    }],
    rows,
    summary: {
      total_rows: rows.length,
      valid_changes: 1,
      unchanged_rows: 1,
      warning_rows: 1,
      error_rows: withError ? 1 : 0,
      duplicate_rows: 0,
      missing_products: withError ? 1 : 0,
      large_changes: 1,
    },
    startedAt: new Date(),
    duplicateWarnings: [],
  }
}

function sourceInfo(rowNumber: number, productName: string) {
  return {
    previewId: 'wp_1',
    sourceId: 'nextcloud:primary',
    sourceType: 'nextcloud_spreadsheet',
    sourceSnapshotId: 1,
    sourceSnapshotVersion: 1,
    sourceFilePath: '/prices.xlsx',
    worksheet: 'Sheet1',
    rowNumber,
    productId: String(100 + rowNumber),
    sku: `SKU-${100 + rowNumber}`,
    productName,
    rawPrice: '110.00',
  }
}

function makeBatch(itemCount: number, status: WritePipelineBatch['status']): WritePipelineBatch {
  return {
    id: 'wb_1',
    channelId: 'woocommerce:primary',
    channelType: 'woocommerce',
    operationType: 'price_update',
    status,
    sourcePreviewId: 'wp_1',
    batchHash: 'hash',
    itemCount,
    currency: 'EUR',
    safetySummary: { stock_update_allowed: false, scheduler_started: false, automatic_apply: false },
    createdBy: 'admin',
    createdAt: new Date(),
    approvedAt: null,
    executedAt: null,
    items: [],
  }
}
