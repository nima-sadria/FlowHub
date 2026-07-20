import { Link } from 'react-router-dom'
import { translate } from '../i18n'

export type SettingsSectionName = 'general' | 'users' | 'rateLimits' | 'advanced'

const ITEMS: Array<{ id: SettingsSectionName; labelKey: string; to?: string }> = [
  { id: 'general', labelKey: 'settings:settings.general', to: '/settings' },
  { id: 'users', labelKey: 'settings:users.title', to: '/settings/users' },
  { id: 'rateLimits', labelKey: 'settings:rateLimits.globalApiRateLimits', to: '/rate-limits' },
  { id: 'advanced', labelKey: 'settings:settings.advanced' },
]

export default function SettingsNav({ active }: { active: SettingsSectionName }) {
  return (
    <nav aria-label={translate('settings:settings.settings')} className="fh-card flex w-full flex-col gap-1 p-2.5 lg:w-[220px] lg:flex-shrink-0">
      {ITEMS.map(item => {
        return item.to ? (
          <Link
            key={item.id}
            to={item.to}
            className={[
              'flex min-h-[42px] items-center rounded-md px-2.5 py-2 text-[13px] leading-[22px]',
              item.id === active
                ? 'bg-[color:var(--fh-info-surface)] font-medium text-accent'
                : 'text-[color:var(--fh-text-secondary)] hover:bg-[color:var(--fh-ui-surface-muted)]',
            ].join(' ')}
          >
            {translate(item.labelKey)}
          </Link>
        ) : (
          <span
            key={item.id}
            aria-disabled="true"
            className={[
              'flex min-h-[42px] cursor-not-allowed items-center rounded-md px-2.5 py-2 text-[13px] leading-[22px] opacity-60',
              item.id === active
                ? 'bg-[color:var(--fh-info-surface)] font-medium text-accent'
                : 'text-[color:var(--fh-text-secondary)] hover:bg-[color:var(--fh-ui-surface-muted)]',
            ].join(' ')}
          >
            {translate(item.labelKey)}
          </span>
        )
      })}
    </nav>
  )
}
