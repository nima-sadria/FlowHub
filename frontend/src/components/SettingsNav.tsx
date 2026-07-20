import { Link } from 'react-router-dom'
import { translate } from '../i18n'

export type SettingsSectionName = 'General' | 'Users' | 'Rate Limits' | 'Advanced'

const ITEMS: Array<{ label: SettingsSectionName; labelKey: string; to?: string }> = [
  { label: 'General', labelKey: 'settings:settings.general', to: '/settings' },
  { label: 'Users', labelKey: 'settings:users.title', to: '/settings/users' },
  { label: 'Rate Limits', labelKey: 'settings:rateLimits.globalApiRateLimits', to: '/rate-limits' },
  { label: 'Advanced', labelKey: 'settings:settings.advanced' },
]

export default function SettingsNav({ active }: { active: SettingsSectionName }) {
  return (
    <nav aria-label={translate('settings:settings.settings')} className="fh-card flex w-full flex-col gap-1 p-2.5 lg:w-[220px] lg:flex-shrink-0">
      {ITEMS.map(item => {
        const className = [
          'flex min-h-[42px] items-center rounded-md px-2.5 py-2 text-[13px] leading-[22px]',
          item.label === active
            ? 'bg-[color:var(--fh-info-surface)] font-medium text-accent'
            : 'text-[color:var(--fh-text-secondary)] hover:bg-[color:var(--fh-ui-surface-muted)]',
          !item.to ? 'cursor-not-allowed opacity-60' : '',
        ].join(' ')
        return item.to ? (
          <Link key={item.label} to={item.to} className={className}>{translate(item.labelKey)}</Link>
        ) : (
          <span key={item.label} aria-disabled="true" className={className}>{translate(item.labelKey)}</span>
        )
      })}
    </nav>
  )
}
