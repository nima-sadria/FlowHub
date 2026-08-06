import { translate } from '../../i18n'
import Alert from '../../components/Alert'
import { PRICING_ERROR_PRESENTATION, type PricingErrorState } from './presentation'

/**
 * Shared, distinct-by-kind error presentation for every Pricing Matrix
 * surface (read-only and editors). Never collapses auth/validation/contract/
 * transport faults into one generic message.
 */
export default function PricingErrorPanel({ state, onRetry }: { state: PricingErrorState; onRetry?: () => void }) {
  const preset = PRICING_ERROR_PRESENTATION[state.kind]
  const message = state.kind === 'unavailable' && typeof state.status === 'number'
    ? translate('pricing:state.unavailable.messageWithStatus', { status: state.status })
    : translate(preset.messageKey)
  return (
    <div className="space-y-3">
      <Alert
        data-testid={preset.testId}
        variant={preset.variant}
        title={translate(preset.titleKey)}
        message={message}
      />
      {onRetry && preset.retryable && (
        <button type="button" className="fh-button-secondary" onClick={onRetry}>
          {translate('pricing:state.retry')}
        </button>
      )}
    </div>
  )
}
