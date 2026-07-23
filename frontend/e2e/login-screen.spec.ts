import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/Login: a centered card with
// FlowHub wordmark + language/theme toggles above it, "Sign in to FlowHub"
// heading, an Email field (Figma relabeled this from the prior "Username"
// text), a password field with a lock icon and reveal toggle, a primary
// Sign in button, a contact-owner hint, and a Privacy/Security/Support
// footer. Figma's frame also shows a "Remember me" checkbox and a "Forgot
// password?" link on every variant, and a "Continue with SSO" button on
// only one of its four variants (dark/LTR, absent from light/LTR,
// light/RTL, and -- by the same inconsistency -- presumably dark/RTL).
// None of the three have any real backing: LoginRequest (app/flowhub/
// auth/router.py) accepts only username/password with no remember-me
// flag or differential token lifetime, no password-reset/forgot-password
// route exists anywhere in the auth module, and no SSO/SAML/OIDC login
// route exists either (only FastAPI's internal OAuth2PasswordBearer
// token-validation scheme, unrelated to federated sign-in). All three are
// intentionally omitted; this spec asserts their absence alongside the
// real, working fields. Captures 1440x900 evidence for Light/Dark and
// LTR/RTL. All network traffic is mocked inside this spec; nothing leaves
// the isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'login-screen')
mkdirSync(screenshotRoot, { recursive: true })

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

async function installLoginMocks(page: Page, audit: TrafficAudit) {
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      audit.externalRequests.push(`${method} ${url.href}`)
      return route.abort('blockedbyclient')
    }
    if (!url.pathname.startsWith('/api/')) return route.continue()

    if (url.pathname === '/api/v2/setup/status' && method === 'GET') return json(route, { completed: true })
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'login-visual-mock' })

    audit.unhandledApiRequests.push(`${method} ${url.pathname}${url.search}`)
    return json(route, { code: 'UNHANDLED_TEST_REQUEST' }, 500)
  })
}

async function seedSession(page: Page, locale: 'en' | 'fa', theme: 'light' | 'dark') {
  await page.addInitScript(([selectedLocale, selectedTheme]) => {
    localStorage.setItem('flowhub.locale', selectedLocale)
    localStorage.setItem('wp_theme', selectedTheme)
  }, [locale, theme])
}

async function assertFigmaLoginHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'Sign in to FlowHub' : 'ورود به FlowHub'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    await expect(page.getByText('Use your workspace account.')).toBeVisible()
    await expect(page.locator('label[for="login-identifier"]')).toHaveText('Email')
    await expect(page.locator('label[for="login-password"]')).toHaveText('Password')
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
    await expect(page.getByText('Need access? Contact your workspace Owner.')).toBeVisible()
    await expect(page.getByText('Privacy · Security · Support')).toBeVisible()

    // No real backing exists for these -- see spec header for the evidence.
    await expect(page.getByText('Remember me')).toHaveCount(0)
    await expect(page.getByText('Forgot password?')).toHaveCount(0)
    await expect(page.getByText('Continue with SSO')).toHaveCount(0)
    await expect(page.locator('input[type="checkbox"]')).toHaveCount(0)
  } else {
    await expect(page.getByText('با حساب فضای کاری خود وارد شوید.')).toBeVisible()
    await expect(page.getByText('ایمیل', { exact: true })).toBeVisible()
  }
}

test('login matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installLoginMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/login')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await assertFigmaLoginHierarchy(page, variant.locale)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({
      path: path.join(screenshotRoot, `login-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Login API request must be explicitly mocked').toEqual([])
})
