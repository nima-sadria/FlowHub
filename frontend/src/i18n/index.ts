import i18n, { type TOptions } from 'i18next'
import { initReactI18next } from 'react-i18next'

export const namespaces = ['common', 'navigation', 'authentication', 'dashboard', 'products', 'orders', 'sources', 'commerce', 'workspace', 'flowhubSheet', 'dataQuality', 'activity', 'diagnostics', 'settings', 'validation', 'errors', 'notifications'] as const
export type FlowHubLocale = 'en' | 'fa'
export const LOCALE_STORAGE_KEY = 'flowhub.locale'
export const DEFAULT_LOCALE: FlowHubLocale = 'en'

type RuntimeResources = Record<string, Record<string, Record<string, string>>>
const localeModules = import.meta.glob('./locales/*/*.json', { eager: true, import: 'default' }) as Record<string, Record<string, string>>
const manifestModules = import.meta.glob('./locales/*/manifest.json', { eager: true, import: 'default' }) as Record<string, { complete?: boolean }>
const resources: RuntimeResources = {}

for (const [file, messages] of Object.entries(localeModules)) {
  const match = file.match(/\/locales\/([^/]+)\/([^/]+)\.json$/)
  if (!match) continue
  const [, locale, namespace] = match
  if (namespace === 'manifest') continue
  resources[locale] ??= {}
  resources[locale][namespace] = messages
}

const pseudoRtlEnabled = import.meta.env.VITE_ENABLE_PSEUDO_RTL === 'true'
if (pseudoRtlEnabled) {
  resources.fa = Object.fromEntries(namespaces.map(namespace => [
    namespace,
    Object.fromEntries(Object.entries(resources.en?.[namespace] ?? {}).map(([key, value]) => [key, `\u27e6${value}\u27e7`])),
  ]))
}

export const localeMetadata: Record<FlowHubLocale, { direction: 'ltr' | 'rtl'; complete: boolean }> = {
  en: { direction: 'ltr', complete: true },
  fa: {
    direction: 'rtl',
    complete: pseudoRtlEnabled || Object.entries(manifestModules).some(([file, manifest]) => /\/fa\/manifest\.json$/.test(file) && manifest.complete === true),
  },
}

function initialLocale(): FlowHubLocale {
  if (typeof window === 'undefined') return DEFAULT_LOCALE
  const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY)
  return stored === 'fa' && localeMetadata.fa.complete ? 'fa' : DEFAULT_LOCALE
}

void i18n.use(initReactI18next).init({
  resources,
  lng: initialLocale(),
  fallbackLng: DEFAULT_LOCALE,
  defaultNS: 'common',
  ns: namespaces,
  interpolation: { escapeValue: false },
  returnNull: false,
})

export function translate(key: string, options?: TOptions): string {
  return i18n.t(key, options)
}

export function localeDirection(locale = i18n.resolvedLanguage ?? DEFAULT_LOCALE): 'ltr' | 'rtl' {
  return localeMetadata[locale.startsWith('fa') ? 'fa' : 'en'].direction
}

export function applyDocumentLocale(locale = i18n.resolvedLanguage ?? DEFAULT_LOCALE): void {
  const normalized: FlowHubLocale = locale.startsWith('fa') ? 'fa' : 'en'
  document.documentElement.lang = normalized
  document.documentElement.dir = localeDirection(normalized)
}

export async function changeLocale(locale: FlowHubLocale): Promise<boolean> {
  if (!localeMetadata[locale].complete) return false
  await i18n.changeLanguage(locale)
  localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  applyDocumentLocale(locale)
  return true
}

export default i18n
