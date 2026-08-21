import { createContext, useContext, type ReactNode } from 'react'
import type { HealthService } from './health/HealthService'
import type { ProductService } from './products/ProductService'
import type { SourceService } from './sources/SourceService'
import type { SettingsService } from './settings/SettingsService'
import type { ActivityService } from './activity/ActivityService'
import type { CommerceService } from './commerce/CommerceService'
import type { WritePipelineService } from './writePipeline/WritePipelineService'
import type { OrderService } from './orders/OrderService'
import type { UnifiedWorkspaceService } from './unifiedWorkspace/UnifiedWorkspaceService'
import type { ExchangeRateService } from './exchangeRates/ExchangeRateService'
import type { BusinessEventService } from './businessEvents/BusinessEventService'

export interface Services {
  health: HealthService
  products: ProductService
  sources: SourceService
  settings: SettingsService
  activity: ActivityService
  commerce: CommerceService
  writePipeline: WritePipelineService
  orders?: OrderService
  unifiedWorkspace?: UnifiedWorkspaceService
  exchangeRates?: ExchangeRateService
  businessEvents?: BusinessEventService
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

export function useOptionalServices(): Services | null {
  return useContext(ServiceContext)
}
