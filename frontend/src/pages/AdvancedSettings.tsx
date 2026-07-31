import Badge from '../components/Badge'
import PageShell from '../components/PageShell'
import SettingsNav from '../components/SettingsNav'
import { translate } from '../i18n'

export default function AdvancedSettings() {
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
        <section className="fh-card fh-card-pad flex w-full max-w-[820px] items-center justify-between gap-4">
          <div>
            <h2 className="fh-section-title">{translate('settings:settings.advanced')}</h2>
            <p className="fh-section-subtitle mt-1">{translate('settings:settings.advancedDescription')}</p>
          </div>
          <Badge variant="disabled">{translate('common:status.unavailable')}</Badge>
        </section>
      </div>
    </PageShell>
  )
}
