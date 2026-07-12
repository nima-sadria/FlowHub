import { describe, expect, it } from 'vitest'
import { workspaceApplyIdempotencyKey } from './useUnifiedWorkspaceController'

describe('bounded Apply identity', () => {
  it.each([1, 6, 500, 10_000])('stays fixed length for %i selected items', async count => {
    const selectionChecksum = await crypto.subtle.digest(
      'SHA-256',
      new TextEncoder().encode(Array.from({ length: count }, (_, index) => `item-${index}`).join(',')),
    ).then(value => Array.from(new Uint8Array(value), byte => byte.toString(16).padStart(2, '0')).join(''))
    const key = await workspaceApplyIdempotencyKey('workspace', 'review', 'revision', selectionChecksum)
    expect(key).toMatch(/^[a-f0-9]{64}$/)
  })
})
