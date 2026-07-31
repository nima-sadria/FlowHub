import type { SourceProfile } from '../features/sourceWorkspace/types'
import type { CommerceChannel, CommerceSource } from '../services/types'

export type ResourceQaFixtureState = 'connected' | 'partial' | 'empty'
export const RESOURCE_QA_SOURCE_ID = 'qa-connected-source'

/**
 * Browser-QA state is deliberately development/test only. Production builds
 * always return null, so these fixtures can never present a fabricated state
 * to a real user or alter connector behavior.
 */
export function resourceQaFixtureState(search: string): ResourceQaFixtureState | null {
  if (!import.meta.env.DEV && import.meta.env.MODE !== 'test') return null
  const requested = new URLSearchParams(search).get('qa')
  return requested === 'connected' || requested === 'partial' || requested === 'empty' ? requested : null
}

export function withConnectedSourceFixture(
  profiles: SourceProfile[],
  integrations: CommerceSource[],
): { profiles: SourceProfile[]; integrations: CommerceSource[] } {
  const candidate = integrations.find(item => item.implemented && !item.placeholder)
  if (!candidate) return { profiles, integrations }

  const now = new Date().toISOString()
  const existing = profiles.find(item => item.externalSourceId === candidate.id)
  const connectedProfile: SourceProfile = existing
    ? { ...existing, status: 'active', mappingVersion: Math.max(1, existing.mappingVersion), updatedAt: now }
    : {
      id: RESOURCE_QA_SOURCE_ID,
      name: `${candidate.name} QA`,
      sourceKind: 'external',
      externalSourceId: candidate.id,
      worksheetMode: 'selected',
      worksheetName: 'Products',
      dataStartRow: 2,
      status: 'active',
      version: 1,
      mappingVersion: 1,
      sheetId: null,
      createdAt: now,
      updatedAt: now,
      legacyMapping: null,
    }
  const nextProfiles = existing
    ? profiles.map(item => item.id === existing.id ? connectedProfile : item)
    : [connectedProfile, ...profiles]
  const nextIntegrations = integrations.map(item => item.id === candidate.id ? {
    ...item,
    status: 'active',
    credential_status: 'configured',
    last_health_check: now,
    health: { ...item.health, status: 'healthy', message: '', error_code: null },
    read_status: {
      enabled: true,
      max_reads_per_24h: 10,
      manual_read_allowed: true,
      reads_used_last_24h: 1,
      reads_remaining: 9,
      reset_at: null,
      last_read_at: now,
      last_read_status: 'completed',
      last_row_count: 24,
      last_warning_count: 0,
      last_error_count: 0,
    },
  } : item)
  return { profiles: nextProfiles, integrations: nextIntegrations }
}

export function withConnectedChannelFixture(channels: CommerceChannel[]): CommerceChannel[] {
  const candidate = channels.find(item => item.implemented && !item.placeholder)
  if (!candidate) return channels
  const now = new Date().toISOString()
  return channels.map(item => item.id === candidate.id ? {
    ...item,
    status: 'active',
    credential_status: 'configured',
    configuration_state: 'configured',
    credentials_configured: true,
    credentials_verified: true,
    last_health_check: now,
    health: { ...item.health, status: 'healthy', message: '', error_code: null },
    cached_products: Math.max(24, item.cached_products),
    last_cache_refresh: now,
    cache_refresh_status: 'completed',
  } : item)
}
