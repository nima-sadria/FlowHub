// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { apiErrorMessage, apiFetch, ApiError } from './client'

function makeFetch(status: number, body: unknown) {
  return (_input: RequestInfo | URL) => Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function makeFailFetch(status: number, text: string) {
  return (_input: RequestInfo | URL) => Promise.resolve(
    new Response(text, { status, headers: { 'Content-Type': 'text/plain' } })
  )
}

function makeJsonFailFetch(status: number, body: unknown) {
  return (_input: RequestInfo | URL) => Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  )
}

describe('apiFetch', () => {
  it('returns parsed JSON on 200', async () => {
    const result = await apiFetch<{ status: string }>('/api/health', makeFetch(200, { status: 'ok' }))
    expect(result.status).toBe('ok')
  })

  it('throws ApiError on 401', async () => {
    await expect(apiFetch('/api/health', makeFailFetch(401, 'Unauthorized'))).rejects.toBeInstanceOf(ApiError)
  })

  it('ApiError has correct status and does not preserve a raw non-JSON body', async () => {
    let err: ApiError | null = null
    try { await apiFetch('/api/health', makeFailFetch(403, 'Forbidden')) } catch (e) { err = e as ApiError }
    expect(err).not.toBeNull()
    expect(err!.status).toBe(403)
    expect(err!.message).toBe('An upstream service returned an invalid response. Check the connection and try again.')
  })

  it('throws ApiError on 500', async () => {
    await expect(apiFetch('/api/health', makeFailFetch(500, 'Internal Server Error'))).rejects.toBeInstanceOf(ApiError)
  })

  it('ApiError name is ApiError', async () => {
    let err: ApiError | null = null
    try { await apiFetch('/api/health', makeFailFetch(404, 'Not Found')) } catch (e) { err = e as ApiError }
    expect(err!.name).toBe('ApiError')
  })

  it('replaces HTML upstream errors with a fixed safe message', async () => {
    const html = '<!DOCTYPE html><html><body>cloudflare ray id=secret-token</body></html>'
    let err: ApiError | null = null
    try { await apiFetch('/api/commerce', makeFailFetch(502, html)) } catch (e) { err = e as ApiError }

    expect(err?.message).toBe('An upstream service returned an invalid response. Check the connection and try again.')
    expect(err?.message).not.toContain('<html')
    expect(err?.message).not.toContain('secret-token')
  })

  it('keeps a safe JSON detail while redacting credential-like values', async () => {
    let err: ApiError | null = null
    try {
      await apiFetch('/api/commerce', makeJsonFailFetch(429, {
        code: 'CHANNEL_RATE_LIMITED',
        message: 'The external service rate limit was reached.',
        detail: 'authorization=private-value',
      }))
    } catch (e) {
      err = e as ApiError
    }

    expect(err?.code).toBe('CHANNEL_RATE_LIMITED')
    expect(apiErrorMessage(err, 'fallback')).toBe('The external service rate limit was reached.')
    expect(apiErrorMessage(new ApiError(502, '<html>proxy</html>'), 'fallback')).toBe('fallback')
  })

  it('retains only structured source-limit recovery metadata', async () => {
    let err: ApiError | null = null
    try {
      await apiFetch('/api/v2/workspace/preview', makeJsonFailFetch(429, {
        detail: {
          code: 'SOURCE_READ_LIMIT_REACHED',
          message: 'Source read limit reached.',
          limit: 6,
          usage: 6,
          reset_at: '2026-07-12T11:08:08Z',
          retry_after_seconds: 120,
          token: 'must-not-survive',
        },
      }))
    } catch (error) {
      err = error as ApiError
    }

    expect(err?.details).toEqual({
      limit: 6,
      usage: 6,
      resetAt: '2026-07-12T11:08:08Z',
      retryAfterSeconds: 120,
    })
    expect(JSON.stringify(err?.details)).not.toContain('must-not-survive')
  })

  it.each([
    ['Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.private.signature', 'Authorization: [REDACTED]'],
    ['authorization=Basic dXNlcjpwYXNz', 'authorization=[REDACTED]'],
    ['Request failed with Bearer eyJhbGciOiJIUzI1NiJ9.private', 'Request failed with [REDACTED]'],
    ['password=private token: abcdefgh api_key=key-value', 'password=[REDACTED] token: [REDACTED] api_key=[REDACTED]'],
    ['cookie=session-secret session=session-value jwt=jwt-value', 'cookie=[REDACTED] session=[REDACTED] jwt=[REDACTED]'],
  ])('fully redacts structured credential text', (unsafe, expected) => {
    expect(apiErrorMessage(new ApiError(400, JSON.stringify({ message: unsafe })), 'fallback')).toBe(expected)
  })

  it('removes userinfo from credential-bearing URLs', () => {
    const error = new ApiError(400, JSON.stringify({ detail: 'Check https://user:pass@example.test/path now.' }))
    const message = apiErrorMessage(error, 'fallback')
    expect(message).toBe('Check https://example.test/path now.')
    expect(message).not.toContain('user:pass')
  })

  it.each([
    'Traceback (most recent call last):\n  File "service.py", line 10\nValueError: secret',
    'Internal Server Error\n    at handler (api.ts:10:2)\n    at next (router.ts:2:1)',
  ])('replaces stack traces with a fixed safe message', (trace) => {
    expect(apiErrorMessage(new ApiError(500, JSON.stringify({ detail: trace })), 'fallback'))
      .toBe('An internal service error occurred.')
  })

  it('truncates long structured errors after sanitization', () => {
    const message = apiErrorMessage(new ApiError(500, JSON.stringify({ message: 'x'.repeat(700) })), 'fallback')
    expect(message).toHaveLength(500)
    expect(message.endsWith('...')).toBe(true)
  })

  it('preserves concise normal messages and supports title/errors fields', () => {
    expect(apiErrorMessage(new ApiError(409, JSON.stringify({ title: 'Configuration conflict.' })), 'fallback'))
      .toBe('Configuration conflict.')
    expect(apiErrorMessage(new ApiError(422, JSON.stringify({ errors: ['Invalid spreadsheet path.'] })), 'fallback'))
      .toBe('Invalid spreadsheet path.')
  })
})
