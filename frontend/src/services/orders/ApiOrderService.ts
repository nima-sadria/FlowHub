import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'
import type { ChannelOrderDetail, ChannelOrderListItem, PaginatedResult } from '../types'
import type { OrderFilter, OrderService, OrderSyncResult, OrderSyncStatus } from './OrderService'

export class ApiOrderService implements OrderService {
  async getOrders(filter: OrderFilter): Promise<PaginatedResult<ChannelOrderListItem>> {
    const params = new URLSearchParams({
      page: String(filter.page),
      pageSize: String(filter.pageSize),
    })
    if (filter.channelId) params.set('channelId', filter.channelId)
    if (filter.status) params.set('status', filter.status)
    if (filter.search) params.set('search', filter.search)
    if (filter.dateFrom) params.set('dateFrom', filter.dateFrom)
    if (filter.dateTo) params.set('dateTo', filter.dateTo)
    return apiFetch<PaginatedResult<ChannelOrderListItem>>(`/api/v2/orders?${params}`, authFetch)
  }

  async getOrder(id: number): Promise<ChannelOrderDetail> {
    return apiFetch<ChannelOrderDetail>(`/api/v2/orders/${encodeURIComponent(String(id))}`, authFetch)
  }

  async getSyncStatus(): Promise<{ items: OrderSyncStatus[] }> {
    return apiFetch<{ items: OrderSyncStatus[] }>('/api/v2/orders/sync-status', authFetch)
  }

  async syncChannel(channelId: string): Promise<OrderSyncResult> {
    return apiFetch<OrderSyncResult>(
      `/api/v2/orders/channels/${encodeURIComponent(channelId)}/sync`,
      authFetch,
      { method: 'POST' },
    )
  }
}
