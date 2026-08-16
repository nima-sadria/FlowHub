import { useEffect, useState } from 'react'
import { translate } from '../i18n'

type SiteFooterProps = {
  version?: string | null
}

export default function SiteFooter({ version: providedVersion }: SiteFooterProps) {
  const [loadedVersion, setLoadedVersion] = useState<string | null>(null)

  useEffect(() => {
    if (providedVersion !== undefined) return
    let active = true
    void fetch('/api/health')
      .then(async response => response.ok
        ? response.json() as Promise<{ version?: string }>
        : null)
      .then(data => {
        if (active && data?.version) setLoadedVersion(data.version)
      })
      .catch(() => undefined)
    return () => { active = false }
  }, [providedVersion])

  const version = providedVersion ?? loadedVersion ?? '1.0.0'

  return (
    <footer className="flex shrink-0 flex-wrap items-center justify-center gap-x-3 gap-y-1 border-t border-border px-4 py-3 text-center text-[11px] leading-4 text-wp-muted">
      <span dir="auto">{translate('common:footer.copyright')}</span>
      <span aria-hidden="true">|</span>
      <span dir="auto">{translate('common:footer.version', { version })}</span>
    </footer>
  )
}
