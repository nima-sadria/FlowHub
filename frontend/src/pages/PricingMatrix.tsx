import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { translate } from '../i18n'
import { formatDateTime } from '../i18n/format'
import PageShell from '../components/PageShell'
import Alert from '../components/Alert'
import Badge from '../components/Badge'
import Icon from '../components/Icon'
import Empty from '../components/Empty'
import Spinner from '../components/loading/Spinner'
import { pricingMatrixApi } from '../features/pricingMatrix/api'
import {
  channelStatusPresentation,
  classifyPricingError,
  derivePolicyChannelIds,
  formatExactInteger,
  lifecycleEventPresentation,
  rateModeLabelKey,
  roundModeLabelKey,
  roundOrderLabelKey,
  unitStatusPresentation,
  validateChannelHead,
  validateLifecycleEvent,
  validatePolicyRevision,
  validatePolicySummary,
  validateUnitDeclaration,
  type DomainPresentation,
  type PricingErrorState,
} from '../features/pricingMatrix/presentation'
import type {
  ChannelPolicyHead,
  LifecycleEvent,
  PolicyRevision,
  PolicyRuleView,
  PolicySummary,
  UnitDeclaration,
} from '../features/pricingMatrix/types'

type Load<T> =
  | { readonly status: 'loading' }
  | { readonly status: 'ready'; readonly data: T }
  | { readonly status: 'error'; readonly error: PricingErrorState }

interface ChannelState {
  readonly head: Load<ChannelPolicyHead>
  readonly unit: Load<UnitDeclaration>
  readonly events: Load<readonly LifecycleEvent[]>
}

const LOADING = { status: 'loading' } as const

function ready<T>(data: T): Load<T> {
  return { status: 'ready', data }
}

function failed<T>(error: unknown): Load<T> {
  return { status: 'error', error: classifyPricingError(error) }
}

function StatusBadge({ presentation, testId }: { presentation: DomainPresentation; testId?: string }) {
  return (
    <Badge variant={presentation.variant}>
      <span className="inline-flex items-center gap-1.5" data-testid={testId}>
        <Icon name={presentation.icon} aria-hidden="true" />
        {translate(presentation.labelKey)}
      </span>
    </Badge>
  )
}

function LoadingBlock({ testId }: { testId: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-[13px] text-wp-muted" role="status" data-testid={testId}>
      <Spinner />
      <span>{translate('pricing:state.loading')}</span>
    </div>
  )
}

const ERROR_PRESENTATION: Record<PricingErrorState['kind'], { testId: string; variant: 'warning' | 'error'; titleKey: string; messageKey: string }> = {
  permission_denied: { testId: 'pricing-permission-denied', variant: 'warning', titleKey: 'pricing:state.permissionDenied.title', messageKey: 'pricing:state.permissionDenied.message' },
  validation_error: { testId: 'pricing-validation-error', variant: 'warning', titleKey: 'pricing:state.validationError.title', messageKey: 'pricing:state.validationError.message' },
  contract_mismatch: { testId: 'pricing-contract-mismatch', variant: 'error', titleKey: 'pricing:state.contractMismatch.title', messageKey: 'pricing:state.contractMismatch.message' },
  unavailable: { testId: 'pricing-unavailable', variant: 'error', titleKey: 'pricing:state.unavailable.title', messageKey: 'pricing:state.unavailable.message' },
}

function PricingErrorPanel({ state, onRetry }: { state: PricingErrorState; onRetry?: () => void }) {
  const preset = ERROR_PRESENTATION[state.kind]
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
      {onRetry && state.kind !== 'permission_denied' && (
        <button type="button" className="fh-button-secondary" onClick={onRetry}>
          {translate('pricing:state.retry')}
        </button>
      )}
    </div>
  )
}

function DefinitionRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 py-1.5">
      <dt className="fh-text-caption font-medium text-wp-muted">{label}</dt>
      <dd className="fh-text-body text-text-base break-words">
        <bdi dir="ltr">{children}</bdi>
      </dd>
    </div>
  )
}

function ruleTargetLabel(rule: PolicyRuleView): string {
  if (rule.productRef) return translate('pricing:rules.target.product', { ref: rule.productRef })
  if (rule.productGroupRevisionId) return translate('pricing:rules.target.group', { ref: rule.productGroupRevisionId })
  return translate('pricing:rules.target.default')
}

function PolicyRulesTable({ rules }: { rules: readonly PolicyRuleView[] }) {
  if (rules.length === 0) {
    return <p className="fh-text-body text-wp-muted">{translate('pricing:policyDetail.noRules')}</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="fh-table w-full" data-testid="pricing-rules-table">
        <thead>
          <tr>
            <th scope="col">{translate('pricing:rules.col.channel')}</th>
            <th scope="col">{translate('pricing:rules.col.target')}</th>
            <th scope="col">{translate('pricing:rules.col.rateMode')}</th>
            <th scope="col">{translate('pricing:rules.col.rateValue')}</th>
            <th scope="col">{translate('pricing:rules.col.roundMode')}</th>
            <th scope="col">{translate('pricing:rules.col.roundStep')}</th>
            <th scope="col">{translate('pricing:rules.col.surcharge')}</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule, index) => (
            <tr key={`${rule.channelId}:${rule.productRef ?? rule.productGroupRevisionId ?? 'default'}:${index}`} data-testid={`pricing-rule-row-${index}`}>
              <td><bdi dir="ltr">{rule.channelId}</bdi></td>
              <td><bdi dir="ltr">{ruleTargetLabel(rule)}</bdi></td>
              <td>{translate(rateModeLabelKey(rule.rateMode))}</td>
              <td><bdi dir="ltr">{formatExactInteger(rule.rateValue)}</bdi></td>
              <td>{translate(roundModeLabelKey(rule.roundMode))}</td>
              <td><bdi dir="ltr">{formatExactInteger(rule.roundStepMinor)}</bdi></td>
              <td><bdi dir="ltr">{formatExactInteger(rule.surchargeMinor)}</bdi></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PolicyDetail({ policy }: { policy: PolicyRevision }) {
  return (
    <div className="fh-card p-4 space-y-4" data-testid="pricing-policy-detail">
      <div>
        <h3 className="fh-text-body font-semibold text-text-base">{policy.name}</h3>
        <p className="fh-text-caption text-wp-muted">
          {translate('pricing:policyDetail.title')} · <bdi dir="ltr">#{policy.revisionNumber}</bdi>
        </p>
      </div>
      <dl className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
        <DefinitionRow label={translate('pricing:policies.col.currency')}>{policy.computationCurrency}</DefinitionRow>
        <DefinitionRow label={translate('pricing:policies.col.roundOrder')}>{translate(roundOrderLabelKey(policy.roundOrder))}</DefinitionRow>
        <DefinitionRow label={translate('pricing:policyDetail.basisStrategy')}>{policy.basisStrategy || '—'}</DefinitionRow>
        <DefinitionRow label={translate('pricing:policyDetail.quoteWindow')}>{policy.maxQuoteAgeDays}</DefinitionRow>
        <DefinitionRow label={translate('pricing:policyDetail.minQuoteCount')}>{policy.minQuoteCount}</DefinitionRow>
        <DefinitionRow label={translate('pricing:policyDetail.timezone')}>{policy.evaluationTimezone || '—'}</DefinitionRow>
        <DefinitionRow label={translate('pricing:policyDetail.policyId')}>{policy.policyId}</DefinitionRow>
        <DefinitionRow label={translate('pricing:policyDetail.checksum')}>{policy.checksum || '—'}</DefinitionRow>
      </dl>
      <div>
        <h4 className="fh-text-body font-semibold text-text-base mb-2">{translate('pricing:policyDetail.rulesTitle')}</h4>
        <PolicyRulesTable rules={policy.rules} />
      </div>
    </div>
  )
}

function noneOr(value: string | null): ReactNode {
  return value ? <bdi dir="ltr">{value}</bdi> : translate('pricing:channels.value.none')
}

function dateOrNone(value: string): ReactNode {
  return value ? <bdi dir="ltr">{formatDateTime(value)}</bdi> : translate('pricing:channels.value.none')
}

function LifecycleEvents({ channelId, events }: { channelId: string; events: readonly LifecycleEvent[] }) {
  return (
    <details className="mt-3">
      <summary className="cursor-pointer fh-text-caption font-medium text-accent">
        {translate('pricing:channels.events.show')} ({events.length})
      </summary>
      <div className="mt-2" data-testid={`pricing-events-${channelId}`}>
        {events.length === 0 ? (
          <p className="fh-text-caption text-wp-muted">{translate('pricing:channels.events.empty')}</p>
        ) : (
          <ul className="space-y-2">
            {events.map(event => (
              <li key={event.id} className="rounded-[var(--fh-radius-md)] border border-border p-2">
                <div className="flex items-center justify-between gap-2">
                  <StatusBadge presentation={lifecycleEventPresentation(event.eventKind)} testId={`pricing-event-kind-${event.id}`} />
                  <span className="fh-text-caption text-wp-muted">{dateOrNone(event.occurredAt)}</span>
                </div>
                {event.reason && (
                  <p className="mt-1 fh-text-caption text-text-base">
                    {translate('pricing:channels.events.reason')}: {event.reason}
                  </p>
                )}
                {event.actorUserId && (
                  <p className="fh-text-caption text-wp-muted">
                    {translate('pricing:channels.events.actor')}: <bdi dir="ltr">{event.actorUserId}</bdi>
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  )
}

function ChannelLifecycleCard({ channelId, state }: { channelId: string; state: ChannelState }) {
  return (
    <article className="fh-card p-4" data-testid={`pricing-channel-card-${channelId}`}>
      <header className="mb-3 flex items-center justify-between gap-2">
        <h3 className="fh-text-body font-semibold text-text-base"><bdi dir="ltr">{channelId}</bdi></h3>
        {state.head.status === 'ready' && (
          <StatusBadge presentation={channelStatusPresentation(state.head.data.status)} testId={`pricing-channel-status-${channelId}`} />
        )}
      </header>

      {state.head.status === 'loading' && <LoadingBlock testId={`pricing-channel-loading-${channelId}`} />}
      {state.head.status === 'error' && <PricingErrorPanel state={state.head.error} />}
      {state.head.status === 'ready' && (
        <dl className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
          <DefinitionRow label={translate('pricing:channels.head.headVersion')}>{formatExactInteger(state.head.data.headVersion)}</DefinitionRow>
          <DefinitionRow label={translate('pricing:channels.head.updated')}>{dateOrNone(state.head.data.updatedAt)}</DefinitionRow>
          <DefinitionRow label={translate('pricing:channels.head.policyRevision')}>{noneOr(state.head.data.policyRevisionId)}</DefinitionRow>
          <DefinitionRow label={translate('pricing:channels.head.channelConfig')}>{noneOr(state.head.data.channelConfigRevisionId)}</DefinitionRow>
          <DefinitionRow label={translate('pricing:channels.head.effectiveActivation')}>{noneOr(state.head.data.effectiveActivationId)}</DefinitionRow>
        </dl>
      )}

      {state.events.status === 'ready' && <LifecycleEvents channelId={channelId} events={state.events.data} />}
      {state.events.status === 'error' && <div className="mt-3"><PricingErrorPanel state={state.events.error} /></div>}
    </article>
  )
}

function UnitsTable({ channelIds, channels }: { channelIds: readonly string[]; channels: Record<string, ChannelState> }) {
  const anyUnresolved = channelIds.some(id => {
    const unit = channels[id]?.unit
    return unit?.status === 'ready' && unit.data.status === 'unresolved'
  })
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="fh-table w-full" data-testid="pricing-units-table">
          <thead>
            <tr>
              <th scope="col">{translate('pricing:units.col.channel')}</th>
              <th scope="col">{translate('pricing:units.col.status')}</th>
              <th scope="col">{translate('pricing:units.col.currency')}</th>
              <th scope="col">{translate('pricing:units.col.unit')}</th>
              <th scope="col">{translate('pricing:units.col.factor')}</th>
            </tr>
          </thead>
          <tbody>
            {channelIds.map(id => {
              const unit = channels[id]?.unit
              return (
                <tr key={id} data-testid={`pricing-unit-row-${id}`}>
                  <td><bdi dir="ltr">{id}</bdi></td>
                  <td>
                    {unit?.status === 'ready'
                      ? <StatusBadge presentation={unitStatusPresentation(unit.data.status)} testId={`pricing-unit-status-${id}`} />
                      : unit?.status === 'error'
                        ? <Badge variant="error">{translate(ERROR_PRESENTATION[unit.error.kind].titleKey)}</Badge>
                        : <span className="fh-text-caption text-wp-muted">…</span>}
                  </td>
                  <td>{unit?.status === 'ready' && unit.data.status === 'resolved' ? <bdi dir="ltr">{unit.data.canonicalCurrency}</bdi> : '—'}</td>
                  <td>{unit?.status === 'ready' && unit.data.status === 'resolved' ? <bdi dir="ltr">{unit.data.canonicalUnit}</bdi> : '—'}</td>
                  <td>{unit?.status === 'ready' && unit.data.status === 'resolved' ? <bdi dir="ltr">{unit.data.canonicalFactor}</bdi> : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {anyUnresolved && (
        <Alert
          data-testid="pricing-units-unresolved"
          variant="warning"
          title={translate('pricing:unitStatus.unresolved')}
          message={translate('pricing:units.unresolvedHelp')}
        />
      )}
    </div>
  )
}

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-[15px] font-semibold text-text-base">{title}</h2>
        {description && <p className="fh-text-caption text-wp-muted">{description}</p>}
      </div>
      {children}
    </section>
  )
}

export default function PricingMatrix() {
  useTranslation()
  const [policies, setPolicies] = useState<Load<readonly PolicySummary[]>>(LOADING)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Load<PolicyRevision> | null>(null)
  const [channelIds, setChannelIds] = useState<readonly string[]>([])
  const [channels, setChannels] = useState<Record<string, ChannelState>>({})
  const selectionToken = useRef(0)

  const loadPolicies = useCallback(async () => {
    setPolicies(LOADING)
    try {
      const response = await pricingMatrixApi.listPolicies()
      if (!Array.isArray(response.items)) throw new Error('policies_not_array')
      setPolicies(ready(response.items.map(validatePolicySummary)))
    } catch (error) {
      setPolicies(failed(error))
    }
  }, [])

  useEffect(() => { void loadPolicies() }, [loadPolicies])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      setChannelIds([])
      setChannels({})
      return
    }
    const token = ++selectionToken.current
    const isCurrent = () => token === selectionToken.current

    setDetail(LOADING)
    setChannelIds([])
    setChannels({})

    void (async () => {
      let policy: PolicyRevision
      try {
        policy = validatePolicyRevision(await pricingMatrixApi.getPolicy(selectedId))
      } catch (error) {
        if (isCurrent()) setDetail(failed(error))
        return
      }
      if (!isCurrent()) return
      setDetail(ready(policy))

      const ids = derivePolicyChannelIds(policy)
      setChannelIds(ids)
      setChannels(Object.fromEntries(ids.map(id => [id, { head: LOADING, unit: LOADING, events: LOADING } as ChannelState])))

      await Promise.all(ids.map(async id => {
        const [head, unit, events] = await Promise.all([
          pricingMatrixApi.getChannelHead(id).then(validateChannelHead).then(ready<ChannelPolicyHead>, (e: unknown) => failed<ChannelPolicyHead>(e)),
          pricingMatrixApi.getUnit('channel', id).then(validateUnitDeclaration).then(ready<UnitDeclaration>, (e: unknown) => failed<UnitDeclaration>(e)),
          pricingMatrixApi.listChannelLifecycleEvents(id)
            .then(response => {
              if (!Array.isArray(response.items)) throw new Error('events_not_array')
              return response.items.map(validateLifecycleEvent)
            })
            .then(ready<readonly LifecycleEvent[]>, (e: unknown) => failed<readonly LifecycleEvent[]>(e)),
        ])
        if (!isCurrent()) return
        setChannels(prev => ({ ...prev, [id]: { head, unit, events } }))
      }))
    })()
  }, [selectedId])

  return (
    <PageShell>
      <div className="space-y-6" data-testid="pricing-page">
        <header className="space-y-2">
          <h1 className="text-[20px] font-bold text-text-base">{translate('pricing:title')}</h1>
          <p className="fh-text-body text-wp-muted">{translate('pricing:subtitle')}</p>
          <Alert variant="info" title={translate('pricing:title')} message={translate('pricing:readOnlyNote')} />
        </header>

        <Section title={translate('pricing:policies.title')} description={translate('pricing:policies.description')}>
          {policies.status === 'loading' && <LoadingBlock testId="pricing-loading" />}
          {policies.status === 'error' && <PricingErrorPanel state={policies.error} onRetry={() => void loadPolicies()} />}
          {policies.status === 'ready' && policies.data.length === 0 && (
            <div data-testid="pricing-empty"><Empty title={translate('pricing:policies.empty')} /></div>
          )}
          {policies.status === 'ready' && policies.data.length > 0 && (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ul className="space-y-2" data-testid="pricing-policies-list">
                {policies.data.map(policy => {
                  const active = policy.id === selectedId
                  return (
                    <li key={policy.id}>
                      <button
                        type="button"
                        aria-pressed={active}
                        data-testid={`pricing-policy-row-${policy.id}`}
                        onClick={() => setSelectedId(active ? null : policy.id)}
                        className={[
                          'fh-card w-full p-3 text-start transition-colors',
                          active ? 'ring-2 ring-accent' : 'hover:bg-[color:var(--fh-ui-surface-muted)]',
                        ].join(' ')}
                      >
                        <span className="flex items-center justify-between gap-2">
                          <span className="fh-text-body font-medium text-text-base">{policy.name}</span>
                          <Badge variant="neutral"><bdi dir="ltr">#{policy.revisionNumber}</bdi></Badge>
                        </span>
                        <span className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 fh-text-caption text-wp-muted">
                          <span><bdi dir="ltr">{policy.computationCurrency}</bdi></span>
                          <span>{translate(roundOrderLabelKey(policy.roundOrder))}</span>
                          {policy.createdAt && <span>{formatDateTime(policy.createdAt)}</span>}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
              <div>
                {!selectedId && <p className="fh-text-body text-wp-muted">{translate('pricing:policies.selectHint')}</p>}
                {detail?.status === 'loading' && <LoadingBlock testId="pricing-detail-loading" />}
                {detail?.status === 'error' && <PricingErrorPanel state={detail.error} />}
                {detail?.status === 'ready' && <PolicyDetail policy={detail.data} />}
              </div>
            </div>
          )}
        </Section>

        <Section title={translate('pricing:channels.title')} description={translate('pricing:channels.description')}>
          {!selectedId && <p className="fh-text-body text-wp-muted">{translate('pricing:channels.selectHint')}</p>}
          {selectedId && detail?.status === 'ready' && channelIds.length === 0 && (
            <Empty title={translate('pricing:channels.empty')} />
          )}
          {selectedId && channelIds.length > 0 && (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {channelIds.map(id => (
                <ChannelLifecycleCard key={id} channelId={id} state={channels[id] ?? { head: LOADING, unit: LOADING, events: LOADING }} />
              ))}
            </div>
          )}
        </Section>

        <Section title={translate('pricing:units.title')} description={translate('pricing:units.description')}>
          {!selectedId && <p className="fh-text-body text-wp-muted">{translate('pricing:units.selectHint')}</p>}
          {selectedId && detail?.status === 'ready' && channelIds.length === 0 && (
            <Empty title={translate('pricing:units.empty')} />
          )}
          {selectedId && channelIds.length > 0 && <UnitsTable channelIds={channelIds} channels={channels} />}
        </Section>
      </div>
    </PageShell>
  )
}
