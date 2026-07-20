import { translate } from './i18n'
import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, RequirePermission, AccessState, useAuth } from './auth'
import { DirectionProvider } from './direction'
import { ThemeProvider } from './theme/ThemeProvider'
import { NotificationProvider } from './notifications/NotificationProvider'
import NotificationContainer from './notifications/NotificationContainer'
import { ServiceProvider } from './services/ServiceContext'
import { ApiHealthService } from './services/health/ApiHealthService'
import { ApiProductService } from './services/products/ApiProductService'
import { ApiSourceService } from './services/sources/ApiSourceService'
import { ApiWorkspaceService } from './services/workspace/ApiWorkspaceService'
import { ApiSettingsService } from './services/settings/ApiSettingsService'
import { ApiActivityService } from './services/activity/ApiActivityService'
import { ApiCommerceService } from './services/commerce/ApiCommerceService'
import { ApiWritePipelineService } from './services/writePipeline/ApiWritePipelineService'
import { ApiOrderService } from './services/orders/ApiOrderService'
import { ApiUnifiedWorkspaceService } from './services/unifiedWorkspace/ApiUnifiedWorkspaceService'
import AppShell from './components/AppShell'
import Products from './pages/Products'

const Activity = lazy(() => import('./pages/Activity'))
const CommerceHub = lazy(() => import('./pages/CommerceHub'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const DataQuality = lazy(() => import('./pages/DataQuality'))
const Diagnostics = lazy(() => import('./pages/Diagnostics'))
const FlowHubSheet = lazy(() => import('./pages/FlowHubSheet'))
const Login = lazy(() => import('./pages/Login'))
const NotFound = lazy(() => import('./pages/NotFound'))
const Orders = lazy(() => import('./pages/Orders'))
const RateLimits = lazy(() => import('./pages/RateLimits'))
const Settings = lazy(() => import('./pages/Settings'))
const Setup = lazy(() => import('./pages/Setup'))
const SourceCenter = lazy(() => import('./pages/SourceCenter'))
const SourceConfiguration = lazy(() => import('./pages/SourceConfiguration'))
const SourceImportWizard = lazy(() => import('./pages/SourceImportWizard'))
const UnifiedWorkspace = lazy(() => import('./pages/UnifiedWorkspace'))
const Workspace = lazy(() => import('./pages/Workspace'))
import type { SetupStatus } from './api/types'

const realServices = {
  health:    new ApiHealthService(),
  products:  new ApiProductService(),
  sources:   new ApiSourceService(),
  workspace: new ApiWorkspaceService(),
  settings:  new ApiSettingsService(),
  activity:  new ApiActivityService(),
  commerce:  new ApiCommerceService(),
  writePipeline: new ApiWritePipelineService(),
  orders: new ApiOrderService(),
  unifiedWorkspace: new ApiUnifiedWorkspaceService(),
}

function MaintenanceOverlay({ message }: { message?: string }) {
  const { logout } = useAuth()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-base/95 backdrop-blur-sm">
      <div className="fh-card max-w-md w-full mx-4 p-8 text-center">
        <div className="w-14 h-14 rounded-lg bg-wp-yellow/10 border border-wp-yellow/20 flex items-center justify-center mx-auto mb-4">
          <svg viewBox="0 0 24 24" className="w-7 h-7 text-wp-yellow" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        </div>
        <h2 className="text-[18px] font-bold text-text-base mb-2">{translate('common:app.maintenanceMode')}</h2>
        <p className="text-[13px] text-wp-muted mb-6">
          {message || "FlowHub is temporarily in maintenance mode. Please try again later."}
        </p>
        <button
          onClick={() => { void logout() }}
          className="fh-button-primary px-5"
        >
          {translate('common:app.signOut')}
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
        <span className="text-[13px] text-wp-muted">{translate('common:app.loading')}</span>
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
        <span className="text-[13px] text-wp-muted">{translate('common:app.loading')}</span>
      </div>
    )
  }
  if (status === 'authenticated') return <Navigate to="/home" replace />
  return <>{children}</>
}

function RouteLoading() {
  return (
    <div className="min-h-[160px] bg-bg-base flex items-center justify-center" role="status">
      <span className="text-[13px] text-wp-muted">{translate('common:app.loading')}</span>
    </div>
  )
}

// -- Setup Gate ----------------------------------------------------------------
// Checks /api/v2/setup/status on first load. If setup is not complete, renders
// only the /setup route and redirects everything else there. Once setup is
// marked complete (or the endpoint is unreachable), normal routing is shown.

function SetupGate() {
  const [setupComplete, setSetupComplete] = useState<boolean | null>(null)

  useEffect(() => {
    fetch('/api/v2/setup/status')
      .then(r => (r.ok ? r.json() as Promise<SetupStatus> : Promise.resolve({ completed: true })))
      .then(d => setSetupComplete(d.completed))
      .catch(() => setSetupComplete(true))
  }, [])

  if (setupComplete === null) {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <span className="text-[13px] text-wp-muted">{translate('common:app.loading')}</span>
      </div>
    )
  }

  if (!setupComplete) {
    return (
      <Suspense fallback={<RouteLoading />}>
        <Routes>
          <Route
            path="/setup"
            element={<Setup onComplete={() => setSetupComplete(true)} />}
          />
          <Route path="*" element={<Navigate to="/setup" replace />} />
        </Routes>
      </Suspense>
    )
  }

  return (
    <Suspense fallback={<RouteLoading />}>
      <Routes>
        <Route path="/setup" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
        <Route path="/" element={<Navigate to="/home" replace />} />
        <Route element={<AuthGuard><AppShell /></AuthGuard>}>
          <Route path="/home" element={<RequirePermission permission="can_access_site"><Dashboard /></RequirePermission>} />
          <Route path="/products" element={<RequirePermission permission="can_fetch"><Products /></RequirePermission>} />
          <Route path="/orders" element={<RequirePermission permission="can_fetch"><Orders /></RequirePermission>} />
          <Route path="/sources" element={<RequirePermission permission="can_access_site"><SourceCenter /></RequirePermission>} />
          <Route path="/sources/new" element={<RequirePermission permission="can_access_site"><SourceCenter /></RequirePermission>} />
          <Route path="/sources/import" element={<RequirePermission permission="can_access_site"><SourceImportWizard /></RequirePermission>} />
          <Route path="/sources/:sourceId" element={<RequirePermission permission="can_access_site"><SourceConfiguration /></RequirePermission>} />
          <Route path="/sheets/:sheetId" element={<RequirePermission permission="can_fetch"><FlowHubSheet /></RequirePermission>} />
          <Route path="/data-quality" element={<RequirePermission permission="can_fetch"><DataQuality /></RequirePermission>} />
          <Route path="/commerce" element={<RequirePermission permission="can_access_site"><CommerceHub /></RequirePermission>} />
          <Route path="/workspace" element={<RequirePermission permission="can_fetch"><Workspace /></RequirePermission>} />
          <Route path="/workspace/:workspaceId" element={<RequirePermission permission="can_fetch"><UnifiedWorkspace /></RequirePermission>} />
          <Route path="/activity" element={<RequirePermission permission="can_view_logs"><Activity /></RequirePermission>} />
          <Route path="/diagnostics" element={<RequirePermission permission="can_view_settings"><Diagnostics /></RequirePermission>} />
          <Route path="/rate-limits" element={<RequirePermission permission="can_view_settings"><RateLimits /></RequirePermission>} />
          <Route path="/settings" element={<RequirePermission permission="can_view_settings"><Settings /></RequirePermission>} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  )
}

// -- App root ------------------------------------------------------------------

export default function App() {
  useTranslation()
  return (
    <BrowserRouter>
      <ThemeProvider>
        <NotificationProvider>
          <NotificationContainer />
          <DirectionProvider>
            <AuthProvider>
              <ServiceProvider services={realServices}>
                <SetupGate />
              </ServiceProvider>
            </AuthProvider>
          </DirectionProvider>
        </NotificationProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}
