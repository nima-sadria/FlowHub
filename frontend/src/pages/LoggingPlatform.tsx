import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { authFetch } from '../api/authFetch'
import Spinner from '../components/loading/Spinner'

interface LoggingSummary {
  total_logs: number
  error_count: number
  warning_count: number
  critical_count: number
  top_components: Array<{ component: string; count: number }>
  top_connectors: Array<{ connector: string; count: number }>
  recent_errors: LogItem[]
}

interface LogItem {
  id: string
  timestamp: string
  severity: string
  component: string
  module: string
  operation: string
  category: string
  message: string
  correlation_id: string
  request_id: string
  user: string
  connector: string
  channel: string
  duration_ms: number | null
  result: string
  exception_summary: string | null
}

function Card({ children }: { children: ReactNode }) {
  return <div className="bg-bg-card border border-border rounded-card shadow-card p-[18px]">{children}</div>
}

function severityClass(severity: string) {
  const map: Record<string, string> = {
    debug: 'bg-bg-base text-wp-muted border-border',
    info: 'bg-accent/10 text-accent border-accent/20',
    warning: 'bg-wp-yellow/10 text-wp-yellow border-wp-yellow/30',
    error: 'bg-wp-red/10 text-wp-red border-wp-red/30',
    critical: 'bg-wp-red/10 text-wp-red border-wp-red/30',
  }
  return ['inline-flex rounded px-2 py-0.5 border text-[11px] font-medium', map[severity] ?? map.info].join(' ')
}

export default function LoggingPlatform() {
  const [summary, setSummary] = useState<LoggingSummary | null>(null)
  const [logs, setLogs] = useState<LogItem[]>([])
  const [retention, setRetention] = useState<Array<{ category: string; retention_days: number }>>([])
  const [redaction, setRedaction] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [severity, setSeverity] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      if (severity) params.set('severity', severity)
      const [summaryResp, logsResp, retentionResp, redactionResp] = await Promise.all([
        authFetch('/api/v2/logging/summary'),
        authFetch(`/api/v2/logging/logs?${params.toString()}`),
        authFetch('/api/v2/logging/retention'),
        authFetch('/api/v2/logging/redaction-policy'),
      ])
      if (!summaryResp.ok) throw new Error(`Summary request failed (${summaryResp.status})`)
      if (!logsResp.ok) throw new Error(`Log search failed (${logsResp.status})`)
      if (!retentionResp.ok) throw new Error(`Retention request failed (${retentionResp.status})`)
      if (!redactionResp.ok) throw new Error(`Redaction policy request failed (${redactionResp.status})`)
      const summaryData = await summaryResp.json() as LoggingSummary
      const logsData = await logsResp.json() as { items: LogItem[] }
      const retentionData = await retentionResp.json() as { policies: Array<{ category: string; retention_days: number }> }
      const redactionData = await redactionResp.json() as { never_exposed: string[] }
      setSummary(summaryData)
      setLogs(logsData.items)
      setRetention(retentionData.policies)
      setRedaction(redactionData.never_exposed)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load logs')
    } finally {
      setLoading(false)
    }
  }, [search, severity])

  useEffect(() => { void load() }, [load])

  return (
    <div className="p-4 sm:p-7 flex flex-col gap-5 max-w-6xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold text-text-base">Unified Logging</h1>
          <p className="text-[13px] text-wp-muted mt-0.5">Application logs, search, correlation, retention, and redaction visibility</p>
        </div>
        <button
          onClick={() => void load()}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-[13px] font-medium text-wp-muted hover:text-text-base hover:border-accent transition-colors disabled:opacity-50"
        >
          {loading ? <Spinner size="sm" /> : 'Refresh'}
        </button>
      </div>

      {error && <div className="bg-wp-red/10 border border-wp-red/30 rounded-card p-4 text-[13px] text-wp-red">{error}</div>}

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <Card><p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-1">Total</p><div className="text-[20px] font-bold text-text-base">{summary?.total_logs ?? 0}</div></Card>
        <Card><p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-1">Warnings</p><div className="text-[20px] font-bold text-wp-yellow">{summary?.warning_count ?? 0}</div></Card>
        <Card><p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-1">Errors</p><div className="text-[20px] font-bold text-wp-red">{summary?.error_count ?? 0}</div></Card>
        <Card><p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-1">Critical</p><div className="text-[20px] font-bold text-wp-red">{summary?.critical_count ?? 0}</div></Card>
      </div>

      <Card>
        <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
          <label className="flex-1 text-[12px] text-wp-muted">
            Search
            <input
              value={search}
              onChange={event => setSearch(event.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-bg-base px-3 py-2 text-[13px] text-text-base"
              placeholder="message, exception, operation"
            />
          </label>
          <label className="w-full sm:w-44 text-[12px] text-wp-muted">
            Severity
            <select
              value={severity}
              onChange={event => setSeverity(event.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-bg-base px-3 py-2 text-[13px] text-text-base"
            >
              <option value="">All</option>
              <option value="debug">Debug</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
              <option value="critical">Critical</option>
            </select>
          </label>
        </div>
      </Card>

      <Card>
        <p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">Log Explorer</p>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-wp-muted border-b border-border">
                <th className="py-2 pe-3 font-medium">Time</th>
                <th className="py-2 pe-3 font-medium">Severity</th>
                <th className="py-2 pe-3 font-medium">Component</th>
                <th className="py-2 pe-3 font-medium">Message</th>
                <th className="py-2 pe-3 font-medium">Correlation</th>
              </tr>
            </thead>
            <tbody>
              {logs.map(item => (
                <tr key={item.id} className="border-b border-border last:border-0">
                  <td className="py-2 pe-3 text-wp-muted whitespace-nowrap">{item.timestamp}</td>
                  <td className="py-2 pe-3"><span className={severityClass(item.severity)}>{item.severity}</span></td>
                  <td className="py-2 pe-3 text-text-base">{item.component}</td>
                  <td className="py-2 pe-3 text-text-base min-w-[260px]">{item.message}</td>
                  <td className="py-2 pe-3 text-wp-muted">{item.correlation_id}</td>
                </tr>
              ))}
              {!loading && logs.length === 0 && (
                <tr><td colSpan={5} className="py-6 text-center text-wp-muted">No logs match the current filters</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">Retention</p>
          <div className="divide-y divide-border">
            {retention.map(item => (
              <div key={item.category} className="py-2 flex items-center justify-between text-[13px]">
                <span className="text-text-base">{item.category}</span>
                <span className="text-wp-muted">{item.retention_days} days</span>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <p className="text-[11px] uppercase tracking-[.7px] text-wp-muted font-semibold mb-3">Redaction</p>
          <div className="flex flex-wrap gap-2">
            {redaction.map(item => (
              <span key={item} className="rounded px-2 py-1 text-[12px] bg-bg-base border border-border text-wp-muted">{item}</span>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
