export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

export async function apiFetch<T>(
  url: string,
  fetchFn: FetchFn,
  init?: RequestInit,
  timeoutMs?: number,
): Promise<T> {
  const controller = timeoutMs ? new AbortController() : null
  const timeoutId = controller
    ? window.setTimeout(() => controller.abort(), timeoutMs)
    : null

  try {
    const requestInit = controller && !init?.signal
      ? { ...init, signal: controller.signal }
      : init
    const r = await fetchFn(url, requestInit)
    if (!r.ok) {
      const text = await r.text().catch(() => r.statusText)
      throw new ApiError(r.status, text)
    }
    return r.json() as Promise<T>
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('request_timeout')
    }
    throw error
  } finally {
    if (timeoutId !== null) window.clearTimeout(timeoutId)
  }
}
