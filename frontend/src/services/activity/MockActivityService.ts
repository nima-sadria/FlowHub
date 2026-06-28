import type { ActivityEvent, ActivityLevel, PaginatedResult } from '../types'
import type { ActivityService } from './ActivityService'

const delay = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

function minutesAgo(m: number): Date {
  return new Date(Date.now() - m * 60 * 1000)
}

function hoursAgo(h: number): Date {
  return new Date(Date.now() - h * 3600 * 1000)
}

function makeEvent(
  id: string,
  ts: Date,
  kind: ActivityEvent['kind'],
  level: ActivityLevel,
  actor: string,
  action: string,
  detail: string | null = null,
): ActivityEvent {
  return { id, timestamp: ts, kind, level, actor, action, detail }
}

const ALL_EVENTS: ActivityEvent[] = [
  makeEvent('evt-001', minutesAgo(3),   'user_action', 'success', 'admin',  'login_success',     'IP: 192.168.1.10'),
  makeEvent('evt-002', minutesAgo(5),   'system_log',  'info',    'system', 'health_check',       'GET /api/health → 200 OK'),
  makeEvent('evt-003', minutesAgo(8),   'system_log',  'info',    'system', 'health_check',       'GET /api/health → 200 OK'),
  makeEvent('evt-004', minutesAgo(12),  'user_action', 'info',    'admin',  'token_refresh',      null),
  makeEvent('evt-005', minutesAgo(15),  'system_log',  'info',    'system', 'sync_check',         'Source: Nextcloud Price List'),
  makeEvent('evt-006', minutesAgo(22),  'user_action', 'info',    'admin',  'settings_viewed',    null),
  makeEvent('evt-007', minutesAgo(35),  'system_log',  'info',    'system', 'health_check',       'GET /api/health → 200 OK'),
  makeEvent('evt-008', minutesAgo(42),  'system_log',  'warning', 'system', 'sync_check',         'Source freshness: may have changed'),
  makeEvent('evt-009', minutesAgo(58),  'user_action', 'info',    'admin',  'token_refresh',      null),
  makeEvent('evt-010', hoursAgo(1.1),   'user_action', 'info',    'admin',  'preview_started',    'Source: Nextcloud Price List'),
  makeEvent('evt-011', hoursAgo(1.2),   'system_log',  'info',    'system', 'preview_complete',   '4 products with pending changes'),
  makeEvent('evt-012', hoursAgo(1.5),   'system_log',  'info',    'system', 'health_check',       'GET /api/health → 200 OK'),
  makeEvent('evt-013', hoursAgo(2),     'user_action', 'success', 'admin',  'login_success',      'IP: 192.168.1.10'),
  makeEvent('evt-014', hoursAgo(2.1),   'system_log',  'info',    'system', 'config_loaded',      'Environment: beta, Version: 0.1.0-dev'),
  makeEvent('evt-015', hoursAgo(2.5),   'system_log',  'info',    'system', 'health_check',       'GET /api/health → 200 OK'),
  makeEvent('evt-016', hoursAgo(3),     'user_action', 'error',   'admin',  'login_failed',       'Invalid credentials. IP: 192.168.1.10'),
  makeEvent('evt-017', hoursAgo(3.1),   'user_action', 'error',   'admin',  'login_failed',       'Invalid credentials. IP: 192.168.1.10'),
  makeEvent('evt-018', hoursAgo(3.2),   'user_action', 'success', 'admin',  'login_success',      'IP: 192.168.1.10'),
  makeEvent('evt-019', hoursAgo(4),     'system_log',  'info',    'system', 'health_check',       'GET /api/health → 200 OK'),
  makeEvent('evt-020', hoursAgo(4.5),   'user_action', 'info',    'admin',  'token_refresh',      null),
  makeEvent('evt-021', hoursAgo(5),     'system_log',  'info',    'system', 'sync_check',         'Source: Nextcloud Price List'),
  makeEvent('evt-022', hoursAgo(5.5),   'system_log',  'info',    'system', 'health_check',       'GET /api/health → 200 OK'),
  makeEvent('evt-023', hoursAgo(6),     'user_action', 'info',    'admin',  'settings_viewed',    null),
  makeEvent('evt-024', hoursAgo(6.5),   'system_log',  'info',    'system', 'health_check',       'GET /api/health → 200 OK'),
  makeEvent('evt-025', hoursAgo(7),     'user_action', 'info',    'admin',  'token_refresh',      null),
  makeEvent('evt-026', hoursAgo(8),     'system_log',  'warning', 'system', 'sync_check',         'Stale: Cable Management Kit not synced > 12h'),
  makeEvent('evt-027', hoursAgo(9),     'system_log',  'info',    'system', 'health_check',       'GET /api/health → 200 OK'),
  makeEvent('evt-028', hoursAgo(10),    'user_action', 'success', 'admin',  'login_success',      'IP: 192.168.1.10'),
  makeEvent('evt-029', hoursAgo(12),    'system_log',  'info',    'system', 'config_loaded',      'Environment: beta, Version: 0.1.0-dev'),
  makeEvent('evt-030', hoursAgo(24),    'user_action', 'info',    'admin',  'logout',             null),
]

export class MockActivityService implements ActivityService {
  async getEvents(opts: { page: number; pageSize: number }): Promise<PaginatedResult<ActivityEvent>> {
    await delay(120)
    const total = ALL_EVENTS.length
    const start = (opts.page - 1) * opts.pageSize
    const items = ALL_EVENTS.slice(start, start + opts.pageSize)
    return { items, total, page: opts.page, pageSize: opts.pageSize }
  }
}
