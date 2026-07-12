import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'

export type NotificationType = 'info' | 'success' | 'warning' | 'error'

export interface NotificationContent {
  title: string
  description?: string
}

export type NotificationInput = string | NotificationContent

export interface Notification {
  id: string
  type: NotificationType
  title: string
  description?: string
  duration: number
}

interface NotificationContextValue {
  notifications: Notification[]
  show: (type: NotificationType, content: NotificationInput, duration?: number) => void
  dismiss: (id: string) => void
}

export const NotificationContext = createContext<NotificationContextValue | null>(null)

const MAX_NOTIFICATIONS = 5
const DEFAULT_DURATION = 4000
let notificationIdCounter = 0

function nextNotificationId(): string {
  const randomUUID = globalThis.crypto?.randomUUID
  if (typeof randomUUID === 'function') return randomUUID.call(globalThis.crypto)
  notificationIdCounter += 1
  return `notification-${Date.now().toString(36)}-${notificationIdCounter.toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  const dismiss = useCallback((id: string) => {
    clearTimeout(timersRef.current[id])
    delete timersRef.current[id]
    setNotifications(prev => prev.filter(n => n.id !== id))
  }, [])

  const show = useCallback((type: NotificationType, content: NotificationInput, duration = DEFAULT_DURATION) => {
    const id = nextNotificationId()
    const { title, description } = typeof content === 'string' ? { title: content } : content
    const notification: Notification = { id, type, title, description, duration }
    setNotifications(prev => {
      const duplicate = prev.find(n => (
        n.type === type && n.title === title && n.description === description
      ))
      if (duplicate) {
        clearTimeout(timersRef.current[duplicate.id])
        delete timersRef.current[duplicate.id]
      }
      const next = [notification, ...prev.filter(n => n.id !== duplicate?.id)]
      return next.length > MAX_NOTIFICATIONS ? next.slice(0, MAX_NOTIFICATIONS) : next
    })
    if (duration > 0) {
      timersRef.current[id] = setTimeout(() => {
        dismiss(id)
      }, duration)
    }
  }, [dismiss])

  const value = useMemo(() => ({ notifications, show, dismiss }), [notifications, show, dismiss])

  return <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>
}

export function useNotification() {
  const ctx = useContext(NotificationContext)
  if (!ctx) throw new Error('useNotification must be used inside NotificationProvider')
  const { show, dismiss } = ctx
  return useMemo(() => ({
    info: (content: NotificationInput, dur?: number) => show('info', content, dur),
    success: (content: NotificationInput, dur?: number) => show('success', content, dur),
    warning: (content: NotificationInput, dur?: number) => show('warning', content, dur),
    error: (content: NotificationInput, dur?: number) => show('error', content, dur),
    dismiss,
  }), [show, dismiss])
}
