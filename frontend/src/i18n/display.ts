import i18n, { translate } from './index'

const statusAliases: Record<string, string> = {
  authentication_failed: 'authenticationFailed',
  completed_with_errors: 'completedWithErrors',
  draft_saved: 'draftSaved',
  in_progress: 'inProgress',
  not_configured: 'notConfigured',
  not_read: 'notRead',
  not_required: 'notRequired',
  not_run: 'notRun',
  read_only: 'readOnly',
  reconciliation_required: 'reconciliationRequired',
  stale_review: 'staleReview',
  unable_to_check: 'unableToCheck',
}

const capabilityAliases: Record<string, string> = {
  category_read: 'categoryRead',
  inventory_read: 'inventoryRead',
  order_read: 'orderRead',
  polling: 'polling',
  price_write: 'priceWrite',
  product_read: 'productRead',
  read_categories: 'categoryRead',
  read_inventory: 'inventoryRead',
  read_orders: 'orderRead',
  read_products: 'productRead',
  status_write: 'statusWrite',
  stock_quantity_read: 'stockQuantityRead',
  stock_quantity_write: 'stockQuantityWrite',
  stock_status_read: 'stockStatusRead',
  stock_status_write: 'stockStatusWrite',
  stock_write: 'stockWrite',
  sku_read: 'skuRead',
  sku_write: 'skuWrite',
  special_price_read: 'specialPriceRead',
  special_price_write: 'specialPriceWrite',
  webhook: 'webhook',
  write_prices: 'priceWrite',
  write_status: 'statusWrite',
  write_stock: 'stockWrite',
  planned_channel_unavailable_in_1_0_0: 'plannedChannelUnavailableIn1_0_0',
}

const dataRoleAliases: Record<string, string> = {
  data_layer: 'dataLayer',
  file_import_input: 'fileImportInput',
  spreadsheet_price_input: 'spreadsheetPriceInput',
  system_import_input: 'systemImportInput',
}

const commerceTypeAliases: Record<string, string> = {
  data_layer: 'dataLayer',
  flowhub_data_layer: 'flowhubDataLayer',
}

const diagnosticMessageKeys: Record<string, string> = {
  'A vendor is selected.': 'vendorSelected',
  'Accepted webhook receipts are waiting for processing.': 'webhookReceiptsWaiting',
  'Capability advertised; FlowHub Apply protections still apply.': 'capabilityApplyProtections',
  'Channel configuration is incomplete.': 'channelConfigurationIncomplete',
  'Channel diagnostics are temporarily unavailable.': 'channelDiagnosticsUnavailable',
  'Channel does not use webhooks.': 'channelDoesNotUseWebhooks',
  'Channel health is derived from the unified diagnostics source.': 'channelHealthDerived',
  'Channel is disabled.': 'channelDisabled',
  'Complete channel configuration and credentials.': 'completeChannelConfiguration',
  'Configure the channel before checking reachability.': 'configureBeforeReachability',
  'Configured, but no recent product or order sync has been recorded.': 'configuredWithoutRecentSync',
  'Credential validation failed.': 'credentialValidationFailed',
  'Credential validation passed.': 'credentialValidationPassed',
  'Credential validation uses the lightweight provider probe.': 'credentialValidationProbe',
  'Credentials are not fully configured.': 'credentialsIncomplete',
  'Enable the channel when it should be monitored.': 'enableChannelForMonitoring',
  'Last successful sync is stale.': 'lastSuccessfulSyncStale',
  'No dead letters.': 'noDeadLetters',
  'No health check has been recorded.': 'noHealthCheckRecorded',
  'No immediate action required.': 'noImmediateAction',
  'No order event polling checkpoint has run.': 'noPollingCheckpoint',
  'No processed webhook receipt yet.': 'noProcessedWebhookReceipt',
  'No product synchronization has been run.': 'noProductSynchronization',
  'No successful sync has been recorded.': 'noSuccessfulSync',
  'No webhook receipt has been accepted yet.': 'noWebhookReceipt',
  'Order polling is not used for this channel.': 'orderPollingUnused',
  'Provider probe failed.': 'providerProbeFailed',
  'Provider probe was inconclusive.': 'providerProbeInconclusive',
  'Recent successful sync recorded.': 'recentSuccessfulSync',
  'Required configuration is incomplete.': 'requiredConfigurationIncomplete',
  'Required configuration is present.': 'requiredConfigurationPresent',
  'Retry the diagnostic check.': 'retryDiagnosticCheck',
  'Review queued webhook receipts.': 'reviewQueuedWebhookReceipts',
  'Review and replay or resolve webhook dead letters.': 'reviewWebhookDeadLetters',
  'Select a vendor before product synchronization.': 'selectVendorBeforeSync',
  'The latest product synchronization failed; the previous cache was preserved.': 'productSyncFailedCachePreserved',
  'The local product cache was refreshed successfully.': 'productCacheRefreshed',
  'Token refresh is not supported for this channel.': 'tokenRefreshUnsupported',
  'Update credentials and run an explicit health refresh.': 'updateCredentialsAndRefresh',
  'Webhook dead letters are present.': 'webhookDeadLettersPresent',
  'Webhook dead letters require operator review.': 'webhookDeadLettersRequireReview',
  'Webhook receipts are being accepted.': 'webhookReceiptsAccepted',
}

function normalize(value: string): string {
  return value.trim().toLowerCase().replace(/[.\s/-]+/g, '_').replace(/^_+|_+$/g, '')
}

export function formatRole(value: string | null | undefined): string {
  if (!value) return '-'
  const normalized = value.trim().replace(/[-_]+(.)/g, (_, character: string) => character.toUpperCase())
  const key = `common:role.${normalized}`
  return i18n.exists(key) ? translate(key) : value
}

export function formatStatus(value: string | null | undefined): string {
  if (!value) return translate('common:status.unknown')
  const normalized = normalize(value)
  const key = `common:status.${statusAliases[normalized] ?? normalized}`
  if (i18n.exists(key)) return translate(key)
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, character => character.toUpperCase())
}

export function formatProductType(value: string | null | undefined): string {
  const normalized = normalize(value || 'simple')
  const key = `products:productType.${normalized}`
  return i18n.exists(key) ? translate(key) : value || translate('products:productType.simple')
}

export function formatCapability(value: string): string {
  const normalized = normalize(value)
  const key = `commerce:capability.${capabilityAliases[normalized] ?? normalized}`
  return i18n.exists(key) ? translate(key) : value
}

export function formatCapabilityList(values: string[]): string {
  const separator = (i18n.resolvedLanguage ?? 'en').startsWith('fa') ? '، ' : ', '
  return values.map(formatCapability).join(separator)
}

export function formatDataRole(value: string | null | undefined): string {
  if (!value) return translate('common:status.unknown')
  const normalized = normalize(value)
  const key = `commerce:dataRole.${dataRoleAliases[normalized] ?? normalized}`
  return i18n.exists(key) ? translate(key) : value
}

export function formatCommerceType(value: string | null | undefined): string {
  if (!value) return translate('common:status.unknown')
  const normalized = normalize(value)
  const key = `commerce:type.${commerceTypeAliases[normalized] ?? normalized}`
  return i18n.exists(key) ? translate(key) : value
}

export function formatDiagnosticDimension(value: string): string {
  const key = `diagnostics:dimension.${value}`
  return i18n.exists(key) ? translate(key) : value
}

export function formatDiagnosticMessage(value: string | null | undefined): string {
  if (!value) return ''
  const operational = value.match(/^(.+) is operational\.$/)
  if (operational) return translate('diagnostics:message.channelOperational', { channel: operational[1] })
  const key = diagnosticMessageKeys[value]
  return key ? translate(`diagnostics:message.${key}`) : value
}

export function formatDataQualityCategory(value: string): string {
  const key = `dataQuality:category.${normalize(value)}`
  return i18n.exists(key) ? translate(key) : value.replace(/[_-]+/g, ' ')
}

export function formatDataQualityIssue(
  code: string,
  part: 'summary' | 'action',
  fallback: string,
  details: Record<string, unknown> = {},
): string {
  const key = `dataQuality:issue.${code}.${part}`
  if (!i18n.exists(key)) return fallback
  const field = typeof details.field === 'string' ? formatField(details.field) : ''
  return translate(key, { field })
}

export function formatField(value: string): string {
  const key = `common:field.${value.toLowerCase()}`
  return i18n.exists(key) ? translate(key) : value
}
