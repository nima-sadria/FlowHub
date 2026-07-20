import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { apiErrorMessage, apiFetch } from '../api/client'
import { useAuth } from '../auth'
import Badge from '../components/Badge'
import Empty from '../components/Empty'
import Icon from '../components/Icon'
import Spinner from '../components/loading/Spinner'
import PageShell from '../components/PageShell'
import SettingsNav from '../components/SettingsNav'
import { useNotification } from '../notifications/NotificationProvider'

type UserRole = 'owner' | 'super_admin' | 'admin' | 'viewer'

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

function roleLabel(role: UserRole): string {
  if (role === 'owner') return 'Owner'
  if (role === 'super_admin') return 'Super Admin'
  if (role === 'admin') return 'Admin'
  return 'Viewer'
}

function UserEditor({ user, allowPrivilegedRoles, onClose, onSaved }: {
  user?: ManagedUser
  allowPrivilegedRoles: boolean
  onClose: () => void
  onSaved: (user: ManagedUser) => void
}) {
  const { authFetch } = useAuth()
  const { success, error: notifyError } = useNotification()
  const [username, setUsername] = useState(user?.username ?? '')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>(user?.role ?? 'viewer')
  const [active, setActive] = useState(user?.is_active ?? true)
  const [saving, setSaving] = useState(false)
  const roleOptions: UserRole[] = allowPrivilegedRoles
    ? ['owner', 'super_admin', 'admin', 'viewer']
    : ['admin', 'viewer']

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const payload = user
        ? {
            role,
            is_active: active,
            ...(password ? { password } : {}),
          }
        : { username: username.trim(), password, role }
      const saved = await apiFetch<ManagedUser>(
        user ? `/api/v2/users/${user.id}` : '/api/v2/users',
        authFetch,
        {
          method: user ? 'PATCH' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )
      onSaved(saved)
      success({
        title: user ? 'User updated' : 'User created',
        description: `${saved.username} is ${saved.is_active ? 'active' : 'disabled'}.`,
      })
    } catch (error) {
      notifyError({
        title: user ? 'Unable to update user' : 'Unable to create user',
        description: apiErrorMessage(error, 'Please review the account details and try again.'),
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-[1px]" role="presentation">
      <section role="dialog" aria-modal="true" aria-labelledby="user-editor-title" className="fh-card w-full max-w-[480px] overflow-hidden">
        <div className="fh-panel-header">
          <div>
            <h2 id="user-editor-title" className="fh-section-title">{user ? 'Edit user' : 'Create user'}</h2>
            <p className="fh-text-caption mt-1">{user ? 'Update account access and credentials.' : 'Add a FlowHub account and assign its role.'}</p>
          </div>
          <button type="button" onClick={onClose} className="fh-button-ghost fh-button-sm" aria-label="Close user editor"><Icon name="close" /></button>
        </div>
        <form onSubmit={event => void submit(event)} className="fh-panel-body flex flex-col gap-4">
          <label className="fh-field">
            <span className="fh-label">Username</span>
            <input
              value={username}
              onChange={event => setUsername(event.target.value)}
              disabled={Boolean(user) || saving}
              minLength={3}
              maxLength={150}
              required
              autoComplete="username"
              className="fh-input"
            />
          </label>
          <label className="fh-field">
            <span className="fh-label">{user ? 'New password (optional)' : 'Password'}</span>
            <input
              type="password"
              value={password}
              onChange={event => setPassword(event.target.value)}
              disabled={saving}
              minLength={8}
              maxLength={256}
              required={!user}
              autoComplete="new-password"
              className="fh-input"
            />
            <span className="fh-help-text">Use at least 8 characters.</span>
          </label>
          <label className="fh-field">
            <span className="fh-label">Role</span>
            <select value={role} onChange={event => setRole(event.target.value as UserRole)} disabled={saving} className="fh-select">
              {roleOptions.includes(role) || !user ? null : <option value={role}>{roleLabel(role)}</option>}
              {roleOptions.map(value => <option key={value} value={value}>{roleLabel(value)}</option>)}
            </select>
          </label>
          {user && (
            <label className="fh-inline-check">
              <input type="checkbox" checked={active} onChange={event => setActive(event.target.checked)} disabled={saving} />
              Active account
            </label>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} disabled={saving} className="fh-button-ghost fh-button-sm">Cancel</button>
            <button type="submit" disabled={saving} className="fh-button-primary fh-button-sm">
              {saving && <Spinner size="sm" className="text-white" />}
              {saving ? 'Saving...' : user ? 'Save changes' : 'Create user'}
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}

export default function UserManagement() {
  const { user: currentUser, authFetch } = useAuth()
  const { error: notifyError } = useNotification()
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [editing, setEditing] = useState<ManagedUser | 'create' | null>(null)

  const loadUsers = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    try {
      const response = await apiFetch<UserListResponse>('/api/v2/users', authFetch)
      setUsers(response.items)
    } catch (error) {
      setLoadError(true)
      notifyError({
        title: 'Unable to load users',
        description: apiErrorMessage(error, 'Please try again.'),
      })
    } finally {
      setLoading(false)
    }
  }, [authFetch, notifyError])

  useEffect(() => { void loadUsers() }, [loadUsers])

  function applySaved(saved: ManagedUser) {
    setUsers(current => {
      const exists = current.some(user => user.id === saved.id)
      return exists ? current.map(user => user.id === saved.id ? saved : user) : [...current, saved]
    })
    setEditing(null)
  }

  return (
    <PageShell>
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">User Management</h1>
          <p className="fh-page-subtitle">Accounts, roles, and permissions.</p>
        </div>
      </div>

      <div className="flex flex-col items-start gap-4 lg:flex-row">
        <SettingsNav active="Users" />

        <section className="fh-card w-full max-w-[720px] p-[18px]">
          <div className="flex items-center gap-3">
            <h2 className="fh-section-title">Users and roles</h2>
            <button type="button" onClick={() => setEditing('create')} className="fh-button-primary fh-button-sm ms-auto">
              <Icon name="add" />
              Create user
            </button>
          </div>

          {loading ? (
            <div className="mt-4 flex items-center gap-2 fh-text-body-sm"><Spinner size="sm" />Loading users</div>
          ) : loadError ? (
            <div className="fh-alert fh-alert-danger mt-4" role="alert">
              <Icon name="error" />
              <span className="flex-1">User accounts are unavailable.</span>
              <button type="button" onClick={() => void loadUsers()} className="fh-toolbar-link"><Icon name="retry" />Retry</button>
            </div>
          ) : users.length === 0 ? (
            <Empty title="No users found" description="Create the first managed account." />
          ) : (
            <div className="mt-3.5 flex flex-col gap-2.5">
              {users.map(user => (
                <div key={user.id} className="flex flex-col gap-3 rounded-md bg-[color:var(--fh-ui-surface-muted)] p-2.5 sm:min-h-[58px] sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium leading-5 text-text-base">{user.username}</p>
                    <p className="truncate text-[11px] leading-4 text-wp-muted">
                      Created {new Date(user.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <span className="text-xs font-medium leading-4 text-[color:var(--fh-text-secondary)]">{roleLabel(user.role)}</span>
                  <Badge variant={user.is_active ? 'success' : 'neutral'} dot>{user.is_active ? 'Active' : 'Disabled'}</Badge>
                  <button type="button" onClick={() => setEditing(user)} className="fh-button-ghost fh-button-sm self-start sm:self-auto">Edit</button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {editing && (
        <UserEditor
          user={editing === 'create' ? undefined : editing}
          allowPrivilegedRoles={Boolean(currentUser?.is_super_admin)}
          onClose={() => setEditing(null)}
          onSaved={applySaved}
        />
      )}
    </PageShell>
  )
}
