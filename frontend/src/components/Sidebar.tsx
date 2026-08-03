import { useEffect, useState } from 'react'
import { translate } from '../i18n'
import { NavLink, useLocation, useSearchParams } from 'react-router'
import type { AuthUser } from '../auth'
import Icon, { routeIconMap } from './Icon'
import type { IconName } from './Icon'
import IconButton from './IconButton'
import { effectiveHasPerm } from '../utils/permissions'
import { WORKSPACE_PERMISSION } from '../utils/workspacePermissions'

type HealthStatus = 'ok' | 'error' | 'loading'

interface Props {
  open: boolean
  collapsed: boolean
  onClose: () => void
  onExpand?: () => void
  user: AuthUser | null
  health: HealthStatus
}

interface NavItem {
  id?: string
  labelKey: string
  to?: string
  icon: IconName
  permission?: string
  adminOnly?: boolean
  children?: NavItem[]
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
    sectionKey: 'navigation:sidebar.commerceHub',
    items: [
      {
        labelKey: 'navigation:sidebar.sources',
        to: '/sources',
        icon: routeIconMap.Sources,
        permission: WORKSPACE_PERMISSION.read,
        isActive: pathname => pathname === '/sources' || pathname.startsWith('/sources/'),
      },
      {
        labelKey: 'navigation:sidebar.channels',
        to: '/channels',
        icon: routeIconMap.Channels,
        permission: 'can_access_site',
        isActive: pathname => pathname === '/channels' || pathname.startsWith('/channels/'),
      },
    ],
  },
  {
    sectionKey: 'navigation:sidebar.operations',
    items: [
      { labelKey: 'navigation:sidebar.activity', to: '/activity', icon: routeIconMap.Activity, permission: WORKSPACE_PERMISSION.readAudit },
      { labelKey: 'navigation:sidebar.dataQuality', to: '/data-quality', icon: 'dataQuality', permission: WORKSPACE_PERMISSION.read },
      { labelKey: 'navigation:sidebar.diagnostics', to: '/diagnostics', icon: routeIconMap.Diagnostics, permission: 'can_view_settings' },
    ],
  },
  {
    sectionKey: null,
    items: [
      {
        id: 'settings',
        labelKey: 'navigation:sidebar.settings',
        icon: routeIconMap.Settings,
        isActive: pathname => pathname === '/settings' || pathname.startsWith('/settings/') || pathname === '/rate-limits',
        children: [
          {
            labelKey: 'navigation:sidebar.general',
            to: '/settings',
            icon: routeIconMap.Settings,
            permission: 'can_view_settings',
            isActive: pathname => pathname === '/settings',
          },
          {
            labelKey: 'settings:exchangeRates.title',
            to: '/settings/exchange-rates',
            icon: 'rateLimits',
            permission: 'can_access_site',
          },
          {
            labelKey: 'navigation:sidebar.users',
            to: '/settings/users',
            icon: routeIconMap.Users,
            permission: 'can_view_settings',
            adminOnly: true,
          },
          {
            labelKey: 'navigation:sidebar.rateLimits',
            to: '/settings/rate-limits',
            icon: 'sliders',
            permission: 'can_view_settings',
          },
          {
            labelKey: 'settings:settings.advanced',
            to: '/settings/advanced',
            icon: 'diagnostics',
            permission: 'can_view_settings',
          },
        ],
      },
    ],
  },
]

const HEALTH_FOOTER: Record<HealthStatus, { dotClass: string; labelKey: string }> = {
  ok: { dotClass: 'fh-status-dot-success', labelKey: 'navigation:sidebar.allSystemsOperational' },
  loading: { dotClass: 'fh-status-dot-neutral', labelKey: 'common:status.checking' },
  error: { dotClass: 'fh-status-dot-error', labelKey: 'common:status.offline' },
}

export default function Sidebar({ open, collapsed, onClose, onExpand, user, health }: Props) {
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const tab = searchParams.get('tab')
  const settingsRouteActive = location.pathname === '/settings'
    || location.pathname.startsWith('/settings/')
    || location.pathname === '/rate-limits'
  const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>({
    settings: settingsRouteActive,
  })

  useEffect(() => {
    if (settingsRouteActive) {
      setExpandedItems(current => ({ ...current, settings: true }))
    }
  }, [settingsRouteActive])

  function isVisible(item: NavItem): boolean {
    return (!item.permission || effectiveHasPerm(user, item.permission))
      && (!item.adminOnly || Boolean(user?.is_admin || user?.is_super_admin))
  }

  const itemCls = (active: boolean) =>
    [
      'fh-menu-item group',
      collapsed ? 'xl:justify-center xl:px-0' : '',
      active ? 'fh-menu-item-active' : '',
    ].join(' ')

  const footer = HEALTH_FOOTER[health]

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-[9998] bg-black/45 backdrop-blur-[1px] xl:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={[
          'flex h-screen h-[100dvh] min-h-0 flex-shrink-0 flex-col border-e border-border',
          'bg-[color:var(--fh-nav-bg)]',
          'fixed top-0 inset-y-0 start-0 z-[9999] xl:sticky',
          'transition-all duration-300 ease-in-out',
          open ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full xl:!translate-x-0',
          collapsed ? 'w-[290px] max-w-[86vw] xl:w-[90px]' : 'w-[290px] max-w-[86vw] xl:w-[290px]',
        ].join(' ')}
      >
        <div
          className={[
            'flex h-[72px] flex-shrink-0 items-center gap-[6px]',
            collapsed ? 'px-[23px] xl:justify-center xl:px-3' : 'px-[23px]',
          ].join(' ')}
        >
          <div
            className="flex min-w-0 items-center gap-[6px]"
            dir="ltr"
            aria-label={translate('navigation:sidebar.flowhub')}
          >
            <img
              src="/static/logos/FlowHub%20Transparent%20WebP%20%20Logo.webp?v=1"
              alt=""
              aria-hidden="true"
              className="h-[34px] w-[34px] flex-shrink-0 select-none object-contain"
            />

            <span
              className={[
                collapsed ? 'xl:hidden' : '',
                'truncate text-[22px] font-semibold leading-8 text-[color:var(--fh-nav-text)]',
              ].join(' ')}
            >
              {translate('navigation:sidebar.flowhub')}
            </span>
          </div>

          <IconButton
            onClick={onClose}
            className="ms-auto border-transparent bg-transparent shadow-none xl:hidden"
            label={translate('navigation:sidebar.closeNavigation')}
          >
            <Icon name="close" size="lg" />
          </IconButton>
        </div>

        <nav className="no-scrollbar min-h-0 flex-1 overflow-y-auto px-[23px] pb-4">
          <div className="flex flex-col gap-[18px]">
            {NAV_GROUPS.map(group => {
              const visible = group.items.filter(item => {
                if (!isVisible(item)) return false
                return !item.children || item.children.some(isVisible)
              })
              if (visible.length === 0) return null
              return (
                <div
                  key={group.sectionKey ?? group.items[0]?.id ?? group.items[0]?.to ?? group.items[0]?.labelKey}
                  className="flex flex-col gap-[6px]"
                >
                  {group.sectionKey && (
                    <p className={['fh-menu-section', collapsed ? 'xl:hidden' : ''].join(' ')}>
                      {translate(group.sectionKey)}
                    </p>
                  )}
                  {visible.map(item => {
                    if (item.children) {
                      const itemId = item.id ?? item.labelKey
                      const submenuId = `sidebar-${itemId}-submenu`
                      const expanded = Boolean(expandedItems[itemId])
                      const active = item.isActive?.(location.pathname, tab) ?? false
                      const visibleChildren = item.children.filter(isVisible)
                      return (
                        <div key={itemId}>
                          <button
                            type="button"
                            className={[itemCls(false), active ? 'fh-menu-parent-active' : ''].join(' ')}
                            aria-expanded={expanded}
                            aria-controls={submenuId}
                            data-active={active ? 'true' : undefined}
                            onClick={() => {
                              if (collapsed) onExpand?.()
                              setExpandedItems(current => ({ ...current, [itemId]: !current[itemId] }))
                            }}
                          >
                            <Icon name={item.icon} className="fh-menu-item-icon" />
                            <span className={collapsed ? 'xl:hidden' : ''}>{translate(item.labelKey)}</span>
                            <Icon
                              name="chevronDown"
                              size="md"
                              className={[
                                'ms-auto transition-transform duration-150',
                                collapsed ? 'xl:hidden' : '',
                                expanded ? 'rotate-180' : '',
                              ].join(' ')}
                            />
                          </button>

                          {expanded && (
                            <div id={submenuId} className="fh-menu-submenu mt-1 flex flex-col gap-1">
                              {visibleChildren.map(child => (
                                <NavLink
                                  key={child.to}
                                  to={child.to!}
                                  end
                                  onClick={onClose}
                                  className={({ isActive }) => [
                                    itemCls(child.isActive ? child.isActive(location.pathname, tab) : isActive),
                                    'fh-menu-submenu-item',
                                  ].join(' ')}
                                >
                                  <Icon name={child.icon} className="fh-menu-item-icon" />
                                  <span className={collapsed ? 'xl:hidden' : ''}>{translate(child.labelKey)}</span>
                                </NavLink>
                              ))}
                            </div>
                          )}
                        </div>
                      )
                    }

                    return (
                      <NavLink
                        key={item.to}
                        to={item.to!}
                        onClick={onClose}
                        className={({ isActive }) =>
                          itemCls(item.isActive ? item.isActive(location.pathname, tab) : isActive)
                        }
                      >
                        <Icon name={item.icon} className="fh-menu-item-icon" />
                        <span className={collapsed ? 'xl:hidden' : ''}>{translate(item.labelKey)}</span>
                      </NavLink>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </nav>

        <div className="flex-shrink-0 px-[23px] py-4">
          <div
            className={[
              'flex items-center gap-2 px-3',
              collapsed ? 'xl:justify-center xl:px-0' : '',
            ].join(' ')}
          >
            <span className={['fh-status-dot h-2 w-2', footer.dotClass].join(' ')} />
            <span
              className={[
                collapsed ? 'xl:hidden' : '',
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
