import { useEffect, useState } from 'react'
import {
  SOURCE_ICON_FALLBACK,
  sourceIconPath,
  type SourceIconIdentityInput,
} from '../features/sourceIntegrations/sourceIconRegistry'

export interface BrandIconProps {
  identity?: SourceIconIdentityInput
  label?: string
  size?: 36 | 40 | 44 | 48
  className?: string
}

/**
 * One local-only brand surface for Sources and Channels. Official artwork is
 * never recolored or cropped; unknown integrations use FlowHub's own mark.
 */
export default function BrandIcon({
  identity,
  label,
  size = 44,
  className = '',
}: BrandIconProps) {
  const resolvedPath = sourceIconPath(identity)
  const [currentPath, setCurrentPath] = useState(resolvedPath)

  useEffect(() => setCurrentPath(resolvedPath), [resolvedPath])

  return (
    <span
      className={`fh-brand-icon ${className}`.trim()}
      data-brand-icon={currentPath}
      data-source-icon={currentPath}
      style={{ height: size, width: size }}
      title={label}
    >
      <img
        alt={label ?? ''}
        aria-hidden={label ? undefined : 'true'}
        className="block h-full w-full object-contain"
        decoding="async"
        height={size}
        loading="lazy"
        onError={() => setCurrentPath(path => path === SOURCE_ICON_FALLBACK ? path : SOURCE_ICON_FALLBACK)}
        src={currentPath}
        width={size}
      />
    </span>
  )
}
