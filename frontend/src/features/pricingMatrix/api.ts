import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'
import { PRICING_MATRIX_BASE_PATH } from './types'
import type {
  ActivateRequest,
  ChannelPolicyHead,
  CreatePolicyRequest,
  CreateProductGroupRequest,
  DeactivateRequest,
  LifecycleEvent,
  ListResponse,
  PolicyRevision,
  PolicySummary,
  ProductGroupRevision,
  PutUnitRequest,
  UnitDeclaration,
  UnitScope,
} from './types'

const base = PRICING_MATRIX_BASE_PATH
const enc = encodeURIComponent

const json = (method: 'POST' | 'PUT', body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

/**
 * Thin client for the currently callable Pricing Matrix backend contract
 * (docs/development/contracts/FRONTEND_CONTRACT.md). Every method maps 1:1 to a documented, implemented
 * route — none is a mock or a placeholder. Future evidence endpoints
 * (preview, apply, diagnostics, source acquisition) are intentionally absent;
 * see `docs/evidence/architecture/PRICING_UI_CONTRACT.md` and do not add clients for
 * routes that are not yet in docs/development/contracts/FRONTEND_CONTRACT.md.
 */
export const pricingMatrixApi = {
  // Policy revisions
  listPolicies: () =>
    apiFetch<ListResponse<PolicySummary>>(`${base}/policies`, authFetch),
  getPolicy: (revisionId: string) =>
    apiFetch<PolicyRevision>(`${base}/policies/${enc(revisionId)}`, authFetch),
  createPolicy: (payload: CreatePolicyRequest) =>
    apiFetch<PolicyRevision>(`${base}/policies`, authFetch, json('POST', payload)),

  // Product group revisions
  listProductGroups: () =>
    apiFetch<ListResponse<ProductGroupRevision>>(`${base}/product-groups`, authFetch),
  getProductGroup: (revisionId: string) =>
    apiFetch<ProductGroupRevision>(`${base}/product-groups/${enc(revisionId)}`, authFetch),
  createProductGroup: (payload: CreateProductGroupRequest) =>
    apiFetch<ProductGroupRevision>(`${base}/product-groups`, authFetch, json('POST', payload)),

  // Currency unit declarations
  getUnit: (scope: UnitScope, scopeReference: string) =>
    apiFetch<UnitDeclaration>(`${base}/units/${enc(scope)}/${enc(scopeReference)}`, authFetch),
  putUnit: (scope: UnitScope, scopeReference: string, payload: PutUnitRequest) =>
    apiFetch<UnitDeclaration>(`${base}/units/${enc(scope)}/${enc(scopeReference)}`, authFetch, json('PUT', payload)),

  // Channel policy lifecycle
  getChannelHead: (channelId: string) =>
    apiFetch<ChannelPolicyHead>(`${base}/channels/${enc(channelId)}/head`, authFetch),
  listChannelLifecycleEvents: (channelId: string) =>
    apiFetch<ListResponse<LifecycleEvent>>(`${base}/channels/${enc(channelId)}/lifecycle-events`, authFetch),
  activateChannel: (channelId: string, payload: ActivateRequest) =>
    apiFetch<ChannelPolicyHead>(`${base}/channels/${enc(channelId)}/activate`, authFetch, json('POST', payload)),
  deactivateChannel: (channelId: string, payload: DeactivateRequest) =>
    apiFetch<ChannelPolicyHead>(`${base}/channels/${enc(channelId)}/deactivate`, authFetch, json('POST', payload)),
} as const
