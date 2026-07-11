import type { ChannelOrderDetail, ChannelOrderListItem, PaginatedResult } from '../types'

export interface OrderFilter {
  page: number
  pageSize: number
  channelId?: string | null
}

export interface OrderService {
  getOrders(filter: OrderFilter): Promise<PaginatedResult<ChannelOrderListItem>>
  getOrder(id: number): Promise<ChannelOrderDetail>
}
