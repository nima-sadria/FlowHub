import type { ReactNode } from 'react'
import Badge, { type BadgeVariant } from './Badge'
import BrandIcon from './BrandIcon'
import Icon, { type IconName } from './Icon'

export type OperationalResourceState = 'connected' | 'needsAttention' | 'setupRequired' | 'disabled' | 'comingSoon'

export interface OperationalResourceFact {
  label: string
  value: ReactNode
}

export interface OperationalResourceAction {
  label: string
  onClick: () => void
  icon?: IconName
  disabled?: boolean
  primary?: boolean
}

export default function OperationalResourceCard({
  resourceId,
  resourceType,
  provider,
  sourceType,
  name,
  description,
  state,
  statusLabel,
  statusVariant,
  statusDetail,
  facts,
  issue,
  actions,
  headerAction,
}: {
  resourceId: string
  resourceType: 'source' | 'channel'
  provider?: string | null
  sourceType?: string | null
  name: string
  description: string
  state: OperationalResourceState
  statusLabel: string
  statusVariant: BadgeVariant
  statusDetail?: ReactNode
  facts: OperationalResourceFact[]
  issue?: ReactNode
  actions: OperationalResourceAction[]
  headerAction?: ReactNode
}) {
  const comingSoon = state === 'comingSoon'
  const setupRequired = state === 'setupRequired'

  return (
    <article
      className={`fh-source-card min-h-[286px] ${comingSoon ? 'opacity-60' : ''}`}
      data-source-card={resourceType === 'source' ? resourceId : undefined}
      data-channel-card={resourceType === 'channel' ? resourceId : undefined}
      data-resource-state={state}
      aria-disabled={comingSoon || undefined}
      title={description}
    >
      <div className="fh-source-card-head">
        <BrandIcon identity={{ provider, sourceType }} label={name} size={36} />
        <div className="min-w-0 flex-1">
          <h3 className="fh-source-card-name">{name}</h3>
          <p className="fh-text-caption truncate">{description}</p>
        </div>
        {!comingSoon && headerAction}
      </div>

      <div className="fh-source-card-row">
        <Badge dot variant={statusVariant}>{statusLabel}</Badge>
        {statusDetail && <span className="fh-text-caption text-end">{statusDetail}</span>}
      </div>

      {facts.length > 0 && (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-2 border-t border-border pt-3">
          {facts.map(fact => (
            <div className="min-w-0" key={fact.label}>
              <dt className="fh-text-caption truncate">{fact.label}</dt>
              <dd className="mt-0.5 truncate text-[13px] font-medium text-text-base" title={typeof fact.value === 'string' ? fact.value : undefined}>
                {fact.value}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {issue && !comingSoon && (
        <div className="fh-alert-warning text-[12px]" role="status">{issue}</div>
      )}

      {!comingSoon && actions.length > 0 && (
        <div className="fh-source-card-actions">
          {actions.map(action => (
            <button
              className={`${action.primary || setupRequired ? 'fh-button-primary' : 'fh-button-secondary'} fh-button-sm`}
              type="button"
              disabled={action.disabled}
              onClick={action.onClick}
              key={action.label}
            >
              {action.icon && <Icon name={action.icon} size="sm" />}
              {action.label}
            </button>
          ))}
        </div>
      )}
    </article>
  )
}
