import Badge from './Badge'
import Icon from './Icon'
import {
  diagnosticStatePresentation,
  type DiagnosticEvidenceLike,
  type DiagnosticState,
} from '../features/diagnostics/diagnosticPresentation'

export default function DiagnosticStateBadge({
  evidence,
  state,
  testId,
}: {
  evidence?: DiagnosticEvidenceLike
  state?: DiagnosticState | string | null
  testId?: string
}) {
  const presentation = diagnosticStatePresentation(evidence ?? state)
  return (
    <Badge variant={presentation.variant}>
      <span
        role="status"
        className="inline-flex items-center gap-1.5"
        data-diagnostic-state={presentation.state}
        data-testid={testId}
      >
        <Icon name={presentation.icon} aria-hidden="true" />
        {presentation.label}
      </span>
    </Badge>
  )
}
