import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import Badge, { type BadgeVariant } from '../components/Badge'
import BrandIcon from '../components/BrandIcon'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import {
  commerceSourceSignals,
  prepareResourceCollection,
  type ResourceBadge,
  type ResourceOrderingSignals,
  type ResourceTier,
} from '../features/resourceOrdering/resourceOrdering'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceLifecycleImpact, SourceMapping, SourceProfile } from '../features/sourceWorkspace/types'
import { translate } from '../i18n'
import { formatDataRole } from '../i18n/display'
import { formatRelativeTime } from '../i18n/format'
import { localizedApiError } from '../i18n/errors'
import { useNotification } from '../notifications/NotificationProvider'
import { useServices } from '../services/ServiceContext'
import type { CommerceSource } from '../services/types'
import { effectiveHasPerm } from '../utils/permissions'
import { WORKSPACE_PERMISSION } from '../utils/workspacePermissions'

const KIND_LABELS: Record<SourceProfile['sourceKind'], string> = {
  flowhub_sheet: 'sources:sourceCenter.flowhubSheet',
  imported_sheet: 'sources:sourceCenter.importedSpreadsheet',
  external: 'sources:sourceCenter.linkedExternalSource',
}

type SourceFilter = 'all' | 'active' | 'attention' | 'disabled' | 'comingSoon'

interface SourceCardModel {
  id: string
  displayName: string
  profile: SourceProfile | null
  integration: CommerceSource | null
}

function sourceIsEnabled(source: SourceProfile): boolean {
  return source.status.trim().toLocaleLowerCase() !== 'disabled'
}

function sourceCardSignals(card: SourceCardModel): ResourceOrderingSignals {
  if (!card.profile && card.integration) {
    return { ...commerceSourceSignals(card.integration), id: card.id, displayName: card.displayName }
  }

  const source = card.profile as SourceProfile
  const integration = card.integration
  const active = source.status === 'active'
  const sourceEnabled = sourceIsEnabled(source)
  const integrationAvailable = !integration || (integration.implemented && !integration.placeholder)
  return {
    id: card.id,
    displayName: card.displayName,
    status: source.status,
    healthStatus: integration?.health.status,
    credentialStatus: integration?.credential_status,
    activityStatuses: [integration?.status, integration?.read_status?.last_read_status],
    enabled: sourceEnabled && integrationAvailable,
    configured: active
      && integrationAvailable
      && source.mappingVersion > 0
      && (source.sourceKind !== 'external' || integration?.credential_status === 'configured'),
    implemented: integrationAvailable,
    placeholder: integration?.placeholder ?? false,
  }
}

function sourceCardDescription(card: SourceCardModel): string {
  if (card.profile) return translate(KIND_LABELS[card.profile.sourceKind])
  const rawRole = card.integration?.data_role
  const localizedRole = formatDataRole(rawRole)
  return rawRole && localizedRole !== rawRole
    ? localizedRole
    : translate('sources:sourceCenter.externalSourceDescription')
}

function matchesFilter(tier: ResourceTier, filter: SourceFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'active') return tier === 'configured' || tier === 'attention'
  return tier === filter
}

function sourceBadgeTone(badge: ResourceBadge): BadgeVariant {
  if (badge === 'healthy' || badge === 'configured') return 'success'
  if (badge === 'warning') return 'warning'
  return 'neutral'
}

function sourceBadgeLabel(badge: ResourceBadge): string {
  if (badge === 'healthy' || badge === 'configured') return translate('sources:sourceCenter.healthy')
  if (badge === 'warning') return translate('sources:sourceCenter.needsReview')
  if (badge === 'disabled') return translate('common:resourceBadge.disabled')
  return translate('common:resourceBadge.comingSoon')
}

function cardUpdatedAt(card: SourceCardModel): string | null {
  return card.profile?.updatedAt ?? card.integration?.read_status?.last_read_at ?? null
}

export default function SourceCenter() {
  const navigate = useNavigate()
  const { commerce, products } = useServices()
  const { user } = useAuth()
  const notify = useNotification()
  const [sources, setSources] = useState<SourceProfile[]>([])
  const [integrations, setIntegrations] = useState<CommerceSource[]>([])
  const [worksheetMappings, setWorksheetMappings] = useState<Record<string, SourceMapping | null>>({})
  const [totalProducts, setTotalProducts] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
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
  const canManageSources = effectiveHasPerm(user, WORKSPACE_PERMISSION.admin)
  const canManageConnectors = user?.is_admin === true

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
      .filter(resource => matchesFilter(resource.tier, filter))
      .filter(resource => !normalizedQuery
        || resource.displayName.toLocaleLowerCase().includes(normalizedQuery)
        || resource.item.integration?.provider.toLocaleLowerCase().includes(normalizedQuery))
  }, [filter, query, sourceResources])

  const needsAttentionCount = useMemo(
    () => sourceResources.ordered.filter(resource => resource.tier === 'attention').length,
    [sourceResources],
  )

  removalBusyRef.current = deleting

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError(false)
    Promise.allSettled([
      sourceWorkspaceApi.listSources(),
      commerce.getSources(),
      products.getProducts({ search: '', status: 'all', page: 1, pageSize: 1 }),
    ])
      .then(([managedResult, integrationResult, productsResult]) => {
        if (!active) return
        if (managedResult.status === 'fulfilled') setSources(managedResult.value.items)
        if (integrationResult.status === 'fulfilled') setIntegrations(integrationResult.value.items)
        if (productsResult.status === 'fulfilled') setTotalProducts(productsResult.value.total)
        if (managedResult.status === 'rejected' && integrationResult.status === 'rejected') setLoadError(true)
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [commerce, products, reloadToken])

  useEffect(() => {
    let active = true
    const managedIds = sources.filter(source => source.mappingVersion > 0).map(source => source.id)
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
        description: translate('sources:sourceCenter.tryAgainNoSourceCreated'),
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
        : current.map(item => item.id === pendingDelete.id ? { ...item, status: 'disabled', version: item.version + 1 } : item))
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

  function openPrimary(card: SourceCardModel) {
    if (card.profile) {
      if (!sourceIsEnabled(card.profile)) return
      if (card.profile.sheetId && card.profile.mappingVersion > 0) navigate(`/sheets/${card.profile.sheetId}`)
      else navigate(`/sources/${card.profile.id}`)
      return
    }
    if (card.integration?.implemented && !card.integration.placeholder) navigate('/commerce?tab=sources')
  }

  function primaryLabel(card: SourceCardModel): string {
    if (card.profile?.sheetId && card.profile.mappingVersion > 0) return translate('sources:sourceCenter.openSheet')
    if (card.profile) return translate('sources:sourceCenter.configureColumns')
    return translate('sources:sourceCenter.manageExternalSources')
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
    { value: 'comingSoon', label: translate('common:resourceGroup.comingSoon') },
  ]

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('sources:sourceCenter.sources')}</h1>
          <p className="fh-page-subtitle">{translate('sources:sourceCenter.manageProductDataSourcesSubtitle')}</p>
        </div>
        {canCreateSources && (
          <button className="fh-button-primary" type="button" onClick={() => setAddPanelOpen(true)}>
            <Icon name="add" /> {translate('sources:sources.addSource')}
          </button>
        )}
      </div>

      <div className="fh-sources-kpi-row">
        <div className="fh-kpi-card">
          <div className="fh-kpi-card-head">
            <span className="fh-kpi-card-label">{translate('sources:sourceCenter.connectedSources')}</span>
            <span className="fh-kpi-card-icon"><Icon name="products" size="sm" /></span>
          </div>
          <div className="fh-kpi-card-value">{cards.length}</div>
        </div>
        <div className="fh-kpi-card">
          <div className="fh-kpi-card-head">
            <span className="fh-kpi-card-label">{translate('sources:sourceCenter.needsAttentionKpi')}</span>
            <span className="fh-kpi-card-icon"><Icon name="products" size="sm" /></span>
          </div>
          <div className="fh-kpi-card-value">
            {needsAttentionCount}
            {needsAttentionCount > 0 && <span className="fh-kpi-card-trend fh-kpi-card-trend-danger">{translate('sources:sourceCenter.reviewCaption')}</span>}
          </div>
        </div>
        <div className="fh-kpi-card">
          <div className="fh-kpi-card-head">
            <span className="fh-kpi-card-label">{translate('sources:sourceCenter.productsImported')}</span>
            <span className="fh-kpi-card-icon"><Icon name="products" size="sm" /></span>
          </div>
          <div className="fh-kpi-card-value">{totalProducts !== null ? totalProducts.toLocaleString() : '—'}</div>
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
        <span className="fh-sources-count ms-auto">{translate('sources:sourceCenter.sourcesCount', { count: cards.length })}</span>
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

      {loading ? <p className="fh-card fh-card-pad fh-text-caption">{translate('sources:sourceCenter.loadingSources')}</p> : loadError ? null : visibleCards.length === 0 ? (
        <div className="fh-card fh-card-pad"><Empty title={translate('sources:sourceCenter.noManagedSourceYetCreateAFlowhub')} description="" /></div>
      ) : (
        <div className="fh-sources-grid" data-testid="source-card-groups">
          {visibleCards.map(resource => {
            const card = resource.item
            const source = card.profile
            const integration = card.integration
            const integrationAvailable = !integration || (integration.implemented && !integration.placeholder)
            const canOpen = Boolean(resource.section === 'active' && (source
              ? sourceIsEnabled(source) && integrationAvailable
              : integration?.implemented && !integration.placeholder))
            const showConfigureSecondary = Boolean(canOpen && source?.sheetId && source.mappingVersion > 0)
            const showDelete = Boolean(canOpen && canManageSources && source?.status === 'active')
            const showMenu = showConfigureSecondary || showDelete
            const updatedAt = cardUpdatedAt(card)
            const worksheetsEnabled = worksheetsEnabledCount(card)
            const hasBrandIdentity = Boolean(integration || source?.sourceKind === 'external')
            return (
              <article
                className="fh-source-card"
                data-source-card={card.id}
                data-resource-id={card.id}
                data-resource-section={resource.section}
                key={card.id}
                title={sourceCardDescription(card)}
              >
                <div className="fh-source-card-head">
                  {hasBrandIdentity
                    ? <BrandIcon identity={{ provider: integration?.provider ?? source?.externalSourceId, sourceType: source?.sourceKind }} label={card.displayName} size={36} />
                    : <span className="fh-source-card-icon"><Icon name="sources" size="md" /></span>}
                  <h2 className="fh-source-card-name">{card.displayName}</h2>
                  {showMenu && (
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
                          {showConfigureSecondary && (
                            <button className="fh-dropdown-item" type="button" role="menuitem" onClick={() => { setOpenMenuId(null); navigate(`/sources/${source.id}`) }}>
                              {translate('sources:sourceCenter.configureColumns')}
                            </button>
                          )}
                          {showDelete && (
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
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="fh-source-card-row">
                  <Badge dot variant={sourceBadgeTone(resource.badge)}>{sourceBadgeLabel(resource.badge)}</Badge>
                  {updatedAt && <span className="fh-text-caption">{translate('sources:sourceCenter.updatedPrefix')} {formatRelativeTime(updatedAt)}</span>}
                </div>

                <div className="fh-source-card-row">
                  <span className="fh-text-caption">
                    {worksheetsEnabled === null
                      ? translate('sources:sourceConfiguration.loading')
                      : translate('sources:sourceCenter.worksheetsEnabledCount', { count: worksheetsEnabled })}
                  </span>
                  {canOpen && (
                    <button className="fh-source-card-configure" type="button" onClick={() => openPrimary(card)}>
                      {primaryLabel(card)}
                    </button>
                  )}
                </div>
              </article>
            )
          })}
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
            <div className="mt-5 grid gap-4 md:grid-cols-3" aria-label={translate('sources:sourceCenter.sourceOptions')}>
              <button className="fh-card fh-card-pad text-start transition hover:border-accent" type="button" disabled={creating} onClick={() => void createFlowHubSheet()}>
                <Icon name="file" size="md" />
                <strong className="mt-3 block text-text-base">{translate('sources:sourceCenter.flowhubSheet')}</strong>
                <span className="fh-text-caption mt-2 block">{translate('sources:sourceCenter.recommendedForEasierMappingSafeFormulasAnd')}</span>
                <span className="fh-button-primary mt-4 w-full">{creating ? translate('sources:sourceCenter.creating') : translate('sources:sourceCenter.createSheet')}</span>
              </button>
              <button className="fh-card fh-card-pad text-start transition hover:border-accent" type="button" onClick={() => navigate('/sources/import')}>
                <Icon name="upload" size="md" />
                <strong className="mt-3 block text-text-base">{translate('sources:sourceCenter.importYourSpreadsheet')}</strong>
                <span className="fh-text-caption mt-2 block">{translate('sources:sourceCenter.bringAnExistingXlsxOrCsvFile')}</span>
                <span className="fh-button-secondary mt-4 w-full">{translate('sources:sourceCenter.importSpreadsheet')}</span>
              </button>
              {canManageConnectors && (
                <button className="fh-card fh-card-pad text-start transition hover:border-accent" type="button" onClick={() => navigate('/commerce?tab=sources')}>
                  <Icon name="connect" size="md" />
                  <strong className="mt-3 block text-text-base">{translate('sources:sourceCenter.keepAnExternalSourceLinked')}</strong>
                  <span className="fh-text-caption mt-2 block">{translate('sources:sourceCenter.forWorkflowsThatRemainManagedOutsideFlowhub')}</span>
                  <span className="fh-button-secondary mt-4 w-full">{translate('sources:sourceCenter.manageExternalSources')}</span>
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
              {pendingImpact && Object.keys(pendingImpact.protectedHistory).length > 0 && <p className="mt-2 fh-text-caption">{translate('sources:sourceCenter.protectedRecords', { count: Object.values(pendingImpact.protectedHistory).reduce((sum, count) => sum + count, 0) })}</p>}
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
