import { NavLink, useNavigate } from 'react-router-dom'
import type { AuthUser } from '../auth'
import { useAuth } from '../auth'
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
      isActive ? 'fh-menu-item-active text-accent' : 'text-wp-muted',
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
          'flex flex-col bg-bg-card border-e border-border h-screen flex-shrink-0 shadow-sm',
          'fixed md:sticky top-0 inset-y-0 start-0 z-30',
          'transition-all duration-300 ease-in-out',
          open ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full md:!translate-x-0',
          collapsed ? 'w-[290px] max-w-[86vw] md:w-[88px]' : 'w-[290px] max-w-[86vw] md:w-[290px]',
        ].join(' ')}
      >
        <div
          className={[
            'flex items-center h-[72px] md:h-[64px] border-b border-border flex-shrink-0',
            collapsed ? 'gap-3 px-4 md:justify-center md:px-3' : 'px-4 gap-3.5',
          ].join(' ')}
        >
          <IconButton
            onClick={onClose}
            className="md:hidden border-transparent shadow-none bg-bg-base"
            label="Close navigation"
          >
            <svg viewBox="0 0 24 24" className="fh-icon-lg" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </IconButton>

          <div className="w-9 h-9 rounded-xl flex items-center justify-center overflow-hidden flex-shrink-0 bg-bg-base border border-border">
            <img
              src="/static/logos/FlowHub%20favicon.png"
              alt=""
              aria-hidden="true"
              className="w-full h-full object-contain flex-shrink-0 select-none"
            />
          </div>

          <div className={[collapsed ? 'md:hidden' : '', 'flex-1 min-w-0'].join(' ')}>
            <div className="font-semibold text-[16px] text-text-base leading-6">FlowHub</div>
            <div className="text-[12px] font-medium text-wp-muted leading-4">Control Center</div>
          </div>

          <IconButton
            onClick={onToggleCollapse}
            className="hidden md:inline-flex h-8 w-8 rounded-lg"
            label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            size="sm"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
              className={['w-4 h-4 transition-transform duration-200', collapsed ? 'rotate-180' : ''].join(' ')}
              aria-hidden="true"
            >
              <path d="m15 18-6-6 6-6" />
            </svg>
          </IconButton>
        </div>

        <nav className="flex-1 px-4 py-4 md:px-4 md:py-5 overflow-y-auto no-scrollbar">
          <p className={[collapsed ? 'md:hidden' : '', 'px-3 mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-wp-muted select-none'].join(' ')}>
            Main
          </p>

          <div className="flex flex-col gap-1.5">
            {hasPerm('can_access_site') && (
              <NavLink to="/home" className={linkCls} onClick={onClose}>
                <svg viewBox="0 0 24 24" className="fh-menu-item-icon h-[21px] w-[21px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <rect x="3.75" y="3.75" width="6.5" height="6.5" rx="1.25" />
                  <rect x="13.75" y="3.75" width="6.5" height="6.5" rx="1.25" />
                  <rect x="3.75" y="13.75" width="6.5" height="6.5" rx="1.25" />
                  <rect x="13.75" y="13.75" width="6.5" height="6.5" rx="1.25" />
                </svg>
                <span className={collapsed ? 'md:hidden' : ''}>Dashboard</span>
              </NavLink>
            )}

            {hasPerm('can_fetch') && (
              <NavLink to="/products" className={linkCls} onClick={onClose}>
                <svg viewBox="0 0 24 24" className="fh-menu-item-icon h-[21px] w-[21px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <rect x="3" y="4" width="18" height="12.5" rx="2.5" />
                  <path d="M8 20h8" />
                  <path d="M12 16.5V20" />
                </svg>
                <span className={collapsed ? 'md:hidden' : ''}>Products</span>
              </NavLink>
            )}

            {hasPerm('can_access_site') && (
              <NavLink to="/commerce" className={linkCls} onClick={onClose}>
                <svg viewBox="0 0 24 24" className="fh-menu-item-icon h-[21px] w-[21px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M4 8h16" />
                  <path d="M6 8.5 7 19h10l1-10.5" />
                  <path d="M9 8a3 3 0 0 1 6 0" />
                </svg>
                <span className={collapsed ? 'md:hidden' : ''}>Commerce Hub</span>
              </NavLink>
            )}

            {hasPerm('can_fetch') && (
              <NavLink to="/workspace" className={linkCls} onClick={onClose}>
                <svg viewBox="0 0 24 24" className="fh-menu-item-icon h-[21px] w-[21px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21 4v5h-5" />
                  <path d="M3 20v-5h5" />
                  <path d="M4.75 9.25a8.5 8.5 0 0 1 13.98-3.17L21 8.5" />
                  <path d="M3 15.5l2.27 2.42A8.5 8.5 0 0 0 19.25 15" />
                </svg>
                <span className={collapsed ? 'md:hidden' : ''}>Workspace</span>
              </NavLink>
            )}

            {hasPerm('can_view_logs') && (
              <NavLink to="/activity" className={linkCls} onClick={onClose}>
                <svg viewBox="0 0 24 24" className="fh-menu-item-icon h-[21px] w-[21px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" />
                  <path d="M14 3v6h6" />
                  <path d="M8 13h8" />
                  <path d="M8 17h6" />
                </svg>
                <span className={collapsed ? 'md:hidden' : ''}>Activity</span>
              </NavLink>
            )}

            {hasPerm('can_view_settings') && (
              <NavLink to="/diagnostics" className={linkCls} onClick={onClose}>
                <svg viewBox="0 0 24 24" className="fh-menu-item-icon h-[21px] w-[21px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M3 12h4l2.5 7L14 5l2.5 7H21" />
                </svg>
                <span className={collapsed ? 'md:hidden' : ''}>Diagnostics</span>
              </NavLink>
            )}

            {hasPerm('can_view_settings') && (
              <NavLink to="/settings" className={linkCls} onClick={onClose}>
                <svg viewBox="0 0 24 24" className="fh-menu-item-icon h-[21px] w-[21px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
                <span className={collapsed ? 'md:hidden' : ''}>Settings</span>
              </NavLink>
            )}
          </div>
        </nav>

        <div className="border-t border-border px-4 py-3 flex-shrink-0">
          <div
            className={[
              'flex items-center gap-2.5',
              collapsed ? 'md:flex-col md:justify-center md:gap-2' : '',
            ].join(' ')}
          >
            <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-[12px] font-semibold flex-shrink-0 select-none shadow-sm">
              {user ? initials(user.username) : '?'}
            </div>
            {user && (
              <div className={[collapsed ? 'md:hidden' : '', 'flex-1 min-w-0'].join(' ')}>
                <div className="text-[13px] font-medium leading-5 text-text-base truncate">{user.username}</div>
                <div className="text-[11px] font-medium uppercase tracking-[0.06em] text-wp-muted">{user.role}</div>
              </div>
            )}
            <button
              onClick={handleLogout}
              title="Sign out"
              aria-label="Sign out"
              className={[
                'inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-bg-base text-wp-muted transition-colors hover:border-wp-red/30 hover:bg-wp-red/5 hover:text-wp-red',
                collapsed ? 'md:ms-0' : 'ms-auto',
              ].join(' ')}
            >
              <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}
