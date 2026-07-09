import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'

export type NotificationType = 'info' | 'success' | 'warning' | 'error'

export interface Notification {
  id: string
  type: NotificationType
  message: string
  duration: number
}

interface NotificationContextValue {
  notifications: Notification[]
  show: (type: NotificationType, message: string, duration?: number) => void
  dismiss: (id: string) => void
}

export const NotificationContext = createContext<NotificationContextValue | null>(null)

const MAX_NOTIFICATIONS = 5
const DEFAULT_DURATION = 4000

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  const dismiss = useCallback((id: string) => {
    clearTimeout(timersRef.current[id])
    delete timersRef.current[id]
    setNotifications(prev => prev.filter(n => n.id !== id))
  }, [])

  const show = useCallback((type: NotificationType, message: string, duration = DEFAULT_DURATION) => {
    const id = crypto.randomUUID()
    const notification: Notification = { id, type, message, duration }
    setNotifications(prev => {
      const duplicate = prev.find(n => n.type === type && n.message === message)
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
    info: (msg: string, dur?: number) => show('info', msg, dur),
    success: (msg: string, dur?: number) => show('success', msg, dur),
    warning: (msg: string, dur?: number) => show('warning', msg, dur),
    error: (msg: string, dur?: number) => show('error', msg, dur),
    dismiss,
  }), [show, dismiss])
}
