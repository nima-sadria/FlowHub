import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { useAuth } from '../auth'
import IconButton from '../components/IconButton'
import Spinner from '../components/loading/Spinner'
import SiteFooter from '../components/SiteFooter'
import { useDirection } from '../direction'
import { translate } from '../i18n'
import { useTheme } from '../theme/ThemeProvider'
import { inputHint } from '../utils/inputHint'

function ThemeGlyph({ theme }: { theme: 'light' | 'dark' }) {
  return theme === 'dark' ? (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z" />
    </svg>
  )
}

function LockGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="4" y="10" width="16" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </svg>
  )
}

function EyeGlyph({ visible }: { visible: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" />
      <circle cx="12" cy="12" r="2.5" />
      {!visible && <path d="m4 4 16 16" />}
    </svg>
  )
}

export default function Login() {
  const { refreshUser } = useAuth()
  const navigate = useNavigate()
  const { language, setLanguage, setDirection } = useDirection()
  const { theme, toggleTheme } = useTheme()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier: identifier.trim(), password }),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({})) as { detail?: string }
        if (response.status === 401) {
          setError(data.detail ?? translate('authentication:login.invalidCredentials'))
        } else if (response.status === 403) {
          setError(data.detail ?? translate('authentication:login.accessNotGranted'))
        } else if (response.status === 429) {
          setError(translate('authentication:login.tooManyAttempts'))
        } else if (response.status === 503) {
          setError(translate('authentication:login.serviceUnavailable'))
        } else {
          setError(data.detail ?? translate('authentication:login.loginFailedHttp', { status: response.status }))
        }
        return
      }

      const data = await response.json() as { token: string; refresh_token: string }
      localStorage.setItem('wp_token', data.token)
      localStorage.setItem('wp_refresh_token', data.refresh_token)
      await refreshUser()
      navigate('/home', { replace: true })
    } catch {
      setError(translate('authentication:login.networkError'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fh-login-shell">
      <header className="fh-login-header">
        <div className="fh-login-controls">
          <IconButton
            onClick={() => {
              const nextLanguage = language === 'fa' ? 'en' : 'fa'
              setLanguage(nextLanguage)
              setDirection(nextLanguage === 'fa' ? 'rtl' : 'ltr')
            }}
            label={translate('settings:language.title')}
            className="fh-login-language text-xs font-medium"
          >
            {language === 'fa' ? 'FA' : 'EN'}
          </IconButton>
          <IconButton
            onClick={toggleTheme}
            className="fh-login-theme"
            label={theme === 'dark'
              ? translate('navigation:topbar.switchToLightMode')
              : translate('navigation:topbar.switchToDarkMode')}
          >
            <ThemeGlyph theme={theme} />
          </IconButton>
        </div>
      </header>

      <div className="fh-login-content">
        <div className="fh-login-stack">
          <div className="fh-login-brand" dir="ltr" aria-label={translate('authentication:login.flowhub')}>
            <img
              src="/static/logos/FlowHub%20Transparent%20WebP%20%20Logo.webp?v=1"
              alt=""
              aria-hidden="true"
              className="h-[34px] w-[34px] object-contain"
            />
            <span className="text-[22px] font-semibold leading-[30px] text-text-base">FlowHub</span>
          </div>

          <main className="fh-login-card">
          <div className="text-center">
            <h1 className="text-2xl font-semibold leading-[30px] text-text-base">
              {translate('authentication:login.signInToFlowhub')}
            </h1>
            <p className="mt-4 text-[13px] leading-[22px] text-[color:var(--fh-text-secondary)]">
              {translate('authentication:login.useWorkspaceAccount')}
            </p>
          </div>

          {error && <div role="alert" className="fh-error-alert mt-5">{error}</div>}

          <form onSubmit={event => { void handleSubmit(event) }} className="mt-6 flex flex-col gap-4">
            <div className="fh-field">
              <label htmlFor="login-identifier" className="fh-label">
                {translate('authentication:login.username')}
              </label>
              <input
                id="login-identifier"
                name="identifier"
                type="text"
                value={identifier}
                onChange={event => setIdentifier(event.target.value)}
                required
                autoComplete="username"
                autoFocus
                disabled={loading}
                className="fh-input fh-login-input"
                {...inputHint(translate('authentication:login.usernameHint'))}
              />
            </div>

            <div className="fh-field">
              <label htmlFor="login-password" className="fh-label">
                {translate('authentication:login.password')}
              </label>
              <div className="relative">
                <span className="pointer-events-none absolute inset-y-0 start-3 flex items-center text-wp-muted" aria-hidden="true">
                  <LockGlyph />
                </span>
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={event => setPassword(event.target.value)}
                  required
                  autoComplete="current-password"
                  disabled={loading}
                  className="fh-input fh-login-input ps-10 pe-11"
                  {...inputHint(translate('authentication:login.passwordHint'))}
                />
                <div className="absolute inset-y-0 end-2 flex items-center">
                  <IconButton
                    size="sm"
                    onClick={() => setShowPassword(current => !current)}
                    disabled={loading}
                    label={showPassword
                      ? translate('settings:users.hidePassword')
                      : translate('settings:users.showPassword')}
                  >
                    <EyeGlyph visible={showPassword} />
                  </IconButton>
                </div>
              </div>
            </div>

            <button type="submit" disabled={loading} className="fh-button-primary fh-button-sm mt-1 w-full">
              {loading && <Spinner size="sm" className="text-white" />}
              {loading
                ? translate('authentication:login.signingIn')
                : translate('authentication:login.signIn')}
            </button>
          </form>

          <p className="mt-6 text-center text-xs leading-4 text-wp-muted">
            {translate('authentication:login.contactOwner')}
          </p>
          </main>
        </div>
      </div>

      <div className="fh-login-footer">
        <SiteFooter />
      </div>
    </div>
  )
}
