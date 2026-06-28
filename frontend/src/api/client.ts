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
): Promise<T> {
  const r = await fetchFn(url, init)
  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText)
    throw new ApiError(r.status, text)
  }
  return r.json() as Promise<T>
}
