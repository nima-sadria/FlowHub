import { memo } from 'react'
import Icon from '../../components/Icon'
import { translate } from '../../i18n'
import { inputHint } from '../../utils/inputHint'

interface PricingWorkspaceStartupProps {
  blockedMessage?: string
  workspaceName?: string
}

/**
 * Lightweight first paint for Products. Handsontable is intentionally absent
 * so the seller can see and focus the critical controls before the Grid chunk
 * is evaluated and its DOM is measured.
 */
function PricingWorkspaceStartup({ blockedMessage, workspaceName }: PricingWorkspaceStartupProps) {
  return (
    <div className="fh-pricing-workspace" data-products-critical-controls aria-busy="true">
      <header className="fh-pricing-header">
        <div className="min-w-0">
          <h1 className="fh-page-title truncate">{workspaceName || translate('products:products.products')}</h1>
          <p className="fh-text-caption">{translate('workspace:sourceCentricWorkspace.loadingSourceProductWorkspace')}</p>
        </div>
      </header>

      <div className="fh-pricing-sticky">
        <section className="fh-pricing-toolbar" aria-label={translate('workspace:unifiedWorkspace.serverSideWorkspaceFilters')}>
          <input
            className="fh-input h-9 min-w-0"
            type="search"
            disabled
            aria-label={translate('workspace:sourceCentricWorkspace.searchSourceProducts')}
            {...inputHint(translate('workspace:sourceCentricWorkspace.searchSourceProducts'))}
          />
          <button type="button" className="fh-button-secondary fh-button-sm" disabled>
            <Icon name="filter" /> {translate('workspace:densePricing.sortProduct')}
          </button>
          <button type="button" className="fh-button-secondary fh-button-sm" disabled>{translate('workspace:densePricing.undo')}</button>
          <button type="button" className="fh-button-secondary fh-button-sm" disabled>{translate('workspace:densePricing.redo')}</button>
        </section>

        <section className="fh-pricing-summary" aria-label={translate('workspace:sourceCentricWorkspace.workspaceChangeSummary')}>
          {(['changed', 'selected', 'ready', 'warning', 'blocked'] as const).map(key => (
            <span key={key} className={`fh-pricing-counter fh-pricing-counter-${key}`}>
              <strong>0</strong> {translate(`workspace:densePricing.counter.${key}`)}
            </span>
          ))}
        </section>

        <section className="fh-pricing-bulk" aria-label={translate('workspace:densePricing.bulkTransformationToolbar')}>
          <div className="ms-auto flex items-center gap-2">
            <button type="button" className="fh-button-secondary fh-button-sm" disabled>{translate('workspace:unifiedWorkspace.review')}</button>
            <button type="button" className="fh-button-secondary fh-button-sm" disabled>{translate('products:products.dryRun')}</button>
            <button type="button" className="fh-button-primary fh-button-sm" disabled>{translate('workspace:sourceCentricWorkspace.apply')} 0</button>
          </div>
        </section>
      </div>

      <div className="fh-grid-scroll fh-pricing-grid-scroll min-h-[480px]" role={blockedMessage ? undefined : 'status'}>
        {blockedMessage
          ? <div className="fh-alert fh-alert-danger m-3"><Icon name="alert" /><span>{blockedMessage}</span></div>
          : <div className="flex items-center gap-3 p-4">
              <span className="fh-spinner" aria-hidden="true" />
              <span className="sr-only">{translate('workspace:sourceCentricWorkspace.loadingSourceProductWorkspace')}</span>
            </div>}
      </div>
    </div>
  )
}

export default memo(PricingWorkspaceStartup)
