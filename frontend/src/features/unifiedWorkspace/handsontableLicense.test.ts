import { describe, expect, it } from 'vitest'
import { resolveHandsontableLicense } from './handsontableLicense'

describe('Handsontable production licensing', () => {
  it.each([undefined, '', '   ', 'non-commercial-and-evaluation', 'placeholder', 'your-license-key', 'test'])(
    'blocks known invalid production value %s',
    value => expect(resolveHandsontableLicense(value, true).kind).toBe('PRODUCTION_BLOCKED'),
  )

  it('accepts a configured non-evaluation production value without exposing it', () => {
    expect(resolveHandsontableLicense('commercial-config-value', true).kind).toBe('PRODUCTION_CONFIGURED')
  })

  it('uses evaluation mode only outside production', () => {
    expect(resolveHandsontableLicense(undefined, false)).toEqual({
      kind: 'DEVELOPMENT_EVALUATION',
      licenseKey: 'non-commercial-and-evaluation',
    })
  })
})
