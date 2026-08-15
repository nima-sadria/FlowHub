import { useEffect, useRef } from 'react'
import type { AuthUser } from '../../auth'

export interface UserbackWidgetProps {
  /** The current FlowHub session. Callers only reach this component once authenticated. */
  user: AuthUser
  /** VITE_USERBACK_ACCESS_TOKEN. Omit/empty disables the widget entirely. */
  accessToken?: string
}

/**
 * Isolated Userback feedback/debug widget integration.
 *
 * Rendered once from AppShell, which only mounts for an authenticated
 * session, so Userback never loads on /login or /setup. To disable Userback,
 * remove this component from AppShell or leave VITE_USERBACK_ACCESS_TOKEN
 * unset - nothing else in FlowHub depends on it. Only non-sensitive identity
 * (id, username, email) is ever passed to the SDK; never extend this with
 * tokens, headers, or other request/session data.
 */
export default function UserbackWidget({ user, accessToken }: UserbackWidgetProps) {
  const destroyRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    if (!accessToken) return
    let cancelled = false

    import('@userback/widget')
      .then(({ default: initUserback }) => initUserback(accessToken, {
        user_data: {
          id: String(user.id),
          info: {
            name: user.username,
            email: user.email || undefined,
          },
        },
      }))
      .then(widget => {
        if (cancelled) {
          widget.destroy()
          return
        }
        destroyRef.current = () => widget.destroy()
      })
      .catch(() => {
        // A misconfigured, blocked, or unreachable Userback SDK must never
        // break FlowHub itself.
      })

    return () => {
      cancelled = true
      destroyRef.current?.()
      destroyRef.current = null
    }
  }, [accessToken, user.id, user.username, user.email])

  return null
}
