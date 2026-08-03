import Icon from './Icon'
import type { IconName } from './Icon'

// Figma: DataDisplay/KPICard (141:3180) — compact business metric card.
export default function KpiCard({ label, value, trend, trendTone = 'neutral', icon }: {
  label: string
  value: string
  trend?: string
  trendTone?: 'up' | 'neutral' | 'warning' | 'danger'
  icon: IconName
}) {
  const trendCls =
    trendTone === 'up' ? 'text-wp-green' :
    trendTone === 'warning' ? 'text-wp-yellow' :
    trendTone === 'danger' ? 'text-wp-red' :
    'text-wp-muted'
  return (
    <div className="fh-stat-card h-[132px]">
      <div className="flex items-center gap-2">
        <p className="text-[13px] font-medium leading-[18px] text-[color:var(--fh-text-secondary)]">{label}</p>
        <span className="ms-auto inline-flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-[color:var(--fh-info-surface)] text-accent">
          <Icon name={icon} size="sm" />
        </span>
      </div>
      <div className="flex items-end gap-2 overflow-hidden">
        <span className="truncate text-[28px] font-semibold leading-9 text-text-base">{value}</span>
        {trend && (
          <span className={['flex-shrink-0 text-xs font-medium leading-[18px]', trendCls].join(' ')}>
            {trend}
          </span>
        )}
      </div>
    </div>
  )
}
