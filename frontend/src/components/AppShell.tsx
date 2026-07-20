import { useEffect, useRef, useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import Sidebar from './Sidebar'
import Topbar from './Topbar'

type HealthStatus = 'ok' | 'error' | 'loading'

const HEALTH_INTERVAL_MS = 15_000
const HEALTH_RETRY_MS = 5_000
const HEALTH_MAX_RETRIES = 3

export default function AppShell() {
  const { user, logout, authFetch } = useAuth()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem('wp-sb-col') === '1'
  )
  const [health, setHealth] = useState<HealthStatus>('loading')
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryCountRef = useRef(0)

  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval>

    const cancelRetry = () => {
      if (retryRef.current !== null) {
        clearTimeout(retryRef.current)
        retryRef.current = null
      }
    }

    const check = async () => {
      cancelRetry()
      try {
        const r = await authFetch('/api/health')
        if (r.ok) {
          retryCountRef.current = 0
          setHealth('ok')
        } else {
          handleFailure()
        }
      } catch {
        handleFailure()
      }
    }

    const handleFailure = () => {
      retryCountRef.current += 1
      if (retryCountRef.current <= HEALTH_MAX_RETRIES) {
        // Show loading (checking) instead of hard error during retry window
        setHealth('loading')
        retryRef.current = setTimeout(() => { void check() }, HEALTH_RETRY_MS)
      } else {
        retryCountRef.current = 0
        setHealth('error')
      }
    }

    void check()
    intervalId = setInterval(() => {
      // Only start a fresh check if no retry cycle is currently active.
      // If retryRef is set, a retry timeout is pending - leave it alone so
      // consecutive failures accumulate and eventually reach Offline threshold.
      // Counter is reset only by a successful response (inside `check`).
      if (retryRef.current === null) {
        void check()
      }
    }, HEALTH_INTERVAL_MS)

    return () => {
      clearInterval(intervalId)
      cancelRetry()
    }
  }, [authFetch])

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  function handleToggleCollapse() {
    setSidebarCollapsed(c => {
      const next = !c
      localStorage.setItem('wp-sb-col', next ? '1' : '0')
      return next
    })
  }

  return (
    <div className="flex h-screen h-[100dvh] min-h-screen min-h-[100dvh] bg-bg-base overflow-hidden">
      <Sidebar
        open={sidebarOpen}
        collapsed={sidebarCollapsed}
        onClose={() => setSidebarOpen(false)}
        user={user}
        health={health}
      />
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <Topbar
          onMenuClick={() => setSidebarOpen(o => !o)}
          onToggleCollapse={handleToggleCollapse}
          user={user}
          onLogout={handleLogout}
        />
        <main className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden bg-bg-base">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
