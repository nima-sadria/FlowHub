// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { apiFetch, ApiError } from './client'

function makeFetch(status: number, body: unknown) {
  return (_input: RequestInfo | URL) => Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function makeFailFetch(status: number, text: string) {
  return (_input: RequestInfo | URL) => Promise.resolve(
    new Response(text, { status, headers: { 'Content-Type': 'text/plain' } })
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

  it('ApiError has correct status', async () => {
    let err: ApiError | null = null
    try { await apiFetch('/api/health', makeFailFetch(403, 'Forbidden')) } catch (e) { err = e as ApiError }
    expect(err).not.toBeNull()
    expect(err!.status).toBe(403)
    expect(err!.message).toBe('Forbidden')
  })

  it('throws ApiError on 500', async () => {
    await expect(apiFetch('/api/health', makeFailFetch(500, 'Internal Server Error'))).rejects.toBeInstanceOf(ApiError)
  })

  it('ApiError name is ApiError', async () => {
    let err: ApiError | null = null
    try { await apiFetch('/api/health', makeFailFetch(404, 'Not Found')) } catch (e) { err = e as ApiError }
    expect(err!.name).toBe('ApiError')
  })
})
