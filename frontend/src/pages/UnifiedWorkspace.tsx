import { type FormEvent, useMemo, useRef } from 'react'
import { useParams } from 'react-router-dom'
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
import { useUnifiedWorkspaceController } from '../features/unifiedWorkspace/useUnifiedWorkspaceController'
import { sanitizeGridHtml, sourceRecordAtVisualRow } from '../features/unifiedWorkspace/handsontableIdentity'
import { resolveHandsontableLicense } from '../features/unifiedWorkspace/handsontableLicense'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { describeWorkspaceStatus } from '../features/unifiedWorkspace/statusDisplay'

registerAllModules()

export default function UnifiedWorkspace() {
  const { workspaceId = '' } = useParams()
  const { unifiedWorkspace } = useServices()
  if (!unifiedWorkspace) {
    return <PageShell><Empty title="Workspace service unavailable" description="The Unified Workspace service is not configured." /></PageShell>
  }
  return <UnifiedWorkspaceContent workspaceId={workspaceId} />
}

function UnifiedWorkspaceContent({ workspaceId }: { workspaceId: string }) {
  const { unifiedWorkspace } = useServices()
  const controller = useUnifiedWorkspaceController(workspaceId, unifiedWorkspace!)
  const tableHeight = useMemo(() => Math.min(760, Math.max(420, (controller.definition.records.length + 3) * 30)), [controller.definition.records.length])
  const gridMinWidth = useMemo(() => Math.max(1100, controller.definition.columns.length * 110 + 560), [controller.definition.columns.length])
  const hotRef = useRef<HotTableRef>(null)
  const license = resolveHandsontableLicense(
    import.meta.env.VITE_HANDSONTABLE_LICENSE_KEY,
    import.meta.env.PROD,
  )
  const handsontableLicense = license.licenseKey

  if (controller.loading) {
    return <PageShell><div className="fh-card fh-card-pad flex items-center gap-3"><Spinner size="sm" /> Loading immutable Workspace Snapshot...</div></PageShell>
  }
  if (!controller.workspace || !controller.grid) {
    return <PageShell><Empty title="Workspace unavailable" description={controller.error ?? 'The Workspace could not be loaded.'} /></PageShell>
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{controller.workspace.name}</h1>
          <p className="fh-page-subtitle">
            Immutable Snapshot {controller.workspace.snapshot.id.slice(0, 8)} · {controller.grid.total} Listing row{controller.grid.total === 1 ? '' : 's'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`fh-workspace-dirty ${controller.dirtyCount ? 'fh-workspace-dirty-active' : ''}`} aria-live="polite">
            {controller.dirtyCount ? `${controller.dirtyCount} unsaved edit${controller.dirtyCount === 1 ? '' : 's'}` : 'Draft saved'}
          </span>
        </div>
      </div>

      {controller.error && <div className="fh-alert fh-alert-danger" role="alert"><Icon name="alert" /><span>{controller.error}</span></div>}

      <section className="fh-card fh-card-pad space-y-4" aria-label="Workspace controls">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="fh-section-title">Visible Channels</p>
            <p className="fh-text-caption">Visibility changes presentation only and never selects a Channel for Apply.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {controller.grid.channels.map(channel => (
              <label key={channel.channelId} className="fh-channel-toggle">
                <input
                  type="checkbox"
                  checked={controller.preferences?.visibleChannelIds.includes(channel.channelId) ?? false}
                  onChange={() => void controller.toggleChannel(channel.channelId)}
                />
                <span>{formatChannelDisplayName(channel.channelId, channel)}</span>
              </label>
            ))}
            <label className="fh-channel-toggle">
              <span>Name source</span>
              <select
                value={controller.preferences?.displayNameSource ?? 'canonical'}
                onChange={event => void controller.setDisplayNameSource(event.target.value)}
                aria-label="Product display name source"
                className="bg-transparent"
              >
                <option value="canonical">Canonical Product</option>
                {controller.grid.channels.map(channel => <option key={channel.channelId} value={channel.channelId}>{formatChannelDisplayName(channel.channelId, channel)}</option>)}
              </select>
            </label>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
          <button type="button" className="fh-button-primary" disabled={controller.dirtyCount === 0 || controller.action !== null} onClick={() => void controller.saveDraft()}>
            <Icon name="apply" /> Save Draft
          </button>
          <button type="button" className="fh-button-secondary" disabled={controller.dirtyCount > 0 || !controller.grid.revisionId || controller.action !== null} onClick={() => void controller.createReview()}>
            <Icon name="preview" /> Review Changes
          </button>
          <button type="button" className="fh-button-primary" disabled={!controller.review || controller.review.status !== 'ready' || controller.dirtyCount > 0 || controller.action !== null} onClick={() => void controller.applySelected()}>
            <Icon name="apply" /> Apply Selected Only
          </button>
          {controller.action && <span className="fh-text-caption" role="status">{controller.action}...</span>}
        </div>
      </section>

      {controller.review && (
        <section className={`fh-card fh-card-pad ${controller.review.status === 'ready' ? 'border-success/30' : 'border-danger/30'}`} aria-label="Review results">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="fh-section-title">Review {controller.review.status}</p>
              <p className="fh-text-caption">Deterministic comparison of Current cache values and saved Draft targets.</p>
            </div>
            <div className="flex gap-2 fh-text-caption">
              <span>Eligible {controller.review.summary.eligible}</span>
              <span>Blocked {controller.review.summary.blocked}</span>
              <span>Warnings {controller.review.summary.warnings}</span>
            </div>
          </div>
        </section>
      )}

      {controller.applyResult && (
        <section className="fh-card fh-card-pad" aria-label="Apply results">
          <p className="fh-section-title">Apply {controller.applyResult.status}</p>
          <p className="fh-text-caption">Correlation {controller.applyResult.correlationId}</p>
          {controller.applyResult.status === 'reconciliation_required' && (
            <button
              type="button"
              className="fh-button-secondary mt-3"
              disabled={controller.action !== null}
              onClick={() => void controller.reconcileApply()}
            >
              Verify uncertain Listings
            </button>
          )}
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {controller.applyResult.items.map(item => (
              <div key={item.id} className="rounded border border-border p-3 fh-text-caption">
                <span className="font-medium">{formatChannelDisplayName(item.channelId)} · {item.field}</span>
                <span className="block">{item.status}{item.errorMessage ? ` — ${item.errorMessage}` : ''}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="fh-card" aria-label="Unified multi-channel product editor">
        <form
          className="grid min-w-0 gap-3 border-b border-slate-200 p-4 md:grid-cols-5"
          aria-label="Server-side Workspace filters"
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
          <label className="fh-field-label min-w-0">Search<input className="fh-input mt-1" name="search" type="search" /></label>
          <label className="fh-field-label min-w-0">Channel<input className="fh-input mt-1" name="channelId" /></label>
          <label className="fh-field-label min-w-0">Status<input className="fh-input mt-1" name="channelStatus" /></label>
          <label className="fh-field-label min-w-0">Price range<span className="mt-1 flex min-w-0 gap-2"><input aria-label="Minimum price" className="fh-input min-w-0" name="minPrice" type="number" min="0" /><input aria-label="Maximum price" className="fh-input min-w-0" name="maxPrice" type="number" min="0" /></span></label>
          <span className="flex min-w-0 flex-wrap items-end gap-2"><button className="fh-button-secondary fh-button-sm" type="submit">Filter server data</button><button className="fh-button-secondary fh-button-sm" type="reset" onClick={() => controller.updateGridQuery({ search: undefined, channelId: undefined, channelStatus: undefined, minPrice: undefined, maxPrice: undefined })}>Clear</button></span>
        </form>
        <div className="fh-panel-header">
          <div>
            <p className="fh-section-title">Workspace Grid</p>
            <p className="fh-text-caption">Edit Target cells inline. Current values, identities, SKUs, and Mapping are read-only.</p>
          </div>
          <div className="flex items-center gap-2 fh-text-caption">
            <span>{controller.selectedListingCount} Listing{controller.selectedListingCount === 1 ? '' : 's'} selected</span>
            <button type="button" className="fh-button-secondary fh-button-sm" disabled={controller.page <= 1} onClick={() => controller.setPage(controller.page - 1)}>Previous</button>
            <span>Page {controller.page} / {controller.totalPages}</span>
            <button type="button" className="fh-button-secondary fh-button-sm" disabled={controller.page >= controller.totalPages} onClick={() => controller.setPage(controller.page + 1)}>Next</button>
          </div>
        </div>
        {!handsontableLicense && (
          <div className="fh-alert fh-alert-danger m-4" role="alert">
            <Icon name="alert" />
            <span>Production Grid is disabled. Configure a valid commercial Handsontable license.</span>
          </div>
        )}
        {handsontableLicense && <div className="fh-grid-scroll" role="region" aria-label="Scrollable Workspace Grid">
          <div className="ht-theme-main fh-handsontable" style={{ minWidth: gridMinWidth }} aria-label="Virtualized multi-channel Workspace Grid" tabIndex={0}>
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
            dropdownMenu={['filter_by_condition', 'filter_by_value', 'filter_action_bar']}
            copyPaste={{ pasteMode: 'overwrite' }}
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
