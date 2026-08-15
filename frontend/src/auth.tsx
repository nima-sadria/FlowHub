import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { effectiveHasPerm } from './utils/permissions'
import { translate } from './i18n'
import {
  AUTH_SESSION_EXPIRED_EVENT,
  authFetch as sharedAuthFetch,
  authHeaders,
  clearStoredAuth,
  refreshAuthSession,
} from './api/authFetch'

type PermissionMap = Record<string, boolean>

export interface MaintenanceState {
  enabled: boolean
  message: string
}

export interface AuthUser {
  id: number
  username: string
  email: string | null
  role: string
  is_admin: boolean
  is_super_admin: boolean
  permissions: PermissionMap
  maintenance?: MaintenanceState
}

type AuthStatus = 'loading' | 'authenticated' | 'login_required' | 'permission_denied'

export interface AuthContextValue {
  user: AuthUser | null
  status: AuthStatus
  refreshUser: () => Promise<void>
  clearAuth: () => void
  logout: () => Promise<void>
  authFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [status, setStatus] = useState<AuthStatus>('loading')

  const clearAuth = useCallback(() => {
    clearStoredAuth()
    setUser(null)
    setStatus('login_required')
  }, [])

  // User-initiated sign out: revoke the refresh token server-side, then clear
  // local state. Revocation is best-effort - local sign-out proceeds even if
  // the server is unreachable.
  const logout = useCallback(async () => {
    const refreshToken = localStorage.getItem('wp_refresh_token') ?? ''
    if (refreshToken) {
      const headers = authHeaders()
      headers.set('Content-Type', 'application/json')
      try {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers,
          body: JSON.stringify({ refresh_token: refreshToken }),
        })
      } catch { /* best-effort revocation */ }
    }
    clearAuth()
  }, [clearAuth])

  const refreshUser = useCallback(async () => {
    const token = localStorage.getItem('wp_token') ?? ''
    const storedRefreshToken = localStorage.getItem('wp_refresh_token') ?? ''
    setStatus('loading')

    if (!token && !storedRefreshToken) {
      setUser(null)
      setStatus('login_required')
      return
    }

    if (!token) {
      const refreshed = await refreshAuthSession()
      if (!refreshed) {
        clearStoredAuth()
        setUser(null)
        setStatus('login_required')
        return
      }
    }

    try {
      const r = await sharedAuthFetch('/api/auth/me')
      if (r.status === 401) {
        setUser(null)
        setStatus('login_required')
        return
      }
      if (r.status === 403) {
        setUser(null)
        setStatus('permission_denied')
        return
      }
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const nextUser = (await r.json()) as AuthUser
      setUser(nextUser)
      setStatus('authenticated')
      localStorage.setItem('wp_user', JSON.stringify(nextUser))
    } catch {
      setUser(null)
      setStatus('login_required')
    }
  }, [])

  const authFetch = useCallback(async (input: RequestInfo | URL, init?: RequestInit) => {
    const r = await sharedAuthFetch(input, init)
    if (r.status === 503) {
      // Detect a maintenance-mode block and immediately activate the overlay,
      // even for sessions that were already authenticated before maintenance was enabled.
      try {
        const body = await r.clone().json() as Record<string, unknown>
        if (body?.maintenance === true) {
          setUser(prev =>
            prev ? { ...prev, maintenance: { enabled: true, message: typeof body.detail === 'string' ? body.detail : '' } } : prev
          )
        }
      } catch { /* not a JSON maintenance response - ignore */ }
    }
    return r
  }, [])

  useEffect(() => {
    void refreshUser()
  }, [refreshUser])

  useEffect(() => {
    const onSessionExpired = () => {
      setUser(null)
      setStatus('login_required')
    }
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, onSessionExpired)
    return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, onSessionExpired)
  }, [])

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === 'wp_token' || e.key === 'wp_refresh_token' || e.key === 'wp_user') {
        void refreshUser()
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [refreshUser])

  const value = useMemo(() => ({
    user,
    status,
    refreshUser,
    clearAuth,
    logout,
    authFetch,
  }), [user, status, refreshUser, clearAuth, logout, authFetch])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

export function AccessState({
  status,
  message,
}: {
  status: Exclude<AuthStatus, 'authenticated'>
  message?: string
}) {
  const title = status === 'permission_denied' ? translate('authentication:access.accessDenied') : status === 'loading' ? translate('authentication:access.verifyingAccess') : translate('authentication:access.loginRequired')
  const body =
    message ??
    (status === 'permission_denied'
      ? translate('authentication:access.permissionDeniedDescription')
      : status === 'loading'
        ? translate('authentication:access.verifyingSession')
        : translate('authentication:access.signInToContinue'))

  return (
    <div className="p-7">
      <div className="fh-card max-w-xl p-6">
        <h1 className="fh-page-title">{title}</h1>
        <p className="text-[13px] text-wp-muted mt-2">{body}</p>
      </div>
    </div>
  )
}

export function RequirePermission({
  permission,
  adminOnly = false,
  children,
}: {
  permission?: string
  adminOnly?: boolean
  children: ReactNode
}) {
  const { user, status } = useAuth()
  if (status !== 'authenticated') return <AccessState status={status} />
  if (!user) return <AccessState status="login_required" />
  if (adminOnly && !user.is_admin && !user.is_super_admin) return <AccessState status="permission_denied" />
  if (permission && !effectiveHasPerm(user, permission)) {
    return <AccessState status="permission_denied" />
  }
  return <>{children}</>
}
