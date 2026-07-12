import type { CSSProperties, HTMLAttributes } from 'react'

const ICON_PATHS = {
  add: 'plus.svg',
  activity: 'docs.svg',
  alert: 'alert.svg',
  apply: 'check-circle.svg',
  calendar: 'calendar.svg',
  channel: 'plug-in.svg',
  close: 'close.svg',
  commerce: 'box-cube.svg',
  connect: 'plug-in.svg',
  copy: 'copy.svg',
  dashboard: 'grid.svg',
  delete: 'trash.svg',
  diagnostics: 'pie-chart.svg',
  disconnect: 'close-line.svg',
  download: 'download.svg',
  dryRun: 'bolt.svg',
  edit: 'pencil.svg',
  error: 'info-error.svg',
  export: 'download.svg',
  filter: 'list.svg',
  file: 'file.svg',
  folder: 'folder.svg',
  logs: 'page.svg',
  info: 'info.svg',
  next: 'angle-right.svg',
  orders: 'task-icon.svg',
  previous: 'angle-left.svg',
  preview: 'eye.svg',
  products: 'box.svg',
  rateLimits: 'time.svg',
  refresh: 'arrow-up.svg',
  replay: 'paper-plane.svg',
  retry: 'arrow-up.svg',
  save: 'check-line.svg',
  search: 'eye.svg',
  settings: 'user-circle.svg',
  success: 'check-circle.svg',
  sync: 'arrow-down.svg',
  testConnection: 'check-circle.svg',
  upload: 'arrow-up.svg',
  warning: 'alert.svg',
  workspace: 'shooting-star.svg',
} as const

export type IconName = keyof typeof ICON_PATHS

export const routeIconMap = {
  Dashboard: 'dashboard',
  Products: 'products',
  Workspace: 'workspace',
  'Commerce Hub': 'commerce',
  Orders: 'orders',
  Activity: 'activity',
  Diagnostics: 'diagnostics',
  Settings: 'settings',
  'Rate Limits': 'rateLimits',
  Logs: 'logs',
} as const satisfies Record<string, IconName>

interface IconProps extends HTMLAttributes<HTMLSpanElement> {
  name: IconName
  label?: string
  size?: 'sm' | 'md' | 'lg'
  mirrorRtl?: boolean
}

export default function Icon({
  name,
  label,
  size = 'sm',
  mirrorRtl = false,
  className = '',
  style,
  ...props
}: IconProps) {
  const sizeClass =
    size === 'lg' ? 'fh-icon-lg' :
    size === 'md' ? 'fh-icon-md' :
    'fh-icon-sm'
  return (
    <span
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      data-icon={name}
      data-rtl-mirror={mirrorRtl ? 'true' : undefined}
      className={['fh-svg-icon', sizeClass, className].filter(Boolean).join(' ')}
      style={{
        '--fh-icon-url': `url("/static/icons/${ICON_PATHS[name]}")`,
        ...style,
      } as CSSProperties}
      {...props}
    />
  )
}
