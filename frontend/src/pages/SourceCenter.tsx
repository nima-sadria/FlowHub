import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import Icon from '../components/Icon'
import PageShell from '../components/PageShell'
import { ResourceSectionList, ResourceStateBadge } from '../components/ResourceOrdering'
import BrandIcon from '../components/BrandIcon'
import {
  commerceSourceSignals,
  prepareResourceCollection,
  type ResourceOrderingSignals,
  type ResourceTier,
} from '../features/resourceOrdering/resourceOrdering'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceLifecycleImpact, SourceProfile } from '../features/sourceWorkspace/types'
import { translate } from '../i18n'
import { formatDataRole } from '../i18n/display'
import { localizedApiError } from '../i18n/errors'
import { formatDateTime } from '../i18n/format'
import { useNotification } from '../notifications/NotificationProvider'
import { useServices } from '../services/ServiceContext'
import type { CommerceSource } from '../services/types'
import { effectiveHasPerm } from '../utils/permissions'

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

export default function SourceCenter() {
  const navigate = useNavigate()
  const { commerce } = useServices()
  const { user } = useAuth()
  const notify = useNotification()
  const [sources, setSources] = useState<SourceProfile[]>([])
  const [integrations, setIntegrations] = useState<CommerceSource[]>([])
  const [loading, setLoading] = useState(true)
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
  const canManageSources = effectiveHasPerm(user, 'workspace.admin')

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
  const visibleResources = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    const visibleCards = sourceResources.ordered
      .filter(resource => matchesFilter(resource.tier, filter))
      .filter(resource => !normalizedQuery
        || resource.displayName.toLocaleLowerCase().includes(normalizedQuery)
        || resource.item.integration?.provider.toLocaleLowerCase().includes(normalizedQuery))
      .map(resource => resource.item)
    return prepareResourceCollection(visibleCards, sourceCardSignals)
  }, [filter, query, sourceResources])

  removalBusyRef.current = deleting

  useEffect(() => {
    let active = true
    Promise.allSettled([sourceWorkspaceApi.listSources(), commerce.getSources()])
      .then(([managedResult, integrationResult]) => {
        if (!active) return
        if (managedResult.status === 'fulfilled') setSources(managedResult.value.items)
        if (integrationResult.status === 'fulfilled') setIntegrations(integrationResult.value.items)
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [commerce])

  useEffect(() => {
    if (!addPanelOpen) return
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setAddPanelOpen(false)
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [addPanelOpen])

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

  const filterOptions: Array<{ value: SourceFilter; label: string }> = [
    { value: 'all', label: translate('dataQuality:dataQuality.allSources') },
    { value: 'active', label: translate('common:resourceGroup.active') },
    { value: 'attention', label: translate('common:resourceBadge.warning') },
    { value: 'disabled', label: translate('common:resourceGroup.disabled') },
    { value: 'comingSoon', label: translate('common:resourceGroup.comingSoon') },
  ]

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('sources:sourceCenter.sources')}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button className="fh-button-secondary" type="button" onClick={() => navigate('/data-quality')}>
            <Icon name="alert" /> {translate('sources:sourceCenter.dataQuality2')}
          </button>
          <button className="fh-button-primary" type="button" onClick={() => setAddPanelOpen(true)}>
            <Icon name="add" /> {translate('sources:sources.addSource')}
          </button>
        </div>
      </div>

      <section className="fh-card fh-card-pad" aria-label={translate('sources:sourceCenter.managedSources')}>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">{translate('workspace:unifiedWorkspace.search')}</span>
            <span className="pointer-events-none absolute inset-y-0 start-3 flex items-center text-wp-muted"><Icon name="search" /></span>
            <input
              className="fh-input w-full ps-10"
              type="search"
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder={translate('workspace:unifiedWorkspace.search')}
            />
          </label>
          <div className="flex max-w-full gap-2 overflow-x-auto" role="group" aria-label={translate('common:field.status')}>
            {filterOptions.map(option => (
              <button
                key={option.value}
                className={filter === option.value ? 'fh-button-primary fh-button-sm whitespace-nowrap' : 'fh-button-secondary fh-button-sm whitespace-nowrap'}
                type="button"
                aria-pressed={filter === option.value}
                onClick={() => setFilter(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="mt-5" aria-label={translate('sources:sourceCenter.managedSources')}>
        {loading ? <p className="fh-card fh-card-pad fh-text-caption">{translate('sources:sourceCenter.loadingSources')}</p> : visibleResources.ordered.length === 0 ? (
          <p className="fh-card fh-card-pad fh-text-caption">{translate('sources:sourceCenter.noManagedSourceYetCreateAFlowhub')}</p>
        ) : (
          <div className="space-y-6" data-testid="source-card-groups">
            <ResourceSectionList
              resources={visibleResources}
              className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3"
              renderItem={resource => {
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
                return (
                  <article
                    className="fh-card fh-card-pad relative flex min-h-[168px] flex-col"
                    data-source-card={card.id}
                    title={sourceCardDescription(card)}
                  >
                    <div className="flex min-w-0 items-start gap-3 pe-9">
                      <BrandIcon
                        identity={{ provider: integration?.provider ?? source?.externalSourceId, sourceType: source?.sourceKind }}
                        label={card.displayName}
                        size={44}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h2 className="truncate font-semibold text-text-base">{card.displayName}</h2>
                          <ResourceStateBadge badge={resource.badge} />
                        </div>
                      </div>
                    </div>

                    {showMenu && (
                      <div className="absolute end-3 top-3">
                        <button
                          className="fh-icon-button-sm"
                          type="button"
                          aria-label={translate('sources:sourceCenter.deleteOrArchive')}
                          aria-expanded={openMenuId === card.id}
                          data-source-menu-trigger={card.id}
                          onClick={() => setOpenMenuId(current => current === card.id ? null : card.id)}
                        >
                          <span aria-hidden="true">•••</span>
                        </button>
                        {openMenuId === card.id && source && (
                          <div className="absolute end-0 z-20 mt-2 grid min-w-48 gap-1 rounded-lg border border-border bg-bg-surface p-2 shadow-lg" role="menu">
                            {showConfigureSecondary && (
                              <button className="fh-button-secondary fh-button-sm justify-start" type="button" role="menuitem" onClick={() => navigate(`/sources/${source.id}`)}>
                                {translate('sources:sourceCenter.configureColumns')}
                              </button>
                            )}
                            {showDelete && (
                              <button
                                className="fh-button-danger fh-button-sm justify-start"
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

                    <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
                      {source && (
                        <span className="fh-badge fh-badge-neutral">
                          {translate('sources:sourceCenter.columnSetupVersion')}{source.mappingVersion || translate('sources:sourceConfiguration.notConfigured')}
                        </span>
                      )}
                      {integration && (
                        <span className="fh-text-caption">
                          {translate('commerce:commerceHub.lastRead')} {integration.read_status?.last_read_at
                            ? formatDateTime(integration.read_status.last_read_at)
                            : translate('commerce:commerceHub.notRead')}
                        </span>
                      )}
                    </div>

                    <div className="mt-auto pt-4">
                      {canOpen && (
                        <button className="fh-button-primary w-full" type="button" onClick={() => openPrimary(card)}>
                          {primaryLabel(card)}
                        </button>
                      )}
                    </div>
                  </article>
                )
              }}
            />
          </div>
        )}
      </section>

      {addPanelOpen && (
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
              <button className="fh-card fh-card-pad text-start transition hover:border-accent" type="button" onClick={() => navigate('/commerce?tab=sources')}>
                <Icon name="connect" size="md" />
                <strong className="mt-3 block text-text-base">{translate('sources:sourceCenter.keepAnExternalSourceLinked')}</strong>
                <span className="fh-text-caption mt-2 block">{translate('sources:sourceCenter.forWorkflowsThatRemainManagedOutsideFlowhub')}</span>
                <span className="fh-button-secondary mt-4 w-full">{translate('sources:sourceCenter.manageExternalSources')}</span>
              </button>
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
