import { translate } from '../../i18n'
interface Props {
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const SIZE: Record<string, string> = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-8 h-8' }

export default function Spinner({ size = 'md', className = '' }: Props) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      className={[SIZE[size], "animate-spin text-accent", className].join(' ')}
      aria-label={translate('common:spinner.loading')}
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  )
}
