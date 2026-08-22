import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { translate } from '../i18n'
import PageShell from '../components/PageShell'
import Alert from '../components/Alert'
import { useOptionalServices } from '../services/ServiceContext'
import { pricingMatrixApi } from '../features/pricingMatrix/api'
import PricingErrorPanel from '../features/pricingMatrix/PricingErrorPanel'
import {
  classifyPricingError,
  formatExactInteger,
  unitStatusPresentation,
  validateUnitDeclaration,
  type PricingErrorState,
} from '../features/pricingMatrix/presentation'
import { isNonEmpty, isSupportedCurrencyUnitPair, IRR_UNITS, SUPPORTED_CURRENCIES } from '../features/pricingMatrix/validation'
import { confirmDiscard, useUnsavedChangesGuard } from '../features/pricingMatrix/useDirtyGuard'
import type { UnitDeclaration, UnitScope } from '../features/pricingMatrix/types'

/**
 * Global scope is intentionally NOT offered: the current UI has no
 * authoritative scope reference for it, and docs/development/contracts/FRONTEND_CONTRACT.md does not
 * document one. See PRICING_UI_CONTRACT.md Open Question PM-8 and
 * docs/archive/handoffs/UI_RESUME.md. Only Source and Channel are supported here.
 */
const EDITABLE_SCOPES: readonly Exclude<UnitScope, 'global'>[] = ['source', 'channel']

interface ScopeOption {
  readonly id: string
  readonly label: string
}

export default function PricingUnitEditor() {
  useTranslation()
  const navigate = useNavigate()
  const services = useOptionalServices()

  const [scope, setScope] = useState<Exclude<UnitScope, 'global'>>('channel')
  const [scopeReference, setScopeReference] = useState('')
  const [sourceOptions, setSourceOptions] = useState<readonly ScopeOption[]>([])
  const [channelOptions, setChannelOptions] = useState<readonly ScopeOption[]>([])
  const [currency, setCurrency] = useState('')
  const [unit, setUnit] = useState('')
  const [connectorConfigVersion, setConnectorConfigVersion] = useState('')

  const [current, setCurrent] = useState<UnitDeclaration | null>(null)
  const [currentError, setCurrentError] = useState<PricingErrorState | null>(null)
  const [loadingCurrent, setLoadingCurrent] = useState(false)

  const [saving, setSaving] = useState(false)
  // A ref, not the `saving` state, guards re-entrancy: two synchronous clicks
  // both run before React flushes the first setSaving(true).
  const submitLock = useRef(false)
  const [submitError, setSubmitError] = useState<PricingErrorState | null>(null)
  const [success, setSuccess] = useState<UnitDeclaration | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const [sources, channels] = await Promise.all([
          services?.commerce ? services.commerce.getSources() : Promise.resolve({ items: [] }),
          services?.commerce ? services.commerce.getChannels() : Promise.resolve({ items: [] }),
        ])
        setSourceOptions(sources.items.map(source => ({ id: source.id, label: source.name || source.id })))
        setChannelOptions(channels.items.map(channel => ({ id: channel.id, label: channel.name || channel.id })))
      } catch {
        // Reference lists are convenience only; leave empty rather than blocking the form.
      }
    })()
  }, [services])

  const options = scope === 'source' ? sourceOptions : channelOptions

  useEffect(() => {
    setScopeReference('')
    setCurrent(null)
    setCurrentError(null)
  }, [scope])

  useEffect(() => {
    if (!scopeReference) {
      setCurrent(null)
      setCurrentError(null)
      return
    }
    let cancelled = false
    setLoadingCurrent(true)
    void (async () => {
      try {
        const declaration = validateUnitDeclaration(await pricingMatrixApi.getUnit(scope, scopeReference))
        if (cancelled) return
        setCurrent(declaration)
        setCurrentError(null)
      } catch (error) {
        if (cancelled) return
        setCurrent(null)
        setCurrentError(classifyPricingError(error))
      } finally {
        if (!cancelled) setLoadingCurrent(false)
      }
    })()
    return () => { cancelled = true }
  }, [scope, scopeReference])

  const dirty = useMemo(
    () => Boolean(scopeReference || currency || unit || connectorConfigVersion),
    [scopeReference, currency, unit, connectorConfigVersion],
  )
  useUnsavedChangesGuard(dirty)

  const unitRequired = currency === 'IRR' && !unit
  const unsupportedPair = Boolean(currency) && Boolean(unit) && !isSupportedCurrencyUnitPair(currency, unit)
  const errors = {
    scopeReference: !isNonEmpty(scopeReference) ? translate('pricing:error.required') : undefined,
    currency: !isNonEmpty(currency) ? translate('pricing:error.required') : undefined,
    unit: unitRequired
      ? translate('pricing:unitEditor.error.unitRequired')
      : unsupportedPair
        ? translate('pricing:unitEditor.error.unsupportedPair')
        : undefined,
    connectorConfigVersion: !isNonEmpty(connectorConfigVersion) ? translate('pricing:error.required') : undefined,
  }
  const hasErrors = Boolean(errors.scopeReference || errors.currency || errors.unit || errors.connectorConfigVersion)
  // Show validation text/aria only once the form is dirty — an untouched
  // fresh form should not read as already invalid. `hasErrors` (submit-
  // disabled) is computed from the real `errors` above and is unaffected.
  const displayErrors = dirty
    ? errors
    : { scopeReference: undefined, currency: undefined, unit: undefined, connectorConfigVersion: undefined }

  function handleCancel() {
    if (!confirmDiscard(dirty)) return
    navigate('/settings/pricing')
  }

  function handleCurrencyChange(nextCurrency: string) {
    setCurrency(nextCurrency)
    // Never infer a unit for IRR — the user must choose explicitly. For a
    // supported non-IRR currency the unit is the same code by definition.
    setUnit(nextCurrency === 'IRR' ? '' : nextCurrency)
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (submitLock.current || hasErrors) return
    submitLock.current = true
    setSaving(true)
    setSubmitError(null)
    try {
      const saved = validateUnitDeclaration(await pricingMatrixApi.putUnit(scope, scopeReference, {
        currency: currency.trim(),
        unit: unit.trim(),
        connector_config_version: connectorConfigVersion.trim(),
      }))
      setSuccess(saved)
    } catch (error) {
      // Entered values are intentionally left in state so the user can fix and resubmit.
      setSubmitError(classifyPricingError(error))
    } finally {
      submitLock.current = false
      setSaving(false)
    }
  }

  if (success) {
    return (
      <PageShell>
        <div className="space-y-4" data-testid="pricing-unit-editor-success">
          <Alert variant="success" title={translate('pricing:unitEditor.success.title')} message={translate('pricing:unitEditor.success.message')} />
          {success.status === 'resolved' && (
            <dl className="fh-card p-4 grid grid-cols-1 gap-x-6 sm:grid-cols-2">
              <div><dt className="fh-text-caption text-wp-muted">{translate('pricing:units.col.currency')}</dt><dd><bdi dir="ltr">{success.canonicalCurrency}</bdi></dd></div>
              <div><dt className="fh-text-caption text-wp-muted">{translate('pricing:units.col.unit')}</dt><dd><bdi dir="ltr">{success.canonicalUnit}</bdi></dd></div>
              <div><dt className="fh-text-caption text-wp-muted">{translate('pricing:units.col.factor')}</dt><dd><bdi dir="ltr">{success.canonicalFactor}</bdi></dd></div>
            </dl>
          )}
          <div className="flex flex-wrap gap-2">
            <button type="button" className="fh-button-primary" onClick={() => navigate('/settings/pricing')}>{translate('pricing:editor.viewInPricingMatrix')}</button>
            <button type="button" className="fh-button-secondary" onClick={() => { setSuccess(null); setCurrency(''); setUnit(''); setConnectorConfigVersion('') }}>{translate('pricing:editor.createAnother')}</button>
          </div>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <form className="space-y-6" data-testid="pricing-unit-editor" onSubmit={event => { void handleSubmit(event) }}>
        <header className="space-y-2">
          <h1 className="text-[20px] font-bold text-text-base">{translate('pricing:unitEditor.title')}</h1>
          <Alert variant="warning" title={translate('pricing:unitEditor.title')} message={translate('pricing:unitEditor.explanation')} />
        </header>

        <div className="fh-card p-4 fh-form-grid md:grid-cols-2">
          <div className="fh-field">
            <label className="fh-label" htmlFor="unit-scope">{translate('pricing:unitEditor.field.scope')}</label>
            <select id="unit-scope" className="fh-select" value={scope} onChange={event => setScope(event.target.value as Exclude<UnitScope, 'global'>)} data-testid="pricing-unit-editor-scope">
              {EDITABLE_SCOPES.map(option => (
                <option key={option} value={option}>{translate(`pricing:unitEditor.field.scope.${option}`)}</option>
              ))}
            </select>
          </div>

          <div className="fh-field">
            <label className="fh-label" htmlFor="unit-scope-reference">
              {translate(scope === 'source' ? 'pricing:unitEditor.field.scopeReferenceSource' : 'pricing:unitEditor.field.scopeReferenceChannel')}
            </label>
            <select
              id="unit-scope-reference"
              className={['fh-select', displayErrors.scopeReference ? 'fh-input-error' : ''].join(' ')}
              value={scopeReference}
              onChange={event => setScopeReference(event.target.value)}
              data-testid="pricing-unit-editor-scope-reference"
              aria-invalid={Boolean(displayErrors.scopeReference)}
              aria-describedby={displayErrors.scopeReference ? 'unit-scope-reference-error' : undefined}
            >
              <option value="">—</option>
              {options.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
            </select>
            {displayErrors.scopeReference && <p id="unit-scope-reference-error" className="fh-field-error">{displayErrors.scopeReference}</p>}
          </div>

          <div className="fh-field">
            <label className="fh-label" htmlFor="unit-currency">{translate('pricing:unitEditor.field.currency')}</label>
            <select id="unit-currency" className={['fh-select', displayErrors.currency ? 'fh-input-error' : ''].join(' ')} value={currency} onChange={event => handleCurrencyChange(event.target.value)} data-testid="pricing-unit-editor-currency" aria-invalid={Boolean(displayErrors.currency)} aria-describedby={displayErrors.currency ? 'unit-currency-error' : undefined}>
              <option value="">—</option>
              {SUPPORTED_CURRENCIES.map(code => <option key={code} value={code} dir="ltr">{code}</option>)}
            </select>
            {displayErrors.currency && <p id="unit-currency-error" className="fh-field-error">{displayErrors.currency}</p>}
          </div>

          <div className="fh-field">
            <label className="fh-label" htmlFor="unit-unit">{translate('pricing:unitEditor.field.unit')}</label>
            {currency === 'IRR' ? (
              <select id="unit-unit" className={['fh-select', displayErrors.unit ? 'fh-input-error' : ''].join(' ')} value={unit} onChange={event => setUnit(event.target.value)} data-testid="pricing-unit-editor-unit" aria-invalid={Boolean(displayErrors.unit)} aria-describedby={displayErrors.unit ? 'unit-unit-error' : undefined}>
                <option value="">{translate('pricing:unitEditor.field.unitChooseIrr')}</option>
                {IRR_UNITS.map(code => <option key={code} value={code} dir="ltr">{code}</option>)}
              </select>
            ) : (
              <input id="unit-unit" className="fh-input" value={unit} disabled dir="ltr" data-testid="pricing-unit-editor-unit" />
            )}
            {displayErrors.unit && <p id="unit-unit-error" className="fh-field-error" data-testid="pricing-unit-editor-unit-error">{displayErrors.unit}</p>}
          </div>

          <div className="fh-field">
            <label className="fh-label" htmlFor="unit-connector-config-version">{translate('pricing:unitEditor.field.connectorConfigVersion')}</label>
            <input id="unit-connector-config-version" className={['fh-input', displayErrors.connectorConfigVersion ? 'fh-input-error' : ''].join(' ')} dir="ltr" value={connectorConfigVersion} onChange={event => setConnectorConfigVersion(event.target.value)} data-testid="pricing-unit-editor-connector-config-version" aria-invalid={Boolean(displayErrors.connectorConfigVersion)} aria-describedby={displayErrors.connectorConfigVersion ? 'unit-connector-config-version-error' : undefined} />
            {displayErrors.connectorConfigVersion && <p id="unit-connector-config-version-error" className="fh-field-error">{displayErrors.connectorConfigVersion}</p>}
          </div>
        </div>

        {loadingCurrent && <p className="fh-text-caption text-wp-muted">{translate('pricing:state.loading')}</p>}
        {currentError && <PricingErrorPanel state={currentError} />}
        {current && (
          <div className="fh-card p-4" data-testid="pricing-unit-editor-current-state">
            <h2 className="fh-text-body font-semibold text-text-base mb-2">{translate('pricing:unitEditor.currentState.title')}</h2>
            <p className="fh-text-body">
              {unitStatusPresentation(current.status).labelKey === 'pricing:unitStatus.resolved'
                ? translate('pricing:unitStatus.resolved')
                : translate('pricing:unitStatus.unresolved')}
              {current.status === 'resolved' && <> — <bdi dir="ltr">{current.canonicalCurrency}/{current.canonicalUnit} ({formatExactInteger(current.canonicalFactor)})</bdi></>}
            </p>
          </div>
        )}

        {submitError && <PricingErrorPanel state={submitError} />}

        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="pricing-unit-editor-actions">
          {dirty && <span className="fh-text-body-sm font-medium text-wp-yellow">{translate('pricing:editor.unsavedChanges')}</span>}
          <div className="ms-auto flex flex-wrap gap-2">
            <button type="button" className="fh-button-secondary" onClick={handleCancel}>{translate('pricing:editor.cancel')}</button>
            <button type="submit" className="fh-button-primary" disabled={saving || hasErrors} data-testid="pricing-unit-editor-submit">
              {saving ? translate('pricing:editor.saving') : translate('pricing:editor.submit')}
            </button>
          </div>
        </div>
      </form>
    </PageShell>
  )
}
