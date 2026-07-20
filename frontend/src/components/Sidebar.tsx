import { translate } from '../i18n'
import { NavLink, useLocation, useSearchParams } from 'react-router-dom'
import type { AuthUser } from '../auth'
import Icon, { routeIconMap } from './Icon'
import type { IconName } from './Icon'
import IconButton from './IconButton'
import { effectiveHasPerm } from '../utils/permissions'

type HealthStatus = 'ok' | 'error' | 'loading'

interface Props {
  open: boolean
  collapsed: boolean
  onClose: () => void
  user: AuthUser | null
  health: HealthStatus
}

interface NavItem {
  labelKey: string
  to: string
  icon: IconName
  permission: string
  /** Overrides NavLink's default active matching (query-tab routes). */
  isActive?: (pathname: string, tab: string | null) => boolean
}

interface NavGroup {
  sectionKey: string | null
  items: NavItem[]
}

// Figma: Navigation/Sidebar (118:1384) — grouped seller-first navigation.
const NAV_GROUPS: NavGroup[] = [
  {
    sectionKey: null,
    items: [
      { labelKey: 'navigation:sidebar.dashboard', to: '/home', icon: routeIconMap.Dashboard, permission: 'can_access_site' },
    ],
  },
  {
    sectionKey: 'navigation:sidebar.commerce',
    items: [
      { labelKey: 'navigation:sidebar.products', to: '/products', icon: routeIconMap.Products, permission: 'can_fetch' },
      { labelKey: 'navigation:sidebar.orders', to: '/orders', icon: routeIconMap.Orders, permission: 'can_fetch' },
      { labelKey: 'navigation:sidebar.workspace', to: '/workspace', icon: routeIconMap.Workspace, permission: 'can_fetch' },
    ],
  },
  {
    sectionKey: 'navigation:sidebar.integrations',
    items: [
      {
        labelKey: 'navigation:sidebar.sources',
        to: '/commerce?tab=sources',
        icon: routeIconMap.Sources,
        permission: 'can_access_site',
        isActive: (pathname, tab) => pathname === '/commerce' && tab === 'sources',
      },
      {
        labelKey: 'navigation:sidebar.channels',
        to: '/commerce?tab=channels',
        icon: routeIconMap.Channels,
        permission: 'can_access_site',
        isActive: (pathname, tab) => pathname === '/commerce' && tab !== 'sources',
      },
    ],
  },
  {
    sectionKey: 'navigation:sidebar.operations',
    items: [
      { labelKey: 'navigation:sidebar.activity', to: '/activity', icon: routeIconMap.Activity, permission: 'can_view_logs' },
      { labelKey: 'navigation:sidebar.diagnostics', to: '/diagnostics', icon: routeIconMap.Diagnostics, permission: 'can_view_settings' },
    ],
  },
  {
    sectionKey: 'navigation:sidebar.settings',
    items: [
      { labelKey: 'navigation:sidebar.general', to: '/settings', icon: routeIconMap.Settings, permission: 'can_view_settings' },
      { labelKey: 'navigation:sidebar.rateLimits', to: '/rate-limits', icon: routeIconMap['Rate Limits'], permission: 'can_view_settings' },
    ],
  },
]

const HEALTH_FOOTER: Record<HealthStatus, { dotClass: string; labelKey: string }> = {
  ok: { dotClass: 'fh-status-dot-success', labelKey: 'common:status.operational' },
  loading: { dotClass: 'fh-status-dot-neutral', labelKey: 'common:status.checking' },
  error: { dotClass: 'fh-status-dot-error', labelKey: 'common:status.offline' },
}

export default function Sidebar({ open, collapsed, onClose, user, health }: Props) {
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const tab = searchParams.get('tab')

  function hasPerm(perm: string): boolean {
    return effectiveHasPerm(user, perm)
  }

  const itemCls = (active: boolean) =>
    [
      'fh-menu-item group',
      collapsed ? 'md:justify-center md:px-0' : '',
      active ? 'fh-menu-item-active' : '',
    ].join(' ')

  const footer = HEALTH_FOOTER[health]

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 bg-black/45 backdrop-blur-[1px] z-20 md:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={[
          'flex h-screen h-[100dvh] min-h-0 flex-shrink-0 flex-col border-e border-border',
          'bg-[color:var(--fh-nav-bg)]',
          'fixed md:sticky top-0 inset-y-0 start-0 z-30',
          'transition-all duration-300 ease-in-out',
          open ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full md:!translate-x-0',
          collapsed ? 'w-[290px] max-w-[86vw] md:w-[88px]' : 'w-[290px] max-w-[86vw] md:w-[290px]',
        ].join(' ')}
      >
        <div
          className={[
            'flex h-[72px] flex-shrink-0 items-center gap-[6px]',
            collapsed ? 'px-[23px] md:justify-center md:px-3' : 'px-[23px]',
          ].join(' ')}
        >
          <IconButton
            onClick={onClose}
            className="md:hidden border-transparent shadow-none bg-transparent"
            label={translate('navigation:sidebar.closeNavigation')}
          >
            <Icon name="close" size="lg" />
          </IconButton>

          <img
            src="/static/logos/FlowHub%20favicon.png?v=4"
            alt=""
            aria-hidden="true"
            className="h-[34px] w-[34px] flex-shrink-0 select-none object-contain"
          />

          <span
            className={[
              collapsed ? 'md:hidden' : '',
              'truncate text-[22px] font-semibold leading-8 text-[color:var(--fh-nav-text)]',
            ].join(' ')}
          >
            {translate('navigation:sidebar.flowhub')}
          </span>
        </div>

        <nav className="no-scrollbar min-h-0 flex-1 overflow-y-auto px-[23px] pb-4">
          <div className="flex flex-col gap-[18px]">
            {NAV_GROUPS.map(group => {
              const visible = group.items.filter(item => hasPerm(item.permission))
              if (visible.length === 0) return null
              return (
                <div key={group.sectionKey ?? 'primary'} className="flex flex-col gap-[6px]">
                  {group.sectionKey && (
                    <p className={['fh-menu-section', collapsed ? 'md:hidden' : ''].join(' ')}>
                      {translate(group.sectionKey)}
                    </p>
                  )}
                  {visible.map(item => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      onClick={onClose}
                      className={({ isActive }) =>
                        itemCls(item.isActive ? item.isActive(location.pathname, tab) : isActive)
                      }
                    >
                      <Icon name={item.icon} className="fh-menu-item-icon" />
                      <span className={collapsed ? 'md:hidden' : ''}>{translate(item.labelKey)}</span>
                    </NavLink>
                  ))}
                </div>
              )
            })}
          </div>
        </nav>

        <div className="flex-shrink-0 px-[23px] py-4">
          <div
            className={[
              'flex items-center gap-2 px-3',
              collapsed ? 'md:justify-center md:px-0' : '',
            ].join(' ')}
          >
            <span className={['fh-status-dot h-2 w-2', footer.dotClass].join(' ')} />
            <span
              className={[
                collapsed ? 'md:hidden' : '',
                'text-xs leading-4 text-[color:var(--fh-nav-text-muted)]',
              ].join(' ')}
            >
              {translate(footer.labelKey)}
            </span>
          </div>
        </div>
      </aside>
    </>
  )
}
