import { ApiError, apiErrorMessage } from '../api/client'
import { translate } from './index'

const knownCodes = new Set(['AUTHENTICATION_REQUIRED', 'CACHE_STALE', 'CAPABILITY_CHANGED', 'CURRENCY_CONFIGURATION_CHANGED', 'MAPPING_CHANGED', 'PERMISSION_DENIED', 'REVIEW_REQUIRED', 'SELECTION_CHECKSUM_MISMATCH', 'SOURCE_READ_LIMIT_REACHED', 'STALE_REVIEW'])

export function localizedApiError(error: unknown, fallbackKey = 'errors:codes.UNKNOWN'): string {
  if (error instanceof ApiError && error.code && knownCodes.has(error.code)) return translate(`errors:codes.${error.code}`)
  return apiErrorMessage(error, translate(fallbackKey))
}
