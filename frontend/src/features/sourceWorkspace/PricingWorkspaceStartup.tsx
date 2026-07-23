import { memo } from 'react'
import Icon from '../../components/Icon'
import { translate } from '../../i18n'
import { inputHint } from '../../utils/inputHint'

interface PricingWorkspaceStartupProps {
  blockedMessage?: string
  workspaceName?: string
}

/**
 * Lightweight first paint for Products, shaped like the approved header,
 * toolbar, and table so the real content does not shift on load.
 */
function PricingWorkspaceStartup({ blockedMessage, workspaceName }: PricingWorkspaceStartupProps) {
  return (
    <div className="fh-products-screen" data-products-critical-controls aria-busy="true">
      <div className="fh-page-header">
        <h1 className="fh-page-title truncate">{workspaceName || translate('products:products.products')}</h1>
        <div className="flex items-center gap-2.5">
          <button type="button" className="fh-button-primary fh-button-sm" disabled>{translate('products:products.saveChanges')}</button>
          <button type="button" className="fh-button-secondary fh-button-sm" disabled>{translate('products:products.bulkEdit')}</button>
        </div>
      </div>

      <div className="fh-products-toolbar" aria-hidden="true">
        <div className="fh-products-search">
          <Icon name="search" size="sm" className="fh-products-search-icon" />
          <input className="fh-products-search-input" type="search" disabled {...inputHint(translate('products:products.searchProducts'))} />
        </div>
        <span className="fh-chip-select fh-chip-select-skeleton" />
        <span className="fh-chip-select fh-chip-select-skeleton" />
        <span className="fh-chip-select fh-chip-select-skeleton" />
      </div>

      <div className="fh-products-card" role={blockedMessage ? undefined : 'status'}>
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
