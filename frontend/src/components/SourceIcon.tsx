import { useEffect, useState } from 'react'
import {
  SOURCE_ICON_FALLBACK,
  sourceIconPath,
  type SourceIconIdentityInput,
} from '../features/sourceIntegrations/sourceIconRegistry'

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
  const resolvedPath = sourceIconPath(identity)
  const [currentPath, setCurrentPath] = useState(resolvedPath)

  useEffect(() => setCurrentPath(resolvedPath), [resolvedPath])

  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border bg-white p-1 ${className}`.trim()}
      data-source-icon={currentPath}
      style={{ height: size, width: size }}
    >
      <img
        alt={label ?? ''}
        aria-hidden={label ? undefined : true}
        className="block h-full w-full object-contain"
        decoding="async"
        height={size}
        onError={() => setCurrentPath(path => path === SOURCE_ICON_FALLBACK ? path : SOURCE_ICON_FALLBACK)}
        src={currentPath}
        width={size}
      />
    </span>
  )
}
