import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../auth'
import { translate } from '../i18n'
import PageShell from '../components/PageShell'
import SettingsNav from '../components/SettingsNav'
import Spinner from '../components/loading/Spinner'
import Icon from '../components/Icon'
import { useNotification } from '../notifications/NotificationProvider'
import { useServices } from '../services/ServiceContext'
import type { ExchangeRateAdminConfig, ExchangeRateDefinition, ExchangeRateDiagnostics, ExchangeRateSnapshotView } from '../services/types'

const DEFAULT_SELECTIONS = ['usd_sell', 'eur', 'aed_sell']

function intervalLabel(perDay: number): string {
  const minutes = Math.round(1440 / Math.max(1, perDay))
  if (minutes >= 60) return `${Math.floor(minutes / 60)}h ${minutes % 60 ? `${minutes % 60}m` : ''}`.trim()
  return `${minutes}m`
}

export default function ExchangeRates() {
  const { exchangeRates } = useServices()
  const exchangeRateService = exchangeRates!
  const { user } = useAuth()
  const { success, error: notifyError } = useNotification()
  const [definitions, setDefinitions] = useState<ExchangeRateDefinition[]>([])
  const [rates, setRates] = useState<ExchangeRateSnapshotView[]>([])
  const [selections, setSelections] = useState<string[]>(DEFAULT_SELECTIONS)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [adminConfig, setAdminConfig] = useState<ExchangeRateAdminConfig | null>(null)
  const [diagnostics, setDiagnostics] = useState<ExchangeRateDiagnostics | null>(null)
  const [adminSaving, setAdminSaving] = useState(false)
  const [testingConnection, setTestingConnection] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [reconciling, setReconciling] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const isSuperAdmin = Boolean(user?.is_super_admin || (user?.role ?? '').toLowerCase() === 'owner')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [supported, latest] = await Promise.all([exchangeRateService.getSupported(), exchangeRateService.getLatest()])
      setDefinitions(supported)
      setSelections(latest.selections)
      setRates(latest.rates)
      if (isSuperAdmin) {
        const config = await exchangeRateService.getAdminConfig()
        setAdminConfig(config)
        setDiagnostics(await exchangeRateService.getDiagnostics())
      }
    } catch {
      notifyError({ title: translate('settings:exchangeRates.loadFailed'), description: translate('settings:exchangeRates.tryAgain') })
    } finally { setLoading(false) }
  }, [exchangeRateService, isSuperAdmin, notifyError])

  useEffect(() => { void load() }, [load])

  const filtered = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase()
    return definitions.filter(item => !needle || `${item.display_name} ${item.display_name_fa} ${item.external_symbol}`.toLocaleLowerCase().includes(needle))
  }, [definitions, search])

  async function saveSelections() {
    if (selections.length !== 3 || new Set(selections).size !== 3) {
      notifyError({ title: translate('settings:exchangeRates.threeDistinct'), description: translate('settings:exchangeRates.duplicateError') })
      return
    }
    setSaving(true)
    try {
      const result = await exchangeRateService.updateSelections(selections)
      setRates(result.rates)
      window.dispatchEvent(new Event('flowhub:exchange-rates-updated'))
      success({ title: translate('settings:exchangeRates.saved'), description: translate('settings:exchangeRates.headerUpdated') })
    } catch { notifyError({ title: translate('settings:exchangeRates.saveFailed'), description: translate('settings:exchangeRates.tryAgain') }) }
    finally { setSaving(false) }
  }

  async function saveAdmin() {
    if (!adminConfig) return
    setAdminSaving(true)
    try {
      const result = await exchangeRateService.updateAdminConfig({
        enabled: adminConfig.enabled,
        refreshes_per_day: adminConfig.refreshes_per_day,
        request_timeout: adminConfig.request_timeout,
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      })
      setAdminConfig(result)
      setApiKey('')
      success({ title: translate('settings:exchangeRates.saved'), description: translate('settings:exchangeRates.adminSaved') })
      setDiagnostics(await exchangeRateService.getDiagnostics())
    } catch { notifyError({ title: translate('settings:exchangeRates.saveFailed'), description: translate('settings:exchangeRates.tryAgain') }) }
    finally { setAdminSaving(false) }
  }

  async function manualRefresh() {
    if (diagnostics && diagnostics.remaining_safe_requests <= 1) {
      if (!window.confirm(translate('settings:exchangeRates.nearLimitConfirm'))) return
    }
    setRefreshing(true)
    try { await exchangeRateService.refresh(); await load(); success({ title: translate('settings:exchangeRates.refreshComplete'), description: translate('settings:exchangeRates.headerUpdated') }) }
    catch { notifyError({ title: translate('settings:exchangeRates.refreshFailed'), description: translate('settings:exchangeRates.tryAgain') }) }
    finally { setRefreshing(false) }
  }

  async function testConnection() {
    setTestingConnection(true)
    try {
      await exchangeRateService.testConnection()
      success({ title: translate('settings:exchangeRates.testSucceeded'), description: translate('settings:exchangeRates.testSucceededDescription') })
      setDiagnostics(await exchangeRateService.getDiagnostics())
    } catch {
      notifyError({ title: translate('settings:exchangeRates.testFailed'), description: translate('settings:exchangeRates.tryAgain') })
    } finally { setTestingConnection(false) }
  }

  async function synchronizeUsage() {
    setReconciling(true)
    try {
      await exchangeRateService.synchronizeUsage()
      setDiagnostics(await exchangeRateService.getDiagnostics())
      success({ title: translate('settings:exchangeRates.usageSynchronized'), description: translate('settings:exchangeRates.usageSynchronizedDescription') })
    } catch {
      notifyError({ title: translate('settings:exchangeRates.usageSyncFailed'), description: translate('settings:exchangeRates.tryAgain') })
    } finally { setReconciling(false) }
  }

  return (
    <PageShell>
      <div className="fh-page-header"><div><h1 className="fh-page-title">{translate('settings:exchangeRates.title')}</h1><p className="fh-page-subtitle">{translate('settings:exchangeRates.description')}</p></div></div>
      <div className="flex flex-col items-start gap-4 lg:flex-row">
        <SettingsNav active="exchangeRates" />
        <div className="flex w-full min-w-0 max-w-[820px] flex-col gap-4">
          <section className="fh-card fh-card-pad">
            <p className="fh-section-title">{translate('settings:exchangeRates.yourHeaderRates')}</p>
            <p className="fh-section-subtitle mt-1">{translate('settings:exchangeRates.selectExactlyThree')}</p>
            {loading ? <div className="mt-4 flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />{translate('settings:rateLimits.loading')}</div> : <>
              <label className="fh-field mt-4"><span className="fh-help-text">{translate('settings:exchangeRates.search')}</span><input className="fh-input" value={search} onChange={event => setSearch(event.target.value)} placeholder={translate('settings:exchangeRates.searchHint')} /></label>
              <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
                {selections.map((value, index) => <label className="fh-field" key={index}><span className="fh-help-text">{translate('settings:exchangeRates.position', { value: index + 1 })}</span><select className="fh-select" value={value} onChange={event => setSelections(current => current.map((item, i) => i === index ? event.target.value : item))}>{definitions.filter(item => item.external_symbol === value || filtered.some(filteredItem => filteredItem.external_symbol === item.external_symbol)).map(item => <option key={item.external_symbol} value={item.external_symbol} disabled={selections.some((selectedSymbol, i) => i !== index && selectedSymbol === item.external_symbol)}>{item.display_name} · {item.external_symbol}</option>)}</select></label>)}
              </div>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><div className="flex flex-wrap gap-2">{rates.slice(0, 3).map(rate => <span key={rate.external_symbol} className="fh-badge fh-badge-neutral">{rate.display_name}: {rate.value ?? '—'} {rate.status === 'stale' ? `· ${translate('settings:exchangeRates.stale')}` : ''}</span>)}</div><button type="button" onClick={() => void saveSelections()} disabled={saving} className="fh-button-primary">{saving && <Spinner size="sm" className="text-white" />}{saving ? translate('settings:rateLimits.saving') : <><Icon name="save" />{translate('settings:rateLimits.saveChanges')}</>}</button></div>
            </>}
          </section>

          {isSuperAdmin && adminConfig && <section className="fh-card fh-card-pad">
            <p className="fh-section-title">{translate('settings:exchangeRates.adminControls')}</p>
            <p className="fh-section-subtitle mt-1">{translate('settings:exchangeRates.adminOnly')}</p>
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="fh-field"><span className="fh-help-text">{translate('settings:exchangeRates.providerStatus')}</span><select className="fh-select" value={adminConfig.enabled ? 'enabled' : 'disabled'} onChange={event => setAdminConfig({ ...adminConfig, enabled: event.target.value === 'enabled' })}><option value="enabled">{translate('settings:exchangeRates.enabled')}</option><option value="disabled">{translate('settings:exchangeRates.disabled')}</option></select></label>
              <label className="fh-field"><span className="fh-help-text">{translate('settings:exchangeRates.refreshesPerDay')}</span><input className="fh-input" type="number" min={1} max={adminConfig.daily_request_limit - adminConfig.reserved_request_count - 1} list="fh-refresh-presets" value={adminConfig.refreshes_per_day} onChange={event => setAdminConfig({ ...adminConfig, refreshes_per_day: Number(event.target.value) })} /><datalist id="fh-refresh-presets">{[1, 2, 4, 6, 8, 12, 24, 48].filter(value => value <= adminConfig.daily_request_limit - adminConfig.reserved_request_count - 1).map(value => <option key={value} value={value}>{intervalLabel(value)}</option>)}</datalist><span className="fh-help-text">{adminConfig.refreshes_per_day} / day · {intervalLabel(adminConfig.refreshes_per_day)}</span></label>
              <label className="fh-field"><span className="fh-help-text">{translate('settings:exchangeRates.apiKey')}</span><input className="fh-input" type="password" value={apiKey} onChange={event => setApiKey(event.target.value)} placeholder={adminConfig.api_key_masked || translate('settings:exchangeRates.notConfigured')} autoComplete="new-password" /></label>
              <div className="fh-field"><span className="fh-help-text">{translate('settings:exchangeRates.budget')}</span><div className="fh-text-body-sm rounded-lg border border-border bg-bg-base px-3 py-2">{adminConfig.daily_request_limit - adminConfig.reserved_request_count} {translate('settings:exchangeRates.safe')} / {adminConfig.daily_request_limit} {translate('settings:exchangeRates.total')} · {adminConfig.reserved_request_count} {translate('settings:exchangeRates.reserved')}</div></div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" onClick={() => void saveAdmin()} disabled={adminSaving} className="fh-button-primary">{adminSaving ? translate('settings:rateLimits.saving') : translate('settings:rateLimits.saveChanges')}</button>
              <button type="button" onClick={() => void testConnection()} disabled={testingConnection || !adminConfig.api_key_configured} className="fh-button-secondary">{testingConnection ? translate('settings:exchangeRates.testing') : translate('settings:exchangeRates.testConnection')}</button>
              <button type="button" onClick={() => void manualRefresh()} disabled={refreshing} className="fh-button-secondary">{refreshing ? translate('settings:exchangeRates.refreshing') : translate('settings:exchangeRates.manualRefresh')}</button>
              <button type="button" onClick={() => void synchronizeUsage()} disabled={reconciling || !adminConfig.api_key_configured} className="fh-button-secondary">{reconciling ? translate('settings:exchangeRates.reconciling') : translate('settings:exchangeRates.synchronizeUsage')}</button>
            </div>
            {diagnostics && <>
              {diagnostics.usage_discrepancy !== null && diagnostics.usage_discrepancy > 0 && <div className="fh-alert fh-alert-warning mt-4" role="status">{translate('settings:exchangeRates.discrepancyWarning', { value: diagnostics.usage_discrepancy })}</div>}
              <div className="mt-4 grid grid-cols-1 gap-2 text-xs text-wp-muted sm:grid-cols-2">
                <span>{translate('settings:exchangeRates.internalUsage')}: {diagnostics.internal_daily_usage}</span>
                <span>{translate('settings:exchangeRates.completedUsage')}: {diagnostics.internal_completed_usage}</span>
                <span>{translate('settings:exchangeRates.providerUsage')}: {diagnostics.provider_usage?.daily_usage ?? '—'}</span>
                <span>{translate('settings:exchangeRates.effectiveUsage')}: {diagnostics.effective_usage}</span>
                <span>{translate('settings:exchangeRates.remainingSafe')}: {diagnostics.remaining_safe_requests}</span>
                <span>{translate('settings:exchangeRates.reconciliationStatus')}: {diagnostics.usage_reconciliation_status}</span>
                <span>{translate('settings:exchangeRates.lastReconciliation')}: {diagnostics.usage_reconciled_at ? new Date(diagnostics.usage_reconciled_at).toLocaleString() : '—'}</span>
                <span>{translate('settings:exchangeRates.lastRefresh')}: {diagnostics.last_success_at ? new Date(diagnostics.last_success_at).toLocaleString() : '—'}</span>
                <span>{translate('settings:exchangeRates.nextRefresh')}: {diagnostics.next_scheduled_refresh ? new Date(diagnostics.next_scheduled_refresh).toLocaleString() : '—'}</span>
                <span>{translate('settings:exchangeRates.runnerState')}: {diagnostics.runner_state ?? '—'}</span>
                <span>{translate('settings:exchangeRates.lastError')}: {diagnostics.last_error ?? diagnostics.usage_error_code ?? '—'}</span>
              </div>
            </>}
          </section>}
        </div>
      </div>
    </PageShell>
  )
}
