import type { ReactNode } from 'react'

interface PageShellProps {
  children: ReactNode
  className?: string
}

// All FlowHub primary pages must use the shared page container.
// Do not create page-specific narrow containers unless explicitly approved by Owner.
export default function PageShell({ children, className = '' }: PageShellProps) {
  return (
    <div className={['fh-page', className].filter(Boolean).join(' ')}>
      {children}
    </div>
  )
}
