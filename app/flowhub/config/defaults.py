"""FlowHub - Configuration defaults and constants.

Default values applied when optional environment variables are absent.
Core startup variables have no defaults. Connector credentials are optional and
may be configured after setup from Settings.
"""

DEFAULTS: dict[str, str | int | bool] = {
    "FLOWHUB_LOG_LEVEL": "INFO",
    "FLOWHUB_JWT_ACCESS_TTL_MINUTES": 15,
    "FLOWHUB_JWT_REFRESH_TTL_DAYS": 7,
    "FLOWHUB_MAX_UPLOAD_MB": 50,
    "FLOWHUB_PLUGIN_DIR": "",  # computed at runtime: $FLOWHUB_STORAGE_PATH/plugins
    "FLOWHUB_WORKER_CONCURRENCY": 2,
    "FLOWHUB_SCHEDULER_POLL_SECONDS": 30,
    "FLOWHUB_ORDER_SYNC_ENABLED": "true",
    "FLOWHUB_ORDER_SYNC_RUNNER_POLL_SECONDS": 30,
    "FLOWHUB_ORDER_SYNC_POLL_INTERVAL_SECONDS": 300,
    "FLOWHUB_ORDER_SYNC_RECONCILE_INTERVAL_SECONDS": 900,
    "FLOWHUB_ORDER_SYNC_LEASE_SECONDS": 900,
    "FLOWHUB_ORDER_SYNC_MAX_PAGES": 10,
    "FLOWHUB_ORDER_SYNC_RECONCILE_PAGE_SIZE": 50,
    "FLOWHUB_ORDER_SYNC_WEBHOOK_BATCH_SIZE": 100,
    "FLOWHUB_ORDER_SYNC_OPERATION_TIMEOUT_SECONDS": 60,
    "FLOWHUB_BACKUP_RETAIN_DAYS": 30,
}

LOG_LEVELS: frozenset[str] = frozenset({
    "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
})

SSL_MODES: frozenset[str] = frozenset({
    "off", "self-signed", "letsencrypt", "manual"
})
