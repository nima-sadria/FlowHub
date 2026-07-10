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
})
