import { useId, useMemo, useState } from 'react'
import Icon from '../../components/Icon'
import BrandIcon from '../../components/BrandIcon'
import Badge, { type BadgeVariant } from '../../components/Badge'
import { ResourceOptionGroups, ResourceSectionList, ResourceStateBadge } from '../../components/ResourceOrdering'
import { prepareResourceCollection, sourceChannelSignals } from '../../features/resourceOrdering/resourceOrdering'
import type { DiscoveredColumn, FieldMapping, ReferenceType, SourceChannel, SourceWorksheetRule } from '../../features/sourceWorkspace/types'
import { translate } from '../../i18n'

export const SOURCE_FIELD_DEFINITIONS = [
  ['name', 'sources:sourceConfiguration.sourceProductName', true],
  ['source_key', 'sources:sourceConfiguration.sourceProductKey', true],
  ['cost', 'sources:sourceConfiguration.cost', false],
  ['category', 'sources:sourceConfiguration.category', false],
  ['brand', 'sources:sourceConfiguration.brand', false],
] as const

export const SOURCE_FIELD_GROUPS = [
  {
    id: 'primary',
    titleKey: 'sources:sourceConfiguration.sourceProductIdentity',
    helpKey: 'sources:sourceConfiguration.sourceProductIdentityHelp',
    fields: ['name', 'source_key', 'cost'],
  },
  {
    id: 'classification',
    titleKey: 'sources:sourceConfiguration.sourceProductClassification',
    helpKey: 'sources:sourceConfiguration.sourceProductClassificationHelp',
    fields: ['category', 'brand'],
  },
] as const

export const CHANNEL_FIELD_DEFINITIONS = [
  ['external_id', 'sources:sourceConfiguration.productIdentifier'],
  ['price', 'common:field.price'],
  ['stock', 'common:field.stock'],
  ['status', 'common:field.status'],
] as const

type ChannelField = typeof CHANNEL_FIELD_DEFINITIONS[number][0]

/**
 * Channel mapping requirements come from the Source-channel contract returned
 * by the API.  The fallback mirrors the pre-capability API contract so older
 * servers remain safe while newer ones can declare requirements directly.
 */
export function requiredChannelMappingFields(
  connectorType: string | undefined,
  capabilities: Readonly<Record<string, unknown>> = {},
): ReadonlySet<ChannelField> {
  const advertised = capabilities.mappingRequiredFields ?? capabilities.mapping_required_fields
  if (Array.isArray(advertised)) {
    const fields = advertised.filter((field): field is ChannelField =>
      typeof field === 'string' && CHANNEL_FIELD_DEFINITIONS.some(([candidate]) => candidate === field))
    if (fields.length > 0) return new Set(fields)
  }
  return new Set(connectorType === 'woocommerce'
    ? ['external_id']
    : ['external_id', 'stock', 'status'])
}

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

function sourceFieldRequired(field: string): boolean {
  return SOURCE_FIELD_DEFINITIONS.find(([candidate]) => candidate === field)?.[2] ?? false
}

function fieldDisplayName(field: string): string {
  const sourceDefinition = SOURCE_FIELD_DEFINITIONS.find(([candidate]) => candidate === field)
  const channelDefinition = CHANNEL_FIELD_DEFINITIONS.find(([candidate]) => candidate === field)
  const translationKey = sourceDefinition?.[1] ?? channelDefinition?.[1]
  return translationKey ? translate(translationKey) : field
}

function sourceFieldMissing(mapping: FieldMapping): boolean {
  return Boolean((mapping.required || mapping.field === 'name' || mapping.field === 'source_key') && (mapping.referenceType === 'disabled' || !mapping.referenceValue?.trim()))
}

export function createWorksheetRule(name: string): SourceWorksheetRule {
  return { worksheetName: name, enabled: true, dataStartRow: 2, valuePolicy: { ...DEFAULT_SOURCE_VALUE_POLICY }, sourceFields: emptySourceFields(), channels: [] }
}

export function smartInputDisplayValue(mapping: FieldMapping): string {
  if (mapping.referenceType === 'disabled') return ''
  return mapping.referenceValue ?? ''
}

export function MappingFieldLabel({ label, required = false, help }: { label: string; required?: boolean; help?: string }) {
  return <>
    <span className="fh-field-label">{label}{required && <><span className="text-danger" aria-hidden="true"> *</span><span className="sr-only"> {translate('sources:sourceConfiguration.requiredField')}</span></>}</span>
    {help && <p className="fh-text-caption">{help}</p>}
  </>
}

const REFERENCE_TYPE_KEYS: Record<ReferenceType, string> = {
  disabled: 'sources:sourceConfiguration.disabled',
  column_letter: 'sources:sourceConfiguration.columnLetter',
  header_name: 'sources:sourceConfiguration.exactHeader',
  column_id: 'sources:sourceConfiguration.internalColumnId',
}

export function SmartColumnInput({ mapping, columns = [], disabled = false, allowInternalColumnId = true, invalid = false, required = false, describedBy, detectedHeader, fieldLabel, onChange }: { mapping: FieldMapping; columns?: DiscoveredColumn[]; disabled?: boolean; allowInternalColumnId?: boolean; invalid?: boolean; required?: boolean; describedBy?: string; detectedHeader?: string | null; fieldLabel?: string; onChange: (mapping: FieldMapping) => void }) {
  const [advanced, setAdvanced] = useState(mapping.referenceType === 'header_name' || mapping.referenceType === 'column_id')
  const displayValue = smartInputDisplayValue(mapping)
  const displayLabel = fieldLabel ?? fieldDisplayName(mapping.field)
  const ariaLabel = translate('sources:sourceConfiguration.columnReference', { field: displayLabel })
  const referenceTypeLabel = translate('sources:sourceConfiguration.referenceType', { field: displayLabel })
  const referenceExample = mapping.referenceType === 'column_letter'
    ? translate('sources:sourceConfiguration.exampleColumn')
    : mapping.referenceType === 'header_name'
      ? translate('sources:sourceConfiguration.exactHeaderExample')
      : translate('sources:sourceConfiguration.internalColumnExample')
  const changeReferenceType = (referenceType: ReferenceType) => {
    if (referenceType === 'disabled') {
      onChange(emptyFieldMapping(mapping.field, mapping.required))
      return
    }
    onChange({
      ...mapping,
      referenceType,
      referenceValue: mapping.referenceType === 'disabled' ? '' : mapping.referenceValue,
    })
  }
  return (
    <div className="grid gap-1">
      {columns.length > 0 && !advanced && <select
        className="fh-input"
        disabled={disabled}
        required={required}
        aria-required={required || undefined}
        value={mapping.referenceType === 'column_letter' ? mapping.referenceValue ?? '' : ''}
        aria-label={ariaLabel}
        onChange={event => onChange(event.target.value
          ? { ...mapping, referenceType: 'column_letter', referenceValue: event.target.value }
          : emptyFieldMapping(mapping.field, mapping.required))}
      >
        <option value="">{translate('sources:sourceConfiguration.chooseDiscoveredColumn')}</option>
        {columns.map(column => <option value={column.id} key={column.id}>{column.letter} — {column.header || translate('sources:sourceConfiguration.unnamedColumn')}</option>)}
      </select>}
      {columns.length > 0 && <button className="fh-button-ghost fh-button-sm justify-self-start" type="button" disabled={disabled} onClick={() => setAdvanced(current => !current)}>
        {advanced ? translate('sources:sourceConfiguration.useDiscoveredColumns') : translate('sources:sourceConfiguration.advancedManualMapping')}
      </button>}
      {(columns.length === 0 || advanced) && <>
      <select
        className="fh-input"
        disabled={disabled}
        required={required}
        aria-required={required || undefined}
        value={mapping.referenceType}
        aria-label={referenceTypeLabel}
        onChange={event => changeReferenceType(event.target.value as ReferenceType)}
      >
        {(Object.keys(REFERENCE_TYPE_KEYS) as ReferenceType[])
          .map(referenceType => <option value={referenceType} disabled={referenceType === 'column_id' && !allowInternalColumnId} key={referenceType}>{translate(REFERENCE_TYPE_KEYS[referenceType])}</option>)}
      </select>
      <div className="relative min-w-0">
        <input
          className="fh-input pe-8"
          disabled={disabled || mapping.referenceType === 'disabled'}
          required={required}
          aria-required={required || undefined}
          value={displayValue}
          aria-label={ariaLabel}
          aria-invalid={invalid || undefined}
          aria-describedby={invalid ? describedBy : undefined}
          placeholder={mapping.referenceType === 'disabled' ? translate('sources:sourceConfiguration.chooseReferenceType') : referenceExample}
          onChange={event => onChange({ ...mapping, referenceValue: event.target.value })}
        />
        {displayValue && !disabled && (
          <button type="button" className="absolute inset-y-0 end-1 flex items-center px-1 text-text-muted hover:text-text-base" aria-label={translate('common:action.clear')} onClick={() => onChange(emptyFieldMapping(mapping.field, mapping.required))}>
            <Icon name="close" className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      </>}
      {displayValue && detectedHeader && <span className="fh-text-caption">{translate('sources:sourceConfiguration.detectedHeaderHint', { value: displayValue, header: detectedHeader })}</span>}
    </div>
  )
}

function isFieldFilled(field: FieldMapping | undefined): boolean {
  return Boolean(field && field.referenceType !== 'disabled' && field.referenceValue?.trim())
}

export function channelValidationIssues(fields: FieldMapping[], enabled: boolean, connectorType?: string, capabilities?: Readonly<Record<string, unknown>>): string[] {
  if (!enabled) return []
  const issues: string[] = []
  const requiredFields = requiredChannelMappingFields(connectorType, capabilities)
  if (requiredFields.has('external_id') && !isFieldFilled(fields.find(item => item.field === 'external_id'))) {
    issues.push(translate('sources:sourceConfiguration.productIdentifierRequired'))
  }
  if ((requiredFields.has('stock') && !isFieldFilled(fields.find(item => item.field === 'stock')))
    || (requiredFields.has('status') && !isFieldFilled(fields.find(item => item.field === 'status')))) {
    issues.push(translate('sources:sourceConfiguration.stockStatusRequired'))
  }
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

export type WorksheetCopyIntent =
  | { kind: 'shared_fields'; worksheetName: string }
  | { kind: 'channel_to_worksheets'; worksheetName: string; channelId: string }
  | { kind: 'channel_to_channel'; worksheetName: string; sourceChannelId: string; targetChannelId: string }

interface Props {
  rule: SourceWorksheetRule
  rowCount?: number
  channels: SourceChannel[]
  sourceKind: 'flowhub_sheet' | 'imported_sheet' | 'external'
  columns?: DiscoveredColumn[]
  selected?: boolean
  expanded?: boolean
  onSelectedChange?: (selected: boolean) => void
  onExpandedChange?: (expanded: boolean) => void
  onChange: (rule: SourceWorksheetRule) => void
  onRemove: () => void
  onRequestCopy?: (intent: WorksheetCopyIntent) => void
}

export default function WorksheetRuleEditor({ rule, rowCount, columns = [], channels, sourceKind, selected = false, expanded = rule.enabled, onSelectedChange = () => {}, onExpandedChange = () => {}, onChange, onRemove, onRequestCopy = () => {} }: Props) {
  const [copyFrom, setCopyFrom] = useState<Record<string, string>>({})
  const [expandedChannels, setExpandedChannels] = useState<string[]>([])
  const editorId = useId().replace(/:/g, '')
  const sourceErrorId = `${editorId}-required-product-column`
  const channelResources = useMemo(() => prepareResourceCollection(channels, sourceChannelSignals), [channels])
  const missingSourceFields = rule.enabled ? rule.sourceFields.filter(sourceFieldMissing) : []
  const configured = (channelId: string) => rule.channels.find(item => item.channelId === channelId) ?? { channelId, worksheetName: rule.worksheetName, enabled: false, fields: emptyChannelFields() }
  const enabledChannels = rule.channels.filter(channel => channel.enabled)
  const channelIssueCount = enabledChannels.reduce((total, channel) => {
    const channelInfo = channels.find(item => item.channelId === channel.channelId)
    return total + channelValidationIssues(channel.fields, true, channelInfo?.connectorType, channelInfo?.capabilities).length
  }, 0)
  const statusKey = !rule.enabled
    ? 'sources:sourceConfiguration.worksheetStatus.ignored'
    : missingSourceFields.length > 0 || channelIssueCount > 0
      ? 'sources:sourceConfiguration.worksheetStatus.validationErrors'
      : enabledChannels.length === 0
        ? 'sources:sourceConfiguration.worksheetStatus.needsColumns'
        : 'sources:sourceConfiguration.worksheetStatus.ready'
  const statusVariant: BadgeVariant = !rule.enabled ? 'disabled' : missingSourceFields.length > 0 || channelIssueCount > 0 ? 'warning' : enabledChannels.length === 0 ? 'pending' : 'success'
  const updateSource = (field: string, mapping: FieldMapping) => onChange({ ...rule, sourceFields: rule.sourceFields.map(item => item.field === field ? mapping : item) })
  const updateChannel = (channelId: string, next: ReturnType<typeof configured>) => onChange({ ...rule, channels: [...rule.channels.filter(item => item.channelId !== channelId), next] })
  const updateChannelField = (channelId: string, field: string, mapping: FieldMapping) => {
    const channel = configured(channelId)
    updateChannel(channelId, { ...channel, fields: channel.fields.map(item => item.field === field ? mapping : item) })
  }

  return <details className="rounded-xl border border-border bg-bg-base" data-worksheet-rule={rule.worksheetName} open={expanded} onToggle={event => {
    const next = event.currentTarget.open
    if (next !== expanded) onExpandedChange(next)
  }}>
    <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 p-4">
      <input type="checkbox" checked={selected} aria-label={translate('sources:sourceConfiguration.selectWorksheet', { worksheet: rule.worksheetName })} onClick={event => event.stopPropagation()} onChange={event => onSelectedChange(event.target.checked)} />
      <Icon name="file" />
      <span className="min-w-0"><strong className="block truncate text-text-base">{rule.worksheetName}</strong>{rowCount != null && <small className="fh-text-caption">{translate('sources:sourceConfiguration.worksheetRowCount', { count: rowCount })}</small>}</span>
      <Badge variant={statusVariant}>{translate(statusKey)}</Badge>
      <span className="fh-text-caption ms-auto">{translate('sources:sourceConfiguration.enabledChannelCount', { count: enabledChannels.length })}</span>
    </summary>
    <div className="border-t border-border p-4 space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <label className="fh-inline-check"><input type="checkbox" checked={rule.enabled} onChange={event => onChange({ ...rule, enabled: event.target.checked })} />{rule.enabled ? translate('sources:sourceConfiguration.worksheetIncluded') : translate('sources:sourceConfiguration.worksheetIgnored')}</label>
        <label className="fh-field-label min-w-[220px]">{translate('sources:sourceConfiguration.dataStartsAtRow')}<input className="fh-input mt-1" type="number" min="1" disabled={!rule.enabled} value={rule.dataStartRow} onChange={event => onChange({ ...rule, dataStartRow: Number(event.target.value) })} /></label>
        <button className="fh-button-danger fh-button-sm ms-auto" type="button" onClick={onRemove}><Icon name="delete" /> {translate('sources:sourceConfiguration.removeWorksheetRule')}</button>
      </div>
      <section>
        <div className="flex flex-wrap items-center justify-between gap-3" title={translate('sources:sourceConfiguration.productColumnsHelp')}><h3 className="fh-form-section-title">{translate('sources:sourceConfiguration.productFieldsSharedByChannels')}</h3><button className="fh-button-secondary fh-button-sm" type="button" disabled={!rule.enabled} onClick={() => onRequestCopy({ kind: 'shared_fields', worksheetName: rule.worksheetName })}><Icon name="copy" /> {translate('sources:sourceConfiguration.copySharedFields')}</button></div>
        <div className="mt-3 grid gap-4">
          {SOURCE_FIELD_GROUPS.map(group => {
            const controls = <>
            <p className="fh-text-caption mb-3">{translate(group.helpKey)}</p>
            {group.id === 'primary' && <p className="fh-text-caption mb-3">{translate('sources:sourceConfiguration.sourceProductCommercialHelp')}</p>}
            <div className="grid gap-3 lg:grid-cols-2">
              {SOURCE_FIELD_DEFINITIONS.filter(([field]) => (group.fields as readonly string[]).includes(field)).map(([field, key]) => {
                const mapping = rule.sourceFields.find(item => item.field === field) ?? emptyFieldMapping(field, sourceFieldRequired(field))
                const required = sourceFieldRequired(field)
                const invalid = sourceFieldMissing(mapping)
                return <div className="grid gap-1" key={field}><MappingFieldLabel label={translate(key)} required={required} help={field === 'source_key' ? translate('sources:sourceConfiguration.sourceProductKeyHelp') : undefined} /><SmartColumnInput mapping={mapping} columns={columns} disabled={!rule.enabled} invalid={invalid} required={required} describedBy={sourceErrorId} allowInternalColumnId={sourceKind === 'flowhub_sheet'} onChange={value => updateSource(field, value)} /></div>
              })}
            </div>
            </>
            return group.id === 'classification'
              ? <section className="rounded-lg border border-dashed border-border bg-bg-base p-3" data-source-field-group={group.id} key={group.id}>
                  <h4 className="font-medium text-text-base">{translate(group.titleKey)}</h4>
                  <div className="mt-3">{controls}</div>
                </section>
              : <fieldset className="rounded-lg border border-border bg-bg-subtle p-3" data-source-field-group={group.id} key={group.id}>
                  <legend className="px-1 font-medium text-text-base">{translate(group.titleKey)}</legend>
                  {controls}
                </fieldset>
          })}
        </div>
        {missingSourceFields.length > 0 && <p className="fh-alert-warning mt-3" id={sourceErrorId} role="alert">{translate('sources:sourceConfiguration.sourceProductFieldsRequired', { fields: missingSourceFields.map(field => fieldDisplayName(field.field)).join(', ') })}</p>}
      </section>
      <section data-worksheet-channel-columns={rule.worksheetName}>
        <h3 className="fh-form-section-title" title={translate('sources:sourceConfiguration.channelMappingsAreIndependent')}>{translate('sources:sourceConfiguration.columnsForEachChannel')}</h3>
        <div className="mt-3 space-y-4">
          <ResourceSectionList resources={channelResources} renderItem={orderedChannel => {
            const channelInfo = orderedChannel.item
            const channel = configured(channelInfo.channelId)
            const disabled = !rule.enabled || !channelInfo.available
            const requiredFields = requiredChannelMappingFields(channelInfo.connectorType, channelInfo.capabilities)
            const issues = channelValidationIssues(channel.fields, true, channelInfo.connectorType, channelInfo.capabilities)
            const copyResources = prepareResourceCollection(channels.filter(candidate => candidate.channelId !== channelInfo.channelId && rule.channels.some(item => item.channelId === candidate.channelId)), sourceChannelSignals)
            const channelOpen = expandedChannels.includes(channelInfo.channelId)
            return <details className="rounded-lg border border-border bg-bg-subtle" data-channel-rule={channelInfo.channelId} open={channelOpen} onToggle={event => {
              const next = event.currentTarget.open
              if (next && !channelOpen) setExpandedChannels(current => [...new Set([...current, channelInfo.channelId])])
              else if (!next && channelOpen) setExpandedChannels(current => current.filter(channelId => channelId !== channelInfo.channelId))
            }}>
              <summary className="flex cursor-pointer list-none items-center gap-3 p-3"><BrandIcon identity={{ provider: channelInfo.connectorType || channelInfo.channelId, sourceType: channelInfo.connectorType }} label={orderedChannel.displayName} size={40} /><strong className="text-text-base">{orderedChannel.displayName}</strong><ResourceStateBadge badge={orderedChannel.badge} />{issues.length > 0 && <Badge variant="warning" className="ms-auto">{translate('sources:sourceConfiguration.issueCount', { count: issues.length })}</Badge>}</summary>
              <div className="border-t border-border p-3">
                <div className="mb-3 flex flex-wrap items-end gap-2">
                  <label className="fh-field-label min-w-[220px]">{translate('sources:sourceConfiguration.copyMappingFrom')}<select className="fh-input mt-1" disabled={disabled} value={copyFrom[channelInfo.channelId] ?? ''} onChange={event => setCopyFrom(current => ({ ...current, [channelInfo.channelId]: event.target.value }))}><option value="">{translate('sources:sourceConfiguration.selectChannel')}</option><ResourceOptionGroups resources={copyResources} renderLabel={item => item.displayName} /></select></label>
                  <button className="fh-button-secondary fh-button-sm" type="button" disabled={disabled || !copyFrom[channelInfo.channelId]} onClick={() => onRequestCopy({ kind: 'channel_to_channel', worksheetName: rule.worksheetName, sourceChannelId: copyFrom[channelInfo.channelId], targetChannelId: channelInfo.channelId })}>{translate('sources:sourceConfiguration.copyMapping')}</button>
                  <button className="fh-button-secondary fh-button-sm" type="button" disabled={disabled} onClick={() => onRequestCopy({ kind: 'channel_to_worksheets', worksheetName: rule.worksheetName, channelId: channelInfo.channelId })}>{translate('sources:sourceConfiguration.copyToWorksheets')}</button>
                  <button className="fh-button-secondary fh-button-sm" type="button" disabled={disabled} onClick={() => updateChannel(channelInfo.channelId, { ...channel, fields: emptyChannelFields() })}>{translate('sources:sourceConfiguration.clearMapping')}</button>
                </div>
                <div className="grid gap-3 lg:grid-cols-2">{CHANNEL_FIELD_DEFINITIONS.map(([field, key]) => {
                  const isWooIdentifier = field === 'external_id' && channelInfo.connectorType === 'woocommerce'
                  const label = translate(isWooIdentifier ? 'sources:sourceConfiguration.woocommerceProductIdentifier' : key)
                  return <div className="grid gap-1" key={field}><MappingFieldLabel label={label} required={channel.enabled && requiredFields.has(field)} help={isWooIdentifier ? translate('sources:sourceConfiguration.woocommerceProductIdentifierHelp') : undefined} /><SmartColumnInput mapping={channel.fields.find(item => item.field === field) ?? emptyFieldMapping(field)} columns={columns} disabled={disabled} required={channel.enabled && requiredFields.has(field)} fieldLabel={label} allowInternalColumnId={sourceKind === 'flowhub_sheet'} onChange={value => updateChannelField(channelInfo.channelId, field, value)} /></div>
                })}</div>
                {issues.length > 0 && <ul className="fh-alert-warning mt-3 list-disc ps-5">{issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}
              </div>
            </details>
          }} />
        </div>
      </section>
      <details className="rounded-lg border border-border bg-bg-subtle p-3">
        <summary className="cursor-pointer font-medium text-text-base" title={translate('sources:sourceConfiguration.eachSpecialValueIsInterpretedExplicitlyCurrency')}>{translate('sources:sourceConfiguration.valueHandling')}</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(POLICY_OPTIONS).map(([key, options]) => <label className="fh-field-label" key={key}>{translate(`sources:sourceConfiguration.valueType.${key}`)}<select className="fh-input mt-1" disabled={!rule.enabled} value={rule.valuePolicy[key] ?? DEFAULT_SOURCE_VALUE_POLICY[key]} onChange={event => onChange({ ...rule, valuePolicy: { ...rule.valuePolicy, [key]: event.target.value } })}>{options.map(([value, label]) => <option value={value} key={value}>{translate(label)}</option>)}</select></label>)}</div>
      </details>
    </div>
  </details>
}
