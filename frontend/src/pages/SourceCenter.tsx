import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageShell from '../components/PageShell'
import Icon from '../components/Icon'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceProfile } from '../features/sourceWorkspace/types'

const KIND_LABELS: Record<SourceProfile['sourceKind'], string> = {
  flowhub_sheet: 'FlowHub Sheet',
  imported_sheet: 'Imported spreadsheet',
  external: 'Linked external Source',
}

export default function SourceCenter() {
  const navigate = useNavigate()
  const [sources, setSources] = useState<SourceProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    sourceWorkspaceApi.listSources().then(result => setSources(result.items)).finally(() => setLoading(false))
  }, [])

  async function createFlowHubSheet() {
    setCreating(true)
    try {
      const sheet = await sourceWorkspaceApi.createSheet('My pricing sheet')
      navigate(`/sheets/${sheet.id}`)
    } finally {
      setCreating(false)
    }
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">Sources</h1>
          <p className="fh-page-subtitle">Choose where Source Products and Channel targets are managed.</p>
        </div>
        <button className="fh-button-secondary" type="button" onClick={() => navigate('/data-quality')}>
          <Icon name="alert" /> Data Quality
        </button>
      </div>

      <section className="grid gap-4 lg:grid-cols-3" aria-label="Source options">
        <article className="fh-card fh-card-pad border-accent/30">
          <span className="fh-badge fh-badge-success">Recommended</span>
          <h2 className="fh-section-title mt-3">FlowHub Sheet</h2>
          <p className="fh-text-caption mt-2">Recommended for easier mapping, safe formulas, and multi-channel pricing.</p>
          <button className="fh-button-primary mt-4" type="button" disabled={creating} onClick={() => void createFlowHubSheet()}>
            <Icon name="add" /> {creating ? 'Creating...' : 'Create Sheet'}
          </button>
        </article>
        <article className="fh-card fh-card-pad">
          <span className="fh-badge fh-badge-success">Recommended migration path</span>
          <h2 className="fh-section-title mt-3">Import your spreadsheet</h2>
          <p className="fh-text-caption mt-2">Bring an existing XLSX or CSV file into FlowHub without changing the original.</p>
          <button className="fh-button-secondary mt-4" type="button" onClick={() => navigate('/sources/import')}>
            <Icon name="upload" /> Import spreadsheet
          </button>
        </article>
        <article className="fh-card fh-card-pad">
          <span className="fh-badge fh-badge-neutral">Advanced</span>
          <h2 className="fh-section-title mt-3">Keep an external Source linked</h2>
          <p className="fh-text-caption mt-2">For workflows that remain managed outside FlowHub. Sources are read once per Workspace Snapshot.</p>
          <button className="fh-button-secondary mt-4" type="button" onClick={() => navigate('/commerce?tab=sources')}>
            <Icon name="connect" /> Manage external Sources
          </button>
        </article>
      </section>

      <section className="fh-card mt-5" aria-label="Managed Sources">
        <div className="fh-panel-header">
          <div><h2 className="fh-section-title">Managed Sources</h2><p className="fh-text-caption">Source Product identity stays separate from Channel Listing identity.</p></div>
        </div>
        {loading ? <p className="fh-card-pad fh-text-caption">Loading Sources...</p> : sources.length === 0 ? (
          <p className="fh-card-pad fh-text-caption">No managed Source yet. Create a FlowHub Sheet or import a spreadsheet.</p>
        ) : (
          <div className="divide-y divide-border">
            {sources.map(source => (
              <div className="flex flex-wrap items-center gap-3 p-4" key={source.id}>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-text-base">{source.name}</p>
                  <p className="fh-text-caption">{KIND_LABELS[source.sourceKind]} · Mapping v{source.mappingVersion || 'not configured'}</p>
                </div>
                {source.sheetId && <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => navigate(`/sheets/${source.sheetId}`)}>Open Sheet</button>}
                <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => navigate(`/sources/${source.id}`)}>Configure</button>
              </div>
            ))}
          </div>
        )}
      </section>
    </PageShell>
  )
}
