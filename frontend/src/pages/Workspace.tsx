import { useCallback, useEffect, useState } from 'react'
import { useServices } from '../services/ServiceContext'
import type { WorkspacePreview, PriceChange } from '../services/types'
import { useNotification } from '../notifications/NotificationProvider'
import Spinner from '../components/loading/Spinner'
import Empty from '../components/Empty'

function fmtPrice(p: number, currency: string): string {
  return `${currency} ${p.toFixed(2)}`
}

function ChangePct({ pct }: { pct: number }) {
  const positive = pct >= 0
  return (
    <span className={['text-[12px] font-semibold', positive ? 'text-wp-orange' : 'text-wp-green'].join(' ')}>
      {positive ? '+' : ''}{pct.toFixed(2)}%
    </span>
  )
}

function PriceChangeRow({ change }: { change: PriceChange }) {
  return (
    <tr className="border-b border-border hover:bg-bg-base/60 transition-colors">
      <td className="px-4 py-3 min-w-0 max-w-[200px]">
        <div className="text-[13px] font-medium text-text-base truncate">{change.productName}</div>
        <div className="text-[11px] font-mono text-wp-muted mt-0.5">{change.sku}</div>
      </td>
      <td className="px-4 py-3 text-[13px] text-wp-muted font-mono">
        {fmtPrice(change.currentPrice, change.currency)}
      </td>
      <td className="px-4 py-3 text-[13px] font-medium text-text-base font-mono">
        {fmtPrice(change.proposedPrice, change.currency)}
      </td>
      <td className="px-4 py-3">
        <ChangePct pct={change.changePct} />
      </td>
      <td className="px-4 py-3 text-[11px] text-wp-muted">
        {change.warning ?? '-'}
      </td>
    </tr>
  )
}

type Phase = 'idle' | 'previewing' | 'preview_ready' | 'error'

export default function Workspace() {
  const { workspace, settings } = useServices()
  const { info } = useNotification()

  const [phase, setPhase] = useState<Phase>('idle')
  const [preview, setPreview] = useState<WorkspacePreview | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Check if both integrations are configured
  const [wcConfigured, setWcConfigured] = useState<boolean | null>(null)
  const [ncConfigured, setNcConfigured] = useState<boolean | null>(null)
  const [configLoading, setConfigLoading] = useState(true)

  useEffect(() => {
    settings.getSettings()
      .then(s => {
        setWcConfigured(s.wcConfigured ?? false)
        setNcConfigured(s.ncConfigured ?? false)
      })
      .catch(() => {
        setWcConfigured(false)
        setNcConfigured(false)
      })
      .finally(() => setConfigLoading(false))
  }, [settings])

  const startPreview = useCallback(async () => {
    setPhase('previewing')
    setErrorMsg(null)
    try {
      const p = await workspace.startPreview('')
      setPreview(p)
      setPhase('preview_ready')
      info(`Preview ready - ${p.totalChanges} product${p.totalChanges !== 1 ? 's' : ''} with pending price changes`)
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : 'Failed to start preview')
      setPhase('error')
    }
  }, [workspace, info])

  const cancelPreview = useCallback(async () => {
    if (preview) await workspace.cancelPreview(preview.id)
    setPreview(null)
    setPhase('idle')
  }, [workspace, preview])

  const bothConfigured = wcConfigured === true && ncConfigured === true

  return (
    <div className="p-4 sm:p-7 flex flex-col gap-5 max-w-3xl">
      <div>
        <h1 className="text-[22px] font-bold text-text-base">Workspace</h1>
        <p className="text-[13px] text-wp-muted mt-0.5">Preview price changes from your sources</p>
      </div>

      {/* Config loading */}
      {configLoading && (
        <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px] flex items-center gap-2 text-[13px] text-wp-muted">
          <Spinner size="sm" />
          Loading configuration...
        </div>
      )}

      {/* Not configured */}
      {!configLoading && !bothConfigured && phase === 'idle' && (
        <div className="bg-bg-card border border-border rounded-card shadow-card">
          {!wcConfigured && (
            <Empty
              title="Product connector required"
              description="Connect a product source from Integrations to use Workspace."
              action={{ label: 'Open Integrations', onClick: () => { window.location.href = '/integrations' } }}
            />
          )}
          {wcConfigured && !ncConfigured && (
            <Empty
              title="Source connector required"
              description="Connect a price source from Integrations to use Workspace."
              action={{ label: 'Open Integrations', onClick: () => { window.location.href = '/integrations' } }}
            />
          )}
        </div>
      )}

      {/* Idle - start button */}
      {!configLoading && bothConfigured && phase === 'idle' && (
        <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px] flex flex-col gap-5">
          <div>
            <p className="text-[13px] text-text-base font-medium mb-1">Ready</p>
            <p className="text-[12px] text-wp-muted">
              FlowHub will fetch products from the connected channel and compare them against the
              configured source data. No changes will be applied.
            </p>
          </div>
          <button
            onClick={() => void startPreview()}
            className="w-full py-3 bg-accent text-white text-[14px] font-semibold rounded-lg hover:bg-accent-hover transition-colors"
          >
            Start Preview
          </button>
        </div>
      )}

      {/* Previewing - loading state */}
      {phase === 'previewing' && (
        <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px] flex flex-col items-center gap-4 py-12">
          <Spinner size="lg" />
          <p className="text-[14px] font-medium text-text-base">Fetching products and source data...</p>
          <p className="text-[12px] text-wp-muted">This may take up to 30 seconds for large catalogues</p>
        </div>
      )}

      {/* Preview ready */}
      {phase === 'preview_ready' && preview && (
        <>
          <div className="bg-wp-yellow/10 border border-wp-yellow/30 rounded-card p-4 flex items-start gap-3">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-wp-yellow flex-shrink-0 mt-0.5">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <div>
              <p className="text-[13px] font-medium text-wp-yellow">
                {preview.totalChanges} product{preview.totalChanges !== 1 ? 's' : ''} with pending price changes
              </p>
              <p className="text-[12px] text-wp-muted mt-0.5">
                Preview only. Changes cannot be applied from this screen.
              </p>
            </div>
          </div>

          {/* Duplicate warnings */}
          {(preview.duplicateWarnings ?? []).length > 0 && (
            <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px]">
              <p className="text-[11.5px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">
                Spreadsheet Warnings ({preview.duplicateWarnings!.length})
              </p>
              {preview.duplicateWarnings!.map((w, i) => (
                <p key={i} className="text-[12px] text-wp-muted py-1 border-b border-border last:border-0">{w}</p>
              ))}
            </div>
          )}

          <div className="bg-bg-card border border-border rounded-card shadow-card overflow-hidden">
            <div className="flex items-center justify-between px-[22px] py-4 border-b border-border">
              <span className="text-[13px] font-semibold text-text-base">
                Preview - {preview.totalChanges} changes
              </span>
              <span className="text-[11px] font-mono text-wp-muted">Source: {preview.sourceName}</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-border bg-bg-base">
                    {['Product', 'Current Price', 'New Price', 'Change', 'Warning'].map(h => (
                      <th key={h} className="px-4 py-2.5 text-start text-[11px] font-semibold text-wp-muted uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.changes.map(c => <PriceChangeRow key={c.productId} change={c} />)}
                </tbody>
              </table>
            </div>

            <div className="px-[22px] py-4 border-t border-border flex items-center justify-between">
              <div className="flex items-center gap-2 text-[12px] text-wp-muted">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
                  <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
                </svg>
                Changes cannot be applied from this preview
              </div>
              <button
                onClick={() => void cancelPreview()}
                className="px-4 py-2 text-[13px] border border-border rounded-lg text-wp-muted hover:text-wp-red hover:border-wp-red transition-colors"
              >
                New Preview
              </button>
            </div>
          </div>
        </>
      )}

      {/* Error */}
      {phase === 'error' && (
        <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px] flex flex-col gap-4">
          <div className="flex items-start gap-3 p-4 bg-wp-red/10 border border-wp-red/30 rounded-lg">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-wp-red flex-shrink-0 mt-0.5">
              <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
            </svg>
            <p className="text-[13px] text-wp-red">{errorMsg ?? 'An error occurred.'}</p>
          </div>
          <button
            onClick={() => setPhase('idle')}
            className="self-start px-4 py-2 text-[13px] border border-border rounded-lg text-wp-muted hover:text-text-base hover:border-accent transition-colors"
          >
            Try again
          </button>
        </div>
      )}
    </div>
  )
}
