interface Props {
  icon?: React.ReactNode
  title: string
  description?: string
  action?: { label: string; onClick: () => void }
}

export default function Empty({ icon, title, description, action }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      {icon && (
        <div className="w-12 h-12 rounded-full bg-bg-base flex items-center justify-center mb-4 text-wp-muted">
          {icon}
        </div>
      )}
      <p className="text-[15px] font-semibold text-text-base mb-1">{title}</p>
      {description && <p className="text-[13px] text-wp-muted max-w-sm mb-4">{description}</p>}
      {action && (
        <button
          onClick={action.onClick}
          className="px-4 py-2 rounded-lg bg-accent text-white text-[13px] font-medium hover:bg-accent-hover transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
