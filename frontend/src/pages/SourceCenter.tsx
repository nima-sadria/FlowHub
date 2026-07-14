import { translate } from '../i18n'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageShell from '../components/PageShell'
import Icon from '../components/Icon'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceProfile } from '../features/sourceWorkspace/types'

const KIND_LABELS: Record<SourceProfile['sourceKind'], string> = {
  flowhub_sheet: 'sources:sourceCenter.flowhubSheet',
  imported_sheet: 'sources:sourceCenter.importedSpreadsheet',
  external: 'sources:sourceCenter.linkedExternalSource',
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
      const sheet = await sourceWorkspaceApi.createSheet(translate('sources:sourceCenter.defaultPricingSheetName'))
      navigate(`/sheets/${sheet.id}`)
    } finally {
      setCreating(false)
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
                  <p className="fh-text-caption">{translate(KIND_LABELS[source.sourceKind])} {translate('sources:sourceCenter.mappingV')}{source.mappingVersion || translate('sources:sourceConfiguration.notConfigured')}</p>
                </div>
                {source.sheetId && <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => navigate(`/sheets/${source.sheetId}`)}>{translate('sources:sourceCenter.openSheet')}</button>}
                <button className="fh-button-secondary fh-button-sm" type="button" onClick={() => navigate(`/sources/${source.id}`)}>{translate('sources:sourceCenter.configure')}</button>
              </div>
            ))}
          </div>
        )}
      </section>
    </PageShell>
  )
}
