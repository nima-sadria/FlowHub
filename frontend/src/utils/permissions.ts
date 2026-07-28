export interface PermissionsUser {
  is_admin: boolean
  is_super_admin: boolean
  permissions?: Record<string, boolean>
}

const CANONICAL_PERMISSION_SEPARATOR = '.'

// Canonical dotted permissions are independent capabilities. Legacy can_*
// aliases retain the historical can_access_site global gate.
export function effectiveHasPerm(user: PermissionsUser | null, perm: string): boolean {
  if (!user) return false
  if (user.is_admin || user.is_super_admin) return true
  if (perm.includes(CANONICAL_PERMISSION_SEPARATOR)) {
    return user.permissions?.[perm] === true
  }
  if (!user.permissions?.['can_access_site']) return false
  return user.permissions?.[perm] === true
}
