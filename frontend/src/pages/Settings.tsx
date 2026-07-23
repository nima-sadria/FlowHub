import { translate } from '../i18n'
import { useCallback, useEffect, useState } from 'react'
import { useServices } from '../services/ServiceContext'
import type { AppSettings } from '../services/types'
import Badge from '../components/Badge'
import Icon from '../components/Icon'
import Spinner from '../components/loading/Spinner'
import PageShell from '../components/PageShell'
import SettingsNav from '../components/SettingsNav'
import { useNotification } from '../notifications/NotificationProvider'
import { useTranslation } from 'react-i18next'
import { changeLocale, localeMetadata, type FlowHubLocale } from '../i18n'

const TIMEZONES = [
  'UTC',
  'Africa/Cairo', 'Africa/Johannesburg', 'Africa/Lagos', 'Africa/Nairobi',
  'America/Bogota', 'America/Buenos_Aires', 'America/Chicago', 'America/Denver',
  'America/Los_Angeles', 'America/Mexico_City', 'America/New_York',
  'America/Sao_Paulo', 'America/Toronto', 'America/Vancouver',
  'Asia/Bangkok', 'Asia/Dubai', 'Asia/Hong_Kong', 'Asia/Jakarta',
  'Asia/Karachi', 'Asia/Kolkata', 'Asia/Kuala_Lumpur', 'Asia/Manila',
  'Asia/Riyadh', 'Asia/Seoul', 'Asia/Shanghai', 'Asia/Singapore',
  'Asia/Taipei', 'Asia/Tehran', 'Asia/Tokyo',
  'Atlantic/Reykjavik',
  'Australia/Melbourne', 'Australia/Perth', 'Australia/Sydney',
  'Europe/Amsterdam', 'Europe/Athens', 'Europe/Berlin', 'Europe/Brussels',
  'Europe/Bucharest', 'Europe/Dublin', 'Europe/Helsinki', 'Europe/Istanbul',
  'Europe/Kiev', 'Europe/Lisbon', 'Europe/London', 'Europe/Madrid',
  'Europe/Moscow', 'Europe/Oslo', 'Europe/Paris', 'Europe/Prague',
  'Europe/Rome', 'Europe/Stockholm', 'Europe/Vienna', 'Europe/Warsaw',
  'Europe/Zurich',
  'Pacific/Auckland', 'Pacific/Honolulu',
]

const CURRENCIES = ['USD', 'EUR', 'IRR', 'IRT', 'AED', 'TRY', 'GBP', 'JPY', 'CAD', 'AUD', 'CHF'] as const

function currencyLabel(code: string): string {
  return translate(`settings:settings.currencyOption.${code}`, { defaultValue: code })
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="fh-field">
      <label className="fh-help-text">{label}</label>
      <div className="rounded-lg border border-border bg-bg-base px-3 py-2 fh-text-body-sm font-mono select-all">
        {value}
      </div>
    </div>
  )
}

export default function Settings() {
  const { settings } = useServices()
  const { success, error: notifyError } = useNotification()
  const { i18n: translationEngine } = useTranslation()
  const language = translationEngine.resolvedLanguage ?? 'en'

  const [appSettings, setAppSettings] = useState<AppSettings | null>(null)
  const [draft, setDraft] = useState<AppSettings | null>(null)
  const [draftLanguage, setDraftLanguage] = useState<FlowHubLocale>(language.startsWith('fa') ? 'fa' : 'en')
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

  const loadSettings = useCallback(() => {
    settings.getSettings().then(s => {
      setAppSettings(s)
      setDraft(s)
    })
  }, [settings])

  useEffect(() => { loadSettings() }, [loadSettings])
  useEffect(() => { setDraftLanguage(language.startsWith('fa') ? 'fa' : 'en') }, [language])

  function updateDraft(patch: Partial<AppSettings>) {
    setDraft(d => d ? { ...d, ...patch } : d)
    setDirty(true)
  }

  function updateDraftLanguage(next: FlowHubLocale) {
    setDraftLanguage(next)
    setDirty(true)
  }

  async function handleSave() {
    if (!draft) return
    setSaving(true)
    try {
      await settings.updateSettings(draft)
      setAppSettings(draft)
      if (draftLanguage !== (language.startsWith('fa') ? 'fa' : 'en')) void changeLocale(draftLanguage)
      setDirty(false)
      success({
        title: translate('settings:rateLimits.settingsSavedSuccessfully'),
        description: translate('settings:rateLimits.yourChangesHaveBeenApplied'),
      })
    } catch {
      notifyError({
        title: translate('settings:rateLimits.unableToSaveSettings'),
        description: translate('settings:rateLimits.pleaseTryAgain'),
      })
    } finally {
      setSaving(false)
    }
  }

  function handleReset() {
    setDraft(appSettings)
    setDraftLanguage(language.startsWith('fa') ? 'fa' : 'en')
    setDirty(false)
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('settings:settings.general')}</h1>
          <p className="fh-page-subtitle">{translate('settings:settings.workspaceDefaultsAndRegionalPreferences')}</p>
        </div>
      </div>

      <div className="flex flex-col items-start gap-4 lg:flex-row">
        <SettingsNav active="general" />

        <div className="flex w-full min-w-0 max-w-[820px] flex-col gap-4">
          <section className={['fh-card fh-card-pad', dirty ? 'border-accent' : ''].join(' ')}>
            <p className="fh-section-title">{translate('settings:settings.workspacePreferences')}</p>
            <p className="fh-section-subtitle mt-1">{translate('settings:settings.regionalDefaultsUsedAcrossSellerWorkflows')}</p>

            {!draft ? (
              <div className="mt-4 flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />{translate('settings:rateLimits.loading')}</div>
            ) : (
              <>
                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <label className="fh-field">
                    <span className="fh-help-text">{translate('settings:language.label')}</span>
                    <select className="fh-select" value={draftLanguage} onChange={event => updateDraftLanguage(event.target.value as FlowHubLocale)}>
                      <option value="en">{translate('settings:language.english')}</option>
                      <option value="fa" disabled={!localeMetadata.fa.complete}>{localeMetadata.fa.complete ? translate('settings:language.persian') : translate('settings:language.persianUnavailable')}</option>
                    </select>
                  </label>
                  <label className="fh-field">
                    <span className="fh-help-text">{translate('settings:settings.timezone')}</span>
                    <select className="fh-select" value={draft.timezone} onChange={event => updateDraft({ timezone: event.target.value })}>
                      {TIMEZONES.map(zone => <option key={zone} value={zone}>{zone}</option>)}
                    </select>
                  </label>
                </div>
                <label className="fh-field mt-4">
                  <span className="fh-help-text">{translate('settings:settings.defaultCurrency')}</span>
                  <select
                    className="fh-select"
                    value={draft.currency}
                    onChange={event => updateDraft({ currency: event.target.value, currencyUnit: event.target.value === 'IRR' ? 'RIAL' : event.target.value })}
                  >
                    {CURRENCIES.map(code => <option key={code} value={code}>{currencyLabel(code)}</option>)}
                  </select>
                </label>

                {dirty && (
                  <div className="mt-4 flex items-center justify-between">
                    <span className="fh-text-body-sm font-medium text-wp-yellow">{translate('settings:settings.unsavedChanges')}</span>
                    <div className="fh-actions">
                      <button type="button" onClick={handleReset} className="fh-toolbar-link">{translate('settings:rateLimits.reset')}</button>
                      <button type="button" onClick={() => void handleSave()} disabled={saving} className="fh-button-primary">
                        {saving && <Spinner size="sm" className="text-white" />}
                        {!saving && <Icon name="save" />}
                        {saving ? translate('settings:rateLimits.saving') : translate('settings:rateLimits.saveChanges')}
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </section>

          {draft && (
            <section className="fh-card fh-card-pad flex flex-wrap items-center justify-between gap-3">
              <ReadOnlyField
                label={translate('settings:settings.localizationPreview')}
                value={`${draftLanguage === 'fa' ? translate('settings:language.persian') : translate('settings:language.english')} · ${draft.currency} · ${draft.timezone}`}
              />
              <Badge dot variant="success">{translate('settings:settings.ready')}</Badge>
            </section>
          )}
        </div>
      </div>
    </PageShell>
  )
}
