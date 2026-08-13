import { memo } from 'react'
import Icon from '../../components/Icon'
import { Skeleton } from '../../components/loading/Skeleton'
import { translate } from '../../i18n'
import { inputHint } from '../../utils/inputHint'

interface PricingWorkspaceStartupProps {
  blockedMessage?: string
}

/**
 * Lightweight first paint for Products, shaped like the approved header,
 * toolbar, and table so the real content does not shift on load.
 */
function PricingWorkspaceStartup({ blockedMessage }: PricingWorkspaceStartupProps) {
  return (
    <div className="fh-products-screen" data-products-critical-controls aria-busy="true">
      <div className="fh-page-header">
        <h1 className="fh-page-title truncate">{translate('products:products.products')}</h1>
        <div className="flex items-center gap-2.5">
          <button type="button" className="fh-button-primary fh-button-sm" disabled>{translate('products:products.saveChanges')}</button>
          <button type="button" className="fh-button-secondary fh-button-sm" disabled>{translate('products:products.bulkEdit')}</button>
        </div>
      </div>

      <div className="fh-products-toolbar">
        <div className="fh-products-search">
          <Icon name="search" size="sm" className="fh-products-search-icon" />
          <input className="fh-products-search-input" type="search" disabled aria-label={translate('products:products.searchProducts')} {...inputHint(translate('products:products.searchProducts'))} />
        </div>
        <LoadingSelect label={translate('products:products.allStatuses')} />
        <LoadingSelect label={translate('products:products.allChannels')} />
        <LoadingSelect label={translate('products:products.savedViews')} />
        <button type="button" className="fh-chip" disabled><Icon name="filter" size="sm" /> {translate('products:products.filters')}</button>
      </div>

      <div className="fh-products-card" role={blockedMessage ? undefined : 'status'}>
        {blockedMessage
          ? <div className="fh-alert fh-alert-danger m-3"><Icon name="alert" /><span>{blockedMessage}</span></div>
          : <div className="grid gap-3 p-4">
              <Skeleton className="h-4 w-3/5" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <span className="sr-only">{translate('workspace:sourceCentricWorkspace.loadingSourceProductWorkspace')}</span>
            </div>}
      </div>
    </div>
  )
}

function LoadingSelect({ label }: { label: string }) {
  return <label className="fh-chip-select">
    <span className="sr-only">{label}</span>
    <select disabled aria-label={label}><option>{label}</option></select>
    <Icon name="chevronDown" size="sm" className="fh-chip-caret" />
  </label>
}

export default memo(PricingWorkspaceStartup)
