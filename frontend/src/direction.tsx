import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import i18n, { applyDocumentLocale, changeLocale, localeDirection, type FlowHubLocale } from './i18n'

interface DirectionContextValue {
  language: string
  direction: 'ltr' | 'rtl'
  setLanguage: (lang: string) => void
  setDirection: (dir: 'ltr' | 'rtl') => void
}

const DirectionContext = createContext<DirectionContextValue | null>(null)

export function DirectionProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState(i18n.resolvedLanguage ?? 'en')
  const direction = localeDirection(language)

  useEffect(() => {
    applyDocumentLocale(language)
    const changed = (locale: string) => { setLanguageState(locale); applyDocumentLocale(locale) }
    i18n.on('languageChanged', changed)
    return () => { i18n.off('languageChanged', changed) }
  }, [language])

  const setLanguage = useCallback((locale: string) => {
    if (locale === 'en' || locale === 'fa') void changeLocale(locale as FlowHubLocale)
  }, [])

  const setDirection = useCallback((_direction: 'ltr' | 'rtl') => {
    applyDocumentLocale(i18n.resolvedLanguage)
  }, [])

  return <DirectionContext.Provider value={{ language, direction, setLanguage, setDirection }}>{children}</DirectionContext.Provider>
}

export function useDirection() {
  const context = useContext(DirectionContext)
  if (!context) throw new Error('useDirection must be used inside DirectionProvider')
  return context
}
