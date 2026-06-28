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
