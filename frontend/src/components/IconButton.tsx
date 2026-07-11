import type { ButtonHTMLAttributes, ReactNode } from 'react'

type IconButtonSize = 'sm' | 'md'
type IconButtonTone = 'default' | 'danger'

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  children: ReactNode
  label: string
  size?: IconButtonSize
  tone?: IconButtonTone
}

export default function IconButton({
  children,
  className = '',
  label,
  size = 'md',
  tone = 'default',
  type = 'button',
  ...props
}: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={props.title ?? label}
      className={[
        'fh-icon-button',
        size === 'sm' ? 'fh-icon-button-sm' : '',
        tone === 'danger' ? 'fh-icon-button-danger' : '',
        className,
      ].filter(Boolean).join(' ')}
      {...props}
    >
      {children}
    </button>
  )
}
