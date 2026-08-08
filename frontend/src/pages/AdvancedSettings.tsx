import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import { useAuth } from '../auth'
import Icon from '../components/Icon'
import Spinner from '../components/loading/Spinner'
import PageShell from '../components/PageShell'
import SettingsNav from '../components/SettingsNav'
import { translate } from '../i18n'
import { useNotification } from '../notifications/NotificationProvider'

type SourceNetworkPolicy = {
  trusted_private_networks: string[]
}

export default function AdvancedSettings() {
  const { authFetch, user } = useAuth()
  const { success, error: notifyError } = useNotification()
  const [current, setCurrent] = useState<string[]>([])
  const [value, setValue] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const canEdit = Boolean(user?.is_admin || user?.is_super_admin)

  useEffect(() => {
    let active = true
    void apiFetch<SourceNetworkPolicy>('/api/v2/settings/advanced/source-network-policy', authFetch)
      .then(policy => {
        if (!active) return
        setCurrent(policy.trusted_private_networks)
        setValue(policy.trusted_private_networks.join('\n'))
      })
      .catch(() => {
        if (active) notifyError({
          title: translate('settings:settings.advancedNetworkLoadFailed'),
          description: translate('settings:rateLimits.pleaseTryAgain'),
        })
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [authFetch, notifyError])

  const networks = useMemo(() => value.split(/[\n,]+/).map(item => item.trim()).filter(Boolean), [value])
  const dirty = networks.join('\n') !== current.join('\n')

  async function save() {
    if (!canEdit) return
    setSaving(true)
    try {
      const policy = await apiFetch<SourceNetworkPolicy>('/api/v2/settings/advanced/source-network-policy', authFetch, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trusted_private_networks: networks }),
      })
      setCurrent(policy.trusted_private_networks)
      setValue(policy.trusted_private_networks.join('\n'))
      success({
        title: translate('settings:settings.advancedNetworkSaved'),
        description: translate('settings:settings.advancedNetworkSavedDescription'),
      })
    } catch {
      notifyError({
        title: translate('settings:settings.advancedNetworkSaveFailed'),
        description: translate('settings:settings.advancedNetworkValidationHint'),
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('settings:settings.advanced')}</h1>
          <p className="fh-page-subtitle">{translate('settings:settings.advancedDescription')}</p>
        </div>
      </div>

      <div className="flex flex-col items-start gap-4 lg:flex-row">
        <SettingsNav />
        <section className="fh-card fh-card-pad w-full max-w-[820px]">
          <h2 className="fh-section-title">{translate('settings:settings.advancedNetworkTitle')}</h2>
          <p className="fh-section-subtitle mt-1">{translate('settings:settings.advancedNetworkDescription')}</p>
          {!canEdit && <div className="fh-alert fh-alert-info mt-4"><Icon name="info" />{translate('settings:rateLimits.adminRequiredOperationalLimits')}</div>}
          {loading ? (
            <div className="mt-5 flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />{translate('settings:rateLimits.loading')}</div>
          ) : (
            <>
              <label className="fh-field mt-5">
                <span className="fh-help-text">{translate('settings:settings.advancedNetworkLabel')}</span>
                <textarea
                  className="fh-textarea min-h-28"
                  value={value}
                  disabled={!canEdit || saving}
                  onChange={event => setValue(event.target.value)}
                  placeholder="192.168.100.11/32"
                  spellCheck={false}
                />
              </label>
              <p className="fh-help-text mt-2">{translate('settings:settings.advancedNetworkValidationHint')}</p>
              <div className="mt-4 flex justify-end gap-2">
                <button type="button" onClick={() => setValue(current.join('\n'))} disabled={!dirty || saving} className="fh-button-ghost fh-button-sm">{translate('settings:rateLimits.reset')}</button>
                <button type="button" onClick={() => void save()} disabled={!dirty || saving || !canEdit} className="fh-button-primary fh-button-sm">
                  {saving && <Spinner size="sm" className="text-white" />}
                  {translate('settings:rateLimits.saveChanges')}
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </PageShell>
  )
}
