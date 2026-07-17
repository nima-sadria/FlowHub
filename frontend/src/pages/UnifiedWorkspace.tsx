import { translate } from '../i18n'
import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { HotTable, type HotTableRef } from '@handsontable/react-wrapper'
import Handsontable from 'handsontable'
import { registerAllModules } from 'handsontable/registry'
import 'handsontable/styles/handsontable.min.css'
import 'handsontable/styles/ht-theme-main.min.css'
import PageShell from '../components/PageShell'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import Spinner from '../components/loading/Spinner'
import { useServices } from '../services/ServiceContext'
import type { UnifiedWorkspaceService } from '../services/unifiedWorkspace/UnifiedWorkspaceService'
import type { UnifiedWorkspaceResource } from '../services/unifiedWorkspace/types'
import { useUnifiedWorkspaceController } from '../features/unifiedWorkspace/useUnifiedWorkspaceController'
import { sanitizeGridHtml, sourceRecordAtVisualRow } from '../features/unifiedWorkspace/handsontableIdentity'
import { resolveHandsontableLicense } from '../features/unifiedWorkspace/handsontableLicense'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { describeWorkspaceStatus } from '../features/unifiedWorkspace/statusDisplay'
import { ResourceOptionGroups, ResourceSectionList, ResourceStateBadge } from '../components/ResourceOrdering'
import {
  channelIdentitySignals,
  prepareResourceCollection,
  workspaceChannelSignals,
} from '../features/resourceOrdering/resourceOrdering'

registerAllModules()

export default function UnifiedWorkspace() {
  const { workspaceId = '' } = useParams()
  const { unifiedWorkspace } = useServices()
  if (!unifiedWorkspace) {
    return <PageShell><Empty title={translate('workspace:unifiedWorkspace.workspaceServiceUnavailable')} description={translate('workspace:unifiedWorkspace.theUnifiedWorkspaceServiceIsNotConfigured')} /></PageShell>
  }
  return <UnifiedWorkspaceRoute workspaceId={workspaceId} service={unifiedWorkspace} />
}

function UnifiedWorkspaceRoute({ workspaceId, service }: { workspaceId: string; service: UnifiedWorkspaceService }) {
  const [workspace, setWorkspace] = useState<UnifiedWorkspaceResource | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    setFailed(false)
    service.getWorkspace(workspaceId)
      .then(result => { if (active) setWorkspace(result) })
      .catch(() => { if (active) setFailed(true) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [service, workspaceId])

  if (loading) {
    return <PageShell><div className="fh-card fh-card-pad flex items-center gap-3"><Spinner size="sm" /> {translate('workspace:unifiedWorkspace.loadingImmutableWorkspaceSnapshot')}</div></PageShell>
  }
  if (failed || !workspace) {
    return <PageShell><Empty title={translate('workspace:unifiedWorkspace.workspaceUnavailable')} description={translate('workspace:unifiedWorkspace.workspaceServiceUnavailable')} /></PageShell>
  }
  if (workspace.entryPoint === 'manual' || workspace.entryPoint === 'source') {
    return <Navigate replace to={`/products?workspace=${encodeURIComponent(workspace.id)}`} />
  }
  return <UnifiedWorkspaceContent workspaceId={workspaceId} />
}

function UnifiedWorkspaceContent({ workspaceId }: { workspaceId: string }) {
  const { unifiedWorkspace } = useServices()
  const controller = useUnifiedWorkspaceController(workspaceId, unifiedWorkspace!)
  const channelResources = useMemo(
    () => prepareResourceCollection(controller.grid?.channels ?? [], workspaceChannelSignals),
    [controller.grid?.channels],
  )
  const applyChannelResources = useMemo(() => {
    const definitions = new Map((controller.grid?.channels ?? []).map(channel => [channel.channelId, channel]))
    const resultChannels = [...new Set(controller.applyResult?.items.map(item => item.channelId) ?? [])]
      .map(channelId => ({ channelId, definition: definitions.get(channelId) }))
    return prepareResourceCollection(resultChannels, item => item.definition
      ? workspaceChannelSignals(item.definition)
      : channelIdentitySignals(item))
  }, [controller.applyResult?.items, controller.grid?.channels])
  const tableHeight = useMemo(() => Math.min(760, Math.max(420, (controller.definition.records.length + 3) * 30)), [controller.definition.records.length])
  const gridMinWidth = useMemo(() => Math.max(1100, controller.definition.columns.length * 110 + 560), [controller.definition.columns.length])
  const hotRef = useRef<HotTableRef>(null)
  const license = resolveHandsontableLicense(
    import.meta.env.VITE_HANDSONTABLE_LICENSE_KEY,
    import.meta.env.PROD,
  )
  const handsontableLicense = license.licenseKey

  if (controller.loading) {
    return <PageShell><div className="fh-card fh-card-pad flex items-center gap-3"><Spinner size="sm" /> {translate('workspace:unifiedWorkspace.loadingImmutableWorkspaceSnapshot')}</div></PageShell>
  }
  if (!controller.workspace) {
    return <PageShell><Empty title={translate('workspace:unifiedWorkspace.workspaceUnavailable')} description={controller.error ?? "The Workspace could not be loaded."} /></PageShell>
  }
  if (!controller.grid) {
    return <PageShell><Empty title={translate('workspace:unifiedWorkspace.workspaceUnavailable')} description={controller.error ?? "The Workspace grid could not be loaded."} /></PageShell>
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{controller.workspace.name}</h1>
          <p className="fh-page-subtitle">
            {translate('workspace:unifiedWorkspace.immutableSnapshot')} {controller.workspace.snapshot.id.slice(0, 8)} · {translate('workspace:unifiedWorkspace.listingRows', { count: controller.grid.total })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`fh-workspace-dirty ${controller.dirtyCount ? "fh-workspace-dirty-active" : ''}`} aria-live="polite">
            {controller.dirtyCount ? translate('workspace:unifiedWorkspace.unsavedEdits', { count: controller.dirtyCount }) : translate('workspace:unifiedWorkspace.draftSaved')}
          </span>
        </div>
      </div>

      {controller.error && <div className="fh-alert fh-alert-danger" role="alert"><Icon name="alert" /><span>{controller.error}</span></div>}

      <section className="fh-card fh-card-pad space-y-4" aria-label={translate('workspace:unifiedWorkspace.workspaceControls')}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="fh-section-title">{translate('workspace:unifiedWorkspace.visibleChannels')}</p>
            <p className="fh-text-caption">{translate('workspace:unifiedWorkspace.visibilityChangesPresentationOnlyAndNeverSelects')}</p>
          </div>
          <div className="grid gap-3">
            <ResourceSectionList resources={channelResources} className="flex flex-wrap gap-2" renderItem={orderedChannel => {
              const channel = orderedChannel.item
              return <label className="fh-channel-toggle">
                <input
                  type="checkbox"
                  disabled={orderedChannel.section !== 'active'}
                  checked={controller.preferences?.visibleChannelIds.includes(channel.channelId) ?? false}
                  onChange={() => void controller.toggleChannel(channel.channelId)}
                />
                <span>{formatChannelDisplayName(channel.channelId, channel)}</span>
                <ResourceStateBadge badge={orderedChannel.badge} />
              </label>
            }} />
            <label className="fh-channel-toggle">
              <span>{translate('workspace:unifiedWorkspace.nameSource')}</span>
              <select
                value={controller.preferences?.displayNameSource ?? "canonical"}
                onChange={event => void controller.setDisplayNameSource(event.target.value)}
                aria-label={translate('workspace:unifiedWorkspace.productDisplayNameSource')}
                className="bg-transparent"
              >
                <option value="canonical">{translate('workspace:unifiedWorkspace.canonicalProduct')}</option>
                <ResourceOptionGroups
                  resources={channelResources}
                  isOptionDisabled={item => item.section !== 'active'}
                  renderLabel={item => formatChannelDisplayName(item.id, item.item)}
                />
              </select>
            </label>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
          <button type="button" className="fh-button-primary" disabled={controller.dirtyCount === 0 || controller.action !== null} onClick={() => void controller.saveDraft()}>
            <Icon name="apply" /> {translate('workspace:unifiedWorkspace.saveDraft')}
          </button>
          <button type="button" className="fh-button-secondary" disabled={controller.dirtyCount > 0 || !controller.grid.revisionId || controller.action !== null} onClick={() => void controller.createReview()}>
            <Icon name="preview" /> {translate('workspace:unifiedWorkspace.reviewChanges')}
          </button>
          <button type="button" className="fh-button-primary" disabled={!controller.review || controller.review.status !== "ready" || controller.dirtyCount > 0 || controller.action !== null} onClick={() => void controller.applySelected()}>
            <Icon name="apply" /> {translate('workspace:unifiedWorkspace.applySelectedOnly')}
          </button>
          {controller.action && <span className="fh-text-caption" role="status">{controller.action}...</span>}
        </div>
      </section>

      {controller.review && (
        <section className={`fh-card fh-card-pad ${controller.review.status === "ready" ? "border-success/30" : "border-danger/30"}`} aria-label={translate('workspace:unifiedWorkspace.reviewResults')}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="fh-section-title">{translate('workspace:unifiedWorkspace.review')} {controller.review.status}</p>
              <p className="fh-text-caption">{translate('workspace:unifiedWorkspace.deterministicComparisonOfCurrentCacheValuesAnd')}</p>
            </div>
            <div className="flex gap-2 fh-text-caption">
              <span>{translate('workspace:unifiedWorkspace.eligible')} {controller.review.summary.eligible}</span>
              <span>{translate('workspace:unifiedWorkspace.blocked')} {controller.review.summary.blocked}</span>
              <span>{translate('workspace:unifiedWorkspace.warnings')} {controller.review.summary.warnings}</span>
            </div>
          </div>
        </section>
      )}

      {controller.applyResult && (
        <section className="fh-card fh-card-pad" aria-label={translate('workspace:sourceCentricWorkspace.applyResults')}>
          <p className="fh-section-title">{translate('workspace:sourceCentricWorkspace.apply')} {controller.applyResult.status}</p>
          <p className="fh-text-caption">{translate('workspace:unifiedWorkspace.correlation')} {controller.applyResult.correlationId}</p>
          {controller.applyResult.status === "reconciliation_required" && (
            <button
              type="button"
              className="fh-button-secondary mt-3"
              disabled={controller.action !== null}
              onClick={() => void controller.reconcileApply()}
            >
              {translate('workspace:unifiedWorkspace.verifyUncertainListings')}
            </button>
          )}
          <div className="mt-3 grid gap-3">
            <ResourceSectionList resources={applyChannelResources} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" renderItem={orderedChannel => <>
              {controller.applyResult!.items.filter(item => item.channelId === orderedChannel.id).map(item => (
                <div key={item.id} className="rounded border border-border p-3 fh-text-caption">
                  <span className="flex items-center gap-2 font-medium">{orderedChannel.displayName} · {item.field}<ResourceStateBadge badge={orderedChannel.badge} /></span>
                  <span className="block">{item.status}{item.errorMessage ? translate('workspace:unifiedWorkspace.errorDetail', { message: item.errorMessage }) : ''}</span>
                </div>
              ))}
            </>} />
          </div>
        </section>
      )}

      <section className="fh-card" aria-label={translate('workspace:unifiedWorkspace.unifiedMultiChannelProductEditor')}>
        <form
          className="grid min-w-0 gap-3 border-b border-slate-200 p-4 md:grid-cols-5"
          aria-label={translate('workspace:unifiedWorkspace.serverSideWorkspaceFilters')}
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault()
            const values = new FormData(event.currentTarget)
            const numberValue = (name: string) => {
              const value = String(values.get(name) ?? '').trim()
              const parsed = Number(value)
              return value === '' || !Number.isFinite(parsed) ? undefined : parsed
            }
            controller.updateGridQuery({
              search: String(values.get('search') ?? '').trim() || undefined,
              channelId: String(values.get('channelId') ?? '').trim() || undefined,
              channelStatus: String(values.get('channelStatus') ?? '').trim() || undefined,
              minPrice: numberValue('minPrice'),
              maxPrice: numberValue('maxPrice'),
            })
          }}
        >
          <label className="fh-field-label min-w-0">{translate('workspace:unifiedWorkspace.search')}<input className="fh-input mt-1" name="search" type="search" /></label>
          <label className="fh-field-label min-w-0">{translate('workspace:unifiedWorkspace.channel')}<select className="fh-input mt-1" name="channelId" defaultValue=""><option value="">{translate('common:selector.allChannels')}</option><ResourceOptionGroups resources={channelResources} renderLabel={item => formatChannelDisplayName(item.id, item.item)} /></select></label>
          <label className="fh-field-label min-w-0">{translate('workspace:unifiedWorkspace.status')}<input className="fh-input mt-1" name="channelStatus" /></label>
          <label className="fh-field-label min-w-0">{translate('workspace:unifiedWorkspace.priceRange')}<span className="mt-1 flex min-w-0 gap-2"><input aria-label={translate('workspace:unifiedWorkspace.minimumPrice')} className="fh-input min-w-0" name="minPrice" type="number" min="0" /><input aria-label={translate('workspace:unifiedWorkspace.maximumPrice')} className="fh-input min-w-0" name="maxPrice" type="number" min="0" /></span></label>
          <span className="flex min-w-0 flex-wrap items-end gap-2"><button className="fh-button-secondary fh-button-sm" type="submit">{translate('workspace:unifiedWorkspace.filterServerData')}</button><button className="fh-button-secondary fh-button-sm" type="reset" onClick={() => controller.updateGridQuery({ search: undefined, channelId: undefined, channelStatus: undefined, minPrice: undefined, maxPrice: undefined })}>{translate('workspace:unifiedWorkspace.clear')}</button></span>
        </form>
        <div className="fh-panel-header">
          <div>
            <p className="fh-section-title">{translate('workspace:unifiedWorkspace.workspaceGrid')}</p>
            <p className="fh-text-caption">{translate('workspace:unifiedWorkspace.editTargetCellsInlineCurrentValuesIdentities')}</p>
          </div>
          <div className="flex items-center gap-2 fh-text-caption">
            <span>{translate('workspace:unifiedWorkspace.listingsSelected', { count: controller.selectedListingCount })}</span>
            <button type="button" className="fh-button-secondary fh-button-sm" disabled={controller.page <= 1} onClick={() => controller.setPage(controller.page - 1)}>{translate('workspace:sourceCentricWorkspace.previous')}</button>
            <span>{translate('workspace:sourceCentricWorkspace.page')} {controller.page} / {controller.totalPages}</span>
            <button type="button" className="fh-button-secondary fh-button-sm" disabled={controller.page >= controller.totalPages} onClick={() => controller.setPage(controller.page + 1)}>{translate('workspace:sourceCentricWorkspace.next')}</button>
          </div>
        </div>
        {!handsontableLicense && (
          <div className="fh-alert fh-alert-danger m-4" role="alert">
            <Icon name="alert" />
            <span>{translate('workspace:unifiedWorkspace.productionGridIsDisabledConfigureAValid')}</span>
          </div>
        )}
        {handsontableLicense && <div className="fh-grid-scroll" role="region" aria-label={translate('workspace:unifiedWorkspace.scrollableWorkspaceGrid')}>
          <div className="ht-theme-main fh-handsontable" style={{ minWidth: gridMinWidth }} aria-label={translate('workspace:unifiedWorkspace.virtualizedMultiChannelWorkspaceGrid')} tabIndex={0}>
          <HotTable
            ref={hotRef}
            data={controller.definition.records}
            columns={controller.definition.columns}
            nestedHeaders={controller.definition.nestedHeaders}
            rowHeaders
            width="100%"
            height={tableHeight}
            stretchH="all"
            fixedColumnsStart={5}
            manualColumnMove
            manualColumnResize
            multiColumnSorting
            filters
            dropdownMenu={["filter_by_condition", "filter_by_value", "filter_action_bar"]}
            copyPaste={{ pasteMode: "overwrite" }}
            fillHandle={{ autoInsertRow: false }}
            licenseKey={handsontableLicense}
            sanitizer={sanitizeGridHtml}
            cells={(row: number, column: number) => {
              const settings = {} as Handsontable.CellProperties
              const columnSetting = controller.definition.columns[column]
              const prop = typeof columnSetting?.data === 'string' ? columnSetting.data : ''
              const meta = controller.definition.columnMeta.get(prop)
              const physicalRow = hotRef.current?.hotInstance?.toPhysicalRow(row) ?? row
              const record = hotRef.current?.hotInstance?.getSourceDataAtRow(physicalRow) as Record<string, unknown> | undefined
              if (meta?.kind === 'target' && meta.channelId && meta.field && record) {
                const statusKey = prop.replace(/__target$/, '__status')
                const status = String(record[statusKey] ?? 'unavailable')
                settings.className = `fh-cell-status fh-cell-status-${status}`
                const display = describeWorkspaceStatus(status)
                settings.title = `Cell status: ${display.label}`
                const renderer: Handsontable.renderers.BaseRenderer = (instance, td, visualRow, visualColumn, cellProp, value, properties) => {
                  Handsontable.renderers.TextRenderer(instance, td, visualRow, visualColumn, cellProp, value, properties)
                  td.dataset.cellStatus = display.label
                  td.dataset.cellIcon = display.icon
                  td.dataset.cellCritical = String(display.critical)
                  td.setAttribute('aria-label', `${String(value ?? '')}; status ${display.label}`)
                }
                settings.renderer = renderer
              }
              return settings
            }}
            afterChange={(changes: Handsontable.CellChange[] | null, source: Handsontable.ChangeSource) => {
              if (!changes || source === 'loadData') return
              for (const [row, prop, _oldValue, value] of changes) {
                const identity = sourceRecordAtVisualRow(hotRef.current?.hotInstance, row)
                if (identity) controller.editCell(identity.listingId, String(prop), value)
              }
            }}
            afterRenderer={(td: HTMLTableCellElement, row: number, column: number) => {
              const identity = sourceRecordAtVisualRow(hotRef.current?.hotInstance, row)
              const setting = controller.definition.columns[column]
              const prop = typeof setting?.data === 'string' ? setting.data : ''
              if (identity) td.dataset.listingId = identity.listingId
              if (prop) td.dataset.columnProp = prop
            }}
            afterColumnSort={((_current, destination) => {
              const sort = destination.map(item => {
                const setting = controller.definition.columns[item.column]
                const prop = typeof setting?.data === 'string' ? setting.data : ''
                const meta = controller.definition.columnMeta.get(prop)
                const field = meta?.field ?? ({ canonicalName: 'name', productType: 'product_type', mappingState: 'mapping_state', listingLabel: 'listing_id' } as Record<string, string>)[prop]
                return field ? `${field}:${item.sortOrder}` : null
              }).filter((item): item is string => item !== null).join(',')
              if (sort) controller.updateGridQuery({ sort })
            }) as NonNullable<Handsontable.GridSettings['afterColumnSort']>}
          />
          </div>
        </div>}
      </section>
    </PageShell>
  )
}
