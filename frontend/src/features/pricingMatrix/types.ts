/**
 * Pricing Matrix — frontend types for the CURRENTLY CALLABLE backend contract.
 *
 * Source of truth: FRONTEND_CONTRACT.md (repository root) — "Pricing Matrix
 * Backend Contract", version `v1-draft`, base path `/api/v2/pricing-matrix`.
 *
 * Scope (UI Phase 1): maps ONLY the endpoints documented as implemented today —
 * policy revisions, product-group revisions, unit declarations, and the channel
 * policy lifecycle. The future evidence model in
 * `docs/architecture/PRICING_UI_CONTRACT.md` (Source Acquisition, Diagnostics,
 * Workspace Preview, Apply Result, `allowed_actions`, the `contract_version`
 * envelope) is intentionally NOT represented here and is NOT callable.
 *
 * Conventions taken verbatim from FRONTEND_CONTRACT.md:
 * - Request bodies use snake_case field names (as shown in the doc examples).
 * - Responses use camelCase field names (as shown in the doc examples).
 * - IDs, checksums, and versions are opaque strings; do not parse or do
 *   arithmetic on them.
 * - `headVersion` is an opaque concurrency token: keep it from the last Head
 *   response and send it back unchanged. A 409 (`pricing_policy_head_conflict`)
 *   means refetch the Head and Lifecycle Events before retrying.
 *
 * Fields typed `| null` reflect states the contract implies can be absent (for
 * example an inactive Head with no activation). Where the contract does not
 * enumerate nullability, or the per-rule casing of the PolicyRevision response,
 * the point is filed as an Open Question for Codex in PRICING_UI_CONTRACT.md
 * (PM-5, PM-6) and typed conservatively rather than presented as confirmed.
 */

export const PRICING_MATRIX_BASE_PATH = '/api/v2/pricing-matrix'
export const PRICING_MATRIX_CONTRACT_VERSION = 'v1-draft'

export type RateMode = 'percent_bp' | 'multiplier_ppm'
export type RoundOrder = 'round_then_surcharge' | 'surcharge_then_round'
export type RoundMode = 'floor' | 'ceil' | 'nearest'
export type ChannelStatus = 'active' | 'inactive'
export type LifecycleEventKind = 'activate' | 'deactivate'
export type UnitScope = 'global' | 'source' | 'channel'
export type UnitStatus = 'unresolved' | 'resolved'

/** Standard list envelope returned by the GET collection endpoints. */
export interface ListResponse<T> {
  readonly items: readonly T[]
}

// ---- Policy revisions -------------------------------------------------------

/** One rule inside a `POST /policies` request body (snake_case, per contract). */
export interface PolicyRuleInput {
  readonly channel_id: string
  /** Target a single product OR a product group, never both. */
  readonly product_ref: string | null
  readonly product_group_revision_id: string | null
  readonly rate_mode: RateMode
  /**
   * Basis points (`percent_bp`) or parts-per-million (`multiplier_ppm`).
   * NOTE: the contract's request example shows these as JSON numbers, while its
   * "Important Frontend Rules" say to treat monetary integers as strings where
   * JS precision could be affected. Typed as `number` to match the documented
   * request example; the tension is filed as Open Question PM-4 for Codex.
   */
  readonly rate_value: number
  readonly fixed_addend_minor: number
  readonly round_mode: RoundMode
  readonly round_step_minor: number
  readonly surcharge_minor: number
  readonly guards: Record<string, unknown>
}

export interface CreatePolicyRequest {
  /** Omit to mint a new policy identity; supply to append the next revision. */
  readonly policy_id?: string
  readonly name: string
  readonly computation_currency: string
  readonly round_order: RoundOrder
  readonly max_quote_age_days: number
  readonly min_quote_count: number
  readonly evaluation_timezone: string
  readonly rules: readonly PolicyRuleInput[]
}

/**
 * Per-rule shape inside a `PolicyRevision` response. FRONTEND_CONTRACT.md lists
 * `rules[]` on the response but does not enumerate its per-rule field names;
 * camelCase is inferred to match the rest of the response envelope. Confirm via
 * Open Question PM-6 before building UI that reads individual rule fields.
 */
export interface PolicyRuleView {
  readonly channelId: string
  readonly productRef: string | null
  readonly productGroupRevisionId: string | null
  readonly rateMode: RateMode
  readonly rateValue: string
  readonly fixedAddendMinor: string
  readonly roundMode: RoundMode
  readonly roundStepMinor: string
  readonly surchargeMinor: string
  readonly guards: Record<string, unknown>
}

/** `GET /policies` list element. Summaries omit `rules`, per contract. */
export interface PolicySummary {
  readonly id: string
  readonly policyId: string
  readonly revisionNumber: number
  readonly name: string
  readonly computationCurrency: string
  /** Currently always `min`. */
  readonly basisStrategy: string
  readonly roundOrder: RoundOrder
  readonly maxQuoteAgeDays: number
  readonly minQuoteCount: number
  readonly evaluationTimezone: string
  readonly arithmeticVersion: string
  readonly unitRegistryVersion: string
  readonly checksum: string
  readonly createdAt: string
}

/** `GET /policies/{revisionId}` and `POST /policies` response. */
export interface PolicyRevision extends PolicySummary {
  readonly rules: readonly PolicyRuleView[]
}

// ---- Product group revisions ------------------------------------------------

export interface CreateProductGroupRequest {
  /** Omit to mint a new group identity; supply to append the next revision. */
  readonly product_group_id?: string
  readonly name: string
  readonly canonical_product_ids: readonly string[]
}

export interface ProductGroupRevision {
  readonly id: string
  readonly productGroupId: string
  readonly revisionNumber: number
  readonly name: string
  readonly canonicalProductIds: readonly string[]
  readonly checksum: string
  readonly createdAt: string
}

// ---- Currency unit declarations ---------------------------------------------

export interface UnitDeclarationUnresolved {
  readonly scope: UnitScope
  readonly scopeReference: string
  readonly status: 'unresolved'
  readonly currency: null
  readonly unit: null
}

export interface UnitDeclarationResolved {
  readonly scope: UnitScope
  readonly scopeReference: string
  /** Literal inferred as `resolved` (contract shows only the unresolved example). */
  readonly status: 'resolved'
  readonly canonicalCurrency: string
  readonly canonicalUnit: string
  readonly canonicalFactor: string
  readonly currencyProfileId: string
  readonly version: string
  /** Present only on a channel-scope PUT that created a new config revision. */
  readonly channelConfigRevisionId?: string
}

export type UnitDeclaration = UnitDeclarationUnresolved | UnitDeclarationResolved

export interface PutUnitRequest {
  readonly currency: string
  /** For IRR, explicitly `RIAL` or `TOMAN`; the backend never infers it. */
  readonly unit: string
  readonly connector_config_version: string
}

// ---- Channel policy lifecycle -----------------------------------------------

export interface ChannelPolicyHead {
  readonly channelId: string
  /** Opaque concurrency token — keep and resend unchanged (see file header). */
  readonly headVersion: number
  readonly currentEventId: string | null
  readonly effectiveActivationId: string | null
  readonly status: ChannelStatus
  readonly policyRevisionId: string | null
  readonly channelConfigRevisionId: string | null
  readonly updatedAt: string
}

export interface LifecycleEvent {
  readonly id: string
  readonly channelId: string
  readonly eventKind: LifecycleEventKind
  readonly predecessorEventId: string | null
  readonly effectiveActivationId: string | null
  readonly policyRevisionId: string | null
  readonly channelConfigRevisionId: string | null
  readonly supersedesActivationId: string | null
  readonly actorUserId: string | null
  readonly reason: string | null
  readonly occurredAt: string
}

export interface ActivateRequest {
  readonly policy_revision_id: string
  readonly expected_head_version: number
  readonly reason: string
}

export interface DeactivateRequest {
  readonly expected_head_version: number
  readonly reason: string
}
