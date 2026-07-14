import { translate } from '../i18n'
import { NavLink, useNavigate } from 'react-router-dom'
import type { AuthUser } from '../auth'
import { useAuth } from '../auth'
import Icon, { routeIconMap } from './Icon'
import IconButton from './IconButton'
import { effectiveHasPerm } from '../utils/permissions'

interface Props {
  open: boolean
  collapsed: boolean
  onClose: () => void
  onToggleCollapse: () => void
  user: AuthUser | null
}

function initials(name: string) {
  return name.slice(0, 2).toUpperCase()
}

export default function Sidebar({ open, collapsed, onClose, onToggleCollapse, user }: Props) {
  const { clearAuth } = useAuth()
  const navigate = useNavigate()

  function hasPerm(perm: string): boolean {
    return effectiveHasPerm(user, perm)
  }

  const linkCls = ({ isActive }: { isActive: boolean }) =>
    [
      'fh-menu-item group',
      collapsed ? 'md:justify-center md:px-0' : '',
      isActive ? 'fh-menu-item-active' : '',
    ].join(' ')

  function handleLogout() {
    clearAuth()
    navigate('/login', { replace: true })
  }

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
          "flex h-screen h-[100dvh] min-h-0 flex-shrink-0 flex-col bg-bg-card border-e border-border shadow-sm",
          "fixed md:sticky top-0 inset-y-0 start-0 z-30",
          "transition-all duration-300 ease-in-out",
          open ? "translate-x-0" : "-translate-x-full rtl:translate-x-full md:!translate-x-0",
          collapsed ? "w-[290px] max-w-[86vw] md:w-[88px]" : "w-[290px] max-w-[86vw] md:w-[290px]",
        ].join(' ')}
      >
        <div
          className={[
            "flex items-center h-20 border-b border-border flex-shrink-0",
            collapsed ? "gap-3 px-5 md:justify-center md:px-3" : "px-5 gap-3",
          ].join(' ')}
        >
          <IconButton
            onClick={onClose}
            className="md:hidden border-transparent shadow-none bg-bg-base"
            label={translate('navigation:sidebar.closeNavigation')}
          >
            <Icon name="close" size="lg" />
          </IconButton>

          <div className="w-8 h-8 rounded-lg flex items-center justify-center overflow-hidden flex-shrink-0 bg-bg-base border border-border">
            <img
              src="/static/logos/FlowHub%20favicon.png"
              alt=""
              aria-hidden="true"
              className="w-full h-full object-contain flex-shrink-0 select-none"
            />
          </div>

          <div className={[collapsed ? "md:hidden" : '', "flex-1 min-w-0"].join(' ')}>
            <div className="font-semibold text-xl text-text-base leading-7">{translate('navigation:sidebar.flowhub')}</div>
            <div className="text-xs font-medium leading-4 text-[color:var(--fh-gray-500)]">{translate('navigation:sidebar.controlCenter')}</div>
          </div>

          <IconButton
            onClick={onToggleCollapse}
            className="hidden md:inline-flex h-8 w-8 rounded-lg"
            label={collapsed ? translate('navigation:sidebar.expandSidebar') : translate('navigation:sidebar.collapseSidebar')}
            size="sm"
          >
            <Icon name={collapsed ? "next" : "previous"} mirrorRtl />
          </IconButton>
        </div>

        <nav className="min-h-0 flex-1 overflow-y-auto px-5 py-5 no-scrollbar">
          <p className={[collapsed ? "md:hidden" : '', "mb-4 text-xs font-semibold uppercase tracking-[0.08em] text-[color:var(--fh-gray-400)] leading-5 select-none"].join(' ')}>
            {translate('navigation:sidebar.main')}
          </p>

          <div className="flex flex-col gap-2">
            {hasPerm("can_access_site") && (
              <NavLink to="/home" className={linkCls} onClick={onClose}>
                <Icon name={routeIconMap.Dashboard} className="fh-menu-item-icon h-6 w-6" />
                <span className={collapsed ? "md:hidden" : ''}>{translate('navigation:sidebar.dashboard')}</span>
              </NavLink>
            )}

            {hasPerm("can_fetch") && (
              <NavLink to="/products" className={linkCls} onClick={onClose}>
                <Icon name={routeIconMap.Products} className="fh-menu-item-icon h-6 w-6" />
                <span className={collapsed ? "md:hidden" : ''}>{translate('navigation:sidebar.products')}</span>
              </NavLink>
            )}

            {hasPerm("can_fetch") && (
              <NavLink to="/orders" className={linkCls} onClick={onClose}>
                <Icon name={routeIconMap.Orders} className="fh-menu-item-icon h-6 w-6" />
                <span className={collapsed ? "md:hidden" : ''}>{translate('navigation:sidebar.orders')}</span>
              </NavLink>
            )}

            {hasPerm("can_access_site") && (
              <NavLink to="/sources" className={linkCls} onClick={onClose}>
                <Icon name="file" className="fh-menu-item-icon h-6 w-6" />
                <span className={collapsed ? "md:hidden" : ''}>{translate('navigation:sidebar.sources')}</span>
              </NavLink>
            )}

            {hasPerm("can_access_site") && (
              <NavLink to="/commerce" className={linkCls} onClick={onClose}>
                <Icon name={routeIconMap["Commerce Hub"]} className="fh-menu-item-icon h-6 w-6" />
                <span className={collapsed ? "md:hidden" : ''}>{translate('navigation:sidebar.commerceHub')}</span>
              </NavLink>
            )}

            {hasPerm("can_fetch") && (
              <NavLink to="/workspace" className={linkCls} onClick={onClose}>
                <Icon name={routeIconMap.Workspace} className="fh-menu-item-icon h-6 w-6" />
                <span className={collapsed ? "md:hidden" : ''}>{translate('navigation:sidebar.workspace')}</span>
              </NavLink>
            )}

            {hasPerm("can_fetch") && (
              <NavLink to="/data-quality" className={linkCls} onClick={onClose}>
                <Icon name="alert" className="fh-menu-item-icon h-6 w-6" />
                <span className={collapsed ? "md:hidden" : ''}>{translate('navigation:sidebar.dataQuality')}</span>
              </NavLink>
            )}

            {hasPerm("can_view_logs") && (
              <NavLink to="/activity" className={linkCls} onClick={onClose}>
                <Icon name={routeIconMap.Activity} className="fh-menu-item-icon h-6 w-6" />
                <span className={collapsed ? "md:hidden" : ''}>{translate('navigation:sidebar.activity')}</span>
              </NavLink>
            )}

            {hasPerm("can_view_settings") && (
              <NavLink to="/diagnostics" className={linkCls} onClick={onClose}>
                <Icon name={routeIconMap.Diagnostics} className="fh-menu-item-icon h-6 w-6" />
                <span className={collapsed ? "md:hidden" : ''}>{translate('navigation:sidebar.diagnostics')}</span>
              </NavLink>
            )}

            {hasPerm("can_view_settings") && (
              <NavLink to="/settings" className={linkCls} onClick={onClose}>
                <Icon name={routeIconMap.Settings} className="fh-menu-item-icon h-6 w-6" />
                <span className={collapsed ? "md:hidden" : ''}>{translate('navigation:sidebar.settings')}</span>
              </NavLink>
            )}
          </div>
        </nav>

        <div className="border-t border-border px-5 py-4 flex-shrink-0">
          <div
            className={[
              "flex items-center gap-2.5",
              collapsed ? "md:flex-col md:justify-center md:gap-2" : '',
            ].join(' ')}
          >
            <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-[12px] font-semibold flex-shrink-0 select-none shadow-sm">
              {user ? initials(user.username) : '?'}
            </div>
            {user && (
              <div className={[collapsed ? "md:hidden" : '', "flex-1 min-w-0"].join(' ')}>
                <div className="text-[13px] font-medium leading-5 text-text-base truncate">{user.username}</div>
                <div className="text-xs font-medium uppercase tracking-[0.06em] text-[color:var(--fh-gray-500)]">{user.role}</div>
              </div>
            )}
            <button
              onClick={handleLogout}
              title={translate('navigation:sidebar.signOut')}
              aria-label={translate('navigation:sidebar.signOut')}
              className={[
                "inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-bg-base text-[color:var(--fh-gray-500)] transition-colors hover:border-wp-red/30 hover:bg-wp-red/5 hover:text-wp-red",
                collapsed ? "md:ms-0" : "ms-auto",
              ].join(' ')}
            >
              <Icon name="next" className="h-[18px] w-[18px]" mirrorRtl />
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}
