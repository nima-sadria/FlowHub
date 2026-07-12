import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiErrorMessage } from '../../api/client'
import type { UnifiedWorkspaceService } from '../../services/unifiedWorkspace/UnifiedWorkspaceService'
import type {
  ApplyResource,
  DraftChangeInput,
  ReviewResource,
  UnifiedWorkspaceResource,
  WorkspaceGridPage,
  WorkspacePreferences,
  WorkspaceGridQuery,
} from '../../services/unifiedWorkspace/types'
import { buildGridDefinition, draftChangeFromEdit, key } from './gridModel'

export function useUnifiedWorkspaceController(workspaceId: string, service: UnifiedWorkspaceService) {
  const [workspace, setWorkspace] = useState<UnifiedWorkspaceResource | null>(null)
  const [grid, setGrid] = useState<WorkspaceGridPage | null>(null)
  const [preferences, setPreferences] = useState<WorkspacePreferences | null>(null)
  const [draftChanges, setDraftChanges] = useState<Map<string, DraftChangeInput>>(new Map())
  const [review, setReview] = useState<ReviewResource | null>(null)
  const [applyResult, setApplyResult] = useState<ApplyResource | null>(null)
  const [loading, setLoading] = useState(true)
  const [action, setAction] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [selectedListingIds, setSelectedListingIds] = useState<Set<string>>(new Set())
  const [gridQuery, setGridQuery] = useState<WorkspaceGridQuery>({ sort: 'name:asc' })

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [workspaceResult, gridResult, preferenceResult] = await Promise.all([
        service.getWorkspace(workspaceId),
        service.getGrid(workspaceId, page, 500, gridQuery),
        service.getPreferences(),
      ])
      setWorkspace(workspaceResult)
      setGrid(gridResult)
      setPreferences(preferenceResult)
    } catch (cause) {
      setError(apiErrorMessage(cause, 'Unable to load Workspace.'))
    } finally {
      setLoading(false)
    }
  }, [gridQuery, page, service, workspaceId])

  useEffect(() => { void load() }, [load])

  const definition = useMemo(() => {
    const built = buildGridDefinition(
      grid?.items ?? [],
      grid?.channels ?? [],
      preferences?.visibleChannelIds ?? ['woocommerce:primary', 'snappshop:main'],
    )
    for (const record of built.records) record.selected = selectedListingIds.has(record.listingId)
    for (const change of draftChanges.values()) {
      const record = built.records.find(item => item.listingId === change.listing_id)
      if (!record) continue
      record[key(change.channel_id, change.field, 'target')] = change.target_value
      record[key(change.channel_id, change.field, 'status')] = 'edited'
    }
    return built
  }, [draftChanges, grid, preferences, selectedListingIds])

  const editCell = useCallback((listingId: string, prop: string, value: unknown) => {
    if (!grid) return
    const row = grid.items.find(item => item.listingId === listingId)
    const meta = definition.columnMeta.get(prop)
    if (prop === 'selected' && row?.listingId) {
      setSelectedListingIds(current => {
        const next = new Set(current)
        if (value === true) next.add(row.listingId!)
        else next.delete(row.listingId!)
        return next
      })
      return
    }
    const channel = grid.channels.find(item => item.channelId === meta?.channelId)
    if (!row || !meta || !channel) return
    const change = draftChangeFromEdit(row, meta, value, channel)
    if (!change) return
    setDraftChanges(current => {
      const next = new Map(current)
      next.set(`${change.listing_id}:${change.field}`, change)
      return next
    })
    setReview(null)
    setApplyResult(null)
  }, [definition.columnMeta, grid])

  const saveDraft = useCallback(async () => {
    if (!workspace || !grid || draftChanges.size === 0) return
    setAction('saving')
    setError(null)
    try {
      const revision = await service.saveDraft(workspace.id, grid.draftVersion, [...draftChanges.values()])
      const refreshed = await service.getGrid(workspace.id, page, 500, gridQuery)
      setGrid(refreshed)
      setWorkspace(current => current ? { ...current, draft: { ...current.draft, version: revision.draftVersion, currentRevisionId: revision.id } } : current)
      setDraftChanges(new Map())
    } catch (cause) {
      setError(apiErrorMessage(cause, 'Unable to save Draft.'))
    } finally {
      setAction(null)
    }
  }, [draftChanges, grid, gridQuery, page, service, workspace])

  const createReview = useCallback(async () => {
    const revisionId = grid?.revisionId ?? workspace?.draft.currentRevisionId
    if (!workspace || !revisionId || draftChanges.size > 0) return
    setAction('reviewing')
    setError(null)
    try {
      setReview(await service.createReview(workspace.id, revisionId))
      setApplyResult(null)
    } catch (cause) {
      setError(apiErrorMessage(cause, 'Unable to generate Review.'))
    } finally {
      setAction(null)
    }
  }, [draftChanges.size, grid?.revisionId, service, workspace])

  const applySelected = useCallback(async () => {
    if (!workspace || !review) return
    const selectedItemIds = review.items.filter(item => item.eligible && selectedListingIds.has(item.listingId)).map(item => item.id)
    if (selectedItemIds.length === 0) {
      setError('Select at least one eligible Listing in the Grid before Apply.')
      return
    }
    setAction('applying')
    setError(null)
    try {
      const selection = await service.saveSelection(workspace.id, review.id, selectedItemIds)
      const idempotencyKey = await workspaceApplyIdempotencyKey(
        workspace.id,
        review.id,
        review.draftRevisionId,
        selection.selectionChecksum,
      )
      setApplyResult(await service.applySelected(workspace.id, review.id, selection.selectionChecksum, idempotencyKey))
      setGrid(await service.getGrid(workspace.id, page, 500, gridQuery))
    } catch (cause) {
      if (cause instanceof ApiError && [
        'STALE_REVIEW',
        'REVIEW_NOT_READY',
        'APPLY_SELECTION_CHECKSUM_MISMATCH',
        'APPLY_REVISION_MISMATCH',
      ].includes(cause.code ?? '')) {
        setReview(null)
      }
      setError(apiErrorMessage(cause, 'Unable to Apply selected changes.'))
    } finally {
      setAction(null)
    }
  }, [gridQuery, page, review, selectedListingIds, service, workspace])

  const toggleChannel = useCallback(async (channelId: string) => {
    if (!preferences) return
    const visible = preferences.visibleChannelIds.includes(channelId)
      ? preferences.visibleChannelIds.filter(item => item !== channelId)
      : [...preferences.visibleChannelIds, channelId]
    try {
      setPreferences(await service.savePreferences({ ...preferences, visibleChannelIds: visible }))
    } catch (cause) {
      setError(apiErrorMessage(cause, 'Unable to save Channel visibility.'))
    }
  }, [preferences, service])

  const setDisplayNameSource = useCallback(async (displayNameSource: string) => {
    if (!preferences) return
    try {
      const saved = await service.savePreferences({ ...preferences, displayNameSource })
      setPreferences(saved)
      setGrid(await service.getGrid(workspaceId, page, 500, gridQuery))
    } catch (cause) {
      setError(apiErrorMessage(cause, 'Unable to save display-name source.'))
    }
  }, [gridQuery, page, preferences, service, workspaceId])

  const updateGridQuery = useCallback((next: WorkspaceGridQuery) => {
    setPage(1)
    setGridQuery(current => ({ ...current, ...next }))
  }, [])

  return {
    workspace, grid, preferences, definition, review, applyResult, loading, action, error,
    dirtyCount: draftChanges.size,
    page,
    totalPages: Math.max(1, Math.ceil((grid?.total ?? 0) / 500)),
    selectedListingCount: selectedListingIds.size,
    setPage, updateGridQuery,
    editCell, saveDraft, createReview, applySelected, toggleChannel, setDisplayNameSource, reload: load,
  }
}

export async function workspaceApplyIdempotencyKey(
  workspaceId: string,
  reviewId: string,
  draftRevisionId: string,
  selectionChecksum: string,
): Promise<string> {
  const canonical = JSON.stringify({
    draftRevisionId,
    operationVersion: 'workspace-apply-v2',
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
