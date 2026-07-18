import BrandIcon from './BrandIcon'
import type { SourceIconIdentityInput } from '../features/sourceIntegrations/sourceIconRegistry'

export interface SourceIconProps {
  identity?: SourceIconIdentityInput
  label?: string
  size?: 44 | 48
  className?: string
}

/**
 * Consistent, local-only Source branding. Brand images remain unmodified and
 * use contain sizing so their aspect ratios are never cropped or stretched.
 */
export default function SourceIcon({
  identity,
  label,
  size = 48,
  className = '',
}: SourceIconProps) {
  return <BrandIcon identity={identity} label={label} size={size} className={className} />
}
