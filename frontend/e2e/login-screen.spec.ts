import { expect, test, type Page, type Route } from '@playwright/test'

// Visual + structural audit of the Figma Screen/Login: a centered card with
// FlowHub wordmark + language/theme toggles above it, "Sign in to FlowHub"
// heading, an Email field (Figma relabeled this from the prior "Username"
// text), a password field with a lock icon and reveal toggle, a primary
// Sign in button, a contact-owner hint, and the shared FlowHub copyright +
// installed-version footer. Figma's frame also shows a "Remember me" checkbox and a "Forgot
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
    await expect(page.locator('label[for="login-identifier"]')).toHaveText('Email or username')
    await expect(page.locator('label[for="login-password"]')).toHaveText('Password')
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
    await expect(page.getByText('Need access? Contact your workspace Owner.')).toBeVisible()
    await expect(page.getByRole('contentinfo')).toContainText('1405')
    await expect(page.getByRole('contentinfo')).toContainText('FlowHub vlogin-visual-mock')

    // No real backing exists for these -- see spec header for the evidence.
    await expect(page.getByText('Remember me')).toHaveCount(0)
    await expect(page.getByText('Forgot password?')).toHaveCount(0)
    await expect(page.getByText('Continue with SSO')).toHaveCount(0)
    await expect(page.locator('input[type="checkbox"]')).toHaveCount(0)
  } else {
    await expect(page.getByText('با حساب فضای کاری خود وارد شوید.')).toBeVisible()
    await expect(page.locator('label[for="login-identifier"]')).toBeVisible()
    await expect(page.locator('label[for="login-password"]')).toBeVisible()
    await expect(page.getByRole('contentinfo')).toContainText('1405')
    await expect(page.getByRole('contentinfo')).toContainText('FlowHub vlogin-visual-mock')
  }
}

test('login matches the approved Figma hierarchy in Light/Dark and LTR/RTL at 1440x900', async ({ page }, testInfo) => {
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
      path: testInfo.outputPath(`login-${variant.theme}-${variant.dir}-1440x900.png`),
      animations: 'disabled',
    })
  }

  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Login API request must be explicitly mocked').toEqual([])
})

test('language, theme, and password-visibility controls meet the mobile touch-target minimum', async ({ page }, testInfo) => {
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installLoginMocks(page, audit)
  await seedSession(page, 'en', 'light')

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/login')
  await expect(page.locator('#login-identifier')).toHaveCSS('font-size', '16px')
  await expect(page.locator('#login-password')).toHaveCSS('font-size', '16px')
  const languageBox = await page.getByRole('button', { name: 'Language' }).boundingBox()
  const themeBox = await page.getByRole('button', { name: 'Switch to dark mode' }).boundingBox()
  const passwordToggleBox = await page.getByRole('button', { name: 'Show password' }).boundingBox()
  for (const box of [languageBox, themeBox]) {
    expect(box?.width).toBeGreaterThanOrEqual(44)
    expect(box?.height).toBeGreaterThanOrEqual(44)
  }
  // The inline password-field toggle intentionally stays compact (matches the
  // shared SecretField pattern) but must still clear the WCAG 2.5.8 AA floor.
  expect(passwordToggleBox?.width).toBeGreaterThanOrEqual(24)
  expect(passwordToggleBox?.height).toBeGreaterThanOrEqual(24)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)

  const ltrBrandBox = await page.locator('.fh-login-brand').boundingBox()
  const ltrControlsBox = await page.locator('.fh-login-controls').boundingBox()
  const ltrCardBox = await page.locator('.fh-login-card').boundingBox()
  const ltrFooterBox = await page.locator('.fh-login-footer').boundingBox()
  expect(ltrBrandBox).not.toBeNull()
  expect(ltrControlsBox).not.toBeNull()
  expect(ltrCardBox?.width).toBeLessThanOrEqual(440)
  expect(ltrControlsBox!.x).toBeGreaterThan(ltrBrandBox!.x)
  expect(ltrFooterBox!.y).toBeGreaterThan(ltrCardBox!.y + ltrCardBox!.height)
  await page.screenshot({
    path: testInfo.outputPath('login-light-ltr-390x844.png'),
    animations: 'disabled',
  })

  await page.locator('.fh-login-language').click()
  await page.locator('.fh-login-theme').click()
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.locator('html')).toHaveClass(/dark/)
  const rtlBrandBox = await page.locator('.fh-login-brand').boundingBox()
  const rtlControlsBox = await page.locator('.fh-login-controls').boundingBox()
  expect(rtlControlsBox!.x + rtlControlsBox!.width).toBeLessThan(rtlBrandBox!.x + rtlBrandBox!.width)
  await page.screenshot({
    path: testInfo.outputPath('login-dark-rtl-390x844.png'),
    animations: 'disabled',
  })

  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await expect(page.locator('html')).not.toHaveClass(/dark/)

  await page.setViewportSize({ width: 1024, height: 1366 })
  await page.goto('/login')
  const tabletThemeBox = await page.getByRole('button', { name: 'Switch to dark mode' }).boundingBox()
  expect(tabletThemeBox?.width).toBeGreaterThanOrEqual(44)
  expect(tabletThemeBox?.height).toBeGreaterThanOrEqual(44)

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/login')
  await expect(page.locator('#login-identifier')).toHaveCSS('font-size', '14px')
  await expect(page.locator('#login-password')).toHaveCSS('font-size', '14px')
  const desktopThemeBox = await page.getByRole('button', { name: 'Switch to dark mode' }).boundingBox()
  expect(desktopThemeBox?.width).toBe(40)
  expect(desktopThemeBox?.height).toBe(40)
})

test('the Design System keeps every editable mobile control at 16px in LTR, RTL, light, and dark', async ({ page }) => {
  const audit: TrafficAudit = { externalRequests: [], unhandledApiRequests: [] }
  await installLoginMocks(page, audit)
  await page.setViewportSize({ width: 430, height: 932 })

  const variants = [
    { locale: 'en', theme: 'light', dir: 'ltr' },
    { locale: 'en', theme: 'dark', dir: 'ltr' },
    { locale: 'fa', theme: 'light', dir: 'rtl' },
    { locale: 'fa', theme: 'dark', dir: 'rtl' },
  ] as const

  for (const variant of variants) {
    await page.goto('/login')
    await page.evaluate(([locale, theme]) => {
      localStorage.setItem('flowhub.locale', locale)
      localStorage.setItem('wp_theme', theme)
    }, [variant.locale, variant.theme])
    await page.reload()

    await expect(page.locator('html')).toHaveAttribute('lang', variant.locale)
    await expect(page.locator('html')).toHaveAttribute('dir', variant.dir)
    if (variant.theme === 'dark') await expect(page.locator('html')).toHaveClass(/dark/)
    else await expect(page.locator('html')).not.toHaveClass(/dark/)

    await page.evaluate(() => {
      const fixture = document.createElement('div')
      fixture.id = 'fh-form-control-contract'
      fixture.style.cssText = 'position:fixed;inset-inline-start:-10000px;top:0;width:320px;'
      fixture.innerHTML = `
        <input data-ds-control class="fh-input" type="text">
        <input data-ds-control class="fh-input" type="email">
        <input data-ds-control class="fh-input" type="password">
        <input data-ds-control class="fh-workspace-search-input" type="search">
        <input data-ds-control class="fh-cell-input" type="number">
        <input data-ds-control class="fh-sheet-cell" type="date">
        <input data-ds-control class="fh-sheet-column-name" type="time">
        <textarea data-ds-control class="fh-textarea"></textarea>
        <select data-ds-control class="fh-select"><option>Standard</option></select>
        <span class="fh-chip-select"><select data-ds-control><option>Compact filter</option></select></span>
        <span class="fh-availability"><select data-ds-control><option>Availability</option></select></span>
      `
      document.body.append(fixture)
    })

    const computedSizes = await page.locator('#fh-form-control-contract [data-ds-control]').evaluateAll(controls =>
      controls.map(control => getComputedStyle(control).fontSize),
    )
    expect(new Set(computedSizes)).toEqual(new Set(['16px']))
    await expect(page.locator('#login-identifier')).toHaveCSS('font-size', '16px')
    await expect(page.locator('#login-password')).toHaveCSS('font-size', '16px')
  }

  const viewportPolicy = await page.locator('meta[name="viewport"]').getAttribute('content')
  expect(viewportPolicy).toContain('width=device-width')
  expect(viewportPolicy).not.toContain('maximum-scale')
  expect(viewportPolicy).not.toContain('user-scalable=no')
  expect(audit.externalRequests, 'No request may leave the isolated local browser environment').toEqual([])
  expect(audit.unhandledApiRequests, 'Every Login API request must be explicitly mocked').toEqual([])
})
