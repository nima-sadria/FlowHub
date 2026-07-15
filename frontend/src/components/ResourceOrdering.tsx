import type { ReactNode } from 'react'
import { translate } from '../i18n'
import type {
  OrderedResource,
  ResourceBadge,
  ResourceCollection,
  ResourceSection,
} from '../features/resourceOrdering/resourceOrdering'
import Badge, { type BadgeVariant } from './Badge'

function sectionLabel(section: ResourceSection): string {
  if (section === 'active') return translate('common:resourceGroup.active')
  if (section === 'disabled') return translate('common:resourceGroup.disabled')
  return translate('common:resourceGroup.comingSoon')
}

function badgePresentation(badge: ResourceBadge): { label: string; variant: BadgeVariant } {
  if (badge === 'healthy') return { label: translate('common:resourceBadge.healthy'), variant: 'success' }
  if (badge === 'configured') return { label: translate('common:resourceBadge.configured'), variant: 'success' }
  if (badge === 'warning') return { label: translate('common:resourceBadge.warning'), variant: 'warning' }
  if (badge === 'disabled') return { label: translate('common:resourceBadge.disabled'), variant: 'neutral' }
  return { label: translate('common:resourceBadge.comingSoon'), variant: 'neutral' }
}

export function ResourceStateBadge({ badge }: { badge: ResourceBadge }) {
  const presentation = badgePresentation(badge)
  return <Badge variant={presentation.variant}>{presentation.label}</Badge>
}

export function ResourceOptionGroups<T>({
  resources,
  renderLabel = item => item.displayName,
  isOptionDisabled,
}: {
  resources: ResourceCollection<T>
  renderLabel?: (item: OrderedResource<T>) => ReactNode
  isOptionDisabled?: (item: OrderedResource<T>) => boolean
}) {
  return <>{resources.sections.map(section => (
    <optgroup key={section.key} label={sectionLabel(section.key)}>
      {section.items.map(item => (
        <option key={item.id} value={item.id} disabled={isOptionDisabled?.(item) ?? false}>
          {renderLabel(item)}
        </option>
      ))}
    </optgroup>
  ))}</>
}

export function ResourceSectionList<T>({
  resources,
  renderItem,
  className = 'space-y-3',
}: {
  resources: ResourceCollection<T>
  renderItem: (item: OrderedResource<T>) => ReactNode
  className?: string
}) {
  return <>{resources.sections.map(section => (
    <section key={section.key} data-resource-section={section.key} aria-label={sectionLabel(section.key)}>
      <h3 className="fh-text-caption mb-2 font-semibold uppercase tracking-wide text-wp-muted">
        {sectionLabel(section.key)}
      </h3>
      <div className={className}>{section.items.map(item => <div key={item.id} data-resource-id={item.id}>{renderItem(item)}</div>)}</div>
    </section>
  ))}</>
}
