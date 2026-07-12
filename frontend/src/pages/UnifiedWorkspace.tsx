import { useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { HotTable } from '@handsontable/react-wrapper'
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
                <span>{channel.channelId}</span>
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
                {controller.grid.channels.map(channel => <option key={channel.channelId} value={channel.channelId}>{channel.channelId}</option>)}
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
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {controller.applyResult.items.map(item => (
              <div key={item.id} className="rounded border border-border p-3 fh-text-caption">
                <span className="font-medium">{item.channelId} · {item.field}</span>
                <span className="block">{item.status}{item.errorMessage ? ` — ${item.errorMessage}` : ''}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="fh-card overflow-hidden" aria-label="Unified multi-channel product editor">
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
        <div className="ht-theme-main fh-handsontable" role="region" aria-label="Virtualized multi-channel Workspace Grid" tabIndex={0}>
          <HotTable
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
            licenseKey="non-commercial-and-evaluation"
            cells={(row: number, column: number) => {
              const settings = {} as Handsontable.CellProperties
              const columnSetting = controller.definition.columns[column]
              const prop = typeof columnSetting?.data === 'string' ? columnSetting.data : ''
              const meta = controller.definition.columnMeta.get(prop)
              const record = controller.definition.records[row]
              if (meta?.kind === 'target' && meta.channelId && meta.field && record) {
                const statusKey = prop.replace(/__target$/, '__status')
                const status = String(record[statusKey] ?? 'unavailable')
                settings.className = `fh-cell-status fh-cell-status-${status}`
                settings.title = `Cell status: ${status.replace(/_/g, ' ')}`
              }
              return settings
            }}
            afterChange={(changes: Handsontable.CellChange[] | null, source: Handsontable.ChangeSource) => {
              if (!changes || source === 'loadData') return
              for (const [row, prop, _oldValue, value] of changes) {
                controller.editCell(row, String(prop), value)
              }
            }}
          />
        </div>
      </section>
    </PageShell>
  )
}
