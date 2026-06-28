import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useServices } from '../services/ServiceContext'
import type { Source } from '../services/types'
import { SkeletonCard } from '../components/loading/Skeleton'
import Empty from '../components/Empty'
import { useNotification } from '../notifications/NotificationProvider'

function relTime(d: Date | null): string {
  if (!d) return '—'
  const s = Math.floor((Date.now() - d.getTime()) / 1000)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

const STATUS_BADGE: Record<Source['status'], { cls: string; label: string }> = {
  active:       { cls: 'bg-wp-green/10 text-wp-green',   label: 'Active' },
  error:        { cls: 'bg-wp-red/10 text-wp-red',       label: 'Error' },
  unconfigured: { cls: 'bg-border/60 text-wp-muted',     label: 'Unconfigured' },
}

function SourceCard({ source }: { source: Source }) {
  const badge = STATUS_BADGE[source.status]
  const { info } = useNotification()

  return (
    <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px]">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[15px] font-semibold text-text-base truncate">{source.name}</span>
            <span className={['text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide', badge.cls].join(' ')}>
              {badge.label}
            </span>
          </div>
          <p className="text-[12px] font-mono text-wp-muted mt-0.5 truncate">{source.displayUrl}</p>
        </div>
        <button
          onClick={() => info('Configuration editing available in a future phase.')}
          className="flex-shrink-0 px-3 py-1.5 text-[12px] border border-border rounded-lg text-wp-muted hover:text-text-base hover:border-accent transition-colors"
        >
          Edit
        </button>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-[12px]">
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
    <div className="p-4 sm:p-7 flex flex-col gap-5 max-w-2xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold text-text-base">Sources</h1>
          <p className="text-[13px] text-wp-muted mt-0.5">Data sources for price synchronisation</p>
        </div>
        <button
          onClick={() => navigate('/sources/new')}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-white text-[13px] font-medium hover:bg-accent-hover transition-colors flex-shrink-0"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="w-4 h-4">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Add Source
        </button>
      </div>

      {loading ? (
        <div className="flex flex-col gap-4">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : items.length === 0 ? (
        <div className="bg-bg-card border border-border rounded-card shadow-card">
          <Empty
            title="No sources configured"
            description="Add a Nextcloud Excel source to start syncing prices."
            action={{ label: 'Add Source', onClick: () => navigate('/sources/new') }}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {items.map(s => <SourceCard key={s.id} source={s} />)}
        </div>
      )}
    </div>
  )
}
