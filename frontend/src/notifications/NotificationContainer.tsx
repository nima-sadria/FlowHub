import { useContext } from 'react'
import { NotificationContext, type NotificationType } from './NotificationProvider'

const TYPE_STYLES: Record<NotificationType, { border: string; icon: string; bg: string }> = {
  info:    { border: 'border-s-[var(--color-accent)]',    icon: 'text-[var(--color-accent)]',    bg: 'bg-bg-card' },
  success: { border: 'border-s-[var(--color-wp-green)]',  icon: 'text-[var(--color-wp-green)]',  bg: 'bg-bg-card' },
  warning: { border: 'border-s-[var(--color-wp-yellow)]', icon: 'text-[var(--color-wp-yellow)]', bg: 'bg-bg-card' },
  error:   { border: 'border-s-[var(--color-wp-red)]',    icon: 'text-[var(--color-wp-red)]',    bg: 'bg-bg-card' },
}

const TYPE_ICONS: Record<NotificationType, JSX.Element> = {
  info: (
    <svg viewBox="0 0 24 24" className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  ),
  success: (
    <svg viewBox="0 0 24 24" className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
  warning: (
    <svg viewBox="0 0 24 24" className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  ),
  error: (
    <svg viewBox="0 0 24 24" className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
    </svg>
  ),
}

export default function NotificationContainer() {
  const ctx = useContext(NotificationContext)
  if (!ctx) return null
  const { notifications, dismiss } = ctx

  return (
    <div
      className="fixed top-4 end-4 z-50 flex flex-col gap-2 w-full max-w-sm pointer-events-none"
      role="region"
      aria-label="Notifications"
    >
      {notifications.map(n => {
        const styles = TYPE_STYLES[n.type]
        return (
          <div
            key={n.id}
            className={[
              'flex items-start gap-3 p-3 rounded-lg border border-border border-s-4 shadow-card pointer-events-auto',
              styles.border,
              styles.bg,
            ].join(' ')}
            role="alert"
          >
            <span className={styles.icon}>{TYPE_ICONS[n.type]}</span>
            <p className="flex-1 text-[13px] text-text-base leading-snug">{n.message}</p>
            <button
              onClick={() => dismiss(n.id)}
              className="flex-shrink-0 text-wp-muted hover:text-text-base transition-colors"
              aria-label="Dismiss"
            >
              <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        )
      })}
    </div>
  )
}
