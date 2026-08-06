import { useEffect } from 'react'
import { translate } from '../../i18n'

/**
 * Warns before an unload/tab-close while `dirty` is true (mirrors the pattern
 * in `pages/SourceConfiguration.tsx`). Pair with {@link confirmDiscard} for
 * in-app navigation (Cancel / back).
 */
export function useUnsavedChangesGuard(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
}

/** Returns true if it is safe to navigate away (not dirty, or user confirmed discarding). */
export function confirmDiscard(dirty: boolean): boolean {
  return !dirty || window.confirm(translate('pricing:editor.discardUnsavedChanges'))
}
