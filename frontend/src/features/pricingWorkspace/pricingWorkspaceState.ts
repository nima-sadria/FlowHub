import type { DraftChangeInput } from '../../services/unifiedWorkspace/types'

export const PRICING_WORKSPACE_STATE_VERSION = 2 as const
export const PRICING_WORKSPACE_HISTORY_LIMIT = 100
const MAX_NUMERIC_DIGITS = 100
const MAX_NUMERIC_SCALE = 18

export type PricingField = 'price' | 'stock' | 'status'
export type PricingSelectionMode = 'automatic' | 'manual_selected' | 'manual_deselected'

export interface PricingFieldIdentity {
  readonly productId: string
  readonly listingId: string
  readonly channelId: string
  readonly field: PricingField
}

export interface PricingFieldPolicy {
  readonly writable: boolean
  readonly mapped: boolean
  readonly supported: boolean
  readonly channelEnabled: boolean
  readonly comingSoon: boolean
  readonly valid: boolean
  readonly blockedReason?: string | null
  readonly warning?: string | null
}

export interface PricingFieldDescriptor {
  readonly identity: PricingFieldIdentity
  readonly currentValue: string | null
  readonly targetValue: string | null
  readonly currency: string | null
  readonly unit: string | null
  readonly policy: PricingFieldPolicy
  /** Decimal places retained by deterministic bulk arithmetic. */
  readonly decimalScale?: number
}

export interface PricingFieldChange extends PricingFieldDescriptor {
  readonly key: string
  readonly targetValue: string
  readonly selectionMode: PricingSelectionMode
}

export interface PricingWorkspaceSnapshot {
  readonly changes: Readonly<Record<string, PricingFieldChange>>
}

export interface PricingWorkspaceState {
  readonly schemaVersion: typeof PRICING_WORKSPACE_STATE_VERSION
  readonly workspaceId: string
  /** Immutable Snapshot + Draft scope. Prevents replay into a newer Workspace meaning. */
  readonly scopeId: string
  readonly revision: number
  readonly present: PricingWorkspaceSnapshot
  readonly past: readonly PricingWorkspaceSnapshot[]
  readonly future: readonly PricingWorkspaceSnapshot[]
}

export interface PricingWorkspaceSummary {
  readonly changed: number
  readonly selected: number
  readonly ready: number
  readonly warning: number
  readonly blocked: number
  readonly products: number
  readonly listings: number
  readonly channels: number
  readonly hidden: number
}

export type BulkTransformationKind =
  | 'set_price'
  | 'increase_price_fixed'
  | 'decrease_price_fixed'
  | 'increase_price_percent'
  | 'decrease_price_percent'
  | 'set_stock'
  | 'set_status'

export interface BulkTransformation {
  readonly kind: BulkTransformationKind
  readonly value: string
}

export interface BulkPreviewItem {
  readonly key: string
  readonly descriptor: PricingFieldDescriptor
  readonly previousValue: string
  readonly resultingValue: string | null
  readonly changed: boolean
  readonly blockedReason: string | null
}

export interface BulkTransformationPreview {
  readonly workspaceId: string
  readonly scopeId: string
  readonly stateRevision: number
  readonly operation: BulkTransformation
  readonly items: readonly BulkPreviewItem[]
  readonly productsAffected: number
  readonly listingsAffected: number
  readonly fieldsAffected: number
  readonly blockedItems: number
}

export interface PricingWorkspaceStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

export function pricingFieldKey(identity: PricingFieldIdentity): string {
  assertIdentity(identity)
  return JSON.stringify([identity.productId, identity.listingId, identity.channelId, identity.field])
}

export function parsePricingFieldKey(key: string): PricingFieldIdentity | null {
  try {
    const value: unknown = JSON.parse(key)
    if (!Array.isArray(value) || value.length !== 4) return null
    const [productId, listingId, channelId, field] = value
    if (!isNonEmptyString(productId) || !isNonEmptyString(listingId) || !isNonEmptyString(channelId) || !isPricingField(field)) return null
    return Object.freeze({ productId, listingId, channelId, field })
  } catch {
    return null
  }
}

export function createPricingWorkspaceState(
  workspaceId: string,
  fields: readonly PricingFieldDescriptor[] = [],
  scopeId = workspaceId,
): PricingWorkspaceState {
  if (!isNonEmptyString(workspaceId)) throw new Error('workspaceId is required')
  if (!isNonEmptyString(scopeId)) throw new Error('scopeId is required')
  return freezeState({
    schemaVersion: PRICING_WORKSPACE_STATE_VERSION,
    workspaceId,
    scopeId,
    revision: 0,
    present: snapshotFromDescriptors(fields),
    past: [],
    future: [],
  })
}

/**
 * Registers source/server targets discovered on another page without making data loading an
 * undoable user action. Existing local edits and manual selection decisions always win.
 */
export function registerPricingFields(
  state: PricingWorkspaceState,
  fields: readonly PricingFieldDescriptor[],
): PricingWorkspaceState {
  const descriptors = uniqueDescriptors(fields)
  const present = refreshSnapshot(state.present, descriptors, true)
  const past = state.past.map(snapshot => refreshSnapshot(snapshot, descriptors, false))
  const future = state.future.map(snapshot => refreshSnapshot(snapshot, descriptors, false))
  const changed = present !== state.present
    || past.some((snapshot, index) => snapshot !== state.past[index])
    || future.some((snapshot, index) => snapshot !== state.future[index])
  return changed ? freezeState({ ...state, revision: state.revision + 1, present, past, future }) : state
}

export function editPricingField(
  state: PricingWorkspaceState,
  descriptor: PricingFieldDescriptor,
  targetValue: string,
): PricingWorkspaceState {
  return editPricingFields(state, [{ descriptor, targetValue }])
}

/** Commits paste or other multi-cell input as one undoable operation. */
export function editPricingFields(
  state: PricingWorkspaceState,
  edits: readonly { readonly descriptor: PricingFieldDescriptor; readonly targetValue: string }[],
): PricingWorkspaceState {
  const next = { ...state.present.changes }
  let changed = false
  for (const edit of uniqueEdits(edits)) {
    const key = pricingFieldKey(edit.descriptor.identity)
    const existing = next[key]
    if (valuesEqual(edit.descriptor.currentValue, edit.targetValue)) {
      if (existing) {
        delete next[key]
        changed = true
      }
      continue
    }
    const selectionMode = existing?.selectionMode ?? 'automatic'
    const replacement = makeChange(descriptorForTarget(edit.descriptor, edit.targetValue), edit.targetValue, selectionMode)
    if (!sameChange(existing, replacement)) {
      next[key] = replacement
      changed = true
    }
  }
  return changed ? commitUserSnapshot(state, next) : state
}

export function setPricingFieldSelected(
  state: PricingWorkspaceState,
  identity: PricingFieldIdentity,
  selected: boolean,
): PricingWorkspaceState {
  const key = pricingFieldKey(identity)
  const existing = state.present.changes[key]
  if (!existing || (selected && !isPricingFieldEligible(existing.policy))) return state
  const selectionMode: PricingSelectionMode = selected ? 'manual_selected' : 'manual_deselected'
  if (existing.selectionMode === selectionMode) return state
  return commitUserSnapshot(state, {
    ...state.present.changes,
    [key]: freezeChange({ ...existing, selectionMode }),
  })
}

export function isPricingFieldEligible(policy: PricingFieldPolicy): boolean {
  return policy.writable
    && policy.mapped
    && policy.supported
    && policy.channelEnabled
    && !policy.comingSoon
    && policy.valid
    && !policy.blockedReason
}

export function isPricingFieldSelected(change: PricingFieldChange): boolean {
  if (!isPricingFieldEligible(change.policy)) return false
  return change.selectionMode !== 'manual_deselected'
}

export function pricingFieldChange(
  state: PricingWorkspaceState,
  identity: PricingFieldIdentity,
): PricingFieldChange | null {
  return state.present.changes[pricingFieldKey(identity)] ?? null
}

export function undoPricingWorkspace(state: PricingWorkspaceState): PricingWorkspaceState {
  const previous = state.past[state.past.length - 1]
  if (!previous) return state
  return freezeState({
    ...state,
    revision: state.revision + 1,
    present: previous,
    past: state.past.slice(0, -1),
    future: [state.present, ...state.future].slice(0, PRICING_WORKSPACE_HISTORY_LIMIT),
  })
}

export function redoPricingWorkspace(state: PricingWorkspaceState): PricingWorkspaceState {
  const next = state.future[0]
  if (!next) return state
  return freezeState({
    ...state,
    revision: state.revision + 1,
    present: next,
    past: [...state.past, state.present].slice(-PRICING_WORKSPACE_HISTORY_LIMIT),
    future: state.future.slice(1),
  })
}

export function pricingWorkspaceSummary(
  state: PricingWorkspaceState,
  visibleFields?: ReadonlySet<string>,
): PricingWorkspaceSummary {
  const changes = Object.values(state.present.changes)
  const products = new Set<string>()
  const listings = new Set<string>()
  const channels = new Set<string>()
  let selected = 0
  let ready = 0
  let warning = 0
  let blocked = 0
  let hidden = 0
  for (const change of changes) {
    products.add(change.identity.productId)
    listings.add(change.identity.listingId)
    channels.add(change.identity.channelId)
    if (isPricingFieldSelected(change)) selected += 1
    if (!isPricingFieldEligible(change.policy)) blocked += 1
    else if (change.policy.warning) warning += 1
    else ready += 1
    if (visibleFields && !visibleFields.has(change.key)) hidden += 1
  }
  return Object.freeze({
    changed: changes.length,
    selected,
    ready,
    warning,
    blocked,
    products: products.size,
    listings: listings.size,
    channels: channels.size,
    hidden,
  })
}

export function selectedPricingChanges(state: PricingWorkspaceState): readonly PricingFieldChange[] {
  return Object.values(state.present.changes)
    .filter(isPricingFieldSelected)
    .sort((left, right) => compareKeys(left.key, right.key))
}

export function pricingDraftChanges(state: PricingWorkspaceState): readonly DraftChangeInput[] {
  return Object.values(state.present.changes)
    .sort((left, right) => compareKeys(left.key, right.key))
    .map(change => ({
      canonical_product_id: change.identity.productId,
      listing_id: change.identity.listingId,
      channel_id: change.identity.channelId,
      field: change.identity.field,
      target_value: change.targetValue,
      currency: change.currency,
      unit: change.unit,
    }))
}

export function previewBulkTransformation(
  state: PricingWorkspaceState,
  fields: readonly PricingFieldDescriptor[],
  operation: BulkTransformation,
): BulkTransformationPreview {
  const expectedField = bulkField(operation.kind)
  const descriptors = uniqueDescriptors(fields)
    .filter(descriptor => descriptor.identity.field === expectedField)
    .sort((left, right) => compareKeys(pricingFieldKey(left.identity), pricingFieldKey(right.identity)))
  const items = descriptors.map(descriptor => {
    const key = pricingFieldKey(descriptor.identity)
    const previousValue = state.present.changes[key]?.targetValue ?? descriptor.targetValue ?? descriptor.currentValue ?? ''
    const policyBlock = isPricingFieldEligible(descriptor.policy) ? null : descriptor.policy.blockedReason || 'field_not_eligible'
    const result = policyBlock ? { value: null, error: policyBlock } : transformValue(previousValue, descriptor, operation)
    return Object.freeze({
      key,
      descriptor: freezeDescriptor(descriptor),
      previousValue,
      resultingValue: result.value,
      changed: result.value !== null && result.value !== previousValue,
      blockedReason: result.error,
    })
  })
  const applicable = items.filter(item => !item.blockedReason && item.changed)
  return Object.freeze({
    workspaceId: state.workspaceId,
    scopeId: state.scopeId,
    stateRevision: state.revision,
    operation: Object.freeze({ ...operation }),
    items: Object.freeze(items),
    productsAffected: new Set(applicable.map(item => item.descriptor.identity.productId)).size,
    listingsAffected: new Set(applicable.map(item => item.descriptor.identity.listingId)).size,
    fieldsAffected: applicable.length,
    blockedItems: items.filter(item => item.blockedReason).length,
  })
}

/** Applies a previously displayed preview atomically as one undo step. */
export function applyBulkTransformation(
  state: PricingWorkspaceState,
  preview: BulkTransformationPreview,
): PricingWorkspaceState {
  if (
    preview.workspaceId !== state.workspaceId
    || preview.scopeId !== state.scopeId
    || preview.stateRevision !== state.revision
  ) {
    throw new Error('Stale bulk preview')
  }
  const next = { ...state.present.changes }
  let changed = false
  for (const item of preview.items) {
    const liveValue = next[item.key]?.targetValue ?? item.descriptor.targetValue ?? item.descriptor.currentValue ?? ''
    if (liveValue !== item.previousValue) throw new Error(`Stale bulk preview for ${item.key}`)
    if (item.blockedReason || !item.changed || item.resultingValue === null) continue
    const existing = next[item.key]
    if (valuesEqual(item.descriptor.currentValue, item.resultingValue)) delete next[item.key]
    else next[item.key] = makeChange(descriptorForTarget(item.descriptor, item.resultingValue), item.resultingValue, existing?.selectionMode ?? 'automatic')
    changed = true
  }
  return changed ? commitUserSnapshot(state, next) : state
}

export function serializePricingWorkspaceState(state: PricingWorkspaceState): string {
  const snapshots = (items: readonly PricingWorkspaceSnapshot[]) => items.map(snapshot => sortedChanges(snapshot.changes))
  return JSON.stringify({
    schemaVersion: PRICING_WORKSPACE_STATE_VERSION,
    workspaceId: state.workspaceId,
    scopeId: state.scopeId,
    revision: state.revision,
    present: sortedChanges(state.present.changes),
    past: snapshots(state.past),
    future: snapshots(state.future),
  })
}

export function hydratePricingWorkspaceState(serialized: string, workspaceId: string, scopeId = workspaceId): PricingWorkspaceState {
  try {
    const payload: unknown = JSON.parse(serialized)
    if (!isRecord(payload)
      || payload.schemaVersion !== PRICING_WORKSPACE_STATE_VERSION
      || payload.workspaceId !== workspaceId
      || payload.scopeId !== scopeId
      || !Number.isSafeInteger(payload.revision)
      || !Array.isArray(payload.present)
      || !Array.isArray(payload.past)
      || !Array.isArray(payload.future)) return createPricingWorkspaceState(workspaceId, [], scopeId)
    const present = snapshotFromUnknown(payload.present)
    const past = payload.past.slice(-PRICING_WORKSPACE_HISTORY_LIMIT).map(snapshotFromUnknown)
    const future = payload.future.slice(0, PRICING_WORKSPACE_HISTORY_LIMIT).map(snapshotFromUnknown)
    return freezeState({
      schemaVersion: PRICING_WORKSPACE_STATE_VERSION,
      workspaceId,
      scopeId,
      revision: payload.revision as number,
      present,
      past,
      future,
    })
  } catch {
    return createPricingWorkspaceState(workspaceId, [], scopeId)
  }
}

export function pricingWorkspaceStorageKey(workspaceId: string, scopeId = workspaceId): string {
  return `flowhub:pricing-workspace:v${PRICING_WORKSPACE_STATE_VERSION}:${encodeURIComponent(workspaceId)}:${encodeURIComponent(scopeId)}`
}

export function persistPricingWorkspaceState(storage: PricingWorkspaceStorage, state: PricingWorkspaceState): void {
  storage.setItem(pricingWorkspaceStorageKey(state.workspaceId, state.scopeId), serializePricingWorkspaceState(state))
}

export function restorePricingWorkspaceState(storage: PricingWorkspaceStorage, workspaceId: string, scopeId = workspaceId): PricingWorkspaceState {
  const serialized = storage.getItem(pricingWorkspaceStorageKey(workspaceId, scopeId))
  return serialized ? hydratePricingWorkspaceState(serialized, workspaceId, scopeId) : createPricingWorkspaceState(workspaceId, [], scopeId)
}

export function clearPersistedPricingWorkspaceState(storage: PricingWorkspaceStorage, workspaceId: string, scopeId = workspaceId): void {
  storage.removeItem(pricingWorkspaceStorageKey(workspaceId, scopeId))
}

function commitUserSnapshot(state: PricingWorkspaceState, changes: Record<string, PricingFieldChange>): PricingWorkspaceState {
  return freezeState({
    ...state,
    revision: state.revision + 1,
    present: freezeSnapshot(changes),
    past: [...state.past, state.present].slice(-PRICING_WORKSPACE_HISTORY_LIMIT),
    future: [],
  })
}

function snapshotFromDescriptors(fields: readonly PricingFieldDescriptor[]): PricingWorkspaceSnapshot {
  const changes: Record<string, PricingFieldChange> = {}
  for (const descriptor of uniqueDescriptors(fields)) {
    if (valuesEqual(descriptor.currentValue, descriptor.targetValue)) continue
    const key = pricingFieldKey(descriptor.identity)
    const target = descriptor.targetValue ?? ''
    changes[key] = makeChange(descriptorForTarget(descriptor, target), target, 'automatic')
  }
  return freezeSnapshot(changes)
}

function refreshSnapshot(
  snapshot: PricingWorkspaceSnapshot,
  descriptors: readonly PricingFieldDescriptor[],
  addServerTargets: boolean,
): PricingWorkspaceSnapshot {
  const next = { ...snapshot.changes }
  let changed = false
  for (const descriptor of descriptors) {
    const key = pricingFieldKey(descriptor.identity)
    const existing = next[key]
    if (!existing) {
      if (!addServerTargets || valuesEqual(descriptor.currentValue, descriptor.targetValue)) continue
      const target = descriptor.targetValue ?? ''
      next[key] = makeChange(descriptorForTarget(descriptor, target), target, 'automatic')
      changed = true
      continue
    }
    // If provider/cache state has reached the local target, this is no longer a change.
    if (valuesEqual(descriptor.currentValue, existing.targetValue)) {
      delete next[key]
      changed = true
      continue
    }
    // Rebind every history layer to the latest server-owned capability/freshness policy,
    // then validate its own historic target. Undo must never resurrect stale eligibility.
    const refreshedDescriptor = descriptorForTarget(descriptor, existing.targetValue)
    const refreshed = makeChange(refreshedDescriptor, existing.targetValue, existing.selectionMode)
    if (!sameChange(existing, refreshed)) {
      next[key] = refreshed
      changed = true
    }
  }
  return changed ? freezeSnapshot(next) : snapshot
}

function descriptorForTarget(descriptor: PricingFieldDescriptor, targetValue: string): PricingFieldDescriptor {
  const trimmed = targetValue.trim()
  const inputValid = descriptor.identity.field === 'status'
    ? trimmed.length > 0
    : descriptor.identity.field === 'stock'
      ? /^\d+$/.test(trimmed)
      : /^\d+(?:\.\d+)?$/.test(trimmed)
  return {
    ...descriptor,
    policy: {
      ...descriptor.policy,
      valid: descriptor.policy.valid && inputValid,
      blockedReason: descriptor.policy.blockedReason ?? (inputValid ? null : 'invalid_value'),
    },
  }
}

function uniqueDescriptors(fields: readonly PricingFieldDescriptor[]): PricingFieldDescriptor[] {
  const seen = new Set<string>()
  return fields.map(freezeDescriptor).filter(field => {
    const key = pricingFieldKey(field.identity)
    if (seen.has(key)) throw new Error(`Duplicate pricing field identity: ${key}`)
    seen.add(key)
    return true
  })
}

function uniqueEdits(
  edits: readonly { readonly descriptor: PricingFieldDescriptor; readonly targetValue: string }[],
): Array<{ readonly descriptor: PricingFieldDescriptor; readonly targetValue: string }> {
  const seen = new Set<string>()
  return edits.map(edit => Object.freeze({ descriptor: freezeDescriptor(edit.descriptor), targetValue: edit.targetValue })).filter(edit => {
    const key = pricingFieldKey(edit.descriptor.identity)
    if (seen.has(key)) throw new Error(`Duplicate pricing field edit: ${key}`)
    seen.add(key)
    return true
  })
}

function makeChange(
  descriptor: PricingFieldDescriptor,
  targetValue: string,
  selectionMode: PricingSelectionMode,
): PricingFieldChange {
  const frozen = freezeDescriptor(descriptor)
  return freezeChange({
    ...frozen,
    key: pricingFieldKey(frozen.identity),
    targetValue,
    selectionMode,
  })
}

function freezeDescriptor(descriptor: PricingFieldDescriptor): PricingFieldDescriptor {
  if (!Number.isInteger(descriptor.decimalScale ?? 0) || (descriptor.decimalScale ?? 0) < 0 || (descriptor.decimalScale ?? 0) > 12) {
    throw new Error('decimalScale must be an integer between 0 and 12')
  }
  return Object.freeze({
    ...descriptor,
    identity: Object.freeze({ ...descriptor.identity }),
    policy: Object.freeze({ ...descriptor.policy }),
  })
}

function freezeChange(change: PricingFieldChange): PricingFieldChange {
  return Object.freeze({
    ...change,
    identity: Object.freeze({ ...change.identity }),
    policy: Object.freeze({ ...change.policy }),
  })
}

function freezeSnapshot(changes: Record<string, PricingFieldChange>): PricingWorkspaceSnapshot {
  const frozen: Record<string, PricingFieldChange> = {}
  for (const key of Object.keys(changes).sort(compareKeys)) frozen[key] = freezeChange(changes[key])
  return Object.freeze({ changes: Object.freeze(frozen) })
}

function freezeState(state: PricingWorkspaceState): PricingWorkspaceState {
  return Object.freeze({
    ...state,
    present: freezeSnapshot({ ...state.present.changes }),
    past: Object.freeze(state.past.map(snapshot => freezeSnapshot({ ...snapshot.changes }))),
    future: Object.freeze(state.future.map(snapshot => freezeSnapshot({ ...snapshot.changes }))),
  })
}

function sameChange(left: PricingFieldChange | undefined, right: PricingFieldChange): boolean {
  return Boolean(left
    && left.targetValue === right.targetValue
    && left.currentValue === right.currentValue
    && left.selectionMode === right.selectionMode
    && JSON.stringify(left.policy) === JSON.stringify(right.policy)
    && left.currency === right.currency
    && left.unit === right.unit
    && left.decimalScale === right.decimalScale)
}

function sortedChanges(changes: Readonly<Record<string, PricingFieldChange>>): readonly PricingFieldChange[] {
  return Object.values(changes).sort((left, right) => compareKeys(left.key, right.key))
}

function snapshotFromUnknown(value: unknown): PricingWorkspaceSnapshot {
  if (!Array.isArray(value) || value.length > 50_000) throw new Error('Invalid pricing workspace snapshot')
  const changes: Record<string, PricingFieldChange> = {}
  for (const candidate of value) {
    if (!isPersistedChange(candidate)) throw new Error('Invalid pricing workspace change')
    const identity = candidate.identity
    const key = pricingFieldKey(identity)
    if (candidate.key !== key || changes[key]) throw new Error('Invalid or duplicate pricing workspace identity')
    changes[key] = makeChange({
      identity,
      currentValue: candidate.currentValue,
      targetValue: candidate.targetValue,
      currency: candidate.currency,
      unit: candidate.unit,
      policy: candidate.policy,
      decimalScale: candidate.decimalScale,
    }, candidate.targetValue, candidate.selectionMode)
  }
  return freezeSnapshot(changes)
}

function isPersistedChange(value: unknown): value is PricingFieldChange {
  if (!isRecord(value) || !isRecord(value.identity) || !isRecord(value.policy)) return false
  const identity = value.identity
  const policy = value.policy
  return isNonEmptyString(value.key)
    && isNonEmptyString(identity.productId)
    && isNonEmptyString(identity.listingId)
    && isNonEmptyString(identity.channelId)
    && isPricingField(identity.field)
    && (value.currentValue === null || typeof value.currentValue === 'string')
    && typeof value.targetValue === 'string'
    && (value.currency === null || typeof value.currency === 'string')
    && (value.unit === null || typeof value.unit === 'string')
    && (value.selectionMode === 'automatic' || value.selectionMode === 'manual_selected' || value.selectionMode === 'manual_deselected')
    && typeof policy.writable === 'boolean'
    && typeof policy.mapped === 'boolean'
    && typeof policy.supported === 'boolean'
    && typeof policy.channelEnabled === 'boolean'
    && typeof policy.comingSoon === 'boolean'
    && typeof policy.valid === 'boolean'
    && (policy.blockedReason === undefined || policy.blockedReason === null || typeof policy.blockedReason === 'string')
    && (policy.warning === undefined || policy.warning === null || typeof policy.warning === 'string')
    && (value.decimalScale === undefined || (Number.isInteger(value.decimalScale) && Number(value.decimalScale) >= 0 && Number(value.decimalScale) <= 12))
}

function bulkField(kind: BulkTransformationKind): PricingField {
  if (kind === 'set_stock') return 'stock'
  if (kind === 'set_status') return 'status'
  return 'price'
}

function transformValue(
  current: string,
  descriptor: PricingFieldDescriptor,
  operation: BulkTransformation,
): { value: string | null; error: string | null } {
  if (operation.kind === 'set_status') {
    return operation.value.length ? { value: operation.value, error: null } : { value: null, error: 'status_required' }
  }
  if (operation.kind === 'set_stock') {
    if (!/^\d+$/.test(operation.value) || operation.value.length > MAX_NUMERIC_DIGITS) return { value: null, error: 'invalid_stock' }
    return { value: BigInt(operation.value).toString(), error: null }
  }
  const base = parseDecimal(current)
  const operand = parseDecimal(operation.value)
  if (!operand || (operation.kind !== 'set_price' && !base)) return { value: null, error: 'invalid_numeric_value' }
  if (operand.coefficient < 0n) return { value: null, error: 'negative_operand' }
  let result: Decimal
  if (operation.kind === 'set_price') result = operand
  else if (operation.kind === 'increase_price_fixed') result = addDecimal(base!, operand)
  else if (operation.kind === 'decrease_price_fixed') result = addDecimal(base!, { coefficient: -operand.coefficient, scale: operand.scale })
  else {
    const sign = operation.kind === 'increase_price_percent' ? 1n : -1n
    const percentageBase = { coefficient: 100n * pow10(operand.scale) + sign * operand.coefficient, scale: operand.scale + 2 }
    result = multiplyDecimal(base!, percentageBase)
  }
  if (result.coefficient < 0n) return { value: null, error: 'negative_value' }
  const scale = descriptor.decimalScale ?? (operation.kind === 'set_price' ? operand.scale : base?.scale ?? 0)
  return { value: formatDecimal(roundDecimal(result, scale)), error: null }
}

interface Decimal { readonly coefficient: bigint; readonly scale: number }

function parseDecimal(value: string): Decimal | null {
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(value)
  if (!match) return null
  const fraction = match[3] ?? ''
  if (match[2].length + fraction.length > MAX_NUMERIC_DIGITS || fraction.length > MAX_NUMERIC_SCALE) return null
  const coefficient = BigInt(`${match[1] === '-' ? '-' : ''}${match[2]}${fraction}`)
  return { coefficient, scale: fraction.length }
}

function addDecimal(left: Decimal, right: Decimal): Decimal {
  const scale = Math.max(left.scale, right.scale)
  return {
    coefficient: left.coefficient * pow10(scale - left.scale) + right.coefficient * pow10(scale - right.scale),
    scale,
  }
}

function multiplyDecimal(left: Decimal, right: Decimal): Decimal {
  return { coefficient: left.coefficient * right.coefficient, scale: left.scale + right.scale }
}

function roundDecimal(value: Decimal, scale: number): Decimal {
  if (value.scale <= scale) return { coefficient: value.coefficient * pow10(scale - value.scale), scale }
  const divisor = pow10(value.scale - scale)
  const quotient = value.coefficient / divisor
  const remainder = value.coefficient % divisor
  const rounded = remainder < 0n
    ? quotient - (remainder * -2n >= divisor ? 1n : 0n)
    : quotient + (remainder * 2n >= divisor ? 1n : 0n)
  return { coefficient: rounded, scale }
}

function formatDecimal(value: Decimal): string {
  const negative = value.coefficient < 0n
  const digits = (negative ? -value.coefficient : value.coefficient).toString().padStart(value.scale + 1, '0')
  if (!value.scale) return `${negative ? '-' : ''}${digits}`
  const whole = digits.slice(0, -value.scale)
  const fraction = digits.slice(-value.scale).replace(/0+$/, '')
  return `${negative ? '-' : ''}${whole}${fraction ? `.${fraction}` : ''}`
}

function pow10(power: number): bigint {
  return 10n ** BigInt(power)
}

function valuesEqual(left: string | null, right: string | null): boolean {
  return (left ?? '') === (right ?? '')
}

function compareKeys(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0
}

function assertIdentity(identity: PricingFieldIdentity): void {
  if (!isNonEmptyString(identity.productId) || !isNonEmptyString(identity.listingId) || !isNonEmptyString(identity.channelId) || !isPricingField(identity.field)) {
    throw new Error('Invalid pricing field identity')
  }
}

function isPricingField(value: unknown): value is PricingField {
  return value === 'price' || value === 'stock' || value === 'status'
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
