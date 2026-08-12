import { ApiError } from '../../api/client'
import { translate } from '../../i18n'
import type { ConnectionCheckResult } from '../../services/commerce/CommerceService'

type ConnectionResultIdentity = Pick<
  ConnectionCheckResult,
  'ok' | 'status' | 'code' | 'error_class'
>

/**
 * Maps only stable, structured connection-test identifiers to localised copy.
 * Provider text is deliberately not displayed: upstream diagnostics can contain
 * credential fragments, URLs, or untranslated implementation detail.
 */
export function connectionResultMessage(result: ConnectionResultIdentity): string {
  if (result.ok) {
    return translate('diagnostics:diagnostics.connectionTestResult.success')
  }

  const identity = [result.status, result.code, result.error_class]
    .filter((value): value is string => Boolean(value))
    .join(' ')
    .trim()
    .toLowerCase()
    .replace(/[\s.-]+/g, '_')

  if (/unsafe_destination|ssrf|private_network|trusted_network|blocked_destination/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.unsafeDestination')
  }
  if (/timeout|timed_out|deadline|gateway_timeout|http_504/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.timeout')
  }
  if (/authentication|auth_failed|unauthorized|invalid_credentials|credential_rejected|authentication_rejected|http_401/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.authenticationRejected')
  }
  if (/authorization|permission|forbidden|access_denied|http_403/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.permissionDenied')
  }
  if (/(^|_)disabled($|_)|channel_disabled/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.disabled')
  }
  if (/coming_soon|channel_coming_soon/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.comingSoon')
  }
  if (/not_configured|required_settings_missing|credentials_missing|configuration_incomplete/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.notConfigured')
  }
  if (/invalid_url|malformed_url|channel_invalid_url/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.invalidUrl')
  }
  if (/invalid_webdav|invalid_path|malformed_path|webdav_path/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.invalidPath')
  }
  if (/(^|_)not_found($|_)|resource_not_found|file_not_found|spreadsheet_not_found|missing_resource|http_404/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.resourceNotFound')
  }
  if (/rate_limit|too_many_requests|http_429/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.rateLimited')
  }
  if (/unsupported|not_implemented/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.unsupported')
  }
  if (/server_failure|provider_error/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.providerError')
  }
  if (/unreachable|connection_failed|dns|network|tls|certificate|upstream_unavailable|http_50[023]/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.unreachable')
  }
  if (/validation|invalid_configuration|unprocessable|http_400|http_422/.test(identity)) {
    return translate('diagnostics:diagnostics.connectionTestResult.invalidConfiguration')
  }
  return translate('diagnostics:diagnostics.connectionTestResult.failed')
}

export function connectionExceptionMessage(error: unknown): string {
  return connectionResultMessage({
    ok: false,
    status: error instanceof Error && error.message === 'request_timeout'
      ? 'timeout'
      : error instanceof ApiError
        ? `http_${error.status}`
        : 'error',
    code: error instanceof ApiError ? error.code : undefined,
    error_class: error instanceof Error ? error.name : undefined,
  })
}
