import { useCallback, useEffect, useState } from 'react'
import Badge from '../components/Badge'
import Icon from '../components/Icon'
import Spinner from '../components/loading/Spinner'
import PageShell from '../components/PageShell'
import SettingsNav from '../components/SettingsNav'
import { useDirection } from '../direction'
import { useNotification } from '../notifications/NotificationProvider'
import { useServices } from '../services/ServiceContext'
import type { AppSettings } from '../services/types'

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

const CURRENCIES = [
  ['IRR', 'IRR — Iranian Rial'],
  ['IRT', 'IRT — Iranian Toman'],
  ['USD', 'USD — US Dollar'],
  ['EUR', 'EUR — Euro'],
  ['AED', 'AED — UAE Dirham'],
  ['TRY', 'TRY — Turkish Lira'],
  ['GBP', 'GBP — British Pound'],
  ['JPY', 'JPY — Japanese Yen'],
  ['CAD', 'CAD — Canadian Dollar'],
  ['AUD', 'AUD — Australian Dollar'],
  ['CHF', 'CHF — Swiss Franc'],
] as const

function SelectField({ label, value, options, onChange, disabled }: {
  label: string
  value: string
  options: ReadonlyArray<readonly [string, string]>
  onChange: (value: string) => void
  disabled?: boolean
}) {
  return (
    <label className="flex min-w-0 flex-1 flex-col gap-1.5">
      <span className="text-xs font-medium leading-4 text-[color:var(--fh-text-secondary)]">{label}</span>
      <select
        value={value}
        onChange={event => onChange(event.target.value)}
        disabled={disabled}
        className="fh-select !min-h-[36px] rounded-md !px-3 !py-2 text-[13px]"
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>{optionLabel}</option>
        ))}
      </select>
    </label>
  )
}

export default function Settings() {
  const { settings } = useServices()
  const { language, setLanguage, setDirection } = useDirection()
  const { success, error: notifyError } = useNotification()
  const [appSettings, setAppSettings] = useState<AppSettings | null>(null)
  const [draft, setDraft] = useState<AppSettings | null>(null)
  const [savedLanguage, setSavedLanguage] = useState(language)
  const [languageDraft, setLanguageDraft] = useState(language)
  const [saving, setSaving] = useState(false)
  const [loadingError, setLoadingError] = useState(false)

  const loadSettings = useCallback(() => {
    setLoadingError(false)
    settings.getSettings()
      .then(value => {
        setAppSettings(value)
        setDraft(value)
        setSavedLanguage(language)
        setLanguageDraft(language)
      })
      .catch(() => setLoadingError(true))
  }, [language, settings])

  useEffect(() => { loadSettings() }, [loadSettings])

  const dirty = Boolean(draft && appSettings && (
    draft.timezone !== appSettings.timezone
    || draft.currency !== appSettings.currency
    || languageDraft !== savedLanguage
  ))

  function updateDraft(patch: Partial<AppSettings>) {
    setDraft(current => current ? { ...current, ...patch } : current)
  }

  function resetDraft() {
    setDraft(appSettings)
    setLanguageDraft(savedLanguage)
  }

  async function handleSave() {
    if (!draft) return
    setSaving(true)
    try {
      const saved = await settings.updateSettings(draft)
      setAppSettings(saved)
      setDraft(saved)
      setLanguage(languageDraft)
      setDirection(languageDraft === 'fa' ? 'rtl' : 'ltr')
      setSavedLanguage(languageDraft)
      success({
        title: 'Settings saved successfully',
        description: 'Your regional preferences have been applied.',
      })
    } catch {
      notifyError({
        title: 'Unable to save settings',
        description: 'Your changes are still available. Please try again.',
      })
    } finally {
      setSaving(false)
    }
  }

  const languageLabel = languageDraft === 'fa' ? 'Persian' : 'English'
  const currencyLabel = CURRENCIES.find(([value]) => value === draft?.currency)?.[0] ?? draft?.currency ?? '—'

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">General</h1>
          <p className="fh-page-subtitle">Workspace defaults and regional preferences.</p>
        </div>
      </div>

      <div className="flex flex-col items-start gap-4 lg:flex-row">
        <SettingsNav active="General" />

        <div className="flex w-full max-w-[660px] min-w-0 flex-col gap-3.5">
          <section className={['fh-card p-[18px]', dirty ? 'border-accent' : ''].join(' ')}>
            <div>
              <h2 className="text-base font-semibold leading-5 text-text-base">Workspace preferences</h2>
              <p className="mt-2 text-xs leading-4 text-[color:var(--fh-text-secondary)]">Regional defaults used across seller workflows.</p>
            </div>

            {loadingError ? (
              <div className="fh-alert fh-alert-danger mt-4" role="alert">
                <Icon name="error" />
                <span className="flex-1">Unable to load workspace preferences.</span>
                <button type="button" onClick={loadSettings} className="fh-toolbar-link"><Icon name="retry" />Retry</button>
              </div>
            ) : !draft ? (
              <div className="mt-4 flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />Loading preferences</div>
            ) : (
              <>
                <div className="mt-3.5 flex flex-col gap-3 sm:flex-row">
                  <SelectField
                    label="Language"
                    value={languageDraft}
                    options={[['en', 'English'], ['fa', 'Persian']]}
                    onChange={setLanguageDraft}
                    disabled={saving}
                  />
                  <SelectField
                    label="Timezone"
                    value={draft.timezone}
                    options={TIMEZONES.map(value => [value, value] as const)}
                    onChange={value => updateDraft({ timezone: value })}
                    disabled={saving}
                  />
                </div>

                <div className="mt-3 w-full sm:w-[calc(50%-6px)]">
                  <SelectField
                    label="Default currency"
                    value={draft.currency}
                    options={CURRENCIES}
                    onChange={value => updateDraft({ currency: value, currencyUnit: value === 'IRR' ? 'RIAL' : value })}
                    disabled={saving}
                  />
                </div>

                <p className={['mt-3 text-xs font-medium leading-4', dirty ? 'text-wp-yellow' : 'invisible'].join(' ')} aria-live="polite">
                  Unsaved changes
                </p>

                <div className="mt-2 flex justify-end gap-2">
                  <button type="button" onClick={resetDraft} disabled={!dirty || saving} className="fh-button-ghost fh-button-sm">Reset</button>
                  <button type="button" onClick={() => void handleSave()} disabled={!dirty || saving} className="fh-button-primary fh-button-sm">
                    {saving && <Spinner size="sm" className="text-white" />}
                    {saving ? 'Saving...' : 'Save changes'}
                  </button>
                </div>
              </>
            )}
          </section>

          <section className="fh-card flex min-h-[68px] items-center gap-2.5 px-3.5 py-3">
            <div className="min-w-0 flex-1">
              <h2 className="text-[13px] font-semibold leading-[22px] text-text-base">Localization preview</h2>
              <p className="truncate text-xs leading-4 text-[color:var(--fh-text-secondary)]">
                {languageLabel} · {currencyLabel} · {draft?.timezone ?? '—'}
              </p>
            </div>
            <Badge variant={loadingError ? 'danger' : draft ? 'success' : 'neutral'} dot>
              {loadingError ? 'Unavailable' : draft ? 'Ready' : 'Loading'}
            </Badge>
          </section>
        </div>
      </div>
    </PageShell>
  )
}
