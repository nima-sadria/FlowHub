export type HandsontableLicenseState =
  | { kind: 'DEVELOPMENT_EVALUATION'; licenseKey: 'non-commercial-and-evaluation' }
  | { kind: 'PRODUCTION_CONFIGURED'; licenseKey: string }
  | { kind: 'PRODUCTION_BLOCKED'; licenseKey: null }

const EVALUATION_KEY = 'non-commercial-and-evaluation'
const BLOCKED_VALUES = new Set([
  '',
  EVALUATION_KEY,
  'your-license-key',
  'placeholder',
  'changeme',
  'test',
])

export function resolveHandsontableLicense(
  configuredValue: string | undefined,
  production: boolean,
): HandsontableLicenseState {
  const configured = configuredValue?.trim() ?? ''
  if (production) {
    if (BLOCKED_VALUES.has(configured.toLowerCase())) {
      return { kind: 'PRODUCTION_BLOCKED', licenseKey: null }
    }
    return { kind: 'PRODUCTION_CONFIGURED', licenseKey: configured }
  }
  return { kind: 'DEVELOPMENT_EVALUATION', licenseKey: EVALUATION_KEY }
}
