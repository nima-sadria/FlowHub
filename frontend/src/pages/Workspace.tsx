import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { ApiError } from '../api/client'
import Empty from '../components/Empty'
import PageShell from '../components/PageShell'
import PricingWorkspaceStartup from '../features/sourceWorkspace/PricingWorkspaceStartup'
import { translate } from '../i18n'
import { useServices } from '../services/ServiceContext'
import type { UnifiedWorkspaceResource } from '../services/unifiedWorkspace/types'

// Automated Source-to-Channel pricing reconciliation: Normalize -> Preview ->
// Auto-selection -> Review -> Dry Run -> Verified Write Set -> Apply Manifest
// -> Apply -> Verify -> Audit/Reconcile. This is the canonical Workspace
// business engine (see docs/workspace-adoption/WORKSPACE_CANONICAL_OWNER_SPEC_2026-08-22.md
// section 9). Products (/products) is the separate, non-automated Manual
// Channel Editor and does not use this pipeline.

const ACTIVE_WORKSPACE_KEY = 'flowhub.workspace.active_workspace'
const DensePricingWorkspace = lazy(() => import('../features/sourceWorkspace/DensePricingWorkspace'))

function storedWorkspaceId(): string {
  try { return window.sessionStorage.getItem(ACTIVE_WORKSPACE_KEY)?.trim() ?? '' } catch { return '' }
}

function rememberWorkspaceId(workspaceId: string) {
  try { window.sessionStorage.setItem(ACTIVE_WORKSPACE_KEY, workspaceId) } catch { /* Session persistence is optional. */ }
}

function forgetWorkspaceId() {
  try { window.sessionStorage.removeItem(ACTIVE_WORKSPACE_KEY) } catch { /* Session persistence is optional. */ }
}

function bootstrapFailure(error: unknown): string {
  if (error instanceof ApiError && error.code === 'CATALOG_SCOPE_EMPTY') {
    return translate('workspace:reconciliation.noEligibleSourceProducts')
  }
  if (error instanceof ApiError) {
    return translate('workspace:reconciliation.workspaceUnavailableHttp', { status: error.status })
  }
  return translate('workspace:reconciliation.workspaceUnavailable')
}

export default function Workspace() {
  const { unifiedWorkspace, settings } = useServices()
  const [searchParams] = useSearchParams()
  const queryWorkspaceId = searchParams.get('workspace')?.trim() ?? ''
  const querySearch = searchParams.get('q')?.trim() ?? ''
  const generation = useRef(0)
  const catalogBootstrap = useRef<Promise<UnifiedWorkspaceResource> | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [ignoreExisting, setIgnoreExisting] = useState(false)
  const [workspace, setWorkspace] = useState<UnifiedWorkspaceResource | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [displayProfile, setDisplayProfile] = useState<{ currency: string; unit: string } | null>(null)

  useEffect(() => {
    let active = true
    const request = settings.getSettings?.()
    if (!request) return () => { active = false }
    request.then(result => {
      const currency = result.currency?.trim().toUpperCase()
      const unit = result.currencyUnit?.trim().toUpperCase()
      if (active && currency && unit) setDisplayProfile({ currency, unit })
    }).catch(() => {
      // The grid remains truthful using its native field unit when the optional
      // presentation preference cannot be loaded.
    })
    return () => { active = false }
  }, [settings])

  const bootstrap = useCallback(async () => {
    const requestGeneration = ++generation.current
    setLoading(true)
    setError(null)
    setWorkspace(null)
    try {
      if (!unifiedWorkspace) throw new Error('workspace_service_unavailable')
      const existingId = ignoreExisting ? '' : queryWorkspaceId || storedWorkspaceId()
      const result = existingId
        ? await unifiedWorkspace.getWorkspace(existingId)
        : unifiedWorkspace.createCatalog
          ? await (() => {
              if (!catalogBootstrap.current) {
                const request = unifiedWorkspace.createCatalog!(translate('workspace:reconciliation.pricingWorkspace'))
                catalogBootstrap.current = request
                void request.finally(() => { if (catalogBootstrap.current === request) catalogBootstrap.current = null }).catch(() => {})
              }
              return catalogBootstrap.current
            })()
          : (() => { throw new Error('workspace_service_unavailable') })()
      if (result.entryPoint !== 'manual' && result.entryPoint !== 'source') {
        throw new Error('catalog_workspace_invalid_entry_point')
      }
      if (requestGeneration !== generation.current) return
      if (!queryWorkspaceId) rememberWorkspaceId(result.id)
      setWorkspace(result)
    } catch (cause) {
      if (requestGeneration !== generation.current) return
      forgetWorkspaceId()
      setError(bootstrapFailure(cause))
    } finally {
      if (requestGeneration === generation.current) setLoading(false)
    }
  }, [ignoreExisting, queryWorkspaceId, unifiedWorkspace])

  useEffect(() => { void bootstrap(); return () => { generation.current += 1 } }, [bootstrap, attempt])

  const retry = () => {
    forgetWorkspaceId()
    setIgnoreExisting(true)
    setAttempt(value => value + 1)
  }

  if (workspace && unifiedWorkspace) {
    return <PageShell>
      <Suspense fallback={<PricingWorkspaceStartup />}>
        <DensePricingWorkspace
          workspace={workspace}
          service={unifiedWorkspace}
          embedded
          initialSearch={querySearch}
          displayProfile={displayProfile}
        />
      </Suspense>
    </PageShell>
  }

  if (loading && !error) {
    return <PageShell><PricingWorkspaceStartup /></PageShell>
  }

  return <PageShell>
    <div className="fh-page-header">
      <div>
        <h1 className="fh-page-title">{translate('workspace:workspace.workspace')}</h1>
        <p className="fh-page-subtitle">{translate('workspace:reconciliation.subtitle')}</p>
      </div>
    </div>
    <div className="fh-card mt-3">
      <Empty
        title={translate('workspace:reconciliation.workspaceUnavailable')}
        description={error ?? translate('workspace:reconciliation.workspaceUnavailable')}
        action={{ label: translate('workspace:workspace.tryAgain'), onClick: retry }}
      />
    </div>
  </PageShell>
}
