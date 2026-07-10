import { NavLink, useNavigate } from 'react-router-dom'
import type { AuthUser } from '../auth'
import { useAuth } from '../auth'
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
      'fh-menu-item group mb-1.5 px-3.5 py-3 text-[15px] font-semibold',
      'md:px-3 md:py-2.5 md:text-[14px]',
      collapsed ? 'md:justify-center md:px-0' : '',
      isActive
        ? 'fh-menu-item-active text-accent'
        : 'text-wp-muted',
    ].join(' ')

  function handleLogout() {
    clearAuth()
    navigate('/login', { replace: true })
  }

  return (
    <>
      {/* Mobile backdrop */}
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
          collapsed ? 'w-[290px] max-w-[86vw] md:w-[90px]' : 'w-[290px] max-w-[86vw] md:w-[290px]',
        ].join(' ')}
      >
        {/* Brand */}
        <div
          className={[
            'flex items-center h-[84px] md:h-[68px] border-b border-border flex-shrink-0',
            collapsed ? 'gap-3 px-4 md:flex-col md:justify-center md:gap-1 md:py-3 md:px-2' : 'px-4 gap-3',
          ].join(' ')}
        >
          <button
            onClick={onClose}
            className="md:hidden flex items-center justify-center w-11 h-11 rounded-xl bg-bg-base text-wp-muted hover:text-accent transition-colors flex-shrink-0"
            aria-label="Close navigation"
          >
            <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>

          <div className="w-10 h-10 rounded-xl flex items-center justify-center overflow-hidden flex-shrink-0">
            <img
              src="/static/logos/FlowHub%20favicon.png"
              alt=""
              aria-hidden="true"
              className="w-full h-full object-contain flex-shrink-0 select-none"
            />
          </div>

          <div className={[collapsed ? 'md:hidden' : '', 'flex-1 min-w-0'].join(' ')}>
            <div className="font-semibold text-[18px] md:text-[16px] text-text-base leading-tight">FlowHub</div>
            <div className="mt-0.5 text-[12px] md:text-[12px] font-medium text-wp-muted">Control Center</div>
          </div>

          {/* Collapse button - desktop only */}
          <button
            onClick={onToggleCollapse}
            className="hidden md:flex items-center justify-center w-[26px] h-[26px] rounded-lg border border-border bg-bg-card text-wp-muted shadow-sm hover:text-accent hover:border-accent transition-colors flex-shrink-0"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              className={[
                'w-3 h-3 transition-transform duration-200',
                collapsed ? 'rotate-180' : '',
              ].join(' ')}
            >
              <path d="m15 18-6-6 6-6" />
            </svg>
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-4 py-5 md:px-4 md:py-6 overflow-y-auto no-scrollbar">
          <p className={[collapsed ? 'md:hidden' : '', 'px-2 mb-4 text-[12px] md:text-[11px] font-semibold uppercase tracking-[0.08em] text-wp-muted select-none'].join(' ')}>
            Main
          </p>

          {hasPerm('can_access_site') && (
            <NavLink to="/home" className={linkCls} onClick={onClose}>
              <svg viewBox="0 0 24 24" className="fh-menu-item-icon w-[18px] h-[18px] flex-shrink-0" fill="currentColor">
                <rect x="3" y="3" width="7" height="7" rx="1" />
                <rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" />
                <rect x="14" y="14" width="7" height="7" rx="1" />
              </svg>
              <span className={collapsed ? 'md:hidden' : ''}>Dashboard</span>
            </NavLink>
          )}

          {hasPerm('can_fetch') && (
            <NavLink to="/products" className={linkCls} onClick={onClose}>
              <svg viewBox="0 0 24 24" className="fh-menu-item-icon w-[18px] h-[18px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="3" width="20" height="14" rx="2" />
                <path d="M8 21h8M12 17v4" />
              </svg>
              <span className={collapsed ? 'md:hidden' : ''}>Products</span>
            </NavLink>
          )}

          {hasPerm('can_access_site') && (
            <NavLink to="/commerce" className={linkCls} onClick={onClose}>
              <svg viewBox="0 0 24 24" className="fh-menu-item-icon w-[18px] h-[18px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 7h18" />
                <path d="M5 7l1 12h12l1-12" />
                <path d="M9 7a3 3 0 0 1 6 0" />
              </svg>
              <span className={collapsed ? 'md:hidden' : ''}>Commerce Hub</span>
            </NavLink>
          )}

          {hasPerm('can_fetch') && (
            <NavLink to="/workspace" className={linkCls} onClick={onClose}>
              <svg viewBox="0 0 24 24" className="fh-menu-item-icon w-[18px] h-[18px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 4v6h-6" />
                <path d="M1 20v-6h6" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
              <span className={collapsed ? 'md:hidden' : ''}>Workspace</span>
            </NavLink>
          )}

          {hasPerm('can_view_logs') && (
            <NavLink to="/activity" className={linkCls} onClick={onClose}>
              <svg viewBox="0 0 24 24" className="fh-menu-item-icon w-[18px] h-[18px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
              </svg>
              <span className={collapsed ? 'md:hidden' : ''}>Activity</span>
            </NavLink>
          )}

          {hasPerm('can_view_settings') && (
            <NavLink to="/diagnostics" className={linkCls} onClick={onClose}>
              <svg viewBox="0 0 24 24" className="fh-menu-item-icon w-[18px] h-[18px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
              <span className={collapsed ? 'md:hidden' : ''}>Diagnostics</span>
            </NavLink>
          )}

          {hasPerm('can_view_settings') && (
            <NavLink to="/settings" className={linkCls} onClick={onClose}>
              <svg viewBox="0 0 24 24" className="fh-menu-item-icon w-[18px] h-[18px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
              <span className={collapsed ? 'md:hidden' : ''}>Settings</span>
            </NavLink>
          )}
        </nav>

        {/* Footer */}
        <div className="border-t border-border p-4 md:p-4 flex-shrink-0 flex flex-col gap-3 md:gap-3">
          <div
            className={[
              'flex items-center gap-2.5',
              collapsed ? 'md:justify-center' : '',
            ].join(' ')}
          >
            <div className="w-10 h-10 md:w-10 md:h-10 rounded-full bg-accent flex items-center justify-center text-white text-[13px] md:text-[13px] font-semibold flex-shrink-0 select-none shadow-sm">
              {user ? initials(user.username) : '?'}
            </div>
            {user && (
              <div className={[collapsed ? 'md:hidden' : '', 'flex-1 min-w-0'].join(' ')}>
                <div className="text-[14px] md:text-[14px] font-medium text-text-base truncate">{user.username}</div>
                <div className="text-[12px] md:text-[12px] font-medium text-wp-muted">{user.role}</div>
              </div>
            )}
          </div>

          <button
            onClick={handleLogout}
            title="Sign out"
            className={[
              'flex items-center gap-2 rounded-lg px-3 py-2.5 text-[13px] font-medium border shadow-sm',
              'border-wp-red/20 text-wp-red bg-bg-card hover:bg-wp-red/5 transition-colors',
              collapsed ? 'md:justify-center w-full' : 'w-full',
            ].join(' ')}
          >
            <svg viewBox="0 0 24 24" className="w-[16px] h-[16px] flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            <span className={collapsed ? 'md:hidden' : ''}>Sign out</span>
          </button>
        </div>
      </aside>
    </>
  )
}
