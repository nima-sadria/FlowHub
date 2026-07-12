import { useContext } from 'react'
import Icon, { type IconName } from '../components/Icon'
import IconButton from '../components/IconButton'
import { NotificationContext, type NotificationType } from './NotificationProvider'

const TYPE_STYLES: Record<NotificationType, { border: string; icon: string; bg: string }> = {
  info: { border: 'border-s-[var(--color-accent)]', icon: 'text-[var(--color-accent)]', bg: 'bg-bg-card' },
  success: { border: 'border-s-[var(--color-wp-green)]', icon: 'text-[var(--color-wp-green)]', bg: 'bg-bg-card' },
  warning: { border: 'border-s-[var(--color-wp-yellow)]', icon: 'text-[var(--color-wp-yellow)]', bg: 'bg-bg-card' },
  error: { border: 'border-s-[var(--color-wp-red)]', icon: 'text-[var(--color-wp-red)]', bg: 'bg-bg-card' },
}

const TYPE_ICONS: Record<NotificationType, IconName> = {
  info: 'info',
  success: 'success',
  warning: 'warning',
  error: 'error',
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
            <Icon name={TYPE_ICONS[n.type]} className={`mt-0.5 flex-shrink-0 ${styles.icon}`} />
            <div className="min-w-0 flex-1">
              <p className="fh-text-body font-semibold leading-snug text-text-base">{n.title}</p>
              {n.description && (
                <p className="fh-text-caption mt-1 leading-snug text-wp-muted">{n.description}</p>
              )}
            </div>
            <IconButton
              onClick={() => dismiss(n.id)}
              className="flex-shrink-0 border-transparent bg-transparent shadow-none"
              label="Close notification"
              size="sm"
            >
              <Icon name="close" />
            </IconButton>
          </div>
        )
      })}
    </div>
  )
}
