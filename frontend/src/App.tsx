import type { ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, RequirePermission, AccessState, useAuth } from './auth'
import { DirectionProvider } from './direction'
import { ThemeProvider } from './theme/ThemeProvider'
import { NotificationProvider } from './notifications/NotificationProvider'
import NotificationContainer from './notifications/NotificationContainer'
import { ServiceProvider } from './services/ServiceContext'
import { MockHealthService } from './services/health/MockHealthService'
import { MockProductService } from './services/products/MockProductService'
import { MockSourceService } from './services/sources/MockSourceService'
import { MockWorkspaceService } from './services/workspace/MockWorkspaceService'
import { MockSettingsService } from './services/settings/MockSettingsService'
import { MockActivityService } from './services/activity/MockActivityService'
import AppShell from './components/AppShell'
import BetaDashboard from './pages/BetaDashboard'
import Products from './pages/Products'
import Sources from './pages/Sources'
import SourceWizard from './pages/SourceWizard'
import Workspace from './pages/Workspace'
import Activity from './pages/Activity'
import Diagnostics from './pages/Diagnostics'
import Settings from './pages/Settings'
import Login from './pages/Login'
import NotFound from './pages/NotFound'

const mockServices = {
  health:    new MockHealthService(),
  products:  new MockProductService(),
  sources:   new MockSourceService(),
  workspace: new MockWorkspaceService(),
  settings:  new MockSettingsService(),
  activity:  new MockActivityService(),
}

function MaintenanceOverlay({ message }: { message?: string }) {
  const { clearAuth } = useAuth()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-base/95 backdrop-blur-sm">
      <div className="max-w-md w-full mx-4 bg-bg-card border border-border rounded-card shadow-card p-8 text-center">
        <div className="w-14 h-14 rounded-full bg-amber-100 flex items-center justify-center mx-auto mb-4">
          <svg viewBox="0 0 24 24" className="w-7 h-7 text-amber-600" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        </div>
        <h2 className="text-[18px] font-bold text-text-base mb-2">Maintenance Mode</h2>
        <p className="text-[13px] text-wp-muted mb-6">
          {message || 'WooPrice is temporarily in maintenance mode. Please try again later.'}
        </p>
        <button
          onClick={() => { clearAuth() }}
          className="px-5 py-2 rounded-lg bg-accent text-white text-[13px] font-medium hover:bg-accent/90 transition-colors"
        >
          Sign out
        </button>
      </div>
    </div>
  )
}

function AuthGuard({ children }: { children: ReactNode }) {
  const { status, user } = useAuth()
  if (status === 'loading') {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <span className="text-[13px] text-wp-muted">Loading…</span>
      </div>
    )
  }
  if (status === 'login_required') return <Navigate to="/login" replace />
  if (status === 'permission_denied') return <AccessState status="permission_denied" />
  if (user?.maintenance?.enabled && !user.is_super_admin) {
    return <MaintenanceOverlay message={user.maintenance.message} />
  }
  return <>{children}</>
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  if (status === 'loading') {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <span className="text-[13px] text-wp-muted">Loading…</span>
      </div>
    )
  }
  if (status === 'authenticated') return <Navigate to="/home" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <NotificationProvider>
          <NotificationContainer />
          <DirectionProvider>
            <AuthProvider>
              <ServiceProvider services={mockServices}>
                <Routes>
                  <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
                  <Route path="/" element={<Navigate to="/home" replace />} />
                  <Route element={<AuthGuard><AppShell /></AuthGuard>}>
                    <Route path="/home" element={<RequirePermission permission="can_access_site"><BetaDashboard /></RequirePermission>} />
                    <Route path="/products" element={<RequirePermission permission="can_fetch"><Products /></RequirePermission>} />
                    <Route path="/sources" element={<RequirePermission permission="can_access_site"><Sources /></RequirePermission>} />
                    <Route path="/sources/new" element={<RequirePermission permission="can_access_site"><SourceWizard /></RequirePermission>} />
                    <Route path="/workspace" element={<RequirePermission permission="can_fetch"><Workspace /></RequirePermission>} />
                    <Route path="/activity" element={<RequirePermission permission="can_view_logs"><Activity /></RequirePermission>} />
                    <Route path="/diagnostics" element={<RequirePermission permission="can_view_settings"><Diagnostics /></RequirePermission>} />
                    <Route path="/settings" element={<RequirePermission permission="can_view_settings"><Settings /></RequirePermission>} />
                  </Route>
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </ServiceProvider>
            </AuthProvider>
          </DirectionProvider>
        </NotificationProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}
