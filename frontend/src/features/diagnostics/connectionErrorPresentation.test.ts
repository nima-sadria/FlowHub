// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { changeLocale, translate } from '../../i18n'
import { connectionResultMessage } from './connectionErrorPresentation'

function failedConnection(overrides: Partial<{
  status: string
  code: string
  error_class: string
}> = {}) {
  return {
    ok: false,
    status: 'error',
    ...overrides,
  }
}

describe('connection error presentation', () => {
  beforeEach(async () => { await changeLocale('en') })

  it.each([
    ['not_found', 'diagnostics:diagnostics.connectionTestResult.resourceNotFound'],
    ['server_failure', 'diagnostics:diagnostics.connectionTestResult.providerError'],
    ['provider_error', 'diagnostics:diagnostics.connectionTestResult.providerError'],
    ['disabled', 'diagnostics:diagnostics.connectionTestResult.disabled'],
    ['coming_soon', 'diagnostics:diagnostics.connectionTestResult.comingSoon'],
  ])('maps the backend %s alias to safe localised copy', (alias, key) => {
    expect(connectionResultMessage(failedConnection({ error_class: alias }))).toBe(translate(key))
  })

  it('uses structured identity instead of exposing provider failure text', () => {
    const providerFailure = {
      ...failedConnection({ code: 'provider_error' }),
      message: 'Authorization: Bearer secret-that-must-not-be-displayed',
    }
    const message = connectionResultMessage(providerFailure)

    expect(message).toBe(translate('diagnostics:diagnostics.connectionTestResult.providerError'))
    expect(message).not.toContain('secret-that-must-not-be-displayed')
  })
})
