// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import i18n, { applyDocumentLocale, changeLocale, translate } from './index'
import {
  formatCapability,
  formatCommerceType,
  formatDataRole,
  formatDiagnosticDimension,
  formatDiagnosticMessage,
  formatProductType,
  formatStatus,
} from './display'

describe('Persian presentation mappings', () => {
  beforeEach(async () => {
    await changeLocale('fa')
  })

  afterEach(async () => {
    await i18n.changeLanguage('en')
    applyDocumentLocale('en')
  })

  it('localizes common API statuses without changing their contract values', () => {
    expect(formatStatus('Connected')).toBe('متصل')
    expect(formatStatus('configured')).toBe('پیکربندی‌شده')
    expect(formatStatus('not_configured')).toBe('پیکربندی‌نشده')
    expect(formatStatus('Healthy')).toBe('سالم')
    expect(formatStatus('Completed With Errors')).toBe('با خطا تکمیل شد')
    expect(formatStatus('Disabled')).toBe('غیرفعال')
    expect(formatStatus('Global')).toBe('سراسری')
  })

  it('localizes Commerce Hub types, data roles, and capability labels', () => {
    expect(formatCommerceType('Channel')).toBe('کانال')
    expect(formatCommerceType('Source')).toBe('منبع')
    expect(formatCommerceType('Data Layer')).toBe('لایه داده')
    expect(formatDataRole('Spreadsheet price input')).toBe('ورودی قیمت از صفحه‌گسترده')
    expect(formatCapability('Product read')).toBe('خواندن محصولات')
    expect(formatCapability('write_stock')).toBe('نوشتن موجودی')
    expect(formatCapability('status.write')).toBe('نوشتن وضعیت')
  })

  it('localizes product types and table labels', () => {
    expect(formatProductType('simple')).toBe('ساده')
    expect(formatProductType('variable')).toBe('متغیر')
    expect(formatProductType('variation')).toBe('تنوع')
    expect(translate('products:column.select')).toBe('انتخاب')
    expect(translate('products:column.product')).toBe('محصول')
    expect(translate('products:column.actions')).toBe('عملیات')
  })

  it('localizes known diagnostics while preserving HTTP codes', () => {
    expect(translate('diagnostics:diagnostics.unavailableHttp', { status: 401 }))
      .toBe('بخش عیب‌یابی در دسترس نیست (HTTP 401)')
    expect(formatDiagnosticDimension('credentials')).toBe('اطلاعات ورود')
    expect(formatDiagnosticMessage('Credential validation passed.')).toBe('اعتبارسنجی اطلاعات ورود موفق بود.')
    expect(formatDiagnosticMessage('WooCommerce is operational.')).toBe('WooCommerce عملیاتی است.')
  })

  it('preserves usernames, product names, SKUs, and technical identities', () => {
    const username = 'admin'
    const product = 'iPhone Cable'
    const sku = 'SKU-FA-001'
    const channel = 'woocommerce:primary'
    expect(username).toBe('admin')
    expect(product).toBe('iPhone Cable')
    expect(translate('workspace:sourceCentricWorkspace.selectListing', { channel, listing: sku }))
      .toContain(`${channel}، ${sku}`)
  })
})
