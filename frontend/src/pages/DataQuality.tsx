import { useEffect, useState } from 'react'
import PageShell from '../components/PageShell'
import Icon from '../components/Icon'
import { formatChannelDisplayName } from '../features/unifiedWorkspace/channelDisplayName'
import { sourceWorkspaceApi } from '../features/sourceWorkspace/api'
import type { SourceChannel, SourceProfile } from '../features/sourceWorkspace/types'

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
    <div className="fh-page-header"><div><h1 className="fh-page-title">Data Quality</h1><p className="fh-page-subtitle">Technical issues are separated from the daily pricing workflow. One blocked row never blocks unrelated valid products.</p></div></div>
    <section className="fh-card fh-card-pad"><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><label className="fh-field-label">Source<select className="fh-input mt-1" value={sourceId} onChange={event => setSourceId(event.target.value)}><option value="">All Sources</option>{sources.map(source => <option value={source.id} key={source.id}>{source.name}</option>)}</select></label><label className="fh-field-label">Worksheet<input className="fh-input mt-1" value={worksheet} onChange={event => setWorksheet(event.target.value)} placeholder="All worksheets" /></label><label className="fh-field-label">Channel<select className="fh-input mt-1" value={channelId} onChange={event => setChannelId(event.target.value)}><option value="">All Channels</option>{channels.map(channel => <option value={channel.channelId} key={channel.channelId}>{formatChannelDisplayName(channel.channelId, { displayName: channel.name })}</option>)}</select></label><label className="fh-field-label">Product<input className="fh-input mt-1" value={product} onChange={event => setProduct(event.target.value)} placeholder="Source Product name" /></label><label className="fh-field-label">Severity<select className="fh-input mt-1" value={severity} onChange={event => setSeverity(event.target.value)}><option value="">All severities</option><option value="blocked">Blocked</option><option value="error">Error</option><option value="warning">Warning</option></select></label><label className="fh-field-label">Category<input className="fh-input mt-1" value={category} onChange={event => setCategory(event.target.value)} placeholder="Issue category" /></label><label className="fh-field-label">Mapping state<select className="fh-input mt-1" value={mappingState} onChange={event => setMappingState(event.target.value)}><option value="">All mapping states</option><option value="resolved">Resolved</option><option value="unmapped">Unmapped</option><option value="conflict">Conflict</option></select></label></div></section>
    <div className="mt-5 grid gap-3">{grouped.length === 0 ? <div className="fh-card fh-card-pad"><p className="font-medium text-text-base">No Data Quality issues</p><p className="fh-text-caption">Source analysis has not recorded any matching issues.</p></div> : grouped.map(([key, items]) => { const issue = items[0]; return <details className="fh-card fh-card-pad" key={key}><summary className="flex cursor-pointer items-center gap-3"><Icon name={issue.severity === 'warning' ? 'warning' : 'alert'} /><span className="font-medium text-text-base">{issue.category.replace(/_/g, ' ')}</span><span className="fh-badge fh-badge-neutral">{items.length}</span><span className="ms-auto fh-text-caption">{issue.channelId ? formatChannelDisplayName(issue.channelId) : 'All Channels'}</span></summary><div className="mt-4 grid gap-3">{items.map(item => <article className="rounded border border-border p-3" key={item.id}><div className="flex flex-wrap gap-2"><p className="font-medium text-text-base">{item.summary}</p>{item.sourceProductName && <span className="fh-badge fh-badge-neutral">{item.sourceProductName}</span>}{item.mappingState && <span className="fh-badge fh-badge-neutral">Mapping: {item.mappingState}</span>}</div><p className="fh-text-caption mt-1">Recommended action: {item.recommendedAction}</p><details className="mt-2"><summary className="fh-text-caption cursor-pointer">Technical details</summary><pre className="mt-2 overflow-auto rounded bg-bg-base p-2 text-xs">{JSON.stringify(item.technicalDetails, null, 2)}</pre></details></article>)}</div></details> })}</div>
  </PageShell>
}
