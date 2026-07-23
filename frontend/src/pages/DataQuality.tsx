import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import PageShell from '../components/PageShell'
import Badge, { type BadgeVariant } from '../components/Badge'
import Icon from '../components/Icon'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { DataQualityScanState, DataQualitySummary, SourceChannel, SourceProfile } from '../features/sourceWorkspace/types'
import { translate } from '../i18n'
import { formatDataQualityCategory, formatDataQualityIssue } from '../i18n/display'
import { formatDateTime, formatNumber, formatRelativeTime } from '../i18n/format'
import { ResourceOptionGroups } from '../components/ResourceOrdering'
import { prepareResourceCollection, sourceChannelSignals, sourceProfileSignals } from '../features/resourceOrdering/resourceOrdering'
import { useServices } from '../services/ServiceContext'

type Issue = {
  id: string
  sourceId?: string
  channelId?: string
  worksheet?: string
  sourceProductName?: string
  mappingState?: string
  category: string
  severity: string
  code: string
  summary: string
  recommendedAction: string
  technicalDetails: Record<string, unknown>
}

const SOURCE_CONFIGURATION_ISSUES = new Set([
  'SOURCE_MAPPING_REQUIRED',
  'MISSING_CHANNEL_WORKSHEET',
  'MISSING_MAPPING_IDENTITY',
  'MISSING_SOURCE_IDENTITY',
  'SHEET_REVISION_REQUIRED',
])

function issueDestination(issue: Issue): string {
  const params = new URLSearchParams({ dataQualityIssue: issue.code })
  if (issue.channelId) params.set('channelId', issue.channelId)
  if (issue.sourceId) params.set('sourceId', issue.sourceId)
  if (issue.worksheet) params.set('worksheet', issue.worksheet)
  if (issue.sourceId && SOURCE_CONFIGURATION_ISSUES.has(issue.code)) {
    // i18n-ignore: internal route, not user-facing copy.
    return `/sources/${encodeURIComponent(issue.sourceId)}?${params}`
  }
  // i18n-ignore: internal route, not user-facing copy.
  return `/products?${params}`
}

const EMPTY_SUMMARY: DataQualitySummary = {
  state: 'never_checked', totalIssues: 0, blockingIssues: 0, warnings: 0,
  affectedProducts: 0, affectedChannels: 0, affectedSources: 0,
  resolvedSinceLastRead: 0, trendSinceLastRead: null,
  productsChecked: 0, sourcesChecked: 0, checkedAt: null, scanId: null,
  errorCode: null, categories: [],
}

function severityVariant(severity: string): BadgeVariant {
  if (severity === 'blocked') return 'danger'
  if (severity === 'warning') return 'warning'
  return 'neutral'
}

function issueSeverityLabel(severity: string): string {
  if (severity === 'blocked') return translate('dataQuality:dataQuality.blocked')
  if (severity === 'error') return translate('dataQuality:dataQuality.error')
  if (severity === 'warning') return translate('dataQuality:dataQuality.warning')
  return severity
}

function SummaryCard({ label, value, suffix, onClick, active }: { label: string; value: string; suffix?: string; onClick?: () => void; active?: boolean }) {
  const content = <>
    <div className="flex items-center justify-between gap-3">
      <span className="fh-stat-card-label">{label}</span>
      <span className="fh-stat-card-icon"><Icon name="products" size="sm" /></span>
    </div>
    <div><span className="fh-stat-card-value">{value}</span>{suffix && <span className="fh-dataquality-card-suffix">{suffix}</span>}</div>
  </>
  return onClick
    ? <button className={`fh-stat-card text-start ${active ? 'ring-2 ring-accent' : ''}`} type="button" aria-pressed={active} onClick={onClick}>{content}</button>
    : <div className="fh-stat-card">{content}</div>
}

function StatePanel({ state, summary, onRun, scanning }: { state: DataQualityScanState; summary: DataQualitySummary; onRun: () => void; scanning: boolean }) {
  if (state === 'issues_found') return null
  const presentation = {
    never_checked: ['info', 'dataQuality.neverCheckedTitle', 'dataQuality.neverCheckedDescription'],
    checking: ['refresh', 'dataQuality.checkingTitle', 'dataQuality.checkingDescription'],
    healthy: ['success', 'dataQuality.healthyTitle', 'dataQuality.healthyDescription'],
    failed: ['error', 'dataQuality.failedTitle', 'dataQuality.failedDescription'],
    permission_denied: ['warning', 'dataQuality.permissionDeniedTitle', 'dataQuality.permissionDeniedDescription'],
  }[state] as ['info' | 'refresh' | 'success' | 'error' | 'warning', string, string]
  return (
    <section className="fh-card fh-card-pad mt-5 text-center" role={state === 'failed' || state === 'permission_denied' ? 'alert' : 'status'}>
      <Icon name={presentation[0]} size="lg" />
      <h2 className="fh-section-title mt-3">{translate(`dataQuality:${presentation[1]}`)}</h2>
      <p className="fh-text-caption mt-2">{translate(`dataQuality:${presentation[2]}`)}</p>
      {summary.checkedAt && <p className="fh-text-caption mt-2">{translate('dataQuality:dataQuality.lastCheck')} {formatDateTime(summary.checkedAt)}</p>}
      {state === 'healthy' && <p className="fh-text-caption mt-2">{translate('dataQuality:dataQuality.healthyCoverage', { sources: formatNumber(summary.sourcesChecked), products: formatNumber(summary.productsChecked) })}</p>}
      {state !== 'permission_denied' && <button className="fh-button-primary mt-4" type="button" disabled={scanning} onClick={onRun}><Icon name="refresh" /> {translate('dataQuality:dataQuality.runCheck')}</button>}
    </section>
  )
}

export default function DataQuality() {
  const { products } = useServices()
  const [issues, setIssues] = useState<Issue[]>([])
  const [summary, setSummary] = useState<DataQualitySummary>(EMPTY_SUMMARY)
  const [sources, setSources] = useState<SourceProfile[]>([])
  const [channels, setChannels] = useState<SourceChannel[]>([])
  const [sourceId, setSourceId] = useState('')
  const [channelId, setChannelId] = useState('')
  const [worksheet, setWorksheet] = useState('')
  const [product, setProduct] = useState('')
  const [mappingState, setMappingState] = useState('')
  const [severity, setSeverity] = useState('')
  const [totalCatalogProducts, setTotalCatalogProducts] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)

  useEffect(() => {
    Promise.all([sourceWorkspaceApi.listSources(), sourceWorkspaceApi.channels()])
      .then(([sourceResult, channelResult]) => { setSources(sourceResult.items); setChannels(channelResult.items) })
  }, [])

  useEffect(() => {
    products.getProducts({ page: 1, pageSize: 1, search: '', status: 'all' }).then(result => setTotalCatalogProducts(result.total)).catch(() => {})
  }, [products])

  const load = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams({ page: '1', pageSize: '200' })
    if (sourceId) params.set('sourceId', sourceId)
    if (channelId) params.set('channelId', channelId)
    if (worksheet) params.set('worksheet', worksheet)
    if (product) params.set('product', product)
    if (mappingState) params.set('mappingState', mappingState)
    if (severity) params.set('severity', severity)
    try {
      const result = await sourceWorkspaceApi.dataQuality(params)
      setIssues(result.items as unknown as Issue[])
      setSummary(result.summary ?? {
        ...EMPTY_SUMMARY,
        state: result.total > 0 ? 'issues_found' : 'never_checked',
        totalIssues: result.total,
      })
    } catch (error) {
      setIssues([])
      setSummary({ ...EMPTY_SUMMARY, state: error instanceof ApiError && error.status === 403 ? 'permission_denied' : 'failed', errorCode: error instanceof ApiError ? error.code ?? String(error.status) : 'REQUEST_FAILED' })
    } finally {
      setLoading(false)
    }
  }, [channelId, mappingState, product, severity, sourceId, worksheet])

  useEffect(() => { void load() }, [load])

  async function runScan() {
    setScanning(true)
    setSummary(current => ({ ...current, state: 'checking' }))
    try {
      await sourceWorkspaceApi.scanDataQuality(sourceId || undefined)
      await load()
    } catch (error) {
      setSummary(current => ({ ...current, state: error instanceof ApiError && error.status === 403 ? 'permission_denied' : 'failed', errorCode: error instanceof ApiError ? error.code ?? String(error.status) : 'SCAN_FAILED' }))
    } finally {
      setScanning(false)
    }
  }

  const sourceResources = useMemo(
    () => prepareResourceCollection(sources, sourceProfileSignals),
    [sources],
  )
  const channelResources = useMemo(
    () => prepareResourceCollection(channels, sourceChannelSignals),
    [channels],
  )

  const state: DataQualityScanState = loading ? 'checking' : summary.state
  const checkedRecently = summary.checkedAt !== null && Date.now() - new Date(summary.checkedAt).getTime() < 60 * 60 * 1000
  const catalogCoverage = totalCatalogProducts && totalCatalogProducts > 0
    ? `${Math.min(100, Math.round((summary.productsChecked / totalCatalogProducts) * 100))}%`
    : undefined

  return <PageShell>
    <div className="fh-page-header">
      <div><h1 className="fh-page-title">{translate('dataQuality:dataQuality.dataQuality')}</h1><p className="fh-page-subtitle">{translate('dataQuality:dataQuality.resolveIssuesBlockingReliableCommerceData')}</p></div>
      <button className="fh-button-primary" type="button" disabled={scanning || state === 'permission_denied'} onClick={() => void runScan()}><Icon name="refresh" /> {scanning ? translate('dataQuality:dataQuality.checking') : translate('dataQuality:dataQuality.runCheck')}</button>
    </div>

    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <SummaryCard label={translate('dataQuality:dataQuality.blockingIssues')} value={formatNumber(summary.blockingIssues)} active={severity === 'blocked'} onClick={() => setSeverity('blocked')} />
      <SummaryCard label={translate('dataQuality:dataQuality.warnings')} value={formatNumber(summary.warnings)} active={severity === 'warning'} onClick={() => setSeverity('warning')} />
      <SummaryCard label={translate('dataQuality:dataQuality.productsChecked')} value={formatNumber(summary.productsChecked)} suffix={catalogCoverage} />
      <SummaryCard label={translate('dataQuality:dataQuality.lastCheckLabel')} value={summary.checkedAt ? formatRelativeTime(summary.checkedAt) : translate('dataQuality:dataQuality.never')} suffix={checkedRecently ? translate('dataQuality:dataQuality.recent') : undefined} />
    </div>

    <div className="fh-dataquality-toolbar">
      <form className="fh-dataquality-search" onSubmit={event => event.preventDefault()}>
        <Icon name="search" size="sm" className="fh-dataquality-search-icon" />
        <input
          className="fh-dataquality-search-input"
          type="search"
          value={product}
          onChange={event => setProduct(event.target.value)}
          placeholder={translate('dataQuality:dataQuality.searchIssues')}
          aria-label={translate('dataQuality:dataQuality.searchIssues')}
        />
      </form>
      <label className="fh-chip-select">
        <span className="sr-only">{translate('dataQuality:dataQuality.allSeverities')}</span>
        <select value={severity} onChange={event => setSeverity(event.target.value)}>
          <option value="">{translate('dataQuality:dataQuality.allSeverities')}</option>
          <option value="blocked">{translate('dataQuality:dataQuality.blocked')}</option>
          <option value="error">{translate('dataQuality:dataQuality.error')}</option>
          <option value="warning">{translate('dataQuality:dataQuality.warning')}</option>
        </select>
        <Icon name="chevronDown" size="sm" className="fh-chip-caret" />
      </label>
      <span className="fh-dataquality-count ms-auto">{translate('dataQuality:dataQuality.issuesCount', { count: summary.totalIssues })}</span>
      <details className="fh-dataquality-filters">
        <summary className="fh-button-secondary fh-button-sm cursor-pointer list-none"><Icon name="filter" size="sm" /> {translate('dataQuality:dataQuality.filters')}</summary>
        <div className="fh-dataquality-filters-panel">
          <label className="fh-field-label">{translate('dataQuality:dataQuality.source')}<select className="fh-input mt-1" value={sourceId} onChange={event => setSourceId(event.target.value)}><option value="">{translate('dataQuality:dataQuality.allSources')}</option><ResourceOptionGroups resources={sourceResources} /></select></label>
          <label className="fh-field-label">{translate('dataQuality:dataQuality.channel')}<select className="fh-input mt-1" value={channelId} onChange={event => setChannelId(event.target.value)}><option value="">{translate('dataQuality:dataQuality.allChannels')}</option><ResourceOptionGroups resources={channelResources} renderLabel={resource => formatChannelDisplayName(resource.id, { displayName: resource.displayName })} /></select></label>
          <label className="fh-field-label">{translate('dataQuality:dataQuality.worksheet')}<input className="fh-input mt-1" value={worksheet} onChange={event => setWorksheet(event.target.value)} placeholder={translate('dataQuality:dataQuality.allWorksheets')} /></label>
          <label className="fh-field-label">{translate('dataQuality:dataQuality.mappingState')}<select className="fh-input mt-1" value={mappingState} onChange={event => setMappingState(event.target.value)}><option value="">{translate('dataQuality:dataQuality.allMappingStates')}</option><option value="resolved">{translate('dataQuality:dataQuality.resolved')}</option><option value="unmapped">{translate('dataQuality:dataQuality.unmapped')}</option><option value="conflict">{translate('dataQuality:dataQuality.conflict')}</option></select></label>
        </div>
      </details>
    </div>

    <StatePanel state={state} summary={summary} onRun={() => void runScan()} scanning={scanning} />

    {(state === 'issues_found' || issues.length > 0) && (
      <div className="fh-card mt-5">
        <div className="fh-grid-scroll">
          <table className="min-w-full border-collapse text-sm">
            <thead>
              <tr>
                <th className="fh-dataquality-th">{translate('dataQuality:dataQuality.issue')}</th>
                <th className="fh-dataquality-th">{translate('dataQuality:dataQuality.record')}</th>
                <th className="fh-dataquality-th">{translate('dataQuality:dataQuality.severity')}</th>
                <th className="fh-dataquality-th">{translate('dataQuality:dataQuality.updated')}</th>
                <th className="fh-dataquality-th" />
              </tr>
            </thead>
            <tbody>
              {issues.map(issue => (
                <tr className="fh-dataquality-row" key={issue.id}>
                  <td className="fh-dataquality-td"><span className="font-medium text-text-base">{formatDataQualityCategory(issue.category)}</span><p className="fh-text-caption mt-0.5">{formatDataQualityIssue(issue.code, 'summary', issue.summary, issue.technicalDetails)}</p></td>
                  <td className="fh-dataquality-td">{issue.sourceProductName ?? (issue.channelId ? formatChannelDisplayName(issue.channelId) : '—')}</td>
                  <td className="fh-dataquality-td"><Badge dot variant={severityVariant(issue.severity)}>{issueSeverityLabel(issue.severity)}</Badge></td>
                  <td className="fh-dataquality-td fh-text-caption">{summary.checkedAt ? formatRelativeTime(summary.checkedAt) : '—'}</td>
                  <td className="fh-dataquality-td"><Link className="fh-button-secondary fh-button-sm" to={issueDestination(issue)}><Icon name="next" /> {translate('dataQuality:dataQuality.openIssue')}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )}

    {summary.scanId && <details className="fh-card fh-card-pad mt-5"><summary className="cursor-pointer font-medium text-text-base">{translate('dataQuality:dataQuality.viewLastScanDetails')}</summary><dl className="mt-3 grid gap-2 sm:grid-cols-3 fh-text-caption"><div><dt>{translate('dataQuality:dataQuality.sourcesChecked')}</dt><dd>{formatNumber(summary.sourcesChecked)}</dd></div><div><dt>{translate('dataQuality:dataQuality.productsChecked')}</dt><dd>{formatNumber(summary.productsChecked)}</dd></div><div><dt>{translate('dataQuality:dataQuality.scanReference')}</dt><dd dir="ltr">{summary.scanId}</dd></div></dl></details>}
  </PageShell>
}
