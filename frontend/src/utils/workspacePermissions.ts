export const WORKSPACE_PERMISSION = {
  read: 'workspace.read',
  create: 'workspace.create',
  edit: 'workspace.edit',
  saveDraft: 'draft.save',
  generateReview: 'review.generate',
  apply: 'apply.execute',
  refreshChannelCache: 'channel_cache.refresh',
  approveMapping: 'mapping.approve',
  readAudit: 'audit.read',
  admin: 'workspace.admin',
} as const

export type WorkspacePermission = typeof WORKSPACE_PERMISSION[keyof typeof WORKSPACE_PERMISSION]
