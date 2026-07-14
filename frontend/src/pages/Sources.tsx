import { translate } from '../i18n'
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
import { formatRelativeTime } from '../i18n/format'

function relTime(d: Date | null): string {
  if (!d) return '-'
  return formatRelativeTime(d)
}

const STATUS_BADGE: Record<Source['status'], { variant: 'success' | 'danger' | 'neutral'; labelKey: string }> = {
  active: { variant: 'success', labelKey: 'sources:sources.active' },
  error: { variant: 'danger', labelKey: 'sources:sources.error' },
  unconfigured: { variant: 'neutral', labelKey: 'sources:sources.unconfigured' },
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
            <Badge variant={badge.variant}>{translate(badge.labelKey)}</Badge>
          </div>
          <p className="fh-text-caption fh-text-mono mt-0.5 truncate">{source.displayUrl}</p>
        </div>
        <button
          onClick={() => info({
            title: translate('sources:sources.editingIsNotAvailableYet'),
            description: translate('sources:sources.thisSourceCannotBeChangedFromThis'),
          })}
          className="fh-button-secondary flex-shrink-0"
        >
          <Icon name="edit" />
          {translate('sources:sources.edit')}
        </button>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-1.5 fh-text-caption">
        <span>
          <span className="text-wp-muted">{translate('sources:sources.type')} </span>
          <span className="font-medium text-text-base capitalize">{source.type.replace(/_/g, ' ')}</span>
        </span>
        <span>
          <span className="text-wp-muted">{translate('sources:sources.products')} </span>
          <span className="font-medium text-text-base">{source.productCount}</span>
        </span>
        <span>
          <span className="text-wp-muted">{translate('sources:sources.lastSynced')} </span>
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
          <h1 className="fh-page-title">{translate('sources:sourceCenter.sources')}</h1>
          <p className="fh-page-subtitle">{translate('sources:sources.dataSourcesForPriceSynchronisation')}</p>
        </div>
        <button
          onClick={() => navigate("/sources/new")}
          className="fh-button-primary flex-shrink-0"
        >
          <Icon name="add" />
          {translate('sources:sources.addSource')}
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
            title={translate('sources:sources.noSourcesConfigured')}
            description={translate('sources:sources.addASourceToStartComparingPrices')}
            action={{ label: translate('sources:sources.addSource'), onClick: () => navigate("/sources/new") }}
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
