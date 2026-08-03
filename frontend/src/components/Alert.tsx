import type { HTMLAttributes, ReactNode } from 'react'
import Icon, { type IconName } from './Icon'

export type AlertVariant = 'success' | 'warning' | 'error' | 'info'

const VARIANT_CLASS: Record<AlertVariant, string> = {
  success: 'fh-alert-success',
  warning: 'fh-alert-warning',
  error: 'fh-alert-danger',
  info: 'fh-alert-info',
}

const VARIANT_ICON: Record<AlertVariant, IconName> = {
  success: 'success',
  warning: 'warning',
  error: 'error',
  info: 'info',
}

interface AlertProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  linkAriaLabel?: string
  linkHref?: string
  linkText?: ReactNode
  message: ReactNode
  title: ReactNode
  variant?: AlertVariant
}

export default function Alert({
  className = '',
  linkAriaLabel,
  linkHref,
  linkText,
  message,
  role,
  title,
  variant = 'info',
  ...props
}: AlertProps) {
  const semanticRole = role ?? (variant === 'error' ? 'alert' : 'status')

  return (
    <div
      className={['fh-alert', VARIANT_CLASS[variant], className].filter(Boolean).join(' ')}
      role={semanticRole}
      {...props}
    >
      <Icon className="fh-alert-icon" name={VARIANT_ICON[variant]} />
      <div className="fh-alert-content">
        <h4 className="fh-alert-title">{title}</h4>
        <p className="fh-alert-message">{message}</p>
        {linkHref && linkText && (
          <a className="fh-alert-link" href={linkHref} aria-label={linkAriaLabel}>
            {linkText}
          </a>
        )}
      </div>
    </div>
  )
}
