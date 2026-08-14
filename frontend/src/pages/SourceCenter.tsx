import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { useAuth } from '../auth'
import type { BadgeVariant } from '../components/Badge'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import { ManagementResourceSections } from '../components/ResourceOrdering'
import OperationalResourceCard, { type OperationalResourceAction, type OperationalResourceState } from '../components/OperationalResourceCard'
import {
  prepareResourceCollection,
  type ResourceBadge,
  type ResourceOrderingSignals,
  type ResourceTier,
} from '../features/resourceOrdering/resourceOrdering'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceLifecycleImpact, SourceMapping, SourceProfile } from '../features/sourceWorkspace/types'
import { translate } from '../i18n'
import { formatDataRole, formatStatus } from '../i18n/display'
import { formatNumber, formatRelativeTime } from '../i18n/format'
import { localizedApiError } from '../i18n/errors'
import { useNotification } from '../notifications/NotificationProvider'
import { useServices } from '../services/ServiceContext'
import type { CommerceSource } from '../services/types'
import { effectiveHasPerm } from '../utils/permissions'
import { WORKSPACE_PERMISSION } from '../utils/workspacePermissions'
import { RESOURCE_QA_SOURCE_ID, resourceQaFixtureState, withConnectedSourceFixture } from '../dev/resourceQaFixtures'

const KIND_LABELS: Record<SourceProfile['sourceKind'], string> = {
  flowhub_sheet: 'sources:sourceCenter.flowhubSheet',
  imported_sheet: 'sources:sourceCenter.importedSpreadsheet',
  external: 'sources:sourceCenter.linkedExternalSource',
}

type SourceFilter = 'all' | 'active' | 'attention' | 'disabled' | 'archived' | 'comingSoon'

interface SourceCardModel {
  id: string
  displayName: string
  profile: SourceProfile | null
  integration: CommerceSource | null
}

function sourceIsEnabled(source: SourceProfile): boolean {
  const lifecycle = source.status.trim().toLocaleLowerCase()
  return lifecycle !== 'disabled' && lifecycle !== 'archived'
}

function sourceIsArchived(source: SourceProfile): boolean {
  return source.status.trim().toLocaleLowerCase() === 'archived'
}

function sourceConfigurationState(source: CommerceSource): string {
  return source.configuration_state
    ?? (source.credential_status === 'configured' ? 'configured' : 'not_configured')
}

function sourceCardSignals(card: SourceCardModel): ResourceOrderingSignals {
  if (!card.profile && card.integration) {
    const configurationState = sourceConfigurationState(card.integration)
    return {
      id: card.id,
      displayName: card.displayName,
      enabled: card.integration.enabled,
      configured: configurationState === 'configured',
      healthStatus: card.integration.health?.status === 'unknown' ? undefined : card.integration.health?.status,
      activityStatuses: [card.integration.read_status?.last_read_status],
      implemented: card.integration.implemented,
      placeholder: card.integration.placeholder,
    }
  }

  const source = card.profile as SourceProfile
  const integration = card.integration
  const active = source.status === 'active'
  const sourceEnabled = sourceIsEnabled(source)
  const integrationAvailable = !integration || (integration.implemented && !integration.placeholder)
  const integrationEnabled = integration?.enabled !== false
  return {
    id: card.id,
    displayName: card.displayName,
    status: source.status,
    // A linked external connector is the effective runtime switch.  Do not
    // render an active Source profile as operational when its connector is
    // deliberately disabled.
    enabled: sourceEnabled && integrationAvailable && integrationEnabled,
    configured: active
      && integrationAvailable
      && source.mappingVersion > 0
      && (source.sourceKind !== 'external'
        || (integration !== null && sourceConfigurationState(integration) === 'configured')),
    healthStatus: integration?.health?.status === 'unknown' ? undefined : integration?.health?.status,
    activityStatuses: [integration?.read_status?.last_read_status],
    implemented: integrationAvailable,
    placeholder: integration?.placeholder ?? false,
  }
}

function sourceCardDescription(card: SourceCardModel): string {
  if (card.profile) return translate(KIND_LABELS[card.profile.sourceKind])
  if (card.integration?.provider === 'erp' || card.integration?.id === 'erp:api-import') {
    return translate('sources:sourceCenter.erpApiImportDescription')
  }
  const rawRole = card.integration?.data_role
  const localizedRole = formatDataRole(rawRole)
  return rawRole && localizedRole !== rawRole
    ? localizedRole
    : translate('sources:sourceCenter.externalSourceDescription')
}

function matchesFilter(state: OperationalResourceState, filter: SourceFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'active') return state === 'connected' || state === 'setupRequired' || state === 'needsAttention'
  if (filter === 'attention') return state === 'needsAttention'
  if (filter === 'archived') return state === 'archived'
  return state === filter
}

function sourceBadgeTone(badge: ResourceBadge): BadgeVariant {
  if (badge === 'healthy' || badge === 'configured') return 'success'
  if (badge === 'warning') return 'warning'
  if (badge === 'disabled') return 'disabled'
  if (badge === 'archived') return 'neutral'
  return 'neutral'
}

function sourceBadgeLabel(badge: ResourceBadge): string {
  if (badge === 'healthy' || badge === 'configured') return translate('common:status.connected')
  if (badge === 'warning') return translate('common:status.setupRequired')
  if (badge === 'disabled') return translate('common:status.disabled')
  if (badge === 'archived') return translate('common:status.archived')
  return translate('common:resourceBadge.comingSoon')
}

function sourceSetupPresentation(
  card: SourceCardModel,
  fallbackBadge: ResourceBadge,
): { label: string; variant: BadgeVariant } {
  const integration = card.integration
  if (card.profile && sourceIsArchived(card.profile)) {
    return {
      label: translate('common:status.archived'),
      variant: 'neutral',
    }
  }
  if (!integration || integration.placeholder || !integration.implemented) {
    return {
      label: sourceBadgeLabel(fallbackBadge),
      variant: sourceBadgeTone(fallbackBadge),
    }
  }
  if ((card.profile !== null && !sourceIsEnabled(card.profile)) || integration.enabled === false) {
    return {
      label: translate('common:status.disabled'),
      variant: 'disabled',
    }
  }
  if (sourceNeedsOperationalAttention(integration)) {
    return {
      label: translate('sources:sourceCenter.needsAttentionKpi'),
      variant: 'warning',
    }
  }
  const linkedProfileComplete = !card.profile
    || (sourceIsEnabled(card.profile) && card.profile.mappingVersion > 0)
  if (sourceConfigurationState(integration) === 'configured' && linkedProfileComplete) {
    return {
      label: translate('commerce:commerceHub.sourceStatus.configured'),
      variant: 'success',
    }
  }
  if (integration.connection_configured || integration.credential_status === 'configured') {
    return {
      label: translate('commerce:commerceHub.sourceStatus.connectedSetupRequired'),
      variant: 'info',
    }
  }
  return {
    label: translate('commerce:commerceHub.sourceStatus.addNow'),
    variant: 'warning',
  }
}

function cardUpdatedAt(card: SourceCardModel): string | null {
  return card.profile?.updatedAt ?? card.integration?.read_status?.last_read_at ?? null
}

function operationalState(card: SourceCardModel, tier: ResourceTier): OperationalResourceState {
  if (tier === 'comingSoon') return 'comingSoon'
  if (tier === 'archived') return 'archived'
  if (tier === 'disabled') return 'disabled'
  if (sourceNeedsOperationalAttention(card.integration)) return 'needsAttention'
  if (tier === 'configured') return 'connected'
  return 'setupRequired'
}

function sourceNeedsOperationalAttention(source: CommerceSource | null): boolean {
  if (!source) return false
  return ['degraded', 'error', 'failed', 'partial_failed', 'unhealthy'].includes(source.health.status)
    || ['failed', 'partial_failed', 'completed_with_errors'].includes(source.read_status?.last_read_status ?? '')
}

/** Keep the card action aligned with the actual provider setup boundary. */
function setupDestinationFor(card: SourceCardModel): string | null {
  if (card.integration?.id === 'csv:import') return '/sources/import'
  if (card.integration?.implemented && !card.integration.placeholder && card.integration.configuration_state !== 'configured') {
    return `/commerce?tab=sources&resource=${encodeURIComponent(card.integration.id)}`
  }
  if (card.profile) return `/sources/${card.profile.id}`
  if (card.integration?.implemented && !card.integration.placeholder) {
    return `/commerce?tab=sources&resource=${encodeURIComponent(card.integration.id)}`
  }
  return null
}

export default function SourceCenter() {
  const navigate = useNavigate()
  const location = useLocation()
  const { commerce, products } = useServices()
  const { user } = useAuth()
  const notify = useNotification()
  const [sources, setSources] = useState<SourceProfile[]>([])
  const [integrations, setIntegrations] = useState<CommerceSource[]>([])
  const [worksheetMappings, setWorksheetMappings] = useState<Record<string, SourceMapping | null>>({})
  const [totalProducts, setTotalProducts] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [partialLoadError, setPartialLoadError] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const [creating, setCreating] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<SourceFilter>('all')
  const [addPanelOpen, setAddPanelOpen] = useState(false)
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<SourceProfile | null>(null)
  const [pendingImpact, setPendingImpact] = useState<SourceLifecycleImpact | null>(null)
  const [checkingImpact, setCheckingImpact] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const removalOverlayRef = useRef<HTMLDivElement | null>(null)
  const removalCancelRef = useRef<HTMLButtonElement | null>(null)
  const removalTriggerRef = useRef<HTMLButtonElement | null>(null)
  const removalBusyRef = useRef(false)
  const impactRequestRef = useRef(0)
  const canCreateSources = effectiveHasPerm(user, WORKSPACE_PERMISSION.create)
  const canEditSources = effectiveHasPerm(user, WORKSPACE_PERMISSION.edit)
  const canManageSources = effectiveHasPerm(user, WORKSPACE_PERMISSION.admin)
  const canManageConnectors = user?.is_admin === true
  const canViewActivity = effectiveHasPerm(user, WORKSPACE_PERMISSION.readAudit)
  const canViewDiagnostics = effectiveHasPerm(user, 'can_view_settings')
  const qaFixture = resourceQaFixtureState(location.search)

  const cards = useMemo<SourceCardModel[]>(() => {
    const integrationById = new Map(integrations.map(item => [item.id, item]))
    const integrationIdFor = (profile: SourceProfile) => profile.externalSourceId
      ?? (integrationById.has(profile.id) ? profile.id : null)
    const linkedIntegrationIds = new Set(sources.flatMap(profile => {
      const integrationId = integrationIdFor(profile)
      return integrationId ? [integrationId] : []
    }))
    return [
      ...sources.map(profile => ({
        id: profile.id,
        displayName: profile.name,
        profile,
        integration: integrationIdFor(profile)
          ? integrationById.get(integrationIdFor(profile) as string) ?? null
          : null,
      })),
      ...integrations
        .filter(integration => !linkedIntegrationIds.has(integration.id))
        .map(integration => ({
          id: `integration:${integration.id}`,
          displayName: integration.name,
          profile: null,
          integration,
        })),
    ]
  }, [integrations, sources])

  const sourceResources = useMemo(
    () => prepareResourceCollection(cards, sourceCardSignals),
    [cards],
  )
  const visibleCards = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    return sourceResources.ordered
      .filter(resource => matchesFilter(operationalState(resource.item, resource.tier), filter))
      .filter(resource => !normalizedQuery
        || resource.displayName.toLocaleLowerCase().includes(normalizedQuery)
        || resource.item.integration?.provider.toLocaleLowerCase().includes(normalizedQuery))
  }, [filter, query, sourceResources])

  const needsAttentionCount = useMemo(
    () => sourceResources.ordered.filter(resource => operationalState(resource.item, resource.tier) === 'needsAttention').length,
    [sourceResources],
  )
  const connectedSourcesCount = useMemo(
    () => sourceResources.ordered.filter(resource => operationalState(resource.item, resource.tier) === 'connected').length,
    [sourceResources],
  )
  const setupRequiredSourcesCount = useMemo(
    () => sourceResources.ordered.filter(resource => operationalState(resource.item, resource.tier) === 'setupRequired').length,
    [sourceResources],
  )
  const filtersActive = query.trim().length > 0 || filter !== 'all'

  removalBusyRef.current = deleting

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError(false)
    setPartialLoadError(false)
    Promise.allSettled([
      sourceWorkspaceApi.listSources(),
      commerce.getSources(),
      products.getProducts({ search: '', status: 'all', page: 1, pageSize: 1 }),
    ])
      .then(([managedResult, integrationResult, productsResult]) => {
        if (!active) return
        let nextSources = managedResult.status === 'fulfilled' ? managedResult.value.items : []
        let nextIntegrations = integrationResult.status === 'fulfilled' ? integrationResult.value.items : []
        if (qaFixture === 'empty') {
          nextSources = []
          nextIntegrations = nextIntegrations.filter(item => item.placeholder || !item.implemented)
        } else if (qaFixture === 'connected') {
          const fixture = withConnectedSourceFixture(nextSources, nextIntegrations)
          nextSources = fixture.profiles
          nextIntegrations = fixture.integrations
        }
        if (managedResult.status === 'fulfilled' || qaFixture === 'connected' || qaFixture === 'empty') setSources(nextSources)
        if (integrationResult.status === 'fulfilled' || qaFixture === 'connected' || qaFixture === 'empty') setIntegrations(nextIntegrations)
        if (productsResult.status === 'fulfilled') setTotalProducts(productsResult.value.total)
        const authoritativeUnavailable = managedResult.status === 'rejected' && integrationResult.status === 'rejected'
        setLoadError(authoritativeUnavailable)
        setPartialLoadError(qaFixture === 'partial' || (!authoritativeUnavailable && [managedResult, integrationResult, productsResult].some(result => result.status === 'rejected')))
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [commerce, products, qaFixture, reloadToken])

  useEffect(() => {
    let active = true
    const managedIds = sources.filter(source => source.mappingVersion > 0 && source.id !== RESOURCE_QA_SOURCE_ID).map(source => source.id)
    if (managedIds.length === 0) return
    Promise.allSettled(managedIds.map(id => sourceWorkspaceApi.source(id))).then(results => {
      if (!active) return
      setWorksheetMappings(current => {
        const next = { ...current }
        results.forEach((result, index) => {
          if (result.status === 'fulfilled') next[managedIds[index]] = result.value.mapping
        })
        return next
      })
    })
    return () => { active = false }
  }, [sources])

  useEffect(() => {
    if (!addPanelOpen) return
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setAddPanelOpen(false)
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [addPanelOpen])

  useEffect(() => {
    if (!openMenuId) return
    const close = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null
      if (target?.closest('[data-source-menu]')) return
      setOpenMenuId(null)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [openMenuId])

  useEffect(() => {
    if (!pendingDelete) return
    const overlay = removalOverlayRef.current
    const parent = overlay?.parentElement
    const trigger = removalTriggerRef.current
    const backgroundSiblings = parent && overlay
      ? Array.from(parent.children).filter(element => element !== overlay) as HTMLElement[]
      : []
    const previousAccessibility = backgroundSiblings.map(element => ({
      element,
      ariaHidden: element.getAttribute('aria-hidden'),
      inert: element.hasAttribute('inert'),
    }))

    for (const element of backgroundSiblings) {
      element.setAttribute('aria-hidden', 'true')
      element.setAttribute('inert', '')
    }
    removalCancelRef.current?.focus()

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !removalBusyRef.current) {
        event.preventDefault()
        impactRequestRef.current += 1
        setPendingDelete(null)
        setPendingImpact(null)
        return
      }
      if (event.key !== 'Tab' || !overlay) return
      const focusable = Array.from(overlay.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ))
      if (focusable.length === 0) {
        event.preventDefault()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      for (const item of previousAccessibility) {
        if (item.ariaHidden === null) item.element.removeAttribute('aria-hidden')
        else item.element.setAttribute('aria-hidden', item.ariaHidden)
        if (!item.inert) item.element.removeAttribute('inert')
      }
      trigger?.focus()
    }
  }, [pendingDelete])

  async function createFlowHubSheet() {
    setCreating(true)
    try {
      const sheet = await sourceWorkspaceApi.createSheet(translate('sources:sourceCenter.defaultPricingSheetName'))
      navigate(`/sheets/${sheet.id}`)
    } catch {
      notify.error({
        title: translate('sources:sourceCenter.sheetCreationFailed'),
        description: translate('sources:sourceCenter.sheetCreationRecovery'),
      })
    } finally {
      setCreating(false)
    }
  }

  async function removeSource() {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      const result = await sourceWorkspaceApi.deleteSource(pendingDelete)
      setSources(current => result.outcome === 'deleted'
        ? current.filter(item => item.id !== pendingDelete.id)
        : current.map(item => item.id === pendingDelete.id ? result.source ?? item : item))
      notify.success({
        title: result.outcome === 'deleted'
          ? translate('sources:sourceCenter.sourceDeleted')
          : translate('sources:sourceCenter.sourceArchived'),
        description: result.outcome === 'deleted'
          ? translate('sources:sourceCenter.unusedSourceDeletedSafely')
          : translate('sources:sourceCenter.protectedHistoryPreserved'),
      })
      setPendingDelete(null)
    } catch (error) {
      notify.error({
        title: translate('sources:sourceCenter.sourceCouldNotBeRemoved'),
        description: localizedApiError(error, 'sources:sourceCenter.activeWorkspacePreventsRemoval'),
      })
    } finally {
      setDeleting(false)
    }
  }

  async function openRemoval(source: SourceProfile) {
    const requestId = impactRequestRef.current + 1
    impactRequestRef.current = requestId
    setOpenMenuId(null)
    setPendingDelete(source)
    setPendingImpact(null)
    setCheckingImpact(true)
    try {
      const impact = await sourceWorkspaceApi.sourceLifecycle(source.id)
      if (impactRequestRef.current !== requestId || impact.sourceId !== source.id) return
      setPendingImpact(impact)
    } catch (error) {
      if (impactRequestRef.current !== requestId) return
      notify.error({
        title: translate('sources:sourceCenter.sourceCouldNotBeRemoved'),
        description: localizedApiError(error, 'sources:sourceCenter.removalImpactUnavailable'),
      })
      setPendingDelete(null)
    } finally {
      if (impactRequestRef.current === requestId) setCheckingImpact(false)
    }
  }

  function worksheetsEnabledCount(card: SourceCardModel): number | null {
    if (!card.profile) return null
    if (card.profile.mappingVersion === 0) return 0
    const mapping = worksheetMappings[card.profile.id]
    if (mapping === undefined) return null
    if (!mapping) return 0
    if (mapping.worksheetRules && mapping.worksheetRules.length > 0) {
      return mapping.worksheetRules.filter(rule => rule.enabled).length
    }
    return mapping.worksheetName ? 1 : 0
  }

  const filterOptions: Array<{ value: SourceFilter; label: string }> = [
    { value: 'all', label: translate('sources:sourceCenter.allHealthStates') },
    { value: 'active', label: translate('common:resourceGroup.active') },
    { value: 'attention', label: translate('sources:sourceCenter.needsReview') },
    { value: 'disabled', label: translate('common:resourceGroup.disabled') },
    { value: 'archived', label: translate('common:resourceGroup.archived') },
    { value: 'comingSoon', label: translate('common:resourceGroup.comingSoon') },
  ]

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('sources:sourceCenter.sources')}</h1>
          <p className="fh-page-subtitle">{translate('sources:sourceCenter.operationalSubtitle')}</p>
        </div>
        {canCreateSources && (
          <button className="fh-button-primary" type="button" onClick={() => setAddPanelOpen(true)}>
            <Icon name="add" /> {translate('sources:sources.addSource')}
          </button>
        )}
      </div>

      <section className="fh-card fh-card-pad mb-5" aria-label={translate('sources:sourceCenter.operationalFlow')}>
        <p className="fh-text-body-sm font-semibold text-text-base" dir="ltr">{translate('sources:sourceCenter.operationalFlow')}</p>
        <p className="fh-text-caption mt-1">{translate('sources:sourceCenter.operationalFlowHelp')}</p>
      </section>

      <div className="fh-sources-kpi-row">
        <div className="fh-kpi-card">
          <div className="fh-kpi-card-head">
            <span className="fh-kpi-card-label">{translate('sources:sourceCenter.connectedSources')}</span>
            <span className="fh-kpi-card-icon"><Icon name="products" size="sm" /></span>
          </div>
          <div className="fh-kpi-card-value">{formatNumber(connectedSourcesCount)}</div>
        </div>
        <div className="fh-kpi-card">
          <div className="fh-kpi-card-head">
            <span className="fh-kpi-card-label">{translate('sources:sourceCenter.needsAttentionKpi')}</span>
            <span className="fh-kpi-card-icon"><Icon name="products" size="sm" /></span>
          </div>
          <div className="fh-kpi-card-value">
            {formatNumber(needsAttentionCount)}
            {needsAttentionCount > 0 && <span className="fh-kpi-card-trend fh-kpi-card-trend-danger">{translate('sources:sourceCenter.reviewCaption')}</span>}
          </div>
        </div>
        <div className="fh-kpi-card">
          <div className="fh-kpi-card-head">
            <span className="fh-kpi-card-label">{translate('sources:sourceCenter.productsImported')}</span>
            <span className="fh-kpi-card-icon"><Icon name="products" size="sm" /></span>
          </div>
          <div className="fh-kpi-card-value">{totalProducts !== null ? formatNumber(totalProducts) : '—'}</div>
        </div>
      </div>

      <div className="fh-sources-toolbar">
        <form className="fh-sources-search" onSubmit={event => event.preventDefault()}>
          <Icon name="search" size="sm" className="fh-sources-search-icon" />
          <input
            className="fh-sources-search-input"
            type="search"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder={translate('sources:sourceCenter.searchSources')}
            aria-label={translate('sources:sourceCenter.searchSources')}
          />
          {query && <button type="button" className="fh-sources-search-clear" aria-label={translate('sources:sourceCenter.clearSearch')} onClick={() => setQuery('')}><Icon name="close" size="sm" /></button>}
        </form>
        <label className="fh-chip-select">
          <span className="sr-only">{translate('sources:sourceCenter.allHealthStates')}</span>
          <select value={filter} onChange={event => setFilter(event.target.value as SourceFilter)}>
            {filterOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          <Icon name="chevronDown" size="sm" className="fh-chip-caret" />
        </label>
        <span className="fh-sources-count ms-auto">{translate('sources:sourceCenter.sourcesCount', { count: cards.length, value: formatNumber(cards.length) })}</span>
      </div>

      {loadError && !loading ? (
        <div className="fh-alert fh-alert-danger mb-4" role="alert">
          <Icon name="error" />
          <span className="flex-1">{translate('sources:sourceCenter.loadFailed')}</span>
          <button type="button" className="fh-button-secondary fh-button-sm" onClick={() => setReloadToken(value => value + 1)}>
            {translate('common:action.retry')}
          </button>
        </div>
      ) : null}

      {partialLoadError && !loading ? (
        <div className="fh-alert fh-alert-warning mb-4" role="status">
          <Icon name="warning" />
          <span className="flex-1">
            <strong className="block">{translate('sources:sourceCenter.partialLoadTitle')}</strong>
            <span className="fh-text-caption">{translate('sources:sourceCenter.partialLoadDescription')}</span>
          </span>
          <button type="button" className="fh-button-secondary fh-button-sm" onClick={() => setReloadToken(value => value + 1)}>{translate('common:action.retry')}</button>
          {canViewDiagnostics && <button type="button" className="fh-button-secondary fh-button-sm" onClick={() => navigate('/diagnostics')}>{translate('common:action.diagnostics')}</button>}
        </div>
      ) : null}

      {!loading && !loadError && !filtersActive && connectedSourcesCount === 0 && setupRequiredSourcesCount === 0 && (
        <div className="fh-card fh-card-pad mb-5" data-testid="sources-onboarding-empty-state">
          <Empty
            title={translate('sources:sourceCenter.noManagedSourceYetCreateAFlowhub')}
            description={translate('sources:sourceCenter.recommendedForEasierMappingSafeFormulasAnd')}
            action={canCreateSources ? { label: translate('sources:sources.addSource'), onClick: () => setAddPanelOpen(true) } : undefined}
          />
        </div>
      )}

      {loading ? <p className="fh-card fh-card-pad fh-text-caption" role="status" aria-live="polite" aria-busy="true">{translate('sources:sourceCenter.loadingSources')}</p> : loadError ? null : visibleCards.length === 0 && (filtersActive || cards.length > 0) ? (
        <div className="fh-card fh-card-pad" data-testid="sources-filter-empty-state">
          <Empty
            title={translate('sources:sourceCenter.noSourcesFound')}
            description={translate('sources:sourceCenter.adjustSearchOrFilters')}
            action={{ label: translate('sources:sourceCenter.clearFilters'), onClick: () => { setQuery(''); setFilter('all') } }}
          />
        </div>
      ) : visibleCards.length === 0 ? null : (
        <div data-testid="source-card-groups">
          <ManagementResourceSections resources={prepareResourceCollection(visibleCards.map(resource => resource.item), sourceCardSignals)} className="fh-sources-grid" setupRequiredLabel={translate('sources:sourceCenter.availableSources')} groupFor={resource => operationalState(resource.item, resource.tier)} renderItem={resource => {
            const card = resource.item
            const source = card.profile
            const integration = card.integration
            const state = operationalState(card, resource.tier)
            const statusPresentation = sourceSetupPresentation(card, resource.badge)
            const showDelete = Boolean(state === 'connected' && canManageSources && source?.status === 'active')
            const updatedAt = cardUpdatedAt(card)
            const worksheetsEnabled = worksheetsEnabledCount(card)
            const readStatus = integration?.read_status
            const lastReadAt = readStatus?.last_read_at ?? null
            const validationStatus = readStatus
              ? translate('sources:sourceCenter.validationSummary', {
                warnings: formatNumber(readStatus.last_warning_count ?? 0),
                errors: formatNumber(readStatus.last_error_count ?? 0),
              })
              : source?.mappingVersion
                ? translate('sources:sourceCenter.mappingReady')
                : translate('sources:sourceCenter.mappingRequired')
            const setupReason = source && sourceIsArchived(source)
              ? translate('sources:sourceCenter.archivedReadOnly')
              : (source && !sourceIsEnabled(source)) || integration?.enabled === false
                ? translate('sources:sourceCenter.setupReasonDisabled')
              : integration && integration.credential_status !== 'configured'
                ? translate('sources:sourceCenter.setupReasonConnection')
                : translate('sources:sourceCenter.setupReasonMapping')
            const facts = state === 'comingSoon' ? [] : state === 'setupRequired' || state === 'disabled' || state === 'archived'
              ? [
                { label: translate('sources:sourceCenter.sourceTypeLabel'), value: sourceCardDescription(card) },
                { label: translate('sources:sourceCenter.validationStatus'), value: validationStatus },
              ]
              : [
                { label: translate('sources:sourceCenter.sourceTypeLabel'), value: sourceCardDescription(card) },
                { label: translate('sources:sourceCenter.healthLabel'), value: formatStatus(integration?.health.status ?? source?.status) },
                { label: translate('sources:sourceCenter.lastSuccessfulRead'), value: lastReadAt ? formatRelativeTime(lastReadAt) : translate('sources:sourceCenter.notReadYet') },
                ...(readStatus?.last_row_count !== null && readStatus?.last_row_count !== undefined
                  ? [{ label: translate('sources:sourceCenter.recordsImported'), value: formatNumber(readStatus.last_row_count) }]
                  : []),
                { label: translate('sources:sourceCenter.validationStatus'), value: validationStatus },
                { label: translate('sources:sourceCenter.dataFreshness'), value: lastReadAt || updatedAt ? formatRelativeTime((lastReadAt ?? updatedAt) as string) : translate('sources:sourceCenter.notReadYet') },
                ...(worksheetsEnabled !== null
                  ? [{ label: translate('sources:sourceConfiguration.worksheet'), value: translate('sources:sourceCenter.worksheetsEnabledCount', { count: worksheetsEnabled, value: formatNumber(worksheetsEnabled) }) }]
                  : []),
                ...(readStatus ? [{ label: translate('sources:sourceCenter.readsRemaining'), value: formatNumber(readStatus.reads_remaining) }] : []),
              ]
            const setupDestination = setupDestinationFor(card)
            const canSetup = Boolean(source ? canEditSources : canManageConnectors)
            const actions: OperationalResourceAction[] = state === 'comingSoon' ? [] : state === 'archived'
              ? [
                ...(source ? [{ label: translate('sources:sourceCenter.viewDataSheet'), icon: 'preview' as const, primary: true, onClick: () => navigate(`/sources/${source.id}`) }] : []),
                ...(canViewActivity ? [{ label: translate('common:action.viewActivity'), icon: 'preview' as const, onClick: () => navigate(`/activity?source=${encodeURIComponent(integration?.id ?? source?.id ?? card.id)}`) }] : []),
                ...(canViewDiagnostics ? [{ label: translate('common:action.diagnostics'), icon: 'diagnostics' as const, onClick: () => navigate(`/diagnostics#source-${integration?.id ?? source?.id ?? card.id}`) }] : []),
              ]
              : state === 'setupRequired'
              ? (setupDestination && canSetup
                  ? [{ label: translate('sources:sourceCenter.setupSource'), icon: 'settings' as const, primary: true, onClick: () => navigate(setupDestination) }]
                  : [])
              : [
                ...(integration && canManageConnectors
                  ? [{ label: translate('sources:sourceCenter.editSource'), icon: 'settings' as const, onClick: () => navigate(`/commerce?tab=sources&resource=${encodeURIComponent(integration.id)}`) }]
                  : []),
                ...(source && canEditSources
                  ? [{ label: translate('sources:sourceCenter.editDataSheet'), icon: 'preview' as const, primary: true, onClick: () => navigate(`/sources/${source.id}`) }]
                  : []),
                ...(canViewActivity ? [{ label: translate('common:action.viewActivity'), icon: 'preview' as const, onClick: () => navigate(`/activity?source=${encodeURIComponent(integration?.id ?? source?.id ?? card.id)}`) }] : []),
                ...(canViewDiagnostics ? [{ label: translate('common:action.diagnostics'), icon: 'diagnostics' as const, onClick: () => navigate(`/diagnostics#source-${integration?.id ?? source?.id ?? card.id}`) }] : []),
              ]
            return (
              <OperationalResourceCard
                resourceId={card.id}
                resourceType="source"
                provider={integration?.provider ?? source?.externalSourceId}
                sourceType={source?.sourceKind}
                name={card.displayName}
                description={sourceCardDescription(card)}
                state={state}
                statusLabel={statusPresentation.label}
                statusVariant={statusPresentation.variant}
                statusDetail={state === 'connected' && updatedAt ? `${translate('sources:sourceCenter.updatedPrefix')} ${formatRelativeTime(updatedAt)}` : undefined}
                facts={facts}
                issue={state === 'setupRequired' || state === 'disabled' || state === 'archived'
                  ? setupReason
                  : sourceNeedsOperationalAttention(integration)
                    ? `${formatStatus(integration?.health.status)} · ${formatStatus(integration?.read_status?.last_read_status)}`
                    : undefined}
                actions={actions}
                headerAction={showDelete ? (
                    <div className="fh-menu-anchor" data-source-menu>
                      <button
                        className="fh-row-actions-trigger"
                        type="button"
                        aria-label={translate('sources:sourceCenter.deleteOrArchive')}
                        aria-expanded={openMenuId === card.id}
                        data-source-menu-trigger={card.id}
                        onClick={() => setOpenMenuId(current => current === card.id ? null : card.id)}
                      >
                        <Icon name="more" size="sm" />
                      </button>
                      {openMenuId === card.id && source && (
                        <div className="fh-dropdown fh-row-actions-menu" role="menu">
                          <button
                            className="fh-dropdown-item"
                            type="button"
                            role="menuitem"
                            onClick={event => {
                              removalTriggerRef.current = event.currentTarget
                                .closest('[data-source-card]')
                                ?.querySelector<HTMLButtonElement>('[data-source-menu-trigger]') ?? null
                              void openRemoval(source)
                            }}
                          >
                            <Icon name="delete" /> {translate('sources:sourceCenter.deleteSource')}
                          </button>
                        </div>
                      )}
                    </div>
                  ) : undefined}
              />
            )
          }} />
        </div>
      )}

      {canCreateSources && addPanelOpen && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="source-add-title">
          <div className="fh-card fh-card-pad w-full max-w-3xl">
            <div className="flex items-center justify-between gap-3">
              <h2 className="fh-page-title" id="source-add-title">{translate('sources:sources.addSource')}</h2>
              <button className="fh-icon-button-sm" type="button" aria-label={translate('commerce:commerceHub.close')} onClick={() => setAddPanelOpen(false)}>
                <Icon name="close" />
              </button>
            </div>
            <div className="fh-source-options mt-5 grid gap-4 md:grid-cols-3" aria-label={translate('sources:sourceCenter.sourceOptions')}>
              <button className="fh-card fh-card-pad text-start transition hover:border-accent" type="button" disabled={creating} onClick={() => void createFlowHubSheet()}>
                <Icon name="file" size="md" />
                <strong className="mt-3 block text-text-base">{translate('sources:sourceCenter.flowhubSheet')}</strong>
                <span className="fh-text-caption mt-2 block">{translate('sources:sourceCenter.recommendedForEasierMappingSafeFormulasAnd')}</span>
                <span className="fh-button-primary w-full">{creating ? translate('sources:sourceCenter.creating') : translate('sources:sourceCenter.createSheet')}</span>
              </button>
              <button className="fh-card fh-card-pad text-start transition hover:border-accent" type="button" onClick={() => navigate('/sources/import')}>
                <Icon name="upload" size="md" />
                <strong className="mt-3 block text-text-base">{translate('sources:sourceCenter.importYourSpreadsheet')}</strong>
                <span className="fh-text-caption mt-2 block">{translate('sources:sourceCenter.bringAnExistingXlsxOrCsvFile')}</span>
                <span className="fh-button-secondary w-full">{translate('sources:sourceCenter.importSpreadsheet')}</span>
              </button>
              {canManageConnectors && (
                <button className="fh-card fh-card-pad text-start transition hover:border-accent" type="button" onClick={() => navigate('/commerce?tab=sources')}>
                  <Icon name="connect" size="md" />
                  <strong className="mt-3 block text-text-base">{translate('sources:sourceCenter.keepAnExternalSourceLinked')}</strong>
                  <span className="fh-text-caption mt-2 block">{translate('sources:sourceCenter.forWorkflowsThatRemainManagedOutsideFlowhub')}</span>
                  <span className="fh-button-secondary w-full">{translate('sources:sourceCenter.manageExternalSources')}</span>
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {pendingDelete && (
        <div ref={removalOverlayRef} className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="source-delete-title" aria-describedby="source-delete-description">
          <div className="fh-card fh-card-pad w-full max-w-lg">
            <h2 className="fh-page-title" id="source-delete-title">{translate('sources:sourceCenter.deleteSource')}</h2>
            <p className="mt-3 text-text-base" id="source-delete-description">{translate('sources:sourceCenter.confirmSourceRemoval', { source: pendingDelete.name })}</p>
            <div className="fh-alert-warning mt-4" role="note" aria-live="polite">
              <strong>{checkingImpact
                ? translate('sources:sourceCenter.checkingHistory')
                : pendingImpact?.action === 'blocked'
                  ? translate('sources:sourceCenter.cannotDeleteActiveWorkspace')
                  : pendingImpact?.action === 'archive'
                    ? translate('sources:sourceCenter.archiveSource')
                    : translate('sources:sourceCenter.deleteUnusedSource')}</strong>
              <p className="mt-1">{pendingImpact?.action === 'archive'
                ? translate('sources:sourceCenter.archiveImpact')
                : pendingImpact?.action === 'blocked'
                  ? translate('sources:sourceCenter.activeWorkspacePreventsRemoval')
                  : translate('sources:sourceCenter.safeRemovalImpact')}</p>
              {pendingImpact && Object.keys(pendingImpact.protectedHistory).length > 0 && <p className="mt-2 fh-text-caption">{translate('sources:sourceCenter.protectedRecords', { value: formatNumber(Object.values(pendingImpact.protectedHistory).reduce((sum, count) => sum + count, 0)) })}</p>}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button ref={removalCancelRef} className="fh-button-secondary" type="button" disabled={deleting} onClick={() => { impactRequestRef.current += 1; setPendingDelete(null); setPendingImpact(null); setCheckingImpact(false) }}>{translate('common:action.cancel')}</button>
              <button className="fh-button-danger" type="button" disabled={deleting || checkingImpact || !pendingImpact || pendingImpact.action === 'blocked' || pendingImpact.action === 'none'} onClick={() => void removeSource()}><Icon name="delete" /> {deleting ? translate('sources:sourceCenter.checkingHistory') : pendingImpact?.action === 'archive' ? translate('sources:sourceCenter.archiveSource') : translate('sources:sourceCenter.deleteSource')}</button>
            </div>
          </div>
        </div>
      )}
    </PageShell>
  )
}
