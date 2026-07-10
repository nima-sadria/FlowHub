import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { inputHint } from '../utils/inputHint'

export default function Login() {
  const { refreshUser } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const r = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      })

      if (!r.ok) {
        const data = await r.json().catch(() => ({})) as { detail?: string }
        if (r.status === 401) {
          setError(data.detail ?? 'Invalid credentials. Please check your username and password.')
        } else if (r.status === 403) {
          setError(data.detail ?? 'Access not granted - contact your administrator.')
        } else if (r.status === 429) {
          setError('Too many login attempts. Please wait a moment and try again.')
        } else if (r.status === 503) {
          setError('Authentication service is temporarily unavailable. Please try again.')
        } else {
          setError(data.detail ?? `Login failed (HTTP ${r.status}). Please try again.`)
        }
        return
      }

      const data = await r.json() as { token: string; refresh_token: string }
      localStorage.setItem('wp_token', data.token)
      localStorage.setItem('wp_refresh_token', data.refresh_token)
      await refreshUser()
      navigate('/home', { replace: true })
    } catch {
      setError('Network error. Please check your connection and try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fh-login-shell min-h-screen flex items-center justify-center p-4 sm:p-6">
      <div className="w-full max-w-[420px]">
        <div className="mb-8 text-center">
          <img
            src="/static/logos/FlowHub.webp"
            alt="FlowHub"
            className="mx-auto mb-6 h-auto w-[220px] max-w-full object-contain sm:w-[310px]"
          />
        </div>

        <div className="fh-login-card p-8 sm:p-10">
          <div className="mb-8 text-center">
            <h1 className="fh-page-title">FlowHub</h1>
            <p className="fh-page-subtitle mt-1">Sign in to FlowHub</p>
          </div>

          {error && (
            <div role="alert" className="fh-error-alert mb-4">
              {error}
            </div>
          )}

          <form onSubmit={(e) => { void handleSubmit(e) }} className="flex flex-col gap-4">
            <div className="fh-field">
              <label htmlFor="login-username" className="fh-label">
                Username
              </label>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
                autoComplete="username"
                autoFocus
                disabled={loading}
                className="fh-input"
                {...inputHint('Administrator username')}
              />
            </div>

            <div className="fh-field">
              <label htmlFor="login-password" className="fh-label">
                Password
              </label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                disabled={loading}
                className="fh-input"
                {...inputHint('Enter your administrator credentials')}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="fh-button-primary mt-2 w-full"
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
