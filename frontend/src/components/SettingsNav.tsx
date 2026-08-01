import { NavLink } from 'react-router'
import { translate } from '../i18n'
import { useAuth } from '../auth'
import { effectiveHasPerm } from '../utils/permissions'

export type SettingsSectionName = 'general' | 'exchangeRates' | 'users' | 'rateLimits' | 'advanced'

const ITEMS: Array<{ id: SettingsSectionName; labelKey: string; to?: string; permission?: string; adminOnly?: boolean }> = [
  { id: 'general', labelKey: 'settings:settings.general', to: '/settings', permission: 'can_view_settings' },
  { id: 'exchangeRates', labelKey: 'settings:exchangeRates.title', to: '/settings/exchange-rates' },
  { id: 'users', labelKey: 'navigation:sidebar.users', to: '/settings/users', permission: 'can_view_settings', adminOnly: true },
  { id: 'rateLimits', labelKey: 'navigation:sidebar.rateLimits', to: '/settings/rate-limits', permission: 'can_view_settings' },
  { id: 'advanced', labelKey: 'settings:settings.advanced', to: '/settings/advanced', permission: 'can_view_settings' },
]

export default function SettingsNav() {
  const { user } = useAuth()
  const isAdmin = Boolean(user?.is_admin || user?.is_super_admin)
  const items = ITEMS.filter(item => {
    if (item.adminOnly && !isAdmin) return false
    return !item.permission || effectiveHasPerm(user, item.permission)
  })
  return (
    <nav aria-label={translate('settings:settings.settings')} className="fh-card flex w-full flex-col gap-1 p-2.5 lg:w-[220px] lg:flex-shrink-0">
      {items.map(item => (
          <NavLink
            key={item.id}
            to={item.to!}
            end
            className={({ isActive }) => [
              'flex min-h-[42px] items-center rounded-[var(--fh-radius-md)] px-2.5 py-2 text-[13px] leading-[22px]',
              isActive
                ? 'bg-[color:var(--fh-info-surface)] font-medium text-accent'
                : 'text-[color:var(--fh-text-secondary)] hover:bg-[color:var(--fh-ui-surface-muted)]',
            ].join(' ')}
          >
            {translate(item.labelKey)}
          </NavLink>
      ))}
    </nav>
  )
}
