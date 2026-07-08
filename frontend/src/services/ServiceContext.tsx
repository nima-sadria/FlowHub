import { createContext, useContext, type ReactNode } from 'react'
import type { HealthService } from './health/HealthService'
import type { ProductService } from './products/ProductService'
import type { SourceService } from './sources/SourceService'
import type { WorkspaceService } from './workspace/WorkspaceService'
import type { SettingsService } from './settings/SettingsService'
import type { ActivityService } from './activity/ActivityService'
import type { CommerceService } from './commerce/CommerceService'
import type { WritePipelineService } from './writePipeline/WritePipelineService'

export interface Services {
  health: HealthService
  products: ProductService
  sources: SourceService
  workspace: WorkspaceService
  settings: SettingsService
  activity: ActivityService
  commerce: CommerceService
  writePipeline: WritePipelineService
}

const ServiceContext = createContext<Services | null>(null)

export function ServiceProvider({ services, children }: { services: Services; children: ReactNode }) {
  return <ServiceContext.Provider value={services}>{children}</ServiceContext.Provider>
}

export function useServices(): Services {
  const ctx = useContext(ServiceContext)
  if (!ctx) throw new Error('useServices must be used inside ServiceProvider')
  return ctx
}
