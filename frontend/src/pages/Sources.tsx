import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import { SkeletonCard } from '../components/loading/Skeleton'
import { useNotification } from '../notifications/NotificationProvider'
import PageShell from '../components/PageShell'
import Icon from '../components/Icon'
import { useServices } from '../services/ServiceContext'
import type { Source } from '../services/types'

function relTime(d: Date | null): string {
  if (!d) return '-'
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

const STATUS_BADGE: Record<Source['status'], { variant: 'success' | 'danger' | 'neutral'; label: string }> = {
  active: { variant: 'success', label: 'Active' },
  error: { variant: 'danger', label: 'Error' },
  unconfigured: { variant: 'neutral', label: 'Unconfigured' },
}

function SourceCard({ source }: { source: Source }) {
  const badge = STATUS_BADGE[source.status]
  const { info } = useNotification()

  return (
    <div className="fh-card fh-card-pad">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="fh-text-body font-medium truncate">{source.name}</span>
            <Badge variant={badge.variant}>{badge.label}</Badge>
          </div>
          <p className="fh-text-caption fh-text-mono mt-0.5 truncate">{source.displayUrl}</p>
        </div>
        <button
          onClick={() => info({
            title: 'Editing is not available yet',
            description: 'This source cannot be changed from this page.',
          })}
          className="fh-button-secondary flex-shrink-0"
        >
          <Icon name="edit" />
          Edit
        </button>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-1.5 fh-text-caption">
        <span>
          <span className="text-wp-muted">Type: </span>
          <span className="font-medium text-text-base capitalize">{source.type.replace(/_/g, ' ')}</span>
        </span>
        <span>
          <span className="text-wp-muted">Products: </span>
          <span className="font-medium text-text-base">{source.productCount}</span>
        </span>
        <span>
          <span className="text-wp-muted">Last synced: </span>
          <span className="text-text-base">{relTime(source.lastSynced)}</span>
        </span>
      </div>
    </div>
  )
}

export default function Sources() {
  const { sources } = useServices()
  const navigate = useNavigate()
  const [items, setItems] = useState<Source[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    sources.getSources()
      .then(setItems)
      .finally(() => setLoading(false))
  }, [sources])

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">Sources</h1>
          <p className="fh-page-subtitle">Data sources for price synchronisation</p>
        </div>
        <button
          onClick={() => navigate('/sources/new')}
          className="fh-button-primary flex-shrink-0"
        >
          <Icon name="add" />
          Add Source
        </button>
      </div>

      {loading ? (
        <div className="flex flex-col gap-4">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : items.length === 0 ? (
        <div className="fh-card">
          <Empty
            title="No sources configured"
            description="Add a source to start comparing prices."
            action={{ label: 'Add Source', onClick: () => navigate('/sources/new') }}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {items.map(s => <SourceCard key={s.id} source={s} />)}
        </div>
      )}
    </PageShell>
  )
}
