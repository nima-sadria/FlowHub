import { apiFetch } from '../../api/client'
import { authFetch } from '../../api/authFetch'
import type { ChannelOrderDetail, ChannelOrderListItem, PaginatedResult } from '../types'
import type { OrderFilter, OrderService } from './OrderService'

export class ApiOrderService implements OrderService {
  async getOrders(filter: OrderFilter): Promise<PaginatedResult<ChannelOrderListItem>> {
    const params = new URLSearchParams({
      page: String(filter.page),
      pageSize: String(filter.pageSize),
    })
    if (filter.channelId) params.set('channelId', filter.channelId)
    return apiFetch<PaginatedResult<ChannelOrderListItem>>(`/api/v2/orders?${params}`, authFetch)
  }

  async getOrder(id: number): Promise<ChannelOrderDetail> {
    return apiFetch<ChannelOrderDetail>(`/api/v2/orders/${encodeURIComponent(String(id))}`, authFetch)
  }
}
