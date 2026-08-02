import type { ReactNode } from 'react'

export type SemanticBadgeVariant =
  | 'neutral'
  | 'info'
  | 'success'
  | 'warning'
  | 'pending'
  | 'disabled'
  | 'danger'

// Legacy aliases remain supported while all new status rendering uses the
// seven semantic variants above.
export type BadgeVariant = SemanticBadgeVariant
  | 'primary'
  | 'error'
  | 'valid'

const VARIANT_CLASS: Record<BadgeVariant, string> = {
  neutral: 'fh-badge-neutral',
  primary: 'fh-badge-primary',
  info: 'fh-badge-info',
  success: 'fh-badge-success',
  warning: 'fh-badge-warning',
  pending: 'fh-badge-warning',
  disabled: 'fh-badge-neutral',
  error: 'fh-badge-error',
  danger: 'fh-badge-danger',
  valid: 'fh-badge-valid',
}

const DOT_CLASS: Record<BadgeVariant, string> = {
  neutral: 'fh-status-dot-neutral',
  primary: 'fh-status-dot-info',
  info: 'fh-status-dot-info',
  success: 'fh-status-dot-success',
  warning: 'fh-status-dot-warning',
  pending: 'fh-status-dot-warning',
  disabled: 'fh-status-dot-neutral',
  error: 'fh-status-dot-error',
  danger: 'fh-status-dot-danger',
  valid: 'fh-status-dot-success',
}

interface BadgeProps {
  children: ReactNode
  className?: string
  dot?: boolean
  icon?: ReactNode
  variant?: BadgeVariant
}

export default function Badge({
  children,
  className = '',
  dot = false,
  icon,
  variant = 'neutral',
}: BadgeProps) {
  return (
    <span className={["fh-badge", VARIANT_CLASS[variant], className].filter(Boolean).join(' ')}>
      {dot && <span aria-hidden="true" className={["fh-status-dot", DOT_CLASS[variant]].join(' ')} />}
      {icon}
      {children}
    </span>
  )
}
