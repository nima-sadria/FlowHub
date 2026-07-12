import { useContext } from 'react'
import Icon, { type IconName } from '../components/Icon'
import IconButton from '../components/IconButton'
import { NotificationContext, type NotificationType } from './NotificationProvider'

const TYPE_STYLES: Record<NotificationType, { card: string; iconWrap: string; icon: string }> = {
  info: {
    card: 'fh-notification-info',
    iconWrap: 'fh-notification-icon-info',
    icon: 'text-[var(--color-accent)]',
  },
  success: {
    card: 'fh-notification-success',
    iconWrap: 'fh-notification-icon-success',
    icon: 'text-[var(--color-wp-green)]',
  },
  warning: {
    card: 'fh-notification-warning',
    iconWrap: 'fh-notification-icon-warning',
    icon: 'text-[var(--color-wp-yellow)]',
  },
  error: {
    card: 'fh-notification-error',
    iconWrap: 'fh-notification-icon-error',
    icon: 'text-[var(--color-wp-red)]',
  },
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
            className={['fh-notification', styles.card].join(' ')}
            data-notification-type={n.type}
            role="alert"
          >
            <span className={['fh-notification-icon', styles.iconWrap].join(' ')}>
              <Icon name={TYPE_ICONS[n.type]} size="md" className={styles.icon} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="fh-notification-title">{n.title}</p>
              {n.description && (
                <p className="fh-notification-description">{n.description}</p>
              )}
            </div>
            <IconButton
              onClick={() => dismiss(n.id)}
              className="fh-notification-close"
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
