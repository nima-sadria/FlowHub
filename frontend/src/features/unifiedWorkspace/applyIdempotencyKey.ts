export async function workspaceApplyIdempotencyKey(
  workspaceId: string,
  reviewId: string,
  draftRevisionId: string,
  selectionChecksum: string,
  manifestChecksum: string,
): Promise<string> {
  const canonical = JSON.stringify({
    draftRevisionId,
    manifestChecksum,
    operationVersion: 'workspace-apply-v3',
    reviewId,
    selectionChecksum,
    workspaceId,
  })
  const digest = await globalThis.crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(canonical),
  )
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
}
