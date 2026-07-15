import { useId, useMemo, useState } from 'react'
import Icon from '../../components/Icon'
import { ResourceOptionGroups, ResourceSectionList, ResourceStateBadge } from '../../components/ResourceOrdering'
import { prepareResourceCollection, sourceChannelSignals } from '../../features/resourceOrdering/resourceOrdering'
import type { FieldMapping, ReferenceType, SourceChannel, SourceWorksheetRule } from '../../features/sourceWorkspace/types'
import { translate } from '../../i18n'

export const SOURCE_FIELD_DEFINITIONS = [
  ['name', 'sources:sourceConfiguration.sourceProductName', true],
  ['source_key', 'sources:sourceConfiguration.sourceProductKey', false],
  ['category', 'sources:sourceConfiguration.category', false],
  ['brand', 'sources:sourceConfiguration.brand', false],
  ['cost', 'sources:sourceConfiguration.cost', false],
] as const

export const CHANNEL_FIELD_DEFINITIONS = [
  ['external_id', 'sources:sourceConfiguration.productIdentifier'],
  ['price', 'common:field.price'],
  ['stock', 'common:field.stock'],
  ['status', 'common:field.status'],
] as const

export const DEFAULT_SOURCE_VALUE_POLICY: Record<string, string> = {
  blank: 'no_change', x: 'unavailable', dash: 'no_change', zero: 'explicit_zero',
  formula: 'calculated_value', invalid: 'blocked',
}

const POLICY_OPTIONS: Record<string, Array<[string, string]>> = {
  blank: [['no_change', 'sources:sourceConfiguration.noTargetChange'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  x: [['unavailable', 'sources:sourceConfiguration.noListingUnavailable'], ['no_change', 'sources:sourceConfiguration.noTargetChange'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  dash: [['no_change', 'sources:sourceConfiguration.noTargetChange'], ['unavailable', 'common:status.unavailable'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  zero: [['explicit_zero', 'sources:sourceConfiguration.explicitZero'], ['no_change', 'sources:sourceConfiguration.noTargetChange'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  formula: [['calculated_value', 'sources:sourceConfiguration.useEvaluatedResult'], ['blocked', 'sources:sourceConfiguration.blockedIssue']],
  invalid: [['blocked', 'sources:sourceConfiguration.blockedIssue']],
}

export const emptyFieldMapping = (field: string, required = false): FieldMapping => ({ field, referenceType: 'disabled', referenceValue: null, required })
export const emptySourceFields = (): FieldMapping[] => SOURCE_FIELD_DEFINITIONS.map(([field, _label, required]) => emptyFieldMapping(field, required))
export const emptyChannelFields = (): FieldMapping[] => CHANNEL_FIELD_DEFINITIONS.map(([field]) => emptyFieldMapping(field))

function fieldDisplayName(field: string): string {
  const sourceDefinition = SOURCE_FIELD_DEFINITIONS.find(([candidate]) => candidate === field)
  const channelDefinition = CHANNEL_FIELD_DEFINITIONS.find(([candidate]) => candidate === field)
  const translationKey = sourceDefinition?.[1] ?? channelDefinition?.[1]
  return translationKey ? translate(translationKey) : field
}

function sourceFieldMissing(mapping: FieldMapping): boolean {
  return Boolean((mapping.required || mapping.field === 'name') && (mapping.referenceType === 'disabled' || !mapping.referenceValue?.trim()))
}

export function createWorksheetRule(name: string): SourceWorksheetRule {
  return { worksheetName: name, enabled: true, dataStartRow: 2, valuePolicy: { ...DEFAULT_SOURCE_VALUE_POLICY }, sourceFields: emptySourceFields(), channels: [] }
}

function ColumnSelector({ mapping, disabled, allowInternalColumnId, invalid = false, describedBy, onChange }: { mapping: FieldMapping; disabled: boolean; allowInternalColumnId: boolean; invalid?: boolean; describedBy?: string; onChange: (mapping: FieldMapping) => void }) {
  return <div className="grid min-w-0 gap-2 sm:grid-cols-[180px_minmax(0,1fr)]">
    <label className="grid gap-1"><span className="fh-text-caption">{translate('sources:sourceConfiguration.mappingMethod')}</span><select className="fh-input" disabled={disabled} value={mapping.referenceType} aria-label={translate('sources:sourceConfiguration.referenceType', { field: fieldDisplayName(mapping.field) })} aria-invalid={invalid || undefined} aria-describedby={invalid ? describedBy : undefined} onChange={event => onChange({ ...mapping, referenceType: event.target.value as ReferenceType, referenceValue: event.target.value === 'disabled' ? null : mapping.referenceValue })}><option value="disabled">{translate('sources:sourceConfiguration.disabled')}</option><option value="column_letter">{translate('sources:sourceConfiguration.columnLetter')}</option><option value="header_name">{translate('sources:sourceConfiguration.exactHeader')}</option>{allowInternalColumnId && <option value="column_id">{translate('sources:sourceConfiguration.internalColumnId')}</option>}</select></label>
    <label className="grid gap-1"><span className="fh-text-caption">{translate('sources:sourceConfiguration.column')}</span><input className="fh-input" disabled={disabled || mapping.referenceType === 'disabled'} value={mapping.referenceValue ?? ''} aria-label={translate('sources:sourceConfiguration.columnReference', { field: fieldDisplayName(mapping.field) })} aria-invalid={invalid || undefined} aria-describedby={invalid ? describedBy : undefined} title={mapping.referenceType === 'column_letter' ? translate('sources:sourceConfiguration.exampleColumn') : translate('sources:sourceConfiguration.exactColumnReference')} onChange={event => onChange({ ...mapping, referenceValue: event.target.value })} /></label>
  </div>
}

function validationIssues(fields: FieldMapping[], enabled: boolean): string[] {
  if (!enabled) return []
  const issues: string[] = []
  const identifier = fields.find(item => item.field === 'external_id')
  if (!identifier || identifier.referenceType === 'disabled' || !identifier.referenceValue?.trim()) issues.push(translate('sources:sourceConfiguration.productIdentifierRequired'))
  const refs = new Map<string, string>()
  for (const field of fields) {
    if (field.referenceType === 'disabled' || !field.referenceValue?.trim()) continue
    const key = `${field.referenceType}:${field.referenceValue.trim().toLocaleLowerCase()}`
    const prior = refs.get(key)
    if (prior) issues.push(translate('sources:sourceConfiguration.conflictingColumnMapping', { first: fieldDisplayName(prior), second: fieldDisplayName(field.field) }))
    else refs.set(key, field.field)
  }
  return issues
}

export default function WorksheetRuleEditor({ rule, channels, sourceKind, onChange, onRemove }: { rule: SourceWorksheetRule; channels: SourceChannel[]; sourceKind: 'flowhub_sheet' | 'imported_sheet' | 'external'; onChange: (rule: SourceWorksheetRule) => void; onRemove: () => void }) {
  const [copyFrom, setCopyFrom] = useState<Record<string, string>>({})
  const editorId = useId().replace(/:/g, '')
  const sourceErrorId = `${editorId}-required-product-column`
  const channelResources = useMemo(
    () => prepareResourceCollection(channels, sourceChannelSignals),
    [channels],
  )
  const missingSourceFields = rule.enabled ? rule.sourceFields.filter(sourceFieldMissing) : []
  const updateSource = (field: string, mapping: FieldMapping) => onChange({ ...rule, sourceFields: rule.sourceFields.map(item => item.field === field ? mapping : item) })
  const configured = (channelId: string) => rule.channels.find(item => item.channelId === channelId) ?? { channelId, worksheetName: rule.worksheetName, enabled: false, fields: emptyChannelFields() }
  const updateChannel = (channelId: string, next: ReturnType<typeof configured>) => onChange({ ...rule, channels: [...rule.channels.filter(item => item.channelId !== channelId), next] })
  const updateChannelField = (channelId: string, field: string, mapping: FieldMapping) => {
    const channel = configured(channelId)
    updateChannel(channelId, { ...channel, fields: channel.fields.map(item => item.field === field ? mapping : item) })
  }
  const copyColumns = (channelId: string) => {
    const source = rule.channels.find(item => item.channelId === copyFrom[channelId])
    if (!source) return
    const target = configured(channelId)
    updateChannel(channelId, { ...target, fields: source.fields.map(item => ({ ...item })) })
  }
  return <details className="rounded-xl border border-border bg-bg-base" open={rule.enabled}>
    <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 p-4"><Icon name="file" /><strong className="text-text-base">{rule.worksheetName}</strong><span className={`fh-badge ${rule.enabled ? 'fh-badge-success' : 'fh-badge-neutral'}`}>{rule.enabled ? translate('sources:sourceConfiguration.worksheetIncluded') : translate('sources:sourceConfiguration.worksheetIgnored')}</span><label className="fh-inline-check ms-auto" onClick={event => event.stopPropagation()}><input type="checkbox" checked={rule.enabled} onChange={event => onChange({ ...rule, enabled: event.target.checked })} />{rule.enabled ? translate('sources:sourceConfiguration.enabled') : translate('sources:sourceConfiguration.disabled')}</label></summary>
    <div className="border-t border-border p-4 space-y-5">
      <div className="flex flex-wrap items-end gap-3"><label className="fh-field-label min-w-[220px]">{translate('sources:sourceConfiguration.dataStartsAtRow')}<input className="fh-input mt-1" type="number" min="1" disabled={!rule.enabled} value={rule.dataStartRow} onChange={event => onChange({ ...rule, dataStartRow: Number(event.target.value) })} /></label><button className="fh-button-danger fh-button-sm" type="button" onClick={onRemove}><Icon name="delete" /> {translate('sources:sourceConfiguration.removeWorksheetRule')}</button></div>
      <section>
        <h3 className="fh-form-section-title">{translate('sources:sourceConfiguration.productColumns')}</h3>
        <p className="fh-form-section-description">{translate('sources:sourceConfiguration.productColumnsHelp')}</p>
        <div className="mt-3 grid gap-3">
          {SOURCE_FIELD_DEFINITIONS.map(([field, key]) => {
            const mapping = rule.sourceFields.find(item => item.field === field) ?? emptyFieldMapping(field, field === 'name')
            const invalid = sourceFieldMissing(mapping)
            return <label className="grid gap-1" key={field}>
              <span className="fh-field-label">{translate(key)}</span>
              <ColumnSelector mapping={mapping} disabled={!rule.enabled} invalid={invalid} describedBy={sourceErrorId} allowInternalColumnId={sourceKind === 'flowhub_sheet'} onChange={value => updateSource(field, value)} />
            </label>
          })}
        </div>
        {missingSourceFields.length > 0 && <p className="fh-alert-warning mt-3" id={sourceErrorId} role="alert">{translate('sources:sourceConfiguration.sourceProductNameRequired')}</p>}
      </section>
      <section>
        <h3 className="fh-form-section-title">{translate('sources:sourceConfiguration.channelMappings')}</h3>
        <div className="mt-3 space-y-4">
          <ResourceSectionList resources={channelResources} renderItem={orderedChannel => {
            const channelInfo = orderedChannel.item
            const channel = configured(channelInfo.channelId)
            const disabled = !rule.enabled || !channelInfo.available || !channel.enabled
            const issues = validationIssues(channel.fields, channel.enabled)
            const copyResources = prepareResourceCollection(
              channels.filter(candidate => candidate.channelId !== channelInfo.channelId && rule.channels.some(item => item.channelId === candidate.channelId)),
              sourceChannelSignals,
            )
            return <details className="rounded-lg border border-border bg-bg-subtle" open={channel.enabled}>
              <summary className="flex cursor-pointer list-none items-center gap-3 p-3">
                <strong className="text-text-base">{orderedChannel.displayName}</strong>
                <ResourceStateBadge badge={orderedChannel.badge} />
                <label className="fh-inline-check ms-auto" onClick={event => event.stopPropagation()}>
                  <input type="checkbox" checked={channel.enabled} disabled={!rule.enabled || !channelInfo.available} onChange={event => updateChannel(channelInfo.channelId, { ...channel, enabled: event.target.checked })} />
                  {channel.enabled ? translate('sources:sourceConfiguration.enabled') : translate('sources:sourceConfiguration.disabled')}
                </label>
              </summary>
              <div className="border-t border-border p-3">
                <div className="mb-3 flex flex-wrap items-end gap-2">
                  <label className="fh-field-label min-w-[220px]">{translate('sources:sourceConfiguration.copyMappingFrom')}
                    <select className="fh-input mt-1" disabled={disabled} value={copyFrom[channelInfo.channelId] ?? ''} onChange={event => setCopyFrom(current => ({ ...current, [channelInfo.channelId]: event.target.value }))}>
                      <option value="">{translate('sources:sourceConfiguration.selectChannel')}</option>
                      <ResourceOptionGroups resources={copyResources} renderLabel={item => item.displayName} />
                    </select>
                  </label>
                  <button className="fh-button-secondary fh-button-sm" type="button" disabled={disabled || !copyFrom[channelInfo.channelId]} onClick={() => copyColumns(channelInfo.channelId)}>{translate('sources:sourceConfiguration.copyMapping')}</button>
                  <button className="fh-button-secondary fh-button-sm" type="button" disabled={disabled} onClick={() => updateChannel(channelInfo.channelId, { ...channel, fields: emptyChannelFields() })}>{translate('sources:sourceConfiguration.clearMapping')}</button>
                </div>
                <div className="grid gap-3">{CHANNEL_FIELD_DEFINITIONS.map(([field, key]) => <label className="grid gap-1" key={field}><span className="fh-field-label">{translate(key)}</span><ColumnSelector mapping={channel.fields.find(item => item.field === field) ?? emptyFieldMapping(field)} disabled={disabled} allowInternalColumnId={sourceKind === 'flowhub_sheet'} onChange={value => updateChannelField(channelInfo.channelId, field, value)} /></label>)}</div>
                {issues.length > 0 && <ul className="fh-alert-warning mt-3 list-disc ps-5">{issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}
              </div>
            </details>
          }} />
        </div>
      </section>
      <section><h3 className="fh-form-section-title">{translate('sources:sourceConfiguration.valueHandling')}</h3><p className="fh-form-section-description">{translate('sources:sourceConfiguration.eachSpecialValueIsInterpretedExplicitlyCurrency')}</p><div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(POLICY_OPTIONS).map(([key, options]) => <label className="fh-field-label" key={key}>{translate(`sources:sourceConfiguration.valueType.${key}`)}<select className="fh-input mt-1" disabled={!rule.enabled} value={rule.valuePolicy[key] ?? DEFAULT_SOURCE_VALUE_POLICY[key]} onChange={event => onChange({ ...rule, valuePolicy: { ...rule.valuePolicy, [key]: event.target.value } })}>{options.map(([value, label]) => <option value={value} key={value}>{translate(label)}</option>)}</select></label>)}</div></section>
    </div>
  </details>
}
