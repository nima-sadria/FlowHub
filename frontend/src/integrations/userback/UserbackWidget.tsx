import { useEffect, useRef } from 'react'
import type { UserbackWidget as UserbackInstance } from '@userback/widget'
import type { AuthUser } from '../../auth'

export interface UserbackWidgetProps {
  /** The current FlowHub session. Callers only reach this component once authenticated. */
  user: AuthUser
}

const POLL_INTERVAL_MS = 250
const POLL_TIMEOUT_MS = 15_000

/**
 * Identifies the authenticated FlowHub user to the Userback widget.
 *
 * The widget itself is loaded unconditionally for every page (including
 * /login) by the static snippet in index.html, driven by
 * VITE_USERBACK_ACCESS_TOKEN, so Userback's site verification can find it
 * without a session. This component never loads or re-initializes the
 * widget; it only calls window.Userback.identify() once the SDK has
 * finished loading, so feedback from a signed-in session is attributed to
 * the real internal id, username, and email. If Userback was never
 * configured (no token, so window.Userback stays undefined) or the SDK is
 * slow/unreachable, this component quietly gives up after a timeout -
 * it never breaks FlowHub. Only non-sensitive identity is ever passed;
 * never extend this with tokens, headers, or other request/session data.
 */
export default function UserbackWidget({ user }: UserbackWidgetProps) {
  const identifiedRef = useRef<string | null>(null)

  useEffect(() => {
    const identity = `${user.id}:${user.username}:${user.email ?? ''}`
    if (identifiedRef.current === identity) return

    let cancelled = false
    let elapsed = 0
    let timer: ReturnType<typeof setTimeout> | null = null

    const tryIdentify = () => {
      if (cancelled) return
      const widget = window.Userback as UserbackInstance | undefined
      if (widget && typeof widget.identify === 'function') {
        try {
          widget.identify(String(user.id), {
            name: user.username,
            email: user.email || undefined,
          })
          identifiedRef.current = identity
        } catch {
          // A misbehaving Userback SDK must never break FlowHub itself.
        }
        return
      }
      elapsed += POLL_INTERVAL_MS
      if (elapsed >= POLL_TIMEOUT_MS) return
      timer = setTimeout(tryIdentify, POLL_INTERVAL_MS)
    }
    tryIdentify()

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [user.id, user.username, user.email])

  return null
}
