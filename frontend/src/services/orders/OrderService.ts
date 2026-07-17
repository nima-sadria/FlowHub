import type { ChannelOrderDetail, ChannelOrderListItem, PaginatedResult } from '../types'

export interface OrderFilter {
  page: number
  pageSize: number
  channelId?: string | null
  status?: string | null
  search?: string | null
  dateFrom?: string | null
  dateTo?: string | null
}

export interface OrderSyncStatus {
  channelId: string
  connectorType: string
  displayName: string
  enabled: boolean
  state: 'never_run' | 'ready' | 'disabled' | 'error'
  lastRunAt: string | null
  lastSuccessAt: string | null
  lastFailureAt: string | null
  failureCategory: string | null
}

export interface OrderSyncResult {
  channelId: string
  source: string
  processed: number
  duplicates: number
  state: string
  canonicalInventoryMutated: false
  productPricesWritten: false
  providerMutationPerformed: false
}

export interface OrderService {
  getOrders(filter: OrderFilter): Promise<PaginatedResult<ChannelOrderListItem>>
  getOrder(id: number): Promise<ChannelOrderDetail>
  getSyncStatus(): Promise<{ items: OrderSyncStatus[] }>
  syncChannel(channelId: string): Promise<OrderSyncResult>
}
