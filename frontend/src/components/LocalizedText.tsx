import type { ReactNode } from 'react'

const PERSIAN_SCRIPT_RE = /[\u0600-\u06FF]/

export function containsPersianScript(value: string): boolean {
  return PERSIAN_SCRIPT_RE.test(value)
}

interface LocalizedTextProps {
  children?: ReactNode
  className?: string
  fallback?: ReactNode
  text?: ReactNode
}

export default function LocalizedText({
  children,
  className = '',
  fallback = '-',
  text,
}: LocalizedTextProps) {
  const content = text ?? children ?? fallback
  const plain = typeof content === 'string' || typeof content === 'number'
    ? String(content)
    : ''
  const hasPersian = containsPersianScript(plain)
  const classes = [className, hasPersian ? 'fh-persian-text' : ''].filter(Boolean).join(' ')

  return (
    <span
      className={classes || undefined}
      dir={hasPersian ? 'auto' : undefined}
      lang={hasPersian ? 'fa' : undefined}
    >
      {content}
    </span>
  )
}
