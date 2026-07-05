import { useEffect, useState } from 'react'
import { useServices } from '../services/ServiceContext'
import type { CommerceChannel, CommerceRelationshipMap, CommerceSource } from '../services/types'
import Spinner from '../components/loading/Spinner'
import { useNotification } from '../notifications/NotificationProvider'

type Tab = 'sources' | 'channels'

function prettyStatus(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function statusClass(status: string): string {
  if (['healthy', 'configured', 'current'].includes(status)) return 'fh-badge-success'
  if (['planned', 'future', 'not_configured', 'unknown'].includes(status)) return 'fh-badge-neutral'
  if (['degraded'].includes(status)) return 'fh-badge-warning'
  return 'fh-badge-danger'
}

function SafetyBadges({ readOnly, writeBlocked }: { readOnly: boolean; writeBlocked: boolean }) {
  return (
    <div className="flex flex-wrap gap-2">
      {readOnly && <span className="fh-badge fh-badge-neutral">Read-only mode</span>}
      {writeBlocked && <span className="fh-badge fh-badge-danger">Writes blocked</span>}
    </div>
  )
}

function RelationshipMap({ map }: { map: CommerceRelationshipMap | null }) {
  const nodes = map?.nodes ?? ['Source', 'FlowHub / Data Layer', 'Channel']
  const example = map?.example ?? ['Nextcloud', 'Data Layer', 'WooCommerce']
  return (
    <div className="fh-card fh-card-pad">
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr_auto_1fr] gap-3 items-center text-center">
        <div className="rounded-lg border border-border bg-bg-base px-4 py-3">
          <p className="text-[11px] text-wp-muted">{nodes[0]}</p>
          <p className="text-[14px] font-semibold text-text-base">{example[0]}</p>
        </div>
        <div className="text-[20px] text-wp-muted">↓</div>
        <div className="rounded-lg border border-border bg-bg-base px-4 py-3">
          <p className="text-[11px] text-wp-muted">FlowHub</p>
          <p className="text-[14px] font-semibold text-text-base">{example[1]}</p>
        </div>
        <div className="text-[20px] text-wp-muted">↓</div>
        <div className="rounded-lg border border-border bg-bg-base px-4 py-3">
          <p className="text-[11px] text-wp-muted">{nodes[2]}</p>
          <p className="text-[14px] font-semibold text-text-base">{example[2]}</p>
        </div>
      </div>
    </div>
  )
}

function SourceCard({ source }: { source: CommerceSource }) {
  return (
    <div className="fh-card fh-card-pad flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-[15px] font-semibold text-text-base">{source.name}</h3>
            <span className={['fh-badge', statusClass(source.status)].join(' ')}>
              {prettyStatus(source.status)}
            </span>
          </div>
          <p className="text-[12px] text-wp-muted mt-1">{source.data_role}</p>
        </div>
        <span className="text-[12px] font-medium text-text-base">{source.type}</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[12px]">
        <p><span className="text-wp-muted">Credential status: </span><span className="font-medium text-text-base">{prettyStatus(source.credential_status)}</span></p>
        <p><span className="text-wp-muted">Last health check: </span><span className="font-medium text-text-base">{source.last_health_check ? new Date(source.last_health_check).toLocaleString() : 'Not checked'}</span></p>
        <p><span className="text-wp-muted">Health: </span><span className="font-medium text-text-base">{prettyStatus(source.health?.status ?? 'unknown')}</span></p>
        <p><span className="text-wp-muted">Data role: </span><span className="font-medium text-text-base">{source.data_role}</span></p>
      </div>

      <div className="flex items-center justify-between gap-3">
        <SafetyBadges readOnly={source.read_only} writeBlocked={source.runtime_write_blocked} />
        <a href={source.action_href} className="fh-button-secondary px-3 py-1.5 text-[12px]">
          {source.action_label}
        </a>
      </div>
    </div>
  )
}

function ChannelCard({ channel, onTest, testing }: {
  channel: CommerceChannel
  onTest: (channelId: string) => void
  testing: boolean
}) {
  return (
    <div className="fh-card fh-card-pad flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-[15px] font-semibold text-text-base">{channel.name}</h3>
            <span className={['fh-badge', statusClass(channel.status)].join(' ')}>
              {prettyStatus(channel.status)}
            </span>
            {channel.placeholder && <span className="fh-badge fh-badge-neutral">Future channel placeholder</span>}
          </div>
          <p className="text-[12px] text-wp-muted mt-1">{channel.capabilities_summary.join(', ')}</p>
        </div>
        <span className="text-[12px] font-medium text-text-base">{channel.type}</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[12px]">
        <p><span className="text-wp-muted">Credential status: </span><span className="font-medium text-text-base">{prettyStatus(channel.credential_status)}</span></p>
        <p><span className="text-wp-muted">Last health check: </span><span className="font-medium text-text-base">{channel.last_health_check ? new Date(channel.last_health_check).toLocaleString() : 'Not checked'}</span></p>
        <p><span className="text-wp-muted">Health: </span><span className="font-medium text-text-base">{prettyStatus(channel.health?.status ?? 'unknown')}</span></p>
        <p><span className="text-wp-muted">Capabilities: </span><span className="font-medium text-text-base">{channel.capabilities_summary.join(', ')}</span></p>
      </div>

      <div className="flex items-center justify-between gap-3">
        <SafetyBadges readOnly={channel.read_only} writeBlocked={channel.write_blocked} />
        <button
          onClick={() => onTest(channel.id)}
          disabled={testing}
          className="fh-button-secondary px-3 py-1.5 text-[12px]"
        >
          {testing && <Spinner size="sm" />}
          {testing ? 'Testing' : 'Test connection'}
        </button>
      </div>
    </div>
  )
}

export default function CommerceHub() {
  const { commerce } = useServices()
  const { info, error: notifyError } = useNotification()
  const [tab, setTab] = useState<Tab>('channels')
  const [sources, setSources] = useState<CommerceSource[]>([])
  const [channels, setChannels] = useState<CommerceChannel[]>([])
  const [map, setMap] = useState<CommerceRelationshipMap | null>(null)
  const [loading, setLoading] = useState(true)
  const [testingId, setTestingId] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([commerce.getSources(), commerce.getChannels()])
      .then(([sourceData, channelData]) => {
        setSources(sourceData.items)
        setMap(sourceData.relationship_map)
        setChannels(channelData.items)
      })
      .finally(() => setLoading(false))
  }, [commerce])

  async function handleTest(channelId: string) {
    setTestingId(channelId)
    try {
      const result = await commerce.testChannel(channelId)
      if (result.ok) info(result.message)
      else notifyError(result.message)
    } catch {
      notifyError('Unable to test connection')
    } finally {
      setTestingId(null)
    }
  }

  return (
    <div className="fh-page max-w-5xl">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="fh-page-title">Commerce Hub</h1>
          <p className="fh-page-subtitle">Read-only source and channel overview</p>
        </div>
        <SafetyBadges readOnly writeBlocked />
      </div>

      <RelationshipMap map={map} />

      <div className="flex items-center gap-1 bg-bg-base rounded-lg p-1 border border-border w-fit">
        {(['sources', 'channels'] as const).map(item => (
          <button
            key={item}
            onClick={() => setTab(item)}
            className={[
              'px-3 py-1.5 text-[13px] font-medium rounded capitalize transition-colors',
              tab === item ? 'bg-bg-card text-accent shadow-sm' : 'text-wp-muted hover:text-text-base',
            ].join(' ')}
          >
            {item === 'sources' ? 'Sources' : 'Channels'}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="fh-card fh-card-pad flex items-center gap-2 text-[13px] text-wp-muted">
          <Spinner size="sm" />Loading Commerce Hub
        </div>
      ) : tab === 'sources' ? (
        <section>
          <div className="mb-4">
            <h2 className="text-[16px] font-semibold text-text-base">Sources</h2>
            <p className="text-[12px] text-wp-muted mt-1">Input systems that feed FlowHub / Data Layer.</p>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {sources.map(source => <SourceCard key={source.id} source={source} />)}
          </div>
        </section>
      ) : (
        <section>
          <div className="mb-4">
            <h2 className="text-[16px] font-semibold text-text-base">Channels</h2>
            <p className="text-[12px] text-wp-muted mt-1">Commerce systems that receive catalog visibility from FlowHub.</p>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {channels.map(channel => (
              <ChannelCard
                key={channel.id}
                channel={channel}
                onTest={(id) => void handleTest(id)}
                testing={testingId === channel.id}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
