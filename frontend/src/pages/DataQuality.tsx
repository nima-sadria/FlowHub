import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import PageShell from '../components/PageShell'
import Icon from '../components/Icon'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { DataQualityScanState, DataQualitySummary, SourceChannel, SourceProfile } from '../features/sourceWorkspace/types'
import { translate } from '../i18n'
import { formatDataQualityCategory, formatDataQualityIssue, formatStatus } from '../i18n/display'
import { formatDateTime, formatNumber } from '../i18n/format'
import { ResourceOptionGroups } from '../components/ResourceOrdering'
import { prepareResourceCollection, sourceChannelSignals, sourceProfileSignals } from '../features/resourceOrdering/resourceOrdering'

type Issue = {
  id: string
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

const EMPTY_SUMMARY: DataQualitySummary = {
  state: 'never_checked', totalIssues: 0, blockingIssues: 0, warnings: 0,
  affectedProducts: 0, affectedChannels: 0, affectedSources: 0,
  resolvedSinceLastRead: 0, trendSinceLastRead: null,
  productsChecked: 0, sourcesChecked: 0, checkedAt: null, scanId: null,
  errorCode: null, categories: [],
}

function SummaryCard({ label, value, icon, onClick, active, emptyLabel }: { label: string; value: number | null; icon: 'alert' | 'error' | 'warning' | 'products' | 'channel' | 'file' | 'activity' | 'success'; onClick?: () => void; active?: boolean; emptyLabel?: string }) {
  // i18n-ignore: the following literal contains Tailwind class names, not user-facing copy.
  const content = <><Icon name={icon} /><span className="fh-text-caption">{label}</span>{value == null ? <span className="mt-2 block text-sm font-medium text-text-base">{emptyLabel}</span> : <strong className="mt-2 block text-2xl text-text-base">{formatNumber(value)}</strong>}</>
  return onClick
    ? <button className={`fh-stat-card text-start ${active ? 'ring-2 ring-accent' : ''}`} type="button" aria-pressed={active === undefined ? undefined : active} onClick={onClick}>{content}</button>
    : <div className="fh-stat-card">{content}</div>
}

function issueSeverityLabel(severity: string): string {
  if (severity === 'blocked') return translate('dataQuality:dataQuality.blocked')
  if (severity === 'error') return translate('dataQuality:dataQuality.error')
  if (severity === 'warning') return translate('dataQuality:dataQuality.warning')
  return formatStatus(severity)
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
    <section className="fh-card fh-card-pad text-center" role={state === 'failed' || state === 'permission_denied' ? 'alert' : 'status'}>
      <Icon name={presentation[0]} size="lg" />
      <h2 className="fh-section-title mt-3">{translate(`dataQuality:${presentation[1]}`)}</h2>
      <p className="fh-text-caption mt-2">{translate(`dataQuality:${presentation[2]}`)}</p>
      {summary.checkedAt && <p className="fh-text-caption mt-2">{translate('dataQuality:dataQuality.lastCheck')} {formatDateTime(summary.checkedAt)}</p>}
      {state === 'healthy' && <p className="fh-text-caption mt-2">{translate('dataQuality:dataQuality.healthyCoverage', { sources: formatNumber(summary.sourcesChecked), products: formatNumber(summary.productsChecked) })}</p>}
      {state !== 'permission_denied' && <button className="fh-button-primary mt-4" type="button" disabled={scanning} onClick={onRun}><Icon name="refresh" /> {translate('dataQuality:dataQuality.runCheckAgain')}</button>}
    </section>
  )
}

export default function DataQuality() {
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
  const [category, setCategory] = useState('')
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const filtersRef = useRef<HTMLDetailsElement>(null)
  const sourceFilterRef = useRef<HTMLSelectElement>(null)
  const channelFilterRef = useRef<HTMLSelectElement>(null)
  const productFilterRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    Promise.all([sourceWorkspaceApi.listSources(), sourceWorkspaceApi.channels()])
      .then(([sourceResult, channelResult]) => { setSources(sourceResult.items); setChannels(channelResult.items) })
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams({ page: '1', pageSize: '200' })
    if (sourceId) params.set('sourceId', sourceId)
    if (channelId) params.set('channelId', channelId)
    if (worksheet) params.set('worksheet', worksheet)
    if (product) params.set('product', product)
    if (mappingState) params.set('mappingState', mappingState)
    if (severity) params.set('severity', severity)
    if (category) params.set('category', category)
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
  }, [category, channelId, mappingState, product, severity, sourceId, worksheet])

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

  const grouped = useMemo(() => Object.entries(issues.reduce<Record<string, Issue[]>>((result, issue) => {
    const key = `${issue.severity}:${issue.category}:${issue.channelId ?? 'all'}`
    ;(result[key] ??= []).push(issue)
    return result
  }, {})), [issues])
  const sourceResources = useMemo(
    () => prepareResourceCollection(sources, sourceProfileSignals),
    [sources],
  )
  const channelResources = useMemo(
    () => prepareResourceCollection(channels, sourceChannelSignals),
    [channels],
  )

  function showFilter(control: { current: HTMLElement | null }) {
    if (filtersRef.current) filtersRef.current.open = true
    queueMicrotask(() => control.current?.focus())
  }

  function showAllIssues() {
    setSourceId('')
    setChannelId('')
    setWorksheet('')
    setProduct('')
    setMappingState('')
    setSeverity('')
    setCategory('')
  }

  const state: DataQualityScanState = loading ? 'checking' : summary.state
  return <PageShell>
    <div className="fh-page-header">
      <div><h1 className="fh-page-title">{translate('dataQuality:dataQuality.dataQuality')}</h1><p className="fh-page-subtitle">{translate('dataQuality:dataQuality.summaryFirstDescription')}</p></div>
      <button className="fh-button-primary" type="button" disabled={scanning || state === 'permission_denied'} onClick={() => void runScan()}><Icon name="refresh" /> {scanning ? translate('dataQuality:dataQuality.checking') : translate('dataQuality:dataQuality.runCheckAgain')}</button>
    </div>

    <section aria-labelledby="data-quality-summary">
      <div className="mb-3 flex items-center gap-3"><h2 className="fh-section-title" id="data-quality-summary">{translate('dataQuality:dataQuality.summary')}</h2>{summary.checkedAt && <span className="fh-text-caption">{translate('dataQuality:dataQuality.lastCheck')} {formatDateTime(summary.checkedAt)}</span>}</div>
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <SummaryCard icon="alert" label={translate('dataQuality:dataQuality.totalIssues')} value={summary.totalIssues} active={!sourceId && !channelId && !worksheet && !product && !mappingState && !severity && !category} onClick={showAllIssues} />
        <SummaryCard icon="error" label={translate('dataQuality:dataQuality.blockingIssues')} value={summary.blockingIssues} active={severity === 'blocked'} onClick={() => setSeverity('blocked')} />
        <SummaryCard icon="warning" label={translate('dataQuality:dataQuality.warnings')} value={summary.warnings} active={severity === 'warning'} onClick={() => setSeverity('warning')} />
        <SummaryCard icon="products" label={translate('dataQuality:dataQuality.affectedProducts')} value={summary.affectedProducts} onClick={() => showFilter(productFilterRef)} />
        <SummaryCard icon="channel" label={translate('dataQuality:dataQuality.affectedChannels')} value={summary.affectedChannels} onClick={() => showFilter(channelFilterRef)} />
        <SummaryCard icon="file" label={translate('dataQuality:dataQuality.affectedSources')} value={summary.affectedSources} onClick={() => showFilter(sourceFilterRef)} />
        <SummaryCard icon="activity" label={translate('dataQuality:dataQuality.trendSinceLastRead')} value={summary.trendSinceLastRead} emptyLabel={translate('dataQuality:dataQuality.noPreviousRead')} />
        <SummaryCard icon="success" label={translate('dataQuality:dataQuality.resolvedSinceLastRead')} value={summary.resolvedSinceLastRead} />
      </div>
    </section>

    {summary.categories.length > 0 && <section className="fh-card fh-card-pad mt-5"><h2 className="fh-section-title">{translate('dataQuality:dataQuality.mostCommonProblems')}</h2><div className="mt-3 flex flex-wrap gap-2">{summary.categories.slice(0, 5).map(item => <button className="fh-badge fh-badge-neutral" type="button" aria-pressed={category === item.category} key={item.category} onClick={() => setCategory(item.category)}>{formatDataQualityCategory(item.category)} · {formatNumber(item.count)}</button>)}</div></section>}

    <StatePanel state={state} summary={summary} onRun={() => void runScan()} scanning={scanning} />

    {(state === 'issues_found' || issues.length > 0) && <>
      <details className="fh-card fh-card-pad mt-5" ref={filtersRef}>
        <summary className="flex cursor-pointer items-center gap-2 font-medium text-text-base"><Icon name="filter" /> {translate('dataQuality:dataQuality.filters')}</summary>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="fh-field-label">{translate('dataQuality:dataQuality.source')}<select className="fh-input mt-1" ref={sourceFilterRef} value={sourceId} onChange={event => setSourceId(event.target.value)}><option value="">{translate('dataQuality:dataQuality.allSources')}</option><ResourceOptionGroups resources={sourceResources} /></select></label>
          <label className="fh-field-label">{translate('dataQuality:dataQuality.worksheet')}<input className="fh-input mt-1" value={worksheet} onChange={event => setWorksheet(event.target.value)} placeholder={translate('dataQuality:dataQuality.allWorksheets')} /></label>
          <label className="fh-field-label">{translate('dataQuality:dataQuality.channel')}<select className="fh-input mt-1" ref={channelFilterRef} value={channelId} onChange={event => setChannelId(event.target.value)}><option value="">{translate('dataQuality:dataQuality.allChannels')}</option><ResourceOptionGroups resources={channelResources} renderLabel={resource => formatChannelDisplayName(resource.id, { displayName: resource.displayName })} /></select></label>
          <label className="fh-field-label">{translate('dataQuality:dataQuality.product')}<input className="fh-input mt-1" ref={productFilterRef} value={product} onChange={event => setProduct(event.target.value)} placeholder={translate('dataQuality:dataQuality.sourceProductName')} /></label>
          <label className="fh-field-label">{translate('dataQuality:dataQuality.severity')}<select className="fh-input mt-1" value={severity} onChange={event => setSeverity(event.target.value)}><option value="">{translate('dataQuality:dataQuality.allSeverities')}</option><option value="blocked">{translate('dataQuality:dataQuality.blocked')}</option><option value="error">{translate('dataQuality:dataQuality.error')}</option><option value="warning">{translate('dataQuality:dataQuality.warning')}</option></select></label>
          <label className="fh-field-label">{translate('dataQuality:dataQuality.category')}<input className="fh-input mt-1" value={category} onChange={event => setCategory(event.target.value)} placeholder={translate('dataQuality:dataQuality.issueCategory')} /></label>
          <label className="fh-field-label">{translate('dataQuality:dataQuality.mappingState')}<select className="fh-input mt-1" value={mappingState} onChange={event => setMappingState(event.target.value)}><option value="">{translate('dataQuality:dataQuality.allMappingStates')}</option><option value="resolved">{translate('dataQuality:dataQuality.resolved')}</option><option value="unmapped">{translate('dataQuality:dataQuality.unmapped')}</option><option value="conflict">{translate('dataQuality:dataQuality.conflict')}</option></select></label>
        </div>
      </details>
      <section className="mt-5" aria-labelledby="issue-list-title"><h2 className="fh-section-title mb-3" id="issue-list-title">{translate('dataQuality:dataQuality.issueList')}</h2><div className="grid gap-3">{grouped.map(([key, items]) => { const issue = items[0]; return <details className="fh-card fh-card-pad" key={key}><summary className="flex cursor-pointer items-center gap-3"><Icon name={issue.severity === 'warning' ? 'warning' : 'alert'} /><span className="font-medium text-text-base">{formatDataQualityCategory(issue.category)}</span><span className={`fh-badge ${issue.severity === 'warning' ? 'fh-badge-warning' : 'fh-badge-danger'}`}>{issueSeverityLabel(issue.severity)}</span><span className="fh-badge fh-badge-neutral">{formatNumber(items.length)}</span><span className="ms-auto fh-text-caption">{issue.channelId ? formatChannelDisplayName(issue.channelId) : translate('dataQuality:dataQuality.allChannels')}</span></summary><div className="mt-4 grid gap-3">{items.map(item => <article className="rounded border border-border p-3" key={item.id}><div className="flex flex-wrap gap-2"><p className="font-medium text-text-base">{formatDataQualityIssue(item.code, 'summary', item.summary, item.technicalDetails)}</p>{item.sourceProductName && <span className="fh-badge fh-badge-neutral">{item.sourceProductName}</span>}{item.mappingState && <span className="fh-badge fh-badge-neutral">{translate('dataQuality:dataQuality.columnSetup')} {formatStatus(item.mappingState)}</span>}</div><p className="fh-text-caption mt-1">{translate('dataQuality:dataQuality.recommendedAction')} {formatDataQualityIssue(item.code, 'action', item.recommendedAction, item.technicalDetails)}</p><details className="mt-2"><summary className="fh-text-caption cursor-pointer">{translate('dataQuality:dataQuality.technicalDetails')}</summary><pre className="mt-2 overflow-auto rounded bg-bg-base p-2 text-xs">{JSON.stringify(item.technicalDetails, null, 2)}</pre></details></article>)}</div></details> })}</div></section>
    </>}

    {summary.scanId && <details className="fh-card fh-card-pad mt-5"><summary className="cursor-pointer font-medium text-text-base">{translate('dataQuality:dataQuality.viewLastScanDetails')}</summary><dl className="mt-3 grid gap-2 sm:grid-cols-3 fh-text-caption"><div><dt>{translate('dataQuality:dataQuality.sourcesChecked')}</dt><dd>{formatNumber(summary.sourcesChecked)}</dd></div><div><dt>{translate('dataQuality:dataQuality.productsChecked')}</dt><dd>{formatNumber(summary.productsChecked)}</dd></div><div><dt>{translate('dataQuality:dataQuality.scanReference')}</dt><dd dir="ltr">{summary.scanId}</dd></div></dl></details>}
  </PageShell>
}
