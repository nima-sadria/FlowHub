// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import i18n, {
  applyDocumentLocale,
  changeLocale,
  LOCALE_STORAGE_KEY,
  translate,
} from './index'
import { localizedApiError } from './errors'
import { formatDate, formatNumber, formatPercent } from './format'

describe('FlowHub internationalization foundation', () => {
  beforeEach(async () => {
    localStorage.clear()
    await i18n.changeLanguage('en')
    applyDocumentLocale('en')
  })

  afterEach(async () => {
    await i18n.changeLanguage('en')
    applyDocumentLocale('en')
  })

  it('uses complete English resources as the fallback catalog', () => {
    expect(translate('navigation:sidebar.dashboard')).toBe('Dashboard')
    expect(translate('common:keyThatDoesNotExist', { defaultValue: 'Safe fallback' })).toBe('Safe fallback')
  })

  it('persists a supported language and rejects an incomplete production catalog', async () => {
    expect(await changeLocale('en')).toBe(true)
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en')
    expect(await changeLocale('fa')).toBe(false)
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en')
  })

  it('updates document language and direction for a test RTL catalog', async () => {
    await i18n.changeLanguage('fa')
    applyDocumentLocale('fa')
    expect(document.documentElement.lang).toBe('fa')
    expect(document.documentElement.dir).toBe('rtl')
  })

  it('preserves interpolation values and applies English plural rules', () => {
    expect(translate('workspace:workspace.tryAgainInMinutes', { count: 1 })).toBe('Try again in about 1 minute.')
    expect(translate('workspace:workspace.tryAgainInMinutes', { count: 3 })).toBe('Try again in about 3 minutes.')
    expect(translate('workspace:sourceCentricWorkspace.selectListing', {
      channel: 'woocommerce:primary',
      listing: 'SKU-FA-001',
    })).toContain('woocommerce:primary SKU-FA-001')
  })

  it('centralizes locale-aware numbers, percentages, and dates', () => {
    expect(formatNumber(1234567)).toBe(new Intl.NumberFormat('en').format(1234567))
    expect(formatPercent(0.25)).toBe(new Intl.NumberFormat('en', { style: 'percent' }).format(0.25))
    expect(formatDate('2026-01-02T00:00:00Z')).toContain('2026')
  })

  it('uses stable API error codes before diagnostic English prose', () => {
    const error = new ApiError(409, 'Backend diagnostic fallback', 'STALE_REVIEW')
    expect(localizedApiError(error)).toBe('This Review is stale. Generate a new Review before Apply.')
  })
})
