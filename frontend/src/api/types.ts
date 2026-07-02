export interface HealthResponse {
  status: string
  env: string
  version: string
}

export interface AuthMeResponse {
  username: string
  role: string
  is_admin: boolean
  is_super_admin: boolean
  permissions: Record<string, boolean>
}

// Setup Wizard types (BU4)

export interface SetupStatus {
  completed: boolean
  has_admin: boolean
}

export interface ServerProfilePayload {
  domain: string
  port?: number
  environment?: string
  timezone: string
  currency: string
}

export interface AdminPayload {
  username: string
  email: string
  password: string
}

export interface SetupAdminResponse {
  token: string
  refresh_token: string
  username: string
}

export interface ConnectionTestResponse {
  ok: boolean
  message: string
}

export interface DatabaseStatusResponse {
  connected: boolean
  migration_version: string | null
  migrations_current: boolean
  current_revision: string | null
  latest_revision: string | null
  is_current: boolean | null
  database_name?: string | null
  error?: string | null
}
