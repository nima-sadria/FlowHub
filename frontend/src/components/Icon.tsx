import type { HTMLAttributes } from 'react'
import {
  Activity,
  Bell,
  Calendar,
  ChartNoAxesCombined,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  CircleX,
  ClipboardList,
  Clock3,
  Copy,
  Database,
  Download,
  Ellipsis,
  Eye,
  File,
  FileText,
  Folder,
  Globe2,
  Info,
  LayoutDashboard,
  ListFilter,
  LogOut,
  Menu,
  Moon,
  Package,
  PackageOpen,
  PanelLeft,
  Pencil,
  Plug,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Store,
  Sun,
  TableProperties,
  Trash2,
  TriangleAlert,
  Unplug,
  Upload,
  UserRound,
  X,
  Zap,
  type LucideIcon,
} from 'lucide-react'

const ICONS = {
  add: Plus,
  activity: Activity,
  alert: CircleAlert,
  apply: CircleCheck,
  bell: Bell,
  calendar: Calendar,
  channel: Store,
  channels: Store,
  chevronDown: ChevronDown,
  close: X,
  commerce: PackageOpen,
  connect: Plug,
  copy: Copy,
  dashboard: LayoutDashboard,
  dataQuality: ShieldCheck,
  delete: Trash2,
  diagnostics: ChartNoAxesCombined,
  disconnect: Unplug,
  download: Download,
  dryRun: Zap,
  edit: Pencil,
  error: CircleX,
  export: Download,
  filter: ListFilter,
  file: File,
  folder: Folder,
  globe: Globe2,
  logs: FileText,
  info: Info,
  menu: Menu,
  more: Ellipsis,
  moon: Moon,
  next: ChevronRight,
  orders: ClipboardList,
  panelToggle: PanelLeft,
  previous: ChevronLeft,
  preview: Eye,
  products: Package,
  rateLimits: Clock3,
  refresh: RefreshCw,
  replay: RotateCcw,
  retry: RefreshCw,
  save: Save,
  search: Search,
  settings: Settings,
  sliders: SlidersHorizontal,
  signOut: LogOut,
  sources: Database,
  success: CircleCheck,
  sun: Sun,
  sync: RefreshCw,
  testConnection: CircleCheck,
  upload: Upload,
  user: UserRound,
  warning: TriangleAlert,
  workspace: TableProperties,
} as const satisfies Record<string, LucideIcon>

export type IconName = keyof typeof ICONS

export const routeIconMap = {
  Dashboard: 'dashboard',
  Products: 'products',
  Workspace: 'workspace',
  'Commerce Hub': 'commerce',
  Orders: 'orders',
  Sources: 'sources',
  Channels: 'channels',
  Activity: 'activity',
  'Data Quality': 'dataQuality',
  Diagnostics: 'diagnostics',
  Settings: 'settings',
  Users: 'user',
  'Rate Limits': 'sliders',
  Advanced: 'settings',
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
  ...props
}: IconProps) {
  const sizeClass = size === 'lg' ? 'fh-icon-lg' : size === 'md' ? 'fh-icon-md' : 'fh-icon-sm'
  const iconClass = ['fh-svg-icon', sizeClass, className].filter(Boolean).join(' ')
  const Glyph = ICONS[name]

  return (
    <span
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      data-icon={name}
      data-rtl-mirror={mirrorRtl ? 'true' : undefined}
      className={iconClass}
      {...props}
    >
      <Glyph aria-hidden="true" focusable="false" strokeWidth={2} />
    </span>
  )
}
