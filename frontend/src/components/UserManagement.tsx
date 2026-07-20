import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth'
import { apiErrorMessage, apiFetch } from '../api/client'
import { translate } from '../i18n'
import Badge from './Badge'
import Icon from './Icon'
import SecretField from './SecretField'

type UserRole = 'owner' | 'super_admin' | 'admin' | 'operator' | 'viewer'

interface ManagedUser {
  id: number
  username: string
  role: UserRole
  is_active: boolean
  created_at: string
  is_admin: boolean
  is_super_admin: boolean
}

interface UserListResponse {
  items: ManagedUser[]
  total: number
}

const EDITABLE_ROLES: UserRole[] = ['owner', 'admin', 'operator', 'viewer']

function roleLabel(role: UserRole): string {
  return translate(`settings:users.role.${role}`, { defaultValue: role })
}

export default function UserManagement() {
  const { authFetch, user: currentUser } = useAuth()
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('viewer')
  const [passwordTarget, setPasswordTarget] = useState<ManagedUser | null>(null)
  const [replacementPassword, setReplacementPassword] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<ManagedUser | null>(null)
  const [busyId, setBusyId] = useState<number | 'create' | null>(null)

  const loadUsers = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch<UserListResponse>('/api/v2/users', authFetch)
      setUsers(response.items)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, translate('settings:users.loadFailed')))
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    if (currentUser?.is_admin || currentUser?.is_super_admin) void loadUsers()
  }, [currentUser?.is_admin, currentUser?.is_super_admin, loadUsers])

  async function createUser(event: React.FormEvent) {
    event.preventDefault()
    setBusyId('create')
    setError('')
    try {
      await apiFetch<ManagedUser>('/api/v2/users', authFetch, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, role }),
      })
      setUsername('')
      setPassword('')
      setRole('viewer')
      setShowCreate(false)
      await loadUsers()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, translate('settings:users.saveFailed')))
    } finally {
      setBusyId(null)
    }
  }

  async function updateUser(target: ManagedUser, patch: Partial<Pick<ManagedUser, 'role' | 'is_active'>> & { password?: string }) {
    setBusyId(target.id)
    setError('')
    try {
      await apiFetch<ManagedUser>(`/api/v2/users/${target.id}`, authFetch, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      })
      setPasswordTarget(null)
      setReplacementPassword('')
      await loadUsers()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, translate('settings:users.saveFailed')))
    } finally {
      setBusyId(null)
    }
  }

  async function deleteUser() {
    if (!deleteTarget) return
    setBusyId(deleteTarget.id)
    setError('')
    try {
      const response = await authFetch(`/api/v2/users/${deleteTarget.id}`, { method: 'DELETE' })
      if (!response.ok) {
        const body = await response.json().catch(() => null) as { detail?: string } | null
        throw new Error(body?.detail || translate('settings:users.deleteFailed'))
      }
      setDeleteTarget(null)
      await loadUsers()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, translate('settings:users.deleteFailed')))
    } finally {
      setBusyId(null)
    }
  }

  if (!currentUser?.is_admin && !currentUser?.is_super_admin) return null

  return (
    <section className="fh-card overflow-hidden" aria-labelledby="user-management-title">
      <div className="fh-panel-header">
        <div>
          <h2 className="fh-section-title" id="user-management-title">{translate('settings:users.title')}</h2>
          <p className="fh-section-subtitle mt-1">{translate('settings:users.description')}</p>
        </div>
        <button type="button" className="fh-button-primary" onClick={() => setShowCreate(current => !current)}>
          <Icon name={showCreate ? 'close' : 'add'} />
          {showCreate ? translate('settings:users.cancel') : translate('settings:users.create')}
        </button>
      </div>

      <div className="fh-panel-body">
        {error && <div className="fh-alert fh-alert-danger mb-4" role="alert"><Icon name="error" />{error}</div>}

        {showCreate && (
          <form className="mb-5 grid gap-3 rounded-lg border border-border bg-bg-subtle p-4 md:grid-cols-3" onSubmit={event => void createUser(event)}>
            <label className="fh-field">
              <span className="fh-help-text">{translate('settings:users.username')}</span>
              <input className="fh-input" minLength={3} maxLength={150} required value={username} onChange={event => setUsername(event.target.value)} autoComplete="off" />
            </label>
            <SecretField
              label={translate('settings:users.password')}
              value={password}
              required
              onChange={setPassword}
              configuredHint={translate('settings:users.passwordConfigured')}
              revealLabel={translate('settings:users.showPassword')}
              concealLabel={translate('settings:users.hidePassword')}
              copyLabel={translate('settings:users.copyPassword')}
            />
            <label className="fh-field">
              <span className="fh-help-text">{translate('settings:users.role')}</span>
              <select className="fh-select" value={role} onChange={event => setRole(event.target.value as UserRole)}>
                {EDITABLE_ROLES.filter(candidate => currentUser.is_super_admin || candidate !== 'owner').map(candidate => <option value={candidate} key={candidate}>{roleLabel(candidate)}</option>)}
              </select>
            </label>
            <div className="md:col-span-3 flex justify-end">
              <button className="fh-button-primary" disabled={busyId === 'create'} type="submit"><Icon name="save" />{translate('settings:users.create')}</button>
            </div>
          </form>
        )}

        {loading ? <p className="fh-text-body-sm">{translate('settings:users.loading')}</p> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-start">
              <thead><tr className="border-b border-border text-start">
                <th className="p-3 text-start">{translate('settings:users.username')}</th>
                <th className="p-3 text-start">{translate('settings:users.role')}</th>
                <th className="p-3 text-start">{translate('settings:users.status')}</th>
                <th className="p-3 text-start">{translate('settings:users.actions')}</th>
              </tr></thead>
              <tbody>
                {users.map(managedUser => {
                  const isSelf = managedUser.username === currentUser.username
                  const protectedTarget = managedUser.is_super_admin && !currentUser.is_super_admin
                  return <tr className="border-b border-border last:border-0" key={managedUser.id}>
                    <td className="p-3 font-medium">{managedUser.username}{isSelf && <span className="fh-text-caption ms-2">{translate('settings:users.you')}</span>}</td>
                    <td className="p-3">
                      <select
                        aria-label={translate('settings:users.roleFor', { username: managedUser.username })}
                        className="fh-select !py-1"
                        value={managedUser.role}
                        disabled={busyId === managedUser.id || isSelf || protectedTarget}
                        onChange={event => void updateUser(managedUser, { role: event.target.value as UserRole })}
                      >
                        {((managedUser.role === 'super_admin' ? ['super_admin', ...EDITABLE_ROLES] : EDITABLE_ROLES) as UserRole[])
                          .filter(candidate => currentUser.is_super_admin || !['owner', 'super_admin'].includes(candidate))
                          .map(candidate => <option value={candidate} key={candidate}>{roleLabel(candidate)}</option>)}
                      </select>
                    </td>
                    <td className="p-3"><Badge variant={managedUser.is_active ? 'success' : 'info'}>{managedUser.is_active ? translate('settings:users.enabled') : translate('settings:users.disabled')}</Badge></td>
                    <td className="p-3">
                      <div className="flex flex-wrap gap-2">
                        <button className="fh-button-secondary !px-2 !py-1" type="button" disabled={busyId === managedUser.id || isSelf || protectedTarget} onClick={() => void updateUser(managedUser, { is_active: !managedUser.is_active })}>{managedUser.is_active ? translate('settings:users.disable') : translate('settings:users.enable')}</button>
                        <button className="fh-button-secondary !px-2 !py-1" type="button" disabled={busyId === managedUser.id || protectedTarget} onClick={() => setPasswordTarget(managedUser)}>{translate('settings:users.changePassword')}</button>
                        <a className="fh-button-secondary !px-2 !py-1" href={`/activity?user=${encodeURIComponent(managedUser.username)}`}>{translate('settings:users.viewActivity')}</a>
                        <button className="fh-button-danger !px-2 !py-1" type="button" disabled={busyId === managedUser.id || isSelf || protectedTarget} onClick={() => setDeleteTarget(managedUser)}><Icon name="delete" />{translate('settings:users.delete')}</button>
                      </div>
                    </td>
                  </tr>
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {passwordTarget && <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="password-dialog-title">
        <form className="fh-card w-full max-w-lg p-5" onSubmit={event => { event.preventDefault(); void updateUser(passwordTarget, { password: replacementPassword }) }}>
          <h3 className="fh-section-title" id="password-dialog-title">{translate('settings:users.changePasswordFor', { username: passwordTarget.username })}</h3>
          <div className="my-4"><SecretField label={translate('settings:users.newPassword')} value={replacementPassword} required onChange={setReplacementPassword} configuredHint="" revealLabel={translate('settings:users.showPassword')} concealLabel={translate('settings:users.hidePassword')} copyLabel={translate('settings:users.copyPassword')} /></div>
          <div className="flex justify-end gap-2"><button className="fh-button-secondary" type="button" onClick={() => setPasswordTarget(null)}>{translate('settings:users.cancel')}</button><button className="fh-button-primary" type="submit" disabled={replacementPassword.length < 8 || busyId === passwordTarget.id}>{translate('settings:users.savePassword')}</button></div>
        </form>
      </div>}

      {deleteTarget && <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="delete-user-title">
        <div className="fh-card w-full max-w-lg p-5">
          <h3 className="fh-section-title" id="delete-user-title">{translate('settings:users.deleteTitle')}</h3>
          <p className="fh-text-body-sm my-3">{translate('settings:users.deleteConfirmation', { username: deleteTarget.username })}</p>
          <p className="fh-text-caption">{translate('settings:users.deleteHistoryWarning')}</p>
          <div className="mt-5 flex justify-end gap-2"><button className="fh-button-secondary" type="button" onClick={() => setDeleteTarget(null)}>{translate('settings:users.cancel')}</button><button className="fh-button-danger" type="button" disabled={busyId === deleteTarget.id} onClick={() => void deleteUser()}><Icon name="delete" />{translate('settings:users.delete')}</button></div>
        </div>
      </div>}
    </section>
  )
}
