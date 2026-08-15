// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { MemoryRouter } from 'react-router'
import PricingMatrix from './PricingMatrix'
import { changeLocale } from '../i18n'
import { AuthContext, type AuthContextValue, type AuthUser } from '../auth'

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let container: HTMLDivElement
let root: ReturnType<typeof createRoot>

const CHANNEL = 'woocommerce:primary'

const policySummary = {
  id: 'rev-1', policyId: 'pol-1', revisionNumber: 1, name: 'Retail EUR',
  computationCurrency: 'EUR', basisStrategy: 'min', roundOrder: 'surcharge_then_round',
  maxQuoteAgeDays: 30, minQuoteCount: 1, evaluationTimezone: 'UTC',
  arithmeticVersion: 'a1', unitRegistryVersion: 'u1', checksum: 'sum-1',
  createdAt: '2026-08-05T00:00:00Z',
}

const policyRevision = {
  ...policySummary,
  rules: [{
    channelId: CHANNEL, productRef: null, productGroupRevisionId: null,
    rateMode: 'percent_bp', rateValue: 1000, fixedAddendMinor: 0, roundMode: 'floor',
    roundStepMinor: 100, surchargeMinor: 0, guards: {},
  }],
}

const inactiveHead = {
  channelId: CHANNEL, headVersion: 0, currentEventId: null, effectiveActivationId: null,
  status: 'inactive', policyRevisionId: null, channelConfigRevisionId: null,
  updatedAt: '2026-08-05T00:00:00Z',
}

const unresolvedUnit = { scope: 'channel', scopeReference: CHANNEL, status: 'unresolved', currency: null, unit: null }

const events = {
  items: [{
    id: 'ev-1', channelId: CHANNEL, eventKind: 'deactivate', predecessorEventId: null,
    effectiveActivationId: null, policyRevisionId: null, channelConfigRevisionId: null,
    supersedesActivationId: null, actorUserId: 'admin', reason: 'pause', occurredAt: '2026-08-05T00:00:00Z',
  }],
}

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

function defaultResponder(policies: unknown = { items: [policySummary] }) {
  return (input: RequestInfo | URL): Response => {
    const url = String(input)
    if (url.includes('/lifecycle-events')) return json(events)
    if (url.includes('/head')) return json(inactiveHead)
    if (url.includes('/units/channel/')) return json(unresolvedUnit)
    if (url.includes('/pricing-matrix/policies/')) return json(policyRevision)
    if (url.includes('/pricing-matrix/policies')) return json(policies)
    return new Response('{}', { status: 404 })
  }
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(async () => {
  act(() => { root.unmount() })
  container.remove()
  vi.unstubAllGlobals()
  await changeLocale('en')
})

const adminUser: AuthUser = {
  id: 1, username: 'admin', email: 'admin@example.com', role: 'admin', is_admin: true, is_super_admin: false,
  permissions: { can_access_site: true, can_view_settings: true, 'workspace.read': true, 'workspace.admin': true },
}

const viewerUser: AuthUser = {
  id: 2, username: 'viewer', email: 'viewer@example.com', role: 'user', is_admin: false, is_super_admin: false,
  permissions: { can_access_site: true, can_view_settings: true, 'workspace.read': true },
}

function authValue(user: AuthUser): AuthContextValue {
  return {
    user,
    status: 'authenticated',
    refreshUser: async () => undefined,
    clearAuth: () => undefined,
    logout: async () => undefined,
    authFetch: fetch,
  }
}

async function renderPage(user: AuthUser = adminUser) {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/settings/pricing']}>
        <AuthContext.Provider value={authValue(user)}>
          <PricingMatrix />
        </AuthContext.Provider>
      </MemoryRouter>,
    )
  })
  await act(async () => { await Promise.resolve() })
  return container
}

async function settle() {
  for (let i = 0; i < 4; i += 1) {
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
  }
}

describe('PricingMatrix (read-only surfaces)', () => {
  it('renders the read-only note and the policies list', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => defaultResponder()(input as RequestInfo | URL)))
    const c = await renderPage()
    expect(c.querySelector('[data-testid="pricing-page"]')).not.toBeNull()
    expect(c.textContent).toContain('Channel activation, pricing preview, and apply are not available')
    expect(c.querySelector('[data-testid="pricing-policy-row-rev-1"]')?.textContent).toContain('Retail EUR')
  })

  it('shows an empty state when there are no policies', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => defaultResponder({ items: [] })(input as RequestInfo | URL)))
    const c = await renderPage()
    expect(c.querySelector('[data-testid="pricing-empty"]')).not.toBeNull()
  })

  it('shows a distinct permission-denied state on 403', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/pricing-matrix/policies')) return json({ detail: { code: 'forbidden', message: 'no' } }, 403)
      return new Response('{}', { status: 404 })
    }))
    const c = await renderPage()
    expect(c.querySelector('[data-testid="pricing-permission-denied"]')).not.toBeNull()
    expect(c.querySelector('[data-testid="pricing-unavailable"]')).toBeNull()
  })

  it('shows a distinct unavailable state with the HTTP status on 500', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/pricing-matrix/policies')) return json({ detail: 'down' }, 500)
      return new Response('{}', { status: 404 })
    }))
    const c = await renderPage()
    const panel = c.querySelector('[data-testid="pricing-unavailable"]')
    expect(panel).not.toBeNull()
    expect(panel?.textContent).toContain('500')
  })

  it('fails closed to a contract-mismatch state on an unknown enum value', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => {
      if (String(input).includes('/pricing-matrix/policies')) {
        return json({ items: [{ ...policySummary, roundOrder: 'sideways' }] })
      }
      return new Response('{}', { status: 404 })
    }))
    const c = await renderPage()
    expect(c.querySelector('[data-testid="pricing-contract-mismatch"]')).not.toBeNull()
  })

  it('reveals rules, channel lifecycle, and an unresolved unit when a policy is selected', async () => {
    vi.stubGlobal('fetch', vi.fn(async input => defaultResponder()(input as RequestInfo | URL)))
    const c = await renderPage()
    const row = c.querySelector('[data-testid="pricing-policy-row-rev-1"]') as HTMLButtonElement
    await act(async () => { row.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()

    expect(c.querySelector('[data-testid="pricing-rules-table"]')).not.toBeNull()
    expect(c.querySelector('[data-testid="pricing-policy-detail"]')?.textContent).toContain('Retail EUR')

    const status = c.querySelector('[data-testid="pricing-channel-status-woocommerce:primary"]')
    expect(status?.textContent).toContain('Inactive')

    const unit = c.querySelector('[data-testid="pricing-unit-status-woocommerce:primary"]')
    expect(unit?.textContent).toContain('Unresolved')
    expect(c.querySelector('[data-testid="pricing-units-unresolved"]')).not.toBeNull()

    expect(c.querySelector('[data-testid="pricing-events-woocommerce:primary"]')?.textContent).toContain('Deactivated')
  })

  it('preserves an exact monetary rate value as text', async () => {
    const bigRate = '9007199254740993000'
    vi.stubGlobal('fetch', vi.fn(async input => {
      const url = String(input)
      if (url.includes('/pricing-matrix/policies/')) {
        return json({ ...policyRevision, rules: [{ ...policyRevision.rules[0], rateValue: bigRate }] })
      }
      return defaultResponder()(input as RequestInfo | URL)
    }))
    const c = await renderPage()
    const row = c.querySelector('[data-testid="pricing-policy-row-rev-1"]') as HTMLButtonElement
    await act(async () => { row.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()
    expect(c.querySelector('[data-testid="pricing-rule-row-0"]')?.textContent).toContain(bigRate)
  })

  it('localizes the page in Persian', async () => {
    await changeLocale('fa')
    vi.stubGlobal('fetch', vi.fn(async input => defaultResponder()(input as RequestInfo | URL)))
    const c = await renderPage()
    expect(c.textContent).toContain('ماتریس قیمت‌گذاری')
    expect(c.textContent).not.toContain('Pricing Matrix')
  })
})

// -- UI Stage 4: Channel Policy Lifecycle Mutations -----------------------------

const CHANNEL_ENCODED = encodeURIComponent(CHANNEL)

const activeHead = {
  channelId: CHANNEL, headVersion: 1, currentEventId: 'evt-1', effectiveActivationId: 'act-1',
  status: 'active', policyRevisionId: 'rev-1', channelConfigRevisionId: 'cfg-1',
  updatedAt: '2026-08-05T00:00:00Z',
}

function setValue(el: Element | null, value: string) {
  const input = el as HTMLInputElement
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
  setter.call(input, value)
  input.dispatchEvent(new Event('change', { bubbles: true }))
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

function stubLifecycleFetch(opts: {
  head?: unknown
  onActivate?: (body: unknown) => Response
  onDeactivate?: (body: unknown) => Response
}) {
  let headCalls = 0
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (method === 'POST' && url.endsWith(`/channels/${CHANNEL_ENCODED}/activate`)) {
      const body: unknown = init?.body ? JSON.parse(String(init.body)) : {}
      return opts.onActivate ? opts.onActivate(body) : json(activeHead)
    }
    if (method === 'POST' && url.endsWith(`/channels/${CHANNEL_ENCODED}/deactivate`)) {
      const body: unknown = init?.body ? JSON.parse(String(init.body)) : {}
      return opts.onDeactivate ? opts.onDeactivate(body) : json(inactiveHead)
    }
    if (url.includes('/lifecycle-events')) return json(events)
    if (url.includes('/head')) {
      headCalls += 1
      const base = opts.head ?? inactiveHead
      // Second and later GETs simulate the Head having changed underneath the
      // client (used by the 409 test to prove a real refetch happened).
      return json(headCalls > 1 ? { ...(base as object), headVersion: 2 } : base)
    }
    if (url.includes('/units/channel/')) return json(unresolvedUnit)
    if (url.includes('/pricing-matrix/policies/')) return json(policyRevision)
    if (url.includes('/pricing-matrix/policies')) return json({ items: [policySummary] })
    return new Response('{}', { status: 404 })
  }))
}

function definitionValue(scope: Element | null, labelText: string): string | null {
  const dt = Array.from(scope?.querySelectorAll('dt') ?? []).find(el => el.textContent === labelText)
  return dt?.nextElementSibling?.textContent ?? null
}

async function selectPolicy(c: HTMLElement) {
  const row = c.querySelector('[data-testid="pricing-policy-row-rev-1"]') as HTMLButtonElement
  await act(async () => { row.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
  await settle()
}

describe('PricingMatrix — channel lifecycle actions (UI Stage 4)', () => {
  it('activates a channel: sends expected_head_version exactly, updates the badge, and clears the form', async () => {
    let activateBody: unknown
    stubLifecycleFetch({
      head: inactiveHead,
      onActivate: body => { activateBody = body; return json(activeHead) },
    })
    const c = await renderPage()
    await selectPolicy(c)

    const openButton = c.querySelector(`[data-testid="pricing-channel-activate-${CHANNEL}"]`) as HTMLButtonElement
    expect(openButton).not.toBeNull()
    await act(async () => { openButton.dispatchEvent(new MouseEvent('click', { bubbles: true })) })

    setValue(c.querySelector(`[data-testid="pricing-channel-reason-${CHANNEL}"]`), 'Go live')
    const confirm = c.querySelector(`[data-testid="pricing-channel-activate-confirm-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { confirm.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()

    expect(activateBody).toMatchObject({ policy_revision_id: 'rev-1', expected_head_version: 0, reason: 'Go live' })
    expect(c.querySelector(`[data-testid="pricing-channel-status-${CHANNEL}"]`)?.textContent).toContain('Active')
    expect(c.querySelector(`[data-testid="pricing-channel-action-form-${CHANNEL}"]`)).toBeNull()
  })

  it('deactivates a channel and updates the badge', async () => {
    let deactivateBody: unknown
    stubLifecycleFetch({
      head: activeHead,
      onDeactivate: body => { deactivateBody = body; return json(inactiveHead) },
    })
    const c = await renderPage()
    await selectPolicy(c)

    const openButton = c.querySelector(`[data-testid="pricing-channel-deactivate-${CHANNEL}"]`) as HTMLButtonElement
    expect(openButton).not.toBeNull()
    await act(async () => { openButton.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    setValue(c.querySelector(`[data-testid="pricing-channel-reason-${CHANNEL}"]`), 'Pause pricing')
    const confirm = c.querySelector(`[data-testid="pricing-channel-deactivate-confirm-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { confirm.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()

    expect(deactivateBody).toMatchObject({ expected_head_version: 1, reason: 'Pause pricing' })
    expect(c.querySelector(`[data-testid="pricing-channel-status-${CHANNEL}"]`)?.textContent).toContain('Inactive')
  })

  it('on 409 conflict, refetches Head and Lifecycle Events, keeps the form open with the reason preserved, and never auto-retries', async () => {
    let activatePostCalls = 0
    stubLifecycleFetch({
      head: inactiveHead,
      onActivate: () => {
        activatePostCalls += 1
        return json({ detail: { code: 'pricing_policy_head_conflict', message: 'stale' } }, 409)
      },
    })
    const c = await renderPage()
    await selectPolicy(c)

    const openButton = c.querySelector(`[data-testid="pricing-channel-activate-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { openButton.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    setValue(c.querySelector(`[data-testid="pricing-channel-reason-${CHANNEL}"]`), 'Go live')
    const confirm = c.querySelector(`[data-testid="pricing-channel-activate-confirm-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { confirm.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()

    expect(activatePostCalls).toBe(1)
    expect(c.querySelector('[data-testid="pricing-stale-state"]')).not.toBeNull()
    // Form stays open (not cleared) and the reason the user typed is preserved.
    expect(c.querySelector(`[data-testid="pricing-channel-action-form-${CHANNEL}"]`)).not.toBeNull()
    expect((c.querySelector(`[data-testid="pricing-channel-reason-${CHANNEL}"]`) as HTMLInputElement).value).toBe('Go live')
    // The Head was refetched (now headVersion 2) — evidence refreshed, but the mutation was not resubmitted.
    const card = c.querySelector(`[data-testid="pricing-channel-card-${CHANNEL}"]`)
    expect(definitionValue(card, 'Head version')).toBe('2')
  })

  it('shows a distinct permission-denied state on a 403 from the mutation, preserving the reason', async () => {
    stubLifecycleFetch({
      head: inactiveHead,
      onActivate: () => json({ detail: { code: 'forbidden', message: 'no' } }, 403),
    })
    const c = await renderPage()
    await selectPolicy(c)
    const openButton = c.querySelector(`[data-testid="pricing-channel-activate-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { openButton.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    setValue(c.querySelector(`[data-testid="pricing-channel-reason-${CHANNEL}"]`), 'Kept reason')
    const confirm = c.querySelector(`[data-testid="pricing-channel-activate-confirm-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { confirm.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()

    expect(c.querySelector('[data-testid="pricing-permission-denied"]')).not.toBeNull()
    expect((c.querySelector(`[data-testid="pricing-channel-reason-${CHANNEL}"]`) as HTMLInputElement).value).toBe('Kept reason')
  })

  it('shows a distinct unavailable state on a network/server failure without losing the reason', async () => {
    stubLifecycleFetch({
      head: inactiveHead,
      onActivate: () => json({ detail: 'down' }, 500),
    })
    const c = await renderPage()
    await selectPolicy(c)
    const openButton = c.querySelector(`[data-testid="pricing-channel-activate-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { openButton.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    setValue(c.querySelector(`[data-testid="pricing-channel-reason-${CHANNEL}"]`), 'Try live')
    const confirm = c.querySelector(`[data-testid="pricing-channel-activate-confirm-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { confirm.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()

    expect(c.querySelector('[data-testid="pricing-unavailable"]')).not.toBeNull()
    expect((c.querySelector(`[data-testid="pricing-channel-reason-${CHANNEL}"]`) as HTMLInputElement).value).toBe('Try live')
  })

  it('does not expose activate/deactivate controls without workspace.admin', async () => {
    stubLifecycleFetch({ head: inactiveHead })
    const c = await renderPage(viewerUser)
    await selectPolicy(c)
    expect(c.querySelector(`[data-testid="pricing-channel-activate-${CHANNEL}"]`)).toBeNull()
    expect(c.querySelector(`[data-testid="pricing-channel-deactivate-${CHANNEL}"]`)).toBeNull()
    // Read-only evidence remains visible regardless of admin gating.
    expect(c.querySelector(`[data-testid="pricing-channel-status-${CHANNEL}"]`)?.textContent).toContain('Inactive')
  })

  it('localizes the lifecycle action form in Persian', async () => {
    await changeLocale('fa')
    stubLifecycleFetch({ head: inactiveHead })
    const c = await renderPage()
    await selectPolicy(c)
    const openButton = c.querySelector(`[data-testid="pricing-channel-activate-${CHANNEL}"]`) as HTMLButtonElement
    expect(openButton.textContent).toContain('فعال‌سازی این بازنگری سیاست')
    await act(async () => { openButton.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    expect(c.textContent).toContain('دلیل')
    expect(c.querySelector(`[data-testid="pricing-channel-activate-confirm-${CHANNEL}"]`)?.textContent).toContain('فعال‌سازی')
  })
})

// -- UI Stage 5: RTL, responsive, theme, accessibility, keyboard ---------------

describe('PricingMatrix — RTL, responsive, and accessibility (UI Stage 5)', () => {
  it('sets document direction to rtl in Persian and isolates technical identifiers with <bdi dir="ltr">', async () => {
    await changeLocale('fa')
    stubLifecycleFetch({ head: activeHead })
    const c = await renderPage()
    await selectPolicy(c)

    expect(document.documentElement.dir).toBe('rtl')
    const channelHeading = c.querySelector(`[data-testid="pricing-channel-card-${CHANNEL}"] h3`)
    expect(channelHeading?.querySelector('bdi[dir="ltr"]')?.textContent).toBe(CHANNEL)
    const revisionBadge = c.querySelector('[data-testid="pricing-policy-detail"] bdi[dir="ltr"]')
    expect(revisionBadge?.textContent).toContain('#1')
  })

  it('wraps a very long English policy name instead of clipping it', async () => {
    const longName = 'Retail Configuration '.repeat(12).trim()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/pricing-matrix/policies') && method === 'GET') return json({ items: [{ ...policySummary, name: longName }] })
      if (url.includes('/lifecycle-events')) return json(events)
      if (url.includes('/head')) return json(inactiveHead)
      if (url.includes('/units/channel/')) return json(unresolvedUnit)
      if (url.includes('/pricing-matrix/policies/')) return json({ ...policyRevision, name: longName })
      return new Response('{}', { status: 404 })
    }))
    const c = await renderPage()
    const nameSpan = c.querySelector(`[data-testid="pricing-policy-row-rev-1"] span span`)
    expect(nameSpan?.textContent).toBe(longName)
    expect(nameSpan?.className).toContain('break-words')
    expect(nameSpan?.className).toContain('min-w-0')
  })

  it('wraps a very long Persian policy name instead of clipping it', async () => {
    await changeLocale('fa')
    const longName = 'سیاست قیمت‌گذاری خرده‌فروشی برای کانال‌های متعدد و بازنگری‌های آینده '.repeat(3).trim()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/pricing-matrix/policies')) return json({ items: [{ ...policySummary, name: longName }] })
      return new Response('{}', { status: 404 })
    }))
    const c = await renderPage()
    const nameSpan = c.querySelector(`[data-testid="pricing-policy-row-rev-1"] span span`)
    expect(nameSpan?.textContent).toBe(longName)
    expect(nameSpan?.className).toContain('break-words')
  })

  it('keeps the rules and units tables horizontally scrollable instead of clipped', async () => {
    stubLifecycleFetch({ head: inactiveHead })
    const c = await renderPage()
    await selectPolicy(c)

    const rulesTable = c.querySelector('[data-testid="pricing-rules-table"]')
    expect(rulesTable?.closest('.overflow-x-auto')).not.toBeNull()
    const unitsTable = c.querySelector('[data-testid="pricing-units-table"]')
    expect(unitsTable?.closest('.overflow-x-auto')).not.toBeNull()
  })

  it('keeps the channel lifecycle action button row wrappable instead of clipped on narrow widths', async () => {
    stubLifecycleFetch({ head: inactiveHead })
    const c = await renderPage()
    await selectPolicy(c)
    const openButton = c.querySelector(`[data-testid="pricing-channel-activate-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { openButton.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    const actionRow = c.querySelector(`[data-testid="pricing-channel-action-form-${CHANNEL}"] .flex.gap-2, [data-testid="pricing-channel-action-form-${CHANNEL}"] .flex.flex-wrap.gap-2`)
    expect(actionRow?.className).toContain('flex-wrap')
  })

  it('moves keyboard focus into the reason field when the activate form opens', async () => {
    stubLifecycleFetch({ head: inactiveHead })
    const c = await renderPage()
    await selectPolicy(c)
    const openButton = c.querySelector(`[data-testid="pricing-channel-activate-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { openButton.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    const reasonInput = c.querySelector(`[data-testid="pricing-channel-reason-${CHANNEL}"]`)
    expect(document.activeElement).toBe(reasonInput)
  })

  it('associates every labeled field with a matching id (label/control pairing)', async () => {
    stubLifecycleFetch({ head: inactiveHead })
    const c = await renderPage()
    await selectPolicy(c)
    // Open the lifecycle action form so its labeled reason field is present.
    const openButton = c.querySelector(`[data-testid="pricing-channel-activate-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { openButton.dispatchEvent(new MouseEvent('click', { bubbles: true })) })

    const labels = Array.from(c.querySelectorAll('label[for]'))
    expect(labels.length).toBeGreaterThan(0)
    for (const label of labels) {
      const forId = label.getAttribute('for')!
      expect(c.querySelector(`[id="${forId}"]`), `no control found for label "${label.textContent}"`).not.toBeNull()
    }
  })

  it('announces the mutation error region distinctly and links it to the reason field', async () => {
    stubLifecycleFetch({ head: inactiveHead, onActivate: () => json({ detail: { code: 'forbidden' } }, 403) })
    const c = await renderPage()
    await selectPolicy(c)
    const openButton = c.querySelector(`[data-testid="pricing-channel-activate-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { openButton.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    setValue(c.querySelector(`[data-testid="pricing-channel-reason-${CHANNEL}"]`), 'Go live')
    const confirm = c.querySelector(`[data-testid="pricing-channel-activate-confirm-${CHANNEL}"]`) as HTMLButtonElement
    await act(async () => { confirm.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await settle()

    const reasonInput = c.querySelector(`[data-testid="pricing-channel-reason-${CHANNEL}"]`)
    const describedBy = reasonInput?.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    const errorRegion = c.querySelector(`[id="${describedBy}"]`)
    expect(errorRegion?.querySelector('[role="alert"], [role="status"]')).not.toBeNull()
  })
})
