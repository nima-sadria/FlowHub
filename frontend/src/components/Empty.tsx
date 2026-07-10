interface Props {
  icon?: React.ReactNode
  title: string
  description?: string
  action?: { label: string; onClick: () => void }
}

function DefaultIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M8 9h8M8 13h5" />
    </svg>
  )
}

export default function Empty({ icon, title, description, action }: Props) {
  return (
    <div className="fh-empty-state">
      <div className="w-12 h-12 rounded-xl bg-bg-base flex items-center justify-center text-wp-muted border border-border">
        {icon ?? <DefaultIcon />}
      </div>
      <p className="fh-empty-state-title">{title}</p>
      {description && <p className="fh-empty-state-description">{description}</p>}
      {action && (
        <button
          onClick={action.onClick}
          className="fh-button-primary"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
