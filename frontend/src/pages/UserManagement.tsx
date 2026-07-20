import PageShell from '../components/PageShell'
import SettingsNav from '../components/SettingsNav'
import UserManagementPanel from '../components/UserManagement'
import { translate } from '../i18n'

export default function UserManagement() {
  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">{translate('settings:users.title')}</h1>
          <p className="fh-page-subtitle">{translate('settings:users.description')}</p>
        </div>
      </div>

      <div className="flex flex-col items-start gap-4 lg:flex-row">
        <SettingsNav active="users" />
        <div className="min-w-0 flex-1">
          <UserManagementPanel />
        </div>
      </div>
    </PageShell>
  )
}
