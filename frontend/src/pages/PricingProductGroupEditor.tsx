import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router'
import { translate } from '../i18n'
import PageShell from '../components/PageShell'
import Alert from '../components/Alert'
import Icon from '../components/Icon'
import Spinner from '../components/loading/Spinner'
import { pricingMatrixApi } from '../features/pricingMatrix/api'
import PricingErrorPanel from '../features/pricingMatrix/PricingErrorPanel'
import { classifyPricingError, type PricingErrorState } from '../features/pricingMatrix/presentation'
import { findDuplicateMemberIndices, isNonEmpty } from '../features/pricingMatrix/validation'
import { confirmDiscard, useUnsavedChangesGuard } from '../features/pricingMatrix/useDirtyGuard'
import type { CreateProductGroupRequest, ProductGroupRevision } from '../features/pricingMatrix/types'

interface FormDraft {
  productGroupId: string
  name: string
  members: string[]
}

function emptyForm(): FormDraft {
  return { productGroupId: '', name: '', members: [''] }
}

function formFromRevision(revision: ProductGroupRevision): FormDraft {
  return {
    productGroupId: revision.productGroupId,
    name: revision.name,
    members: revision.canonicalProductIds.length > 0 ? [...revision.canonicalProductIds] : [''],
  }
}

interface FormErrors {
  name?: string
  members: Record<number, string>
}

function validateForm(form: FormDraft): FormErrors {
  const errors: FormErrors = { members: {} }
  if (!isNonEmpty(form.name)) errors.name = translate('pricing:error.required')
  const duplicates = new Set(findDuplicateMemberIndices(form.members))
  duplicates.forEach(index => { errors.members[index] = translate('pricing:error.duplicateMember') })
  return errors
}

function hasErrors(errors: FormErrors): boolean {
  return Boolean(errors.name) || Object.keys(errors.members).length > 0
}

function toRequest(form: FormDraft): CreateProductGroupRequest {
  return {
    ...(isNonEmpty(form.productGroupId) ? { product_group_id: form.productGroupId.trim() } : {}),
    name: form.name.trim(),
    canonical_product_ids: form.members.map(id => id.trim()).filter(isNonEmpty),
  }
}

export default function PricingProductGroupEditor() {
  useTranslation()
  const navigate = useNavigate()
  const { revisionId } = useParams<{ revisionId?: string }>()
  const isNextRevision = Boolean(revisionId)

  const [prefillState, setPrefillState] = useState<'loading' | 'ready' | 'error'>(revisionId ? 'loading' : 'ready')
  const [prefillError, setPrefillError] = useState<PricingErrorState | null>(null)
  const [form, setForm] = useState<FormDraft>(emptyForm())
  const [baseline, setBaseline] = useState<FormDraft>(emptyForm())
  const [saving, setSaving] = useState(false)
  // A ref, not the `saving` state, guards re-entrancy: two synchronous clicks
  // both run before React flushes the first setSaving(true).
  const submitLock = useRef(false)
  const [submitError, setSubmitError] = useState<PricingErrorState | null>(null)
  const [success, setSuccess] = useState<ProductGroupRevision | null>(null)

  useEffect(() => {
    if (!revisionId) return
    let cancelled = false
    setPrefillState('loading')
    void (async () => {
      try {
        const revision = await pricingMatrixApi.getProductGroup(revisionId)
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

  function updateMember(index: number, value: string) {
    setForm(prev => ({ ...prev, members: prev.members.map((member, i) => (i === index ? value : member)) }))
  }

  function addMember() {
    setForm(prev => ({ ...prev, members: [...prev.members, ''] }))
  }

  function removeMember(index: number) {
    setForm(prev => ({ ...prev, members: prev.members.length > 1 ? prev.members.filter((_, i) => i !== index) : [''] }))
  }

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
      const created = await pricingMatrixApi.createProductGroup(toRequest(form))
      setSuccess(created)
    } catch (error) {
      // Entered members are intentionally left in `form` state so the user can fix and resubmit.
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
        <div className="space-y-3" data-testid="pricing-product-group-editor-prefill-error">
          <Alert variant="warning" title={translate('pricing:editor.loadFailed')} message="" />
          <PricingErrorPanel state={prefillError} />
        </div>
      </PageShell>
    )
  }

  if (success) {
    return (
      <PageShell>
        <div className="space-y-4" data-testid="pricing-product-group-editor-success">
          <Alert
            variant="success"
            title={translate('pricing:productGroupEditor.success.title')}
            message={translate('pricing:productGroupEditor.success.message', {
              revisionNumber: success.revisionNumber,
              name: success.name,
              count: success.canonicalProductIds.length,
            })}
          />
          <div className="flex flex-wrap gap-2">
            <button type="button" className="fh-button-primary" onClick={() => navigate(`/settings/pricing/product-groups/${encodeURIComponent(success.id)}/new-revision`)}>
              {translate('pricing:productGroupEditor.createNextRevisionAction')}
            </button>
            <button type="button" className="fh-button-secondary" onClick={() => { setSuccess(null); setForm(emptyForm()); setBaseline(emptyForm()) }}>
              {translate('pricing:editor.createAnother')}
            </button>
          </div>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <form className="space-y-6" data-testid="pricing-product-group-editor" onSubmit={event => { void handleSubmit(event) }}>
        <header className="space-y-2">
          <h1 className="text-[20px] font-bold text-text-base">
            {translate(isNextRevision ? 'pricing:productGroupEditor.titleNextRevision' : 'pricing:productGroupEditor.title')}
          </h1>
          <Alert
            variant="info"
            title={translate('pricing:editor.immutableTitle')}
            message={translate(isNextRevision ? 'pricing:productGroupEditor.explanationNextRevision' : 'pricing:productGroupEditor.explanationNew')}
          />
        </header>

        <div className="fh-card p-4 fh-form-grid md:grid-cols-2">
          <div className="fh-field">
            <label className="fh-label" htmlFor="group-name">{translate('pricing:productGroupEditor.field.name')}</label>
            <input id="group-name" className={['fh-input', errors.name ? 'fh-input-error' : ''].join(' ')} value={form.name} onChange={event => setForm(prev => ({ ...prev, name: event.target.value }))} aria-invalid={Boolean(errors.name)} aria-describedby={errors.name ? 'group-name-error' : undefined} />
            {errors.name && <p id="group-name-error" className="fh-field-error">{errors.name}</p>}
          </div>

          <div className="fh-field">
            <label className="fh-label" htmlFor="group-id">{translate('pricing:productGroupEditor.field.productGroupId')}</label>
            <input id="group-id" className="fh-input" value={form.productGroupId} disabled={isNextRevision} onChange={event => setForm(prev => ({ ...prev, productGroupId: event.target.value }))} data-testid="pricing-product-group-editor-group-id" />
            <p className="fh-text-caption text-wp-muted mt-1">{translate('pricing:productGroupEditor.field.productGroupIdHelp')}</p>
          </div>
        </div>

        <div className="fh-card p-4 space-y-3">
          <div>
            <h2 className="fh-text-body font-semibold text-text-base">{translate('pricing:productGroupEditor.membersTitle')}</h2>
            <p className="fh-text-caption text-wp-muted">{translate('pricing:productGroupEditor.membersDescription')}</p>
          </div>
          <div className="space-y-2">
            {form.members.map((member, index) => (
              <div key={index} className="flex items-start gap-2">
                <div className="fh-field flex-1">
                  <input
                    className={['fh-input', errors.members[index] ? 'fh-input-error' : ''].join(' ')}
                    dir="ltr"
                    placeholder={translate('pricing:productGroupEditor.memberPlaceholder')}
                    value={member}
                    onChange={event => updateMember(index, event.target.value)}
                    aria-label={translate('pricing:productGroupEditor.memberPlaceholder')}
                    aria-invalid={Boolean(errors.members[index])}
                    aria-describedby={errors.members[index] ? `product-group-member-${index}-error` : undefined}
                    data-testid={`pricing-product-group-editor-member-${index}`}
                  />
                  {errors.members[index] && <p id={`product-group-member-${index}-error`} className="fh-field-error" data-testid={`pricing-product-group-editor-member-${index}-error`}>{errors.members[index]}</p>}
                </div>
                <button type="button" className="fh-button-secondary" onClick={() => removeMember(index)} aria-label={translate('pricing:productGroupEditor.removeMember')}>
                  <Icon name="delete" aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
          <button type="button" className="fh-button-secondary" onClick={addMember} data-testid="pricing-product-group-editor-add-member">
            <Icon name="add" aria-hidden="true" /> {translate('pricing:productGroupEditor.addMember')}
          </button>
        </div>

        {submitError && <PricingErrorPanel state={submitError} />}

        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="pricing-product-group-editor-actions">
          {dirty && <span className="fh-text-body-sm font-medium text-wp-yellow">{translate('pricing:editor.unsavedChanges')}</span>}
          <div className="ms-auto flex flex-wrap gap-2">
            <button type="button" className="fh-button-secondary" onClick={handleCancel}>{translate('pricing:editor.cancel')}</button>
            <button type="submit" className="fh-button-primary" disabled={saving || hasErrors(errors)} data-testid="pricing-product-group-editor-submit">
              {saving ? translate('pricing:editor.saving') : translate('pricing:editor.submit')}
            </button>
          </div>
        </div>
      </form>
    </PageShell>
  )
}
