import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router'
import { translate } from '../i18n'
import PageShell from '../components/PageShell'
import Alert from '../components/Alert'
import Icon from '../components/Icon'
import Spinner from '../components/loading/Spinner'
import { useOptionalServices } from '../services/ServiceContext'
import { pricingMatrixApi } from '../features/pricingMatrix/api'
import PricingErrorPanel from '../features/pricingMatrix/PricingErrorPanel'
import {
  classifyPricingError,
  rateModeLabelKey,
  roundModeLabelKey,
  roundOrderLabelKey,
  validatePolicyRevision,
  type PricingErrorState,
} from '../features/pricingMatrix/presentation'
import {
  findDuplicateRuleScopeIndices,
  isNonEmpty,
  isValidExactIntegerInput,
  validateRuleTarget,
} from '../features/pricingMatrix/validation'
import { confirmDiscard, useUnsavedChangesGuard } from '../features/pricingMatrix/useDirtyGuard'
import type { CreatePolicyRequest, PolicyRevision, PolicyRuleView, RateMode, RoundMode, RoundOrder } from '../features/pricingMatrix/types'

const RATE_MODES: readonly RateMode[] = ['percent_bp', 'multiplier_ppm']
const ROUND_MODES: readonly RoundMode[] = ['floor', 'ceil', 'nearest']
const ROUND_ORDERS: readonly RoundOrder[] = ['round_then_surcharge', 'surcharge_then_round']

type TargetKind = 'none' | 'product' | 'group'

interface RuleDraft {
  readonly key: string
  channelId: string
  targetKind: TargetKind
  productRef: string
  productGroupRevisionId: string
  rateMode: RateMode
  rateValue: string
  fixedAddendMinor: string
  roundMode: RoundMode
  roundStepMinor: string
  surchargeMinor: string
}

let ruleKeyCounter = 0
function nextRuleKey(): string {
  ruleKeyCounter += 1
  return `rule-${ruleKeyCounter}`
}

function emptyRule(): RuleDraft {
  return {
    key: nextRuleKey(),
    channelId: '',
    targetKind: 'none',
    productRef: '',
    productGroupRevisionId: '',
    rateMode: 'percent_bp',
    rateValue: '',
    fixedAddendMinor: '0',
    roundMode: 'floor',
    roundStepMinor: '100',
    surchargeMinor: '0',
  }
}

/** Builds an editable draft from a `PolicyRevision` response rule (PM-6 camelCase). */
function ruleFromView(rule: PolicyRuleView): RuleDraft {
  return {
    key: nextRuleKey(),
    channelId: rule.channelId ?? '',
    targetKind: rule.productRef ? 'product' : rule.productGroupRevisionId ? 'group' : 'none',
    productRef: rule.productRef ?? '',
    productGroupRevisionId: rule.productGroupRevisionId ?? '',
    rateMode: rule.rateMode,
    rateValue: String(rule.rateValue ?? ''),
    fixedAddendMinor: String(rule.fixedAddendMinor ?? '0'),
    roundMode: rule.roundMode,
    roundStepMinor: String(rule.roundStepMinor ?? '0'),
    surchargeMinor: String(rule.surchargeMinor ?? '0'),
  }
}

interface FormDraft {
  policyId: string
  name: string
  computationCurrency: string
  roundOrder: RoundOrder
  maxQuoteAgeDays: string
  minQuoteCount: string
  evaluationTimezone: string
  rules: RuleDraft[]
}

function emptyForm(): FormDraft {
  return {
    policyId: '',
    name: '',
    computationCurrency: '',
    roundOrder: 'surcharge_then_round',
    maxQuoteAgeDays: '30',
    minQuoteCount: '1',
    evaluationTimezone: 'UTC',
    rules: [],
  }
}

function formFromRevision(revision: PolicyRevision): FormDraft {
  return {
    policyId: revision.policyId,
    name: revision.name,
    computationCurrency: revision.computationCurrency,
    roundOrder: revision.roundOrder,
    maxQuoteAgeDays: String(revision.maxQuoteAgeDays),
    minQuoteCount: String(revision.minQuoteCount),
    evaluationTimezone: revision.evaluationTimezone,
    rules: revision.rules.map(ruleFromView),
  }
}

interface RuleErrors {
  channelId?: string
  rateValue?: string
  fixedAddendMinor?: string
  roundStepMinor?: string
  surchargeMinor?: string
  target?: string
  duplicate?: string
}

interface FormErrors {
  name?: string
  computationCurrency?: string
  maxQuoteAgeDays?: string
  minQuoteCount?: string
  evaluationTimezone?: string
  rules: Record<string, RuleErrors>
}

function validateForm(form: FormDraft): FormErrors {
  const errors: FormErrors = { rules: {} }
  if (!isNonEmpty(form.name)) errors.name = translate('pricing:error.required')
  if (!isNonEmpty(form.computationCurrency)) errors.computationCurrency = translate('pricing:error.required')
  if (!isValidExactIntegerInput(form.maxQuoteAgeDays)) errors.maxQuoteAgeDays = translate('pricing:error.invalidInteger')
  if (!isValidExactIntegerInput(form.minQuoteCount)) errors.minQuoteCount = translate('pricing:error.invalidInteger')
  if (!isNonEmpty(form.evaluationTimezone)) errors.evaluationTimezone = translate('pricing:error.required')

  const duplicateIndices = new Set(findDuplicateRuleScopeIndices(form.rules.map(rule => ({
    channel_id: rule.channelId,
    product_ref: rule.targetKind === 'product' ? rule.productRef : null,
    product_group_revision_id: rule.targetKind === 'group' ? rule.productGroupRevisionId : null,
  }))))

  form.rules.forEach((rule, index) => {
    const ruleErrors: RuleErrors = {}
    if (!isNonEmpty(rule.channelId)) ruleErrors.channelId = translate('pricing:error.required')
    if (!isValidExactIntegerInput(rule.rateValue)) ruleErrors.rateValue = translate('pricing:error.invalidInteger')
    if (!isValidExactIntegerInput(rule.fixedAddendMinor)) ruleErrors.fixedAddendMinor = translate('pricing:error.invalidInteger')
    if (!isValidExactIntegerInput(rule.roundStepMinor)) ruleErrors.roundStepMinor = translate('pricing:error.invalidInteger')
    if (!isValidExactIntegerInput(rule.surchargeMinor)) ruleErrors.surchargeMinor = translate('pricing:error.invalidInteger')
    const targetError = validateRuleTarget({
      product_ref: rule.targetKind === 'product' ? rule.productRef : null,
      product_group_revision_id: rule.targetKind === 'group' ? rule.productGroupRevisionId : null,
    })
    if (targetError) ruleErrors.target = translate('pricing:error.bothTargetsSet')
    if (duplicateIndices.has(index)) ruleErrors.duplicate = translate('pricing:error.duplicateScope')
    if (Object.keys(ruleErrors).length > 0) errors.rules[rule.key] = ruleErrors
  })

  return errors
}

function hasErrors(errors: FormErrors): boolean {
  return Boolean(errors.name || errors.computationCurrency || errors.maxQuoteAgeDays || errors.minQuoteCount || errors.evaluationTimezone)
    || Object.keys(errors.rules).length > 0
}

function toRequest(form: FormDraft): CreatePolicyRequest {
  return {
    ...(isNonEmpty(form.policyId) ? { policy_id: form.policyId.trim() } : {}),
    name: form.name.trim(),
    computation_currency: form.computationCurrency.trim(),
    round_order: form.roundOrder,
    max_quote_age_days: Number(form.maxQuoteAgeDays),
    min_quote_count: Number(form.minQuoteCount),
    evaluation_timezone: form.evaluationTimezone.trim(),
    rules: form.rules.map(rule => ({
      channel_id: rule.channelId.trim(),
      product_ref: rule.targetKind === 'product' ? rule.productRef.trim() : null,
      product_group_revision_id: rule.targetKind === 'group' ? rule.productGroupRevisionId.trim() : null,
      rate_mode: rule.rateMode,
      rate_value: rule.rateValue.trim(),
      fixed_addend_minor: rule.fixedAddendMinor.trim(),
      round_mode: rule.roundMode,
      round_step_minor: rule.roundStepMinor.trim(),
      surcharge_minor: rule.surchargeMinor.trim(),
      guards: {},
    })),
  }
}

export default function PricingPolicyEditor() {
  useTranslation()
  const navigate = useNavigate()
  const { revisionId } = useParams<{ revisionId?: string }>()
  const isNextRevision = Boolean(revisionId)
  const services = useOptionalServices()

  const [prefillState, setPrefillState] = useState<'idle' | 'loading' | 'ready' | 'error'>(revisionId ? 'loading' : 'ready')
  const [prefillError, setPrefillError] = useState<PricingErrorState | null>(null)
  const [form, setForm] = useState<FormDraft>(emptyForm())
  const [baseline, setBaseline] = useState<FormDraft>(emptyForm())
  const [channelOptions, setChannelOptions] = useState<readonly string[]>([])
  const [productGroupOptions, setProductGroupOptions] = useState<readonly { id: string; label: string }[]>([])
  const [saving, setSaving] = useState(false)
  // A ref, not the `saving` state, guards re-entrancy: two synchronous clicks
  // (e.g. double-click) both run before React flushes the first setSaving(true).
  const submitLock = useRef(false)
  const [submitError, setSubmitError] = useState<PricingErrorState | null>(null)
  const [success, setSuccess] = useState<PolicyRevision | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const [channels, groups] = await Promise.all([
          services?.commerce ? services.commerce.getChannels() : Promise.resolve({ items: [] }),
          pricingMatrixApi.listProductGroups(),
        ])
        setChannelOptions(channels.items.map(channel => channel.id))
        if (!Array.isArray(groups.items)) throw new Error('groups_not_array')
        setProductGroupOptions(groups.items.map(group => ({ id: group.id, label: `${group.name} (#${group.revisionNumber})` })))
      } catch {
        // Reference lists are convenience only; leave them empty rather than blocking the form.
      }
    })()
  }, [services])

  useEffect(() => {
    if (!revisionId) return
    let cancelled = false
    setPrefillState('loading')
    void (async () => {
      try {
        const revision = validatePolicyRevision(await pricingMatrixApi.getPolicy(revisionId))
        if (cancelled) return
        const next = formFromRevision(revision)
        setForm(next)
        setBaseline(next)
        setPrefillState('ready')
      } catch (error) {
        if (cancelled) return
        setPrefillError(classifyPricingError(error))
        setPrefillState('error')
      }
    })()
    return () => { cancelled = true }
  }, [revisionId])

  const dirty = useMemo(() => JSON.stringify(form) !== JSON.stringify(baseline), [form, baseline])
  useUnsavedChangesGuard(dirty)

  const errors = useMemo(() => validateForm(form), [form])
  // Validation errors are computed from the very first render (an empty form
  // is "invalid"), but showing them before the user has touched anything
  // reads as the form being broken. Gate the visible text/aria on `dirty` —
  // the real `errors` (and the submit-disabled state) are unaffected.
  const displayErrors = dirty ? errors : { rules: {} }

  const updateField = useCallback(<K extends keyof FormDraft>(key: K, value: FormDraft[K]) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }, [])

  const updateRule = useCallback((key: string, patch: Partial<RuleDraft>) => {
    setForm(prev => ({ ...prev, rules: prev.rules.map(rule => (rule.key === key ? { ...rule, ...patch } : rule)) }))
  }, [])

  const addRule = useCallback(() => {
    setForm(prev => ({ ...prev, rules: [...prev.rules, emptyRule()] }))
  }, [])

  const removeRule = useCallback((key: string) => {
    setForm(prev => ({ ...prev, rules: prev.rules.filter(rule => rule.key !== key) }))
  }, [])

  function handleCancel() {
    if (!confirmDiscard(dirty)) return
    navigate('/settings/pricing')
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (submitLock.current) return
    if (hasErrors(errors)) return
    submitLock.current = true
    setSaving(true)
    setSubmitError(null)
    try {
      const created = validatePolicyRevision(await pricingMatrixApi.createPolicy(toRequest(form)))
      setSuccess(created)
    } catch (error) {
      // Entered data is intentionally left in `form` state so the user can fix and resubmit.
      setSubmitError(classifyPricingError(error))
    } finally {
      submitLock.current = false
      setSaving(false)
    }
  }

  if (revisionId && prefillState === 'loading') {
    return (
      <PageShell>
        <div className="flex items-center gap-2 py-6 text-[13px] text-wp-muted" role="status">
          <Spinner /> <span>{translate('pricing:state.loading')}</span>
        </div>
      </PageShell>
    )
  }

  if (revisionId && prefillState === 'error' && prefillError) {
    return (
      <PageShell>
        <div className="space-y-3" data-testid="pricing-policy-editor-prefill-error">
          <Alert variant="warning" title={translate('pricing:editor.loadFailed')} message="" />
          <PricingErrorPanel state={prefillError} />
        </div>
      </PageShell>
    )
  }

  if (success) {
    return (
      <PageShell>
        <div className="space-y-4" data-testid="pricing-policy-editor-success">
          <Alert
            variant="success"
            title={translate('pricing:policyEditor.success.title')}
            message={translate('pricing:policyEditor.success.message', { revisionNumber: success.revisionNumber, name: success.name })}
          />
          <div className="flex flex-wrap gap-2">
            <button type="button" className="fh-button-primary" onClick={() => navigate(`/settings/pricing?revision=${encodeURIComponent(success.id)}`)}>
              {translate('pricing:editor.viewInPricingMatrix')}
            </button>
            <button type="button" className="fh-button-secondary" onClick={() => navigate(`/settings/pricing/policies/${encodeURIComponent(success.id)}/new-revision`)}>
              {translate('pricing:policyEditor.createNextRevisionAction')}
            </button>
          </div>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <form className="space-y-6" data-testid="pricing-policy-editor" onSubmit={event => { void handleSubmit(event) }}>
        <header className="space-y-2">
          <h1 className="text-[20px] font-bold text-text-base">
            {translate(isNextRevision ? 'pricing:policyEditor.titleNextRevision' : 'pricing:policyEditor.title')}
          </h1>
          <Alert
            variant="info"
            title={translate('pricing:editor.immutableTitle')}
            message={translate(isNextRevision ? 'pricing:policyEditor.explanationNextRevision' : 'pricing:policyEditor.explanationNew')}
          />
        </header>

        <div className="fh-card p-4 fh-form-grid md:grid-cols-2">
          <div className="fh-field">
            <label className="fh-label" htmlFor="policy-name">{translate('pricing:policyEditor.field.name')}</label>
            <input id="policy-name" className={['fh-input', displayErrors.name ? 'fh-input-error' : ''].join(' ')} value={form.name} onChange={event => updateField('name', event.target.value)} aria-invalid={Boolean(displayErrors.name)} aria-describedby={displayErrors.name ? 'policy-name-error' : undefined} />
            {displayErrors.name && <p id="policy-name-error" className="fh-field-error">{displayErrors.name}</p>}
          </div>

          <div className="fh-field">
            <label className="fh-label" htmlFor="policy-id">{translate('pricing:policyEditor.field.policyId')}</label>
            <input
              id="policy-id"
              className="fh-input"
              value={form.policyId}
              disabled={isNextRevision}
              onChange={event => updateField('policyId', event.target.value)}
              data-testid="pricing-policy-editor-policy-id"
            />
            <p className="fh-text-caption text-wp-muted mt-1">{translate('pricing:policyEditor.field.policyIdHelp')}</p>
          </div>

          <div className="fh-field">
            <label className="fh-label" htmlFor="policy-currency">{translate('pricing:policyEditor.field.currency')}</label>
            <input id="policy-currency" className={['fh-input', displayErrors.computationCurrency ? 'fh-input-error' : ''].join(' ')} value={form.computationCurrency} onChange={event => updateField('computationCurrency', event.target.value.toUpperCase())} aria-invalid={Boolean(displayErrors.computationCurrency)} aria-describedby={displayErrors.computationCurrency ? 'policy-currency-error' : undefined} />
            {displayErrors.computationCurrency && <p id="policy-currency-error" className="fh-field-error">{displayErrors.computationCurrency}</p>}
          </div>

          <div className="fh-field">
            <label className="fh-label" htmlFor="policy-round-order">{translate('pricing:policyEditor.field.roundOrder')}</label>
            <select id="policy-round-order" className="fh-select" value={form.roundOrder} onChange={event => updateField('roundOrder', event.target.value as RoundOrder)}>
              {ROUND_ORDERS.map(order => <option key={order} value={order}>{translate(roundOrderLabelKey(order))}</option>)}
            </select>
          </div>

          <div className="fh-field">
            <label className="fh-label" htmlFor="policy-quote-age">{translate('pricing:policyEditor.field.maxQuoteAgeDays')}</label>
            <input id="policy-quote-age" className={['fh-input', displayErrors.maxQuoteAgeDays ? 'fh-input-error' : ''].join(' ')} inputMode="numeric" value={form.maxQuoteAgeDays} onChange={event => updateField('maxQuoteAgeDays', event.target.value)} aria-invalid={Boolean(displayErrors.maxQuoteAgeDays)} aria-describedby={displayErrors.maxQuoteAgeDays ? 'policy-quote-age-error' : undefined} />
            {displayErrors.maxQuoteAgeDays && <p id="policy-quote-age-error" className="fh-field-error">{displayErrors.maxQuoteAgeDays}</p>}
          </div>

          <div className="fh-field">
            <label className="fh-label" htmlFor="policy-min-quotes">{translate('pricing:policyEditor.field.minQuoteCount')}</label>
            <input id="policy-min-quotes" className={['fh-input', displayErrors.minQuoteCount ? 'fh-input-error' : ''].join(' ')} inputMode="numeric" value={form.minQuoteCount} onChange={event => updateField('minQuoteCount', event.target.value)} aria-invalid={Boolean(displayErrors.minQuoteCount)} aria-describedby={displayErrors.minQuoteCount ? 'policy-min-quotes-error' : undefined} />
            {displayErrors.minQuoteCount && <p id="policy-min-quotes-error" className="fh-field-error">{displayErrors.minQuoteCount}</p>}
          </div>

          <div className="fh-field">
            <label className="fh-label" htmlFor="policy-timezone">{translate('pricing:policyEditor.field.timezone')}</label>
            <input id="policy-timezone" className={['fh-input', displayErrors.evaluationTimezone ? 'fh-input-error' : ''].join(' ')} value={form.evaluationTimezone} onChange={event => updateField('evaluationTimezone', event.target.value)} aria-invalid={Boolean(displayErrors.evaluationTimezone)} aria-describedby={displayErrors.evaluationTimezone ? 'policy-timezone-error' : undefined} />
            {displayErrors.evaluationTimezone && <p id="policy-timezone-error" className="fh-field-error">{displayErrors.evaluationTimezone}</p>}
          </div>
        </div>

        <div className="fh-card p-4 space-y-4">
          <div>
            <h2 className="fh-text-body font-semibold text-text-base">{translate('pricing:policyEditor.rulesTitle')}</h2>
            <p className="fh-text-caption text-wp-muted">{translate('pricing:policyEditor.rulesDescription')}</p>
          </div>

          {channelOptions.length === 0 && (
            <Alert variant="warning" title={translate('pricing:policyEditor.noChannelsAvailable')} message="" />
          )}

          <div className="space-y-4">
            {form.rules.map((rule, index) => {
              const ruleErrors = displayErrors.rules[rule.key]
              return (
                <div key={rule.key} className="rounded-[var(--fh-radius-md)] border border-border p-3" data-testid={`pricing-policy-editor-rule-${index}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="fh-form-grid flex-1 md:grid-cols-2">
                      <div className="fh-field">
                        <label className="fh-label" htmlFor={`rule-${rule.key}-channel`}>{translate('pricing:policyEditor.rule.channel')}</label>
                        <select
                          id={`rule-${rule.key}-channel`}
                          className={['fh-select', ruleErrors?.channelId ? 'fh-input-error' : ''].join(' ')}
                          value={rule.channelId}
                          onChange={event => updateRule(rule.key, { channelId: event.target.value })}
                          data-testid={`pricing-policy-editor-rule-${index}-channel`}
                          aria-invalid={Boolean(ruleErrors?.channelId || ruleErrors?.duplicate)}
                          aria-describedby={[
                            ruleErrors?.channelId ? `rule-${rule.key}-channel-error` : null,
                            ruleErrors?.duplicate ? `rule-${rule.key}-duplicate-error` : null,
                          ].filter(Boolean).join(' ') || undefined}
                        >
                          <option value="">—</option>
                          {channelOptions.map(id => <option key={id} value={id}>{id}</option>)}
                        </select>
                        {ruleErrors?.channelId && <p id={`rule-${rule.key}-channel-error`} className="fh-field-error">{ruleErrors.channelId}</p>}
                      </div>

                      <div className="fh-field">
                        <label className="fh-label" htmlFor={`rule-${rule.key}-target`}>{translate('pricing:policyEditor.rule.targetKind')}</label>
                        <select
                          id={`rule-${rule.key}-target`}
                          className="fh-select"
                          value={rule.targetKind}
                          onChange={event => updateRule(rule.key, { targetKind: event.target.value as TargetKind })}
                          data-testid={`pricing-policy-editor-rule-${index}-target-kind`}
                          aria-invalid={Boolean(ruleErrors?.target)}
                          aria-describedby={ruleErrors?.target ? `rule-${rule.key}-target-error` : undefined}
                        >
                          <option value="none">{translate('pricing:policyEditor.rule.targetKind.none')}</option>
                          <option value="product">{translate('pricing:policyEditor.rule.targetKind.product')}</option>
                          <option value="group">{translate('pricing:policyEditor.rule.targetKind.group')}</option>
                        </select>
                      </div>

                      {rule.targetKind === 'product' && (
                        <div className="fh-field">
                          <label className="fh-label" htmlFor={`rule-${rule.key}-product-ref`}>{translate('pricing:policyEditor.rule.productRef')}</label>
                          <input id={`rule-${rule.key}-product-ref`} className="fh-input" value={rule.productRef} onChange={event => updateRule(rule.key, { productRef: event.target.value })} data-testid={`pricing-policy-editor-rule-${index}-product-ref`} />
                        </div>
                      )}

                      {rule.targetKind === 'group' && (
                        <div className="fh-field">
                          <label className="fh-label" htmlFor={`rule-${rule.key}-group`}>{translate('pricing:policyEditor.rule.productGroupRevisionId')}</label>
                          <select id={`rule-${rule.key}-group`} className="fh-select" value={rule.productGroupRevisionId} onChange={event => updateRule(rule.key, { productGroupRevisionId: event.target.value })} data-testid={`pricing-policy-editor-rule-${index}-group`}>
                            <option value="">—</option>
                            {productGroupOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
                          </select>
                          <p className="fh-text-caption text-wp-muted mt-1">{translate('pricing:policyEditor.rule.productGroupRevisionHelp')}</p>
                        </div>
                      )}

                      <div className="fh-field">
                        <label className="fh-label" htmlFor={`rule-${rule.key}-rate-mode`}>{translate('pricing:policyEditor.rule.rateMode')}</label>
                        <select id={`rule-${rule.key}-rate-mode`} className="fh-select" value={rule.rateMode} onChange={event => updateRule(rule.key, { rateMode: event.target.value as RateMode })}>
                          {RATE_MODES.map(mode => <option key={mode} value={mode}>{translate(rateModeLabelKey(mode))}</option>)}
                        </select>
                      </div>

                      <div className="fh-field">
                        <label className="fh-label" htmlFor={`rule-${rule.key}-rate-value`}>{translate('pricing:policyEditor.rule.rateValue')}</label>
                        <input id={`rule-${rule.key}-rate-value`} className={['fh-input', ruleErrors?.rateValue ? 'fh-input-error' : ''].join(' ')} inputMode="numeric" dir="ltr" value={rule.rateValue} onChange={event => updateRule(rule.key, { rateValue: event.target.value })} data-testid={`pricing-policy-editor-rule-${index}-rate-value`} aria-invalid={Boolean(ruleErrors?.rateValue)} aria-describedby={ruleErrors?.rateValue ? `rule-${rule.key}-rate-value-error` : undefined} />
                        {ruleErrors?.rateValue && <p id={`rule-${rule.key}-rate-value-error`} className="fh-field-error">{ruleErrors.rateValue}</p>}
                      </div>

                      <div className="fh-field">
                        <label className="fh-label" htmlFor={`rule-${rule.key}-fixed-addend`}>{translate('pricing:policyEditor.rule.fixedAddendMinor')}</label>
                        <input id={`rule-${rule.key}-fixed-addend`} className={['fh-input', ruleErrors?.fixedAddendMinor ? 'fh-input-error' : ''].join(' ')} inputMode="numeric" dir="ltr" value={rule.fixedAddendMinor} onChange={event => updateRule(rule.key, { fixedAddendMinor: event.target.value })} aria-invalid={Boolean(ruleErrors?.fixedAddendMinor)} aria-describedby={ruleErrors?.fixedAddendMinor ? `rule-${rule.key}-fixed-addend-error` : undefined} />
                        {ruleErrors?.fixedAddendMinor && <p id={`rule-${rule.key}-fixed-addend-error`} className="fh-field-error">{ruleErrors.fixedAddendMinor}</p>}
                      </div>

                      <div className="fh-field">
                        <label className="fh-label" htmlFor={`rule-${rule.key}-round-mode`}>{translate('pricing:policyEditor.rule.roundMode')}</label>
                        <select id={`rule-${rule.key}-round-mode`} className="fh-select" value={rule.roundMode} onChange={event => updateRule(rule.key, { roundMode: event.target.value as RoundMode })}>
                          {ROUND_MODES.map(mode => <option key={mode} value={mode}>{translate(roundModeLabelKey(mode))}</option>)}
                        </select>
                      </div>

                      <div className="fh-field">
                        <label className="fh-label" htmlFor={`rule-${rule.key}-round-step`}>{translate('pricing:policyEditor.rule.roundStepMinor')}</label>
                        <input id={`rule-${rule.key}-round-step`} className={['fh-input', ruleErrors?.roundStepMinor ? 'fh-input-error' : ''].join(' ')} inputMode="numeric" dir="ltr" value={rule.roundStepMinor} onChange={event => updateRule(rule.key, { roundStepMinor: event.target.value })} aria-invalid={Boolean(ruleErrors?.roundStepMinor)} aria-describedby={ruleErrors?.roundStepMinor ? `rule-${rule.key}-round-step-error` : undefined} />
                        {ruleErrors?.roundStepMinor && <p id={`rule-${rule.key}-round-step-error`} className="fh-field-error">{ruleErrors.roundStepMinor}</p>}
                      </div>

                      <div className="fh-field">
                        <label className="fh-label" htmlFor={`rule-${rule.key}-surcharge`}>{translate('pricing:policyEditor.rule.surchargeMinor')}</label>
                        <input id={`rule-${rule.key}-surcharge`} className={['fh-input', ruleErrors?.surchargeMinor ? 'fh-input-error' : ''].join(' ')} inputMode="numeric" dir="ltr" value={rule.surchargeMinor} onChange={event => updateRule(rule.key, { surchargeMinor: event.target.value })} aria-invalid={Boolean(ruleErrors?.surchargeMinor)} aria-describedby={ruleErrors?.surchargeMinor ? `rule-${rule.key}-surcharge-error` : undefined} />
                        {ruleErrors?.surchargeMinor && <p id={`rule-${rule.key}-surcharge-error`} className="fh-field-error">{ruleErrors.surchargeMinor}</p>}
                      </div>
                    </div>
                    <button type="button" className="fh-button-secondary" onClick={() => removeRule(rule.key)} aria-label={translate('pricing:policyEditor.removeRule')}>
                      <Icon name="delete" aria-hidden="true" />
                    </button>
                  </div>
                  {ruleErrors?.target && <p id={`rule-${rule.key}-target-error`} className="fh-field-error mt-2" data-testid={`pricing-policy-editor-rule-${index}-target-error`}>{ruleErrors.target}</p>}
                  {ruleErrors?.duplicate && <p id={`rule-${rule.key}-duplicate-error`} className="fh-field-error mt-2" data-testid={`pricing-policy-editor-rule-${index}-duplicate-error`}>{ruleErrors.duplicate}</p>}
                </div>
              )
            })}
          </div>

          <button type="button" className="fh-button-secondary" onClick={addRule} data-testid="pricing-policy-editor-add-rule">
            <Icon name="add" aria-hidden="true" /> {translate('pricing:policyEditor.addRule')}
          </button>
        </div>

        {submitError && <PricingErrorPanel state={submitError} />}

        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="pricing-policy-editor-actions">
          {dirty && <span className="fh-text-body-sm font-medium text-wp-yellow">{translate('pricing:editor.unsavedChanges')}</span>}
          <div className="ms-auto flex flex-wrap gap-2">
            <button type="button" className="fh-button-secondary" onClick={handleCancel}>{translate('pricing:editor.cancel')}</button>
            <button type="submit" className="fh-button-primary" disabled={saving || hasErrors(errors)} data-testid="pricing-policy-editor-submit">
              {saving ? translate('pricing:editor.saving') : translate('pricing:editor.submit')}
            </button>
          </div>
        </div>
      </form>
    </PageShell>
  )
}
