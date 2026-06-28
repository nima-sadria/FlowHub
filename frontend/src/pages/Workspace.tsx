import { useCallback, useEffect, useState } from 'react'
import { useServices } from '../services/ServiceContext'
import type { Source, WorkspacePreview, PriceChange } from '../services/types'
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
    </tr>
  )
}

type Phase = 'idle' | 'previewing' | 'preview_ready' | 'error'

export default function Workspace() {
  const { workspace, sources } = useServices()
  const { info } = useNotification()

  const [phase, setPhase] = useState<Phase>('idle')
  const [sourceList, setSources] = useState<Source[]>([])
  const [selectedSourceId, setSelectedSourceId] = useState<string>('')
  const [preview, setPreview] = useState<WorkspacePreview | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [sourcesLoading, setSourcesLoading] = useState(true)

  useEffect(() => {
    sources.getSources().then(list => {
      setSources(list)
      if (list.length > 0) setSelectedSourceId(list[0].id)
      setSourcesLoading(false)
    })

    workspace.getState().then(state => {
      if (state === 'preview_ready') {
        workspace.startPreview('').then(p => {
          if (p) { setPreview(p); setPhase('preview_ready') }
        }).catch(() => {})
      }
    })
  }, [workspace, sources])

  const startPreview = useCallback(async () => {
    setPhase('previewing')
    setErrorMsg(null)
    try {
      const p = await workspace.startPreview(selectedSourceId)
      setPreview(p)
      setPhase('preview_ready')
      info('Preview ready — 4 products with pending price changes')
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : 'Failed to start preview')
      setPhase('error')
    }
  }, [workspace, selectedSourceId, info])

  const cancelPreview = useCallback(async () => {
    if (preview) await workspace.cancelPreview(preview.id)
    setPreview(null)
    setPhase('idle')
  }, [workspace, preview])

  return (
    <div className="p-4 sm:p-7 flex flex-col gap-5 max-w-3xl">
      <div>
        <h1 className="text-[22px] font-bold text-text-base">Workspace</h1>
        <p className="text-[13px] text-wp-muted mt-0.5">Preview price changes from your sources</p>
      </div>

      {/* Idle — source selector + start button */}
      {phase === 'idle' && (
        <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px] flex flex-col gap-5">
          {sourcesLoading ? (
            <div className="flex items-center gap-2 text-[13px] text-wp-muted">
              <Spinner size="sm" />
              Loading sources…
            </div>
          ) : sourceList.length === 0 ? (
            <Empty
              title="No sources configured"
              description="Add a Nextcloud source to enable preview."
              action={{ label: 'Add Source', onClick: () => { window.location.href = '/sources/new' } }}
            />
          ) : (
            <>
              <div>
                <label className="block text-[12px] font-medium text-text-base mb-1.5">Source</label>
                <select
                  value={selectedSourceId}
                  onChange={e => setSelectedSourceId(e.target.value)}
                  className="w-full px-3 py-2 text-[13px] border border-border rounded-lg bg-bg-base text-text-base focus:outline-none focus:border-accent transition-colors"
                >
                  {sourceList.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
              <button
                onClick={() => void startPreview()}
                className="w-full py-3 bg-accent text-white text-[14px] font-semibold rounded-lg hover:bg-accent-hover transition-colors"
              >
                Start Preview
              </button>
            </>
          )}
        </div>
      )}

      {/* Previewing — loading state */}
      {phase === 'previewing' && (
        <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px] flex flex-col items-center gap-4 py-12">
          <Spinner size="lg" />
          <p className="text-[14px] font-medium text-text-base">Fetching latest prices from source…</p>
          <p className="text-[12px] text-wp-muted">Comparing source prices with current WooCommerce prices</p>
        </div>
      )}

      {/* Preview ready — changes table */}
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
                Review the changes below. Apply functionality is coming in BU7.
              </p>
            </div>
          </div>

          <div className="bg-bg-card border border-border rounded-card shadow-card overflow-hidden">
            <div className="flex items-center justify-between px-[22px] py-4 border-b border-border">
              <span className="text-[13px] font-semibold text-text-base">
                Preview — {preview.totalChanges} changes
              </span>
              <span className="text-[11px] font-mono text-wp-muted">Source: {preview.sourceName}</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-border bg-bg-base">
                    {['Product', 'Current Price', 'New Price', 'Change'].map(h => (
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
                Apply changes is coming in BU7
              </div>
              <button
                onClick={() => void cancelPreview()}
                className="px-4 py-2 text-[13px] border border-border rounded-lg text-wp-muted hover:text-wp-red hover:border-wp-red transition-colors"
              >
                Cancel Preview
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
