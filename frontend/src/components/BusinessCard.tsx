import Badge, { type BadgeVariant } from './Badge'
import Icon, { type IconName } from './Icon'

export type BusinessCardTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

export interface BusinessCardStatus {
  label: string
  tone: BusinessCardTone
  icon: IconName
}

export interface BusinessCardAction {
  label: string
  onClick: () => void
}

interface BusinessCardProps {
  title: string
  value: string
  explanation: string
  meaning: string
  icon: IconName
  status: BusinessCardStatus
  recommendationLabel: string
  recommendation: string
  action?: BusinessCardAction
  testId?: string
}

const badgeVariants: Record<BusinessCardTone, BadgeVariant> = {
  neutral: 'neutral',
  info: 'info',
  success: 'success',
  warning: 'warning',
  danger: 'danger',
}

export default function BusinessCard({
  title,
  value,
  explanation,
  meaning,
  icon,
  status,
  recommendationLabel,
  recommendation,
  action,
  testId,
}: BusinessCardProps) {
  return (
    <article
      className="fh-business-card"
      data-business-card={testId ?? title}
      data-tone={status.tone}
      aria-label={title}
      title={`${meaning} ${recommendation}`}
    >
      <div className="fh-business-card-header">
        <div className="fh-business-card-heading">
          <span className="fh-business-card-icon" aria-hidden="true">
            <Icon name={icon} size="md" />
          </span>
          <h2 className="fh-business-card-title">{title}</h2>
        </div>
        <Badge
          variant={badgeVariants[status.tone]}
          icon={<Icon name={status.icon} />}
        >
          {status.label}
        </Badge>
      </div>

      <bdi className="fh-business-card-value" dir="auto">{value}</bdi>
      <p className="fh-business-card-explanation">{explanation}</p>

      <div className="fh-business-card-recommendation">
        <Icon name="info" label={`${recommendationLabel}: ${recommendation}`} />
        {action && (
          <button type="button" className="fh-toolbar-link flex-shrink-0" onClick={action.onClick}>
            {action.label}
            <Icon name="next" mirrorRtl />
          </button>
        )}
      </div>
    </article>
  )
}
