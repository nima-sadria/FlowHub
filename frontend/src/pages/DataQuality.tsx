import { translate } from '../i18n'
import { useEffect, useState } from 'react'
import PageShell from '../components/PageShell'
import Icon from '../components/Icon'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceChannel, SourceProfile } from '../features/sourceWorkspace/types'
import { formatDataQualityCategory, formatDataQualityIssue, formatStatus } from '../i18n/display'

type Issue = { id: string; channelId?: string; worksheet?: string; sourceProductName?: string; mappingState?: string; category: string; severity: string; code: string; summary: string; recommendedAction: string; technicalDetails: Record<string, unknown> }

export default function DataQuality() {
  const [issues, setIssues] = useState<Issue[]>([])
  const [sources, setSources] = useState<SourceProfile[]>([])
  const [channels, setChannels] = useState<SourceChannel[]>([])
  const [sourceId, setSourceId] = useState('')
  const [channelId, setChannelId] = useState('')
  const [worksheet, setWorksheet] = useState('')
  const [product, setProduct] = useState('')
  const [mappingState, setMappingState] = useState('')
  const [severity, setSeverity] = useState('')
  const [category, setCategory] = useState('')
  useEffect(() => { Promise.all([sourceWorkspaceApi.listSources(), sourceWorkspaceApi.channels()]).then(([sourceResult, channelResult]) => { setSources(sourceResult.items); setChannels(channelResult.items) }) }, [])
  useEffect(() => {
    const params = new URLSearchParams({ page: '1', pageSize: '200' })
    if (sourceId) params.set('sourceId', sourceId)
    if (channelId) params.set('channelId', channelId)
    if (worksheet) params.set('worksheet', worksheet)
    if (product) params.set('product', product)
    if (mappingState) params.set('mappingState', mappingState)
    if (severity) params.set('severity', severity)
    if (category) params.set('category', category)
    sourceWorkspaceApi.dataQuality(params).then(result => setIssues(result.items as unknown as Issue[]))
  }, [sourceId, channelId, worksheet, product, mappingState, severity, category])
  const grouped = Object.entries(issues.reduce<Record<string, Issue[]>>((result, issue) => {
    const key = `${issue.severity}:${issue.category}:${issue.channelId ?? 'all'}`
    ;(result[key] ??= []).push(issue)
    return result
  }, {}))
  return <PageShell>
    <div className="fh-page-header"><div><h1 className="fh-page-title">{translate('dataQuality:dataQuality.dataQuality')}</h1><p className="fh-page-subtitle">{translate('dataQuality:dataQuality.technicalIssuesAreSeparatedFromTheDaily')}</p></div></div>
    <section className="fh-card fh-card-pad"><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><label className="fh-field-label">{translate('dataQuality:dataQuality.source')}<select className="fh-input mt-1" value={sourceId} onChange={event => setSourceId(event.target.value)}><option value="">{translate('dataQuality:dataQuality.allSources')}</option>{sources.map(source => <option value={source.id} key={source.id}>{source.name}</option>)}</select></label><label className="fh-field-label">{translate('dataQuality:dataQuality.worksheet')}<input className="fh-input mt-1" value={worksheet} onChange={event => setWorksheet(event.target.value)} placeholder={translate('dataQuality:dataQuality.allWorksheets')} /></label><label className="fh-field-label">{translate('dataQuality:dataQuality.channel')}<select className="fh-input mt-1" value={channelId} onChange={event => setChannelId(event.target.value)}><option value="">{translate('dataQuality:dataQuality.allChannels')}</option>{channels.map(channel => <option value={channel.channelId} key={channel.channelId}>{formatChannelDisplayName(channel.channelId, { displayName: channel.name })}</option>)}</select></label><label className="fh-field-label">{translate('dataQuality:dataQuality.product')}<input className="fh-input mt-1" value={product} onChange={event => setProduct(event.target.value)} placeholder={translate('dataQuality:dataQuality.sourceProductName')} /></label><label className="fh-field-label">{translate('dataQuality:dataQuality.severity')}<select className="fh-input mt-1" value={severity} onChange={event => setSeverity(event.target.value)}><option value="">{translate('dataQuality:dataQuality.allSeverities')}</option><option value="blocked">{translate('dataQuality:dataQuality.blocked')}</option><option value="error">{translate('dataQuality:dataQuality.error')}</option><option value="warning">{translate('dataQuality:dataQuality.warning')}</option></select></label><label className="fh-field-label">{translate('dataQuality:dataQuality.category')}<input className="fh-input mt-1" value={category} onChange={event => setCategory(event.target.value)} placeholder={translate('dataQuality:dataQuality.issueCategory')} /></label><label className="fh-field-label">{translate('dataQuality:dataQuality.mappingState')}<select className="fh-input mt-1" value={mappingState} onChange={event => setMappingState(event.target.value)}><option value="">{translate('dataQuality:dataQuality.allMappingStates')}</option><option value="resolved">{translate('dataQuality:dataQuality.resolved')}</option><option value="unmapped">{translate('dataQuality:dataQuality.unmapped')}</option><option value="conflict">{translate('dataQuality:dataQuality.conflict')}</option></select></label></div></section>
    <div className="mt-5 grid gap-3">{grouped.length === 0 ? <div className="fh-card fh-card-pad"><p className="font-medium text-text-base">{translate('dataQuality:dataQuality.noDataQualityIssues')}</p><p className="fh-text-caption">{translate('dataQuality:dataQuality.sourceAnalysisHasNotRecordedAnyMatching')}</p></div> : grouped.map(([key, items]) => { const issue = items[0]; return <details className="fh-card fh-card-pad" key={key}><summary className="flex cursor-pointer items-center gap-3"><Icon name={issue.severity === "warning" ? "warning" : "alert"} /><span className="font-medium text-text-base">{formatDataQualityCategory(issue.category)}</span><span className="fh-badge fh-badge-neutral">{items.length}</span><span className="ms-auto fh-text-caption">{issue.channelId ? formatChannelDisplayName(issue.channelId) : translate('dataQuality:dataQuality.allChannels')}</span></summary><div className="mt-4 grid gap-3">{items.map(item => <article className="rounded border border-border p-3" key={item.id}><div className="flex flex-wrap gap-2"><p className="font-medium text-text-base">{formatDataQualityIssue(item.code, 'summary', item.summary, item.technicalDetails)}</p>{item.sourceProductName && <span className="fh-badge fh-badge-neutral">{item.sourceProductName}</span>}{item.mappingState && <span className="fh-badge fh-badge-neutral">{translate('dataQuality:dataQuality.mapping')} {formatStatus(item.mappingState)}</span>}</div><p className="fh-text-caption mt-1">{translate('dataQuality:dataQuality.recommendedAction')} {formatDataQualityIssue(item.code, 'action', item.recommendedAction, item.technicalDetails)}</p><details className="mt-2"><summary className="fh-text-caption cursor-pointer">{translate('dataQuality:dataQuality.technicalDetails')}</summary><pre className="mt-2 overflow-auto rounded bg-bg-base p-2 text-xs">{JSON.stringify(item.technicalDetails, null, 2)}</pre></details></article>)}</div></details> })}</div>
  </PageShell>
}
