/**
 * Lightweight authenticated fetch wrapper for BU5 real service implementations.
 * Reads the JWT from localStorage on every call so stale references are avoided
 * after token refresh.  The auth key matches what AuthProvider writes.
 */

export function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const token = localStorage.getItem('wp_token') ?? ''
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return fetch(input, { ...init, headers })
}
