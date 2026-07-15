import { translate } from '../i18n'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageShell from '../components/PageShell'
import Icon from '../components/Icon'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceLifecycleImpact, SourceProfile } from '../features/sourceWorkspace/types'
import { useAuth } from '../auth'
import { effectiveHasPerm } from '../utils/permissions'
import { useNotification } from '../notifications/NotificationProvider'
import { localizedApiError } from '../i18n/errors'

const KIND_LABELS: Record<SourceProfile['sourceKind'], string> = {
  flowhub_sheet: 'sources:sourceCenter.flowhubSheet',
  imported_sheet: 'sources:sourceCenter.importedSpreadsheet',
  external: 'sources:sourceCenter.linkedExternalSource',
}

export default function SourceCenter() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const notify = useNotification()
  const [sources, setSources] = useState<SourceProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
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

  removalBusyRef.current = deleting

  useEffect(() => {
    sourceWorkspaceApi.listSources().then(result => setSources(result.items)).finally(() => setLoading(false))
  }, [])

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

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('sources:sourceCenter.sources')}</h1>
          <p className="fh-page-subtitle">{translate('sources:sourceCenter.chooseWhereSourceProductsAndChannelTargets')}</p>
        </div>
        <button className="fh-button-secondary" type="button" onClick={() => navigate("/data-quality")}>
          <Icon name="alert" /> {translate('sources:sourceCenter.dataQuality2')}
        </button>
      </div>

      <section className="grid gap-4 lg:grid-cols-3" aria-label={translate('sources:sourceCenter.sourceOptions')}>
        <article className="fh-card fh-card-pad border-accent/30">
          <span className="fh-badge fh-badge-success">{translate('sources:sourceCenter.recommended')}</span>
          <h2 className="fh-section-title mt-3">{translate('sources:sourceCenter.flowhubSheet')}</h2>
          <p className="fh-text-caption mt-2">{translate('sources:sourceCenter.recommendedForEasierMappingSafeFormulasAnd')}</p>
          <button className="fh-button-primary mt-4" type="button" disabled={creating} onClick={() => void createFlowHubSheet()}>
            <Icon name="add" /> {creating ? translate('sources:sourceCenter.creating') : translate('sources:sourceCenter.createSheet')}
          </button>
        </article>
        <article className="fh-card fh-card-pad">
          <span className="fh-badge fh-badge-success">{translate('sources:sourceCenter.recommendedMigrationPath')}</span>
          <h2 className="fh-section-title mt-3">{translate('sources:sourceCenter.importYourSpreadsheet')}</h2>
          <p className="fh-text-caption mt-2">{translate('sources:sourceCenter.bringAnExistingXlsxOrCsvFile')}</p>
          <button className="fh-button-secondary mt-4" type="button" onClick={() => navigate("/sources/import")}>
            <Icon name="upload" /> {translate('sources:sourceCenter.importSpreadsheet')}
          </button>
        </article>
        <article className="fh-card fh-card-pad">
          <span className="fh-badge fh-badge-neutral">{translate('sources:sourceCenter.advanced')}</span>
          <h2 className="fh-section-title mt-3">{translate('sources:sourceCenter.keepAnExternalSourceLinked')}</h2>
          <p className="fh-text-caption mt-2">{translate('sources:sourceCenter.forWorkflowsThatRemainManagedOutsideFlowhub')}</p>
          <button className="fh-button-secondary mt-4" type="button" onClick={() => navigate("/commerce?tab=sources")}>
            <Icon name="connect" /> {translate('sources:sourceCenter.manageExternalSources')}
          </button>
        </article>
      </section>

      <section className="fh-card mt-5" aria-label={translate('sources:sourceCenter.managedSources')}>
        <div className="fh-panel-header">
          <div><h2 className="fh-section-title">{translate('sources:sourceCenter.managedSources')}</h2><p className="fh-text-caption">{translate('sources:sourceCenter.sourceProductIdentityStaysSeparateFromChannel')}</p></div>
        </div>
        {loading ? <p className="fh-card-pad fh-text-caption">{translate('sources:sourceCenter.loadingSources')}</p> : sources.length === 0 ? (
          <p className="fh-card-pad fh-text-caption">{translate('sources:sourceCenter.noManagedSourceYetCreateAFlowhub')}</p>
        ) : (
          <div className="divide-y divide-border">
            {sources.map(source => (
              <div className="flex flex-wrap items-center gap-3 p-4" key={source.id}>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-text-base">{source.name}</p>
                  <p className="fh-text-caption">{translate(KIND_LABELS[source.sourceKind])} {translate('sources:sourceCenter.columnSetupVersion')}{source.mappingVersion || translate('sources:sourceConfiguration.notConfigured')}</p>
                  {source.status === 'disabled' && <span className="fh-badge fh-badge-neutral mt-2">{translate('sources:sourceCenter.archived')}</span>}
                </div>
                {source.status === 'active' && source.sheetId && <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => navigate(`/sheets/${source.sheetId}`)}>{translate('sources:sourceCenter.openSheet')}</button>}
                {source.status === 'active' && <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => navigate(`/sources/${source.id}`)}>{translate('sources:sourceCenter.configureColumns')}</button>}
                {canManageSources && source.status === 'active' && <button className="fh-button-danger fh-button-sm" type="button" onClick={event => { removalTriggerRef.current = event.currentTarget; void openRemoval(source) }}><Icon name="delete" /> {translate('sources:sourceCenter.deleteSource')}</button>}
              </div>
            ))}
          </div>
        )}
      </section>
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
