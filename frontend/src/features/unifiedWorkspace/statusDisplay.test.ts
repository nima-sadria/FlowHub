import { describe, expect, it } from 'vitest'
import { describeWorkspaceStatus } from './statusDisplay'

describe('Workspace status presentation', () => {
  it('provides text, icon, and critical emphasis for important states', () => {
    for (const status of ['warning', 'error', 'failed', 'stale_review', 'reconciliation_required']) {
      const display = describeWorkspaceStatus(status)
      expect(display.label).not.toBe('')
      expect(display.icon).not.toBe('')
      expect(display.critical).toBe(true)
    }
    expect(describeWorkspaceStatus('draft_saved').label).toBe('Draft Saved')
  })
})
