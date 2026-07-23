import path from 'node:path'
import { mkdirSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/SetupWizard: a centered
// "Set up your workspace" card with a 4-stage step progress indicator, a
// "Workspace details" form (domain, language, timezone, default currency),
// a "Save and exit" / "Continue to database" action pair, and a "Setup
// checklist" sidebar. Figma's own step-progress control (and its detailed
// mock) is only for step 1; it labels the later stages "Source" and
// "Channel", but neither has any real backend endpoint (confirmed by
// reading app/flowhub/api/v2/setup.py's own module docstring, which lists
// exactly four real routes: server-profile, database, admin, complete --
// no source/channel routes exist anywhere in the setup API). This mirrors
// the already-established SourceSetup/ChannelSetup HOLD finding from
// earlier in this pass. A database-readiness check and an owner-account
// step are both real, required parts of getting a fresh install running,
// so the wizard keeps its existing Workspace/Database/Owner/Review stages
// rather than replacing two of them with the unbacked Source/Channel
// concepts Figma's step labels name. Figma's "Workspace name" field
// (mock value "FlowHub Commerce") has no corresponding field in
// ServerProfilePayload either (domain/port/environment/timezone/currency
// only) and is likewise omitted; the real "Workspace domain" field it
// would have displaced is kept. "Save and exit" is real: it reuses the
// exact same POST /api/v2/setup/server-profile the "Continue" action
// already uses, just without advancing afterward. Captures 1440x900
// evidence for Light/Dark and LTR/RTL of the one step Figma fully
// specifies. All network traffic is mocked inside this spec; nothing
// leaves the isolated browser.

const screenshotRoot = path.resolve('..', 'docs', 'screenshots', 'v1.3', 'setup-wizard-screen')
mkdirSync(screenshotRoot, { recursive: true })

interface TrafficAudit {
  externalRequests: string[]
  unhandledApiRequests: string[]
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) })
}

async function installSetupMocks(page: Page, audit: TrafficAudit) {
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      audit.externalRequests.push(`${method} ${url.href}`)
      return route.abort('blockedbyclient')
    }
    if (!url.pathname.startsWith('/api/')) return route.continue()

    if (url.pathname === '/api/v2/setup/status' && method === 'GET') {
      return json(route, { completed: false, has_admin: false })
    }
    if (url.pathname === '/api/health' && method === 'GET') return json(route, { status: 'ok', env: 'test', version: 'setup-wizard-visual-mock' })

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

async function assertFigmaSetupWizardHierarchy(page: Page, locale: 'en' | 'fa') {
  const heading = locale === 'en' ? 'Set up your workspace' : 'راه‌اندازی فضای کاری'
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()

  if (locale === 'en') {
    await expect(page.getByText('Step 1 of 4')).toBeVisible()
    await expect(page.getByText('Workspace', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('Database', { exact: true })).toBeVisible()
    await expect(page.getByText('Owner', { exact: true })).toBeVisible()
    await expect(page.getByText('Review', { exact: true })).toBeVisible()

    await expect(page.getByText('Workspace details')).toBeVisible()
    await expect(page.getByText('Workspace domain')).toBeVisible()
    await expect(page.getByText('Default currency')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Save and exit' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Continue to database' })).toBeVisible()

    await expect(page.getByText('Setup checklist')).toBeVisible()
    await expect(page.getByText('Workspace defaults')).toBeVisible()

    // Figma's own step labels for stages 2-3 ("Source"/"Channel") and its
    // "Workspace name" field have no real backing -- see spec header.
    await expect(page.getByText('Workspace name')).toHaveCount(0)
    await expect(page.getByText('Connect a source')).toHaveCount(0)
    await expect(page.getByText('Connect a channel')).toHaveCount(0)
  } else {
    await expect(page.getByText('این پیش‌فرض‌ها روندهای فروش را شکل می‌دهند و بعداً قابل تغییرند.')).toBeVisible()
    await expect(page.getByText('فهرست بررسی راه‌اندازی')).toBeVisible()
  }
}

test('setup wizard matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }) => {
  test.setTimeout(180_000)
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installSetupMocks(page, audit)
  await page.setViewportSize({ width: 1440, height: 900 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await seedSession(page, variant.locale, variant.theme)
    await page.goto('/setup')
    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') {
      await expect(page.locator('html')).toHaveClass(/dark/)
    }
    await assertFigmaSetupWizardHierarchy(page, variant.locale)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({
      path: path.join(screenshotRoot, `setup-wizard-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every SetupWizard API request must be explicitly mocked').toEqual([])
})
