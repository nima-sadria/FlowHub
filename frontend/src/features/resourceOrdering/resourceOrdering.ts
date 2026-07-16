import type {
  ChannelHealthItem,
  CommerceChannel,
  CommerceSource,
  CommerceTypeOption,
  ProductChannelPriceState,
  Source,
} from '../../services/types'
import type { WorkspaceChannelDefinition } from '../../services/unifiedWorkspace/types'
import type { SourceChannel, SourceProfile } from '../sourceWorkspace/types'
import { formatChannelDisplayName } from '../unifiedWorkspace/channelDisplayName'

export type ResourceTier = 'configured' | 'attention' | 'disabled' | 'comingSoon'
export type ResourceSection = 'active' | 'disabled' | 'comingSoon'
export type ResourceBadge = 'configured' | 'healthy' | 'warning' | 'disabled' | 'comingSoon'

export interface ResourceOrderingSignals {
  id: string
  displayName: string
  status?: string | null
  healthStatus?: string | null
  credentialStatus?: string | null
  activityStatuses?: readonly (string | null | undefined)[]
  enabled?: boolean | null
  available?: boolean | null
  configured?: boolean | null
  implemented?: boolean | null
  placeholder?: boolean | null
  implementationState?: string | null
}

export interface OrderedResource<T> {
  item: T
  id: string
  displayName: string
  tier: ResourceTier
  section: ResourceSection
  badge: ResourceBadge
}

export interface ResourceSectionGroup<T> {
  key: ResourceSection
  items: readonly OrderedResource<T>[]
}

export interface ResourceCollection<T> {
  ordered: readonly OrderedResource<T>[]
  sections: readonly ResourceSectionGroup<T>[]
  defaultActiveId: string | null
  orderIndex: ReadonlyMap<string, number>
}

export interface DiagnosticResourceLike {
  id?: string | null
  name?: string | null
  connector_type?: string | null
  enabled?: boolean | null
  status?: string | null
  health?: string | null
  credential_status?: string | null
  implemented?: boolean | null
  placeholder?: boolean | null
}

type CommerceChannelRuntime = CommerceChannel & { enabled?: boolean | null }

const TIER_ORDER: Record<ResourceTier, number> = {
  configured: 0,
  attention: 1,
  disabled: 2,
  comingSoon: 3,
}

const SECTION_ORDER: readonly ResourceSection[] = ['active', 'disabled', 'comingSoon']
const COLLATOR = new Intl.Collator(['en', 'fa'], {
  numeric: true,
  sensitivity: 'base',
  usage: 'sort',
})

const COMING_SOON_STATES = new Set([
  'coming_soon',
  'future',
  'planned',
  'not_supported',
  'not_yet_supported',
  'unsupported',
  'placeholder',
])

const DISABLED_STATES = new Set([
  'archived',
  'deactivated',
  'disabled',
  'inactive',
])

const ATTENTION_STATES = new Set([
  'authentication_expiring',
  'completed_with_errors',
  'completed_with_warnings',
  'credentials_expiring',
  'degraded',
  'disconnected',
  'error',
  'expiring',
  'failed',
  'invalid',
  'not_configured',
  'not_run',
  'not_verified',
  'offline',
  'partial',
  'partial_failed',
  'partially_failed',
  'read_failed',
  'refresh_failed',
  'stale',
  'timeout',
  'unable_to_check',
  'unhealthy',
  'unknown',
  'warning',
])

const POSITIVE_STATES = new Set([
  'active',
  'completed',
  'configured',
  'connected',
  'credentials_verified',
  'current',
  'healthy',
  'ok',
  'online',
  'operational',
  'ready',
  'success',
  'valid',
])

const HEALTHY_STATES = new Set(['healthy', 'ok', 'operational'])

function normalizeState(value: string | null | undefined): string {
  return String(value ?? '')
    .trim()
    .toLocaleLowerCase('en-US')
    .replace(/[\s-]+/g, '_')
}

function stateValues(signals: ResourceOrderingSignals): string[] {
  return [
    signals.status,
    signals.healthStatus,
    signals.credentialStatus,
    signals.implementationState,
    ...(signals.activityStatuses ?? []),
  ].map(normalizeState).filter(Boolean)
}

function classify(signals: ResourceOrderingSignals): Pick<OrderedResource<never>, 'tier' | 'section' | 'badge'> {
  const states = stateValues(signals)
  const comingSoon = signals.placeholder === true
    || signals.implemented === false
    || states.some(state => COMING_SOON_STATES.has(state))
  if (comingSoon) return { tier: 'comingSoon', section: 'comingSoon', badge: 'comingSoon' }

  const disabled = signals.enabled === false
    || signals.available === false
    || states.some(state => DISABLED_STATES.has(state))
  if (disabled) return { tier: 'disabled', section: 'disabled', badge: 'disabled' }

  const attention = signals.configured === false
    || states.some(state => ATTENTION_STATES.has(state))
  if (attention) return { tier: 'attention', section: 'active', badge: 'warning' }

  const configured = signals.configured === true
    || signals.enabled === true
    || signals.available === true
    || signals.implemented === true
    || states.some(state => POSITIVE_STATES.has(state))
  if (!configured) return { tier: 'attention', section: 'active', badge: 'warning' }

  const explicitlyHealthy = [signals.healthStatus, signals.status]
    .map(normalizeState)
    .some(state => HEALTHY_STATES.has(state))
  return {
    tier: 'configured',
    section: 'active',
    badge: explicitlyHealthy ? 'healthy' : 'configured',
  }
}

export function prepareResourceCollection<T>(
  items: readonly T[],
  signalsFor: (item: T) => ResourceOrderingSignals,
): ResourceCollection<T> {
  const orderedWithInputPosition = items.map((item, inputPosition) => {
    const signals = signalsFor(item)
    const classification = classify(signals)
    return {
      item,
      id: signals.id,
      displayName: signals.displayName,
      inputPosition,
      ...classification,
    }
  }).sort((left, right) => {
    const tier = TIER_ORDER[left.tier] - TIER_ORDER[right.tier]
    if (tier !== 0) return tier
    const name = COLLATOR.compare(left.displayName, right.displayName)
    return name !== 0 ? name : left.inputPosition - right.inputPosition
  })
  const ordered: OrderedResource<T>[] = orderedWithInputPosition.map(({ inputPosition: _inputPosition, ...resource }) => resource)

  const sections = SECTION_ORDER.flatMap(key => {
    const sectionItems = ordered.filter(item => item.section === key)
    return sectionItems.length ? [{ key, items: sectionItems }] : []
  })
  const orderIndex = new Map(ordered.map((item, index) => [item.id, index]))

  return {
    ordered,
    sections,
    defaultActiveId: ordered.find(item => item.section === 'active')?.id ?? null,
    orderIndex,
  }
}

export function orderRelatedItems<TResource, TItem>(
  items: readonly TItem[],
  resources: ResourceCollection<TResource>,
  resourceId: (item: TItem) => string,
): TItem[] {
  return items.map((item, index) => ({ item, index })).sort((left, right) => {
    const leftRank = resources.orderIndex.get(resourceId(left.item)) ?? Number.MAX_SAFE_INTEGER
    const rightRank = resources.orderIndex.get(resourceId(right.item)) ?? Number.MAX_SAFE_INTEGER
    return leftRank - rightRank || left.index - right.index
  }).map(entry => entry.item)
}

export function preferredResourceId<T>(
  currentId: string | null | undefined,
  resources: ResourceCollection<T>,
): string | null {
  if (currentId && resources.ordered.some(item => item.id === currentId)) return currentId
  return resources.defaultActiveId
}

export function sourceProfileSignals(source: SourceProfile): ResourceOrderingSignals {
  return {
    id: source.id,
    displayName: source.name,
    status: source.status,
    enabled: normalizeState(source.status) !== 'disabled',
    configured: normalizeState(source.status) === 'active' && source.mappingVersion > 0,
    implemented: true,
  }
}

export function legacySourceSignals(source: Source): ResourceOrderingSignals {
  return {
    id: source.id,
    displayName: source.name,
    status: source.status,
    enabled: normalizeState(source.status) !== 'disabled',
    configured: normalizeState(source.status) === 'active',
    implemented: true,
  }
}

export function commerceSourceSignals(source: CommerceSource): ResourceOrderingSignals {
  return {
    id: source.id,
    displayName: source.name,
    status: source.status,
    healthStatus: source.health?.status,
    credentialStatus: source.credential_status,
    activityStatuses: [source.read_status?.last_read_status],
    configured: source.credential_status === 'configured',
    implemented: source.implemented,
    placeholder: source.placeholder,
  }
}

export function commerceChannelSignals(channel: CommerceChannelRuntime): ResourceOrderingSignals {
  return {
    id: channel.id,
    displayName: channel.name,
    status: channel.status,
    healthStatus: channel.health?.status,
    credentialStatus: channel.credential_status,
    activityStatuses: [channel.configuration_state, channel.cache_refresh_status],
    enabled: channel.enabled,
    configured: channel.credential_status === 'configured',
    implemented: channel.implemented,
    placeholder: channel.placeholder,
  }
}

export function commerceTypeSignals(item: CommerceTypeOption): ResourceOrderingSignals {
  return {
    id: item.id,
    displayName: item.name,
    configured: item.implemented && !item.placeholder,
    implemented: item.implemented,
    placeholder: item.placeholder,
  }
}

export function channelIdentitySignals<T extends { channelId: string }>(
  item: T,
  displayName?: string | null,
): ResourceOrderingSignals {
  return {
    id: item.channelId,
    displayName: formatChannelDisplayName(item.channelId, { displayName }),
    enabled: true,
    configured: true,
    implemented: true,
  }
}

export function sourceChannelSignals(channel: SourceChannel): ResourceOrderingSignals {
  const implementationState = normalizeState(channel.implementationState)
  return {
    id: channel.channelId,
    displayName: channel.name,
    enabled: channel.enabled,
    available: channel.available,
    configured: channel.available,
    implemented: implementationState === 'implemented'
      ? true
      : COMING_SOON_STATES.has(implementationState)
        ? false
        : undefined,
    implementationState: channel.implementationState,
  }
}

export function workspaceChannelSignals(channel: WorkspaceChannelDefinition): ResourceOrderingSignals {
  return {
    id: channel.channelId,
    displayName: formatChannelDisplayName(channel.channelId, {
      displayName: channel.displayName,
      instanceLabel: channel.instanceLabel,
    }),
    status: channel.healthState,
  }
}

export function productChannelSignals(channel: ProductChannelPriceState): ResourceOrderingSignals {
  const connectionState = normalizeState(channel.connectionState)
  return {
    id: channel.channelId,
    displayName: channel.channelName,
    status: channel.connectionState,
    healthStatus: channel.healthStatus,
    activityStatuses: [channel.validationState],
    configured: ['configured', 'connected'].includes(connectionState)
      ? true
      : connectionState === 'not_configured'
        ? false
        : undefined,
  }
}

export function diagnosticChannelSignals(channel: ChannelHealthItem): ResourceOrderingSignals {
  return {
    id: channel.channelId,
    displayName: formatChannelDisplayName(channel.channelId),
    status: channel.state ?? channel.status,
    enabled: channel.enabled,
    configured: channel.enabled,
  }
}

export function diagnosticSourceSignals(source: DiagnosticResourceLike): ResourceOrderingSignals {
  const id = source.id?.trim() || source.connector_type?.trim() || source.name?.trim() || 'unknown-source'
  return {
    id,
    displayName: source.name?.trim() || source.connector_type?.trim() || id,
    status: source.status,
    healthStatus: source.health,
    credentialStatus: source.credential_status,
    enabled: source.enabled,
    configured: source.credential_status === 'configured' ? true : undefined,
    implemented: source.implemented,
    placeholder: source.placeholder,
  }
}
