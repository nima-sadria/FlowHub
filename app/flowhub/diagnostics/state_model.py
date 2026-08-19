"""Canonical, backend-owned Diagnostics state projection.

The projection reads persisted evidence only.  Provider I/O belongs to explicit
commands or the existing background runner and is never performed here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Iterable

from sqlalchemy import func, inspect
from sqlalchemy.orm import Session

from app.flowhub.channels.contracts import ChannelCapability
from app.flowhub.channels.registry import default_marketplace_registry
from app.flowhub.config.values import parse_config_bool
from app.flowhub.data_layer.job_lifecycle import RefreshJobLifecycle
from app.flowhub.data_layer.models import (
    DlChannelEntityWork,
    DlConnectorHealth,
    DlProductCache,
    DlRefreshJob,
    DlSourceSnapshot,
)
from app.flowhub.integration_platform.models import (
    IntegrationConnectorEvent,
    IntegrationConnectorInstance,
    IntegrationConnectorSetting,
)
from app.flowhub.orders.models import OrderSyncCheckpoint
from app.flowhub.read_engine.observation_confidence import ObservationConfidence
from app.flowhub.source_acquisition.models import AcquisitionRun
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.source_workspace.service import SourceWorkspaceService
from app.flowhub.webhooks.models import WebhookDeadLetter, WebhookReceipt


DEFAULT_CHANNELS: tuple[tuple[str, str, str], ...] = (
    ("woocommerce:primary", "woocommerce", "WooCommerce"),
    ("snappshop:main", "snappshop", "SnappShop"),
    ("tapsishop:main", "tapsishop", "TapsiShop"),
    ("technolife:main", "technolife", "Technolife"),
    ("digikala:main", "digikala", "Digikala"),
)
DEFAULT_CHANNEL_BY_ID = {item[0]: item for item in DEFAULT_CHANNELS}
COMING_SOON_PROVIDERS = frozenset({"digikala"})
SOURCE_CONNECTOR_TYPES = frozenset({"nextcloud", "csv", "gsheets", "erp"})


class ConnectivityState(StrEnum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReadinessState(StrEnum):
    READY = "READY"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    BLOCKED = "BLOCKED"
    DISABLED = "DISABLED"
    ARCHIVED = "ARCHIVED"
    COMING_SOON = "COMING_SOON"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FreshnessState(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    NEVER_RUN = "NEVER_RUN"
    NOT_SCHEDULED = "NOT_SCHEDULED"
    NOT_ENABLED = "NOT_ENABLED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CapabilitySupport(StrEnum):
    SUPPORTED_ENABLED = "SUPPORTED_ENABLED"
    SUPPORTED_DISABLED = "SUPPORTED_DISABLED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    COMING_SOON = "COMING_SOON"


class ScheduleMode(StrEnum):
    SCHEDULED = "SCHEDULED"
    EVENT_DRIVEN = "EVENT_DRIVEN"
    # Provider pushes changes as they happen AND an operator has additionally
    # configured a periodic reconciliation poll as a safety net. Both facts are
    # true at once; collapsing either one into the other loses information.
    EVENT_DRIVEN_WITH_RECONCILIATION = "EVENT_DRIVEN_WITH_RECONCILIATION"
    MANUAL = "MANUAL"
    NOT_SCHEDULED = "NOT_SCHEDULED"
    NOT_ENABLED = "NOT_ENABLED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


EVENT_DRIVEN_MODES = frozenset(
    {ScheduleMode.EVENT_DRIVEN, ScheduleMode.EVENT_DRIVEN_WITH_RECONCILIATION}
)


class ReconciliationMode(StrEnum):
    """Whether a *reconciliation* pass exists, independent of event delivery."""

    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"
    DISABLED = "DISABLED"


class RunnerState(StrEnum):
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    # A live, healthy runner that has real executable work waiting. Distinct
    # from IDLE (live and nothing to do) and from RUNNING (currently executing
    # a job in this heartbeat). A queue depth above zero must never present as
    # IDLE: that contradiction is what made the tile untrustworthy.
    PENDING = "PENDING"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class OverallState(StrEnum):
    ERROR = "ERROR"
    BLOCKED = "BLOCKED"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    HEALTHY = "HEALTHY"
    # Lifecycle-excluded states. These take precedence over connection-health
    # coloring: a resource that is intentionally non-operational must never
    # render as HEALTHY (or any other operational state) in Recent Checks or
    # anywhere else this projection is displayed.
    ARCHIVED = "ARCHIVED"
    COMING_SOON = "COMING_SOON"
    DISABLED = "DISABLED"


class OutcomeState(StrEnum):
    SUCCESSFUL = "SUCCESSFUL"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    RUNNING = "RUNNING"
    CANCELLED = "CANCELLED"
    NEVER_RUN = "NEVER_RUN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CapabilityPolicy:
    mode: ScheduleMode
    enabled: bool
    interval_seconds: int | None
    freshness_ttl_seconds: int | None
    policy_source: str
    jitter_seconds: int = 0
    # An explicit, connector-declared requirement that this capability have
    # current evidence for the resource to be READY.  Never inferred from
    # `mode == SCHEDULED` alone: an operator choosing to schedule a capability
    # is a separate fact from the connector contract requiring it.
    required_for_readiness: bool = False

    def shape(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "enabled": self.enabled,
            "intervalSeconds": self.interval_seconds,
            "jitterSeconds": self.jitter_seconds,
            "policySource": self.policy_source,
        }


class DiagnosticsPolicyCatalog:
    """One policy source shared by projection and scheduled execution."""

    _CONNECTION_INTERVALS = {
        "woocommerce": 1_800,
        "snappshop": 3_600,
        "tapsishop": 3_600,
        "technolife": 3_600,
        "nextcloud": 3_600,
    }
    _CONNECTION_JITTER_SECONDS = 300
    _PRODUCT_CACHE_TTL_SECONDS = 86_400
    _WEBHOOK_EVIDENCE_TTL_SECONDS = 86_400
    _RUNNER_HEARTBEAT_TTL_SECONDS = 180

    def connection(self, provider: str) -> CapabilityPolicy:
        if provider in COMING_SOON_PROVIDERS or provider not in self._CONNECTION_INTERVALS:
            return CapabilityPolicy(
                ScheduleMode.NOT_APPLICABLE,
                False,
                None,
                None,
                "diagnostics_policy_catalog",
            )
        prefix = f"FLOWHUB_{provider.upper()}_CONNECTION_HEALTH"
        enabled = _env_bool(
            f"{prefix}_ENABLED",
            _env_bool("FLOWHUB_CONNECTION_HEALTH_ENABLED", True),
        )
        if not enabled:
            return CapabilityPolicy(
                ScheduleMode.NOT_ENABLED,
                False,
                None,
                None,
                "diagnostics_policy_catalog",
            )
        interval = _env_positive_int(
            f"{prefix}_INTERVAL_SECONDS",
            self._CONNECTION_INTERVALS[provider],
        )
        ttl = _env_positive_int(f"{prefix}_FRESHNESS_TTL_SECONDS", interval * 2)
        jitter = _env_nonnegative_int(
            f"{prefix}_JITTER_SECONDS", self._CONNECTION_JITTER_SECONDS
        )
        return CapabilityPolicy(
            ScheduleMode.SCHEDULED,
            True,
            interval,
            ttl,
            "diagnostics_policy_catalog",
            jitter,
        )

    def product_sync(self, provider: str) -> CapabilityPolicy:
        prefix = f"FLOWHUB_{provider.upper()}_PRODUCT_SYNC"
        enabled = _env_bool(f"{prefix}_ENABLED", False)
        interval = _env_optional_positive_int(f"{prefix}_INTERVAL_SECONDS")
        # Operator-declared: this connector's product data must stay current
        # for the resource to be READY, independent of whether an automatic
        # schedule is configured. Defaults False for every connector — no
        # capability is treated as required unless explicitly declared.
        required = _env_bool(f"{prefix}_REQUIRED", False)
        # Operator-declared: this connector is refreshed by manual trigger by
        # design (no automatic schedule is ever expected). Distinct from
        # NOT_SCHEDULED, which may simply mean nobody has configured a
        # schedule yet.
        manual = _env_bool(f"{prefix}_MANUAL", False)
        if not enabled or interval is None:
            return CapabilityPolicy(
                ScheduleMode.MANUAL if manual else ScheduleMode.NOT_SCHEDULED,
                False,
                None,
                None,
                "connector_product_sync_environment",
                required_for_readiness=required,
            )
        freshness = _env_positive_int(
            f"{prefix}_FRESHNESS_TTL_SECONDS", max(interval * 2, 3_600)
        )
        return CapabilityPolicy(
            ScheduleMode.SCHEDULED,
            True,
            interval,
            freshness,
            "connector_product_sync_environment",
            required_for_readiness=required,
        )

    def product_sync_event_driven_ttl_seconds(self, provider: str) -> int:
        """Accepted evidence window for webhook-driven product currency.

        An event-driven connector has no polling interval to derive a TTL
        from, so product-sync currency is judged against the same window the
        product cache already uses, with the existing product-sync override
        honoured when an operator has declared one.
        """

        return _env_positive_int(
            f"FLOWHUB_{provider.upper()}_PRODUCT_SYNC_FRESHNESS_TTL_SECONDS",
            self.product_cache(provider).freshness_ttl_seconds
            or self._PRODUCT_CACHE_TTL_SECONDS,
        )

    def product_cache(self, provider: str) -> CapabilityPolicy:
        ttl = _env_positive_int(
            f"FLOWHUB_{provider.upper()}_PRODUCT_CACHE_FRESHNESS_TTL_SECONDS",
            self._PRODUCT_CACHE_TTL_SECONDS,
        )
        return CapabilityPolicy(
            ScheduleMode.MANUAL,
            True,
            None,
            ttl,
            "data_layer_product_cache_policy",
        )

    _WEBHOOK_SUPPORTED_PROVIDERS = frozenset({"tapsishop", "woocommerce"})

    def webhook(self, provider: str) -> CapabilityPolicy:
        if provider not in self._WEBHOOK_SUPPORTED_PROVIDERS:
            return CapabilityPolicy(
                ScheduleMode.NOT_APPLICABLE,
                False,
                None,
                None,
                "channel_capability_contract",
            )
        ttl = _env_positive_int(
            f"FLOWHUB_{provider.upper()}_WEBHOOK_EVIDENCE_TTL_SECONDS",
            self._WEBHOOK_EVIDENCE_TTL_SECONDS,
        )
        return CapabilityPolicy(
            ScheduleMode.EVENT_DRIVEN,
            True,
            None,
            ttl,
            f"{provider}_webhook_contract",
        )

    def runner_heartbeat_ttl_seconds(self) -> int:
        return _env_positive_int(
            "FLOWHUB_RUNNER_HEARTBEAT_TTL_SECONDS",
            self._RUNNER_HEARTBEAT_TTL_SECONDS,
        )


class CanonicalDiagnosticsProjector:
    """Project one deterministic Diagnostics model from local evidence."""

    def __init__(
        self,
        db: Session,
        *,
        now: datetime | None = None,
        policies: DiagnosticsPolicyCatalog | None = None,
    ) -> None:
        self.db = db
        self.now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        self.policies = policies or DiagnosticsPolicyCatalog()
        self.marketplace = default_marketplace_registry()

    def project(self, *, platform_state: str = "HEALTHY") -> dict[str, Any]:
        channels = self._channels()
        sources = self._sources()
        resources = channels + sources
        background_jobs = [self._runner(resources)]
        overall = self._overall(resources, background_jobs, platform_state)
        summary = self._summary(resources, overall)
        recent_checks = self._recent_checks(resources, background_jobs)
        generated_at = _iso(self.now)
        return {
            "schemaVersion": "diagnostics-state-v1",
            "generatedAt": generated_at,
            "overallState": overall.value,
            "summary": summary,
            "resources": resources,
            "backgroundJobs": background_jobs,
            "recentChecks": recent_checks,
            "consumerStates": {
                "diagnostics": overall.value,
                "dashboard": overall.value,
                "sidebar": overall.value,
                "recentChecks": overall.value,
                "sourcesSummary": overall.value,
                "channelsSummary": overall.value,
            },
            "externalCallPerformed": False,
        }

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    def _channels(self) -> list[dict[str, Any]]:
        instances = {
            row.id: row
            for row in self.db.query(IntegrationConnectorInstance)
            .filter(~IntegrationConnectorInstance.connector_type.in_(SOURCE_CONNECTOR_TYPES))
            .all()
        }
        channel_ids = set(instances) | set(DEFAULT_CHANNEL_BY_ID)
        resources = [
            self._channel(channel_id, instances.get(channel_id))
            for channel_id in sorted(channel_ids)
        ]
        return resources

    def _channel(
        self,
        channel_id: str,
        instance: IntegrationConnectorInstance | None,
    ) -> dict[str, Any]:
        default = DEFAULT_CHANNEL_BY_ID.get(channel_id)
        provider = instance.connector_type if instance else (default[1] if default else channel_id.split(":", 1)[0])
        display_name = (
            self._channel_display_name(instance)
            or (default[2] if default else provider)
        )
        coming_soon = provider in COMING_SOON_PROVIDERS
        enabled = bool(instance and instance.enabled and not coming_soon)
        configured = self._configured(instance, provider)
        lifecycle = "COMING_SOON" if coming_soon else "ACTIVE" if enabled else "DISABLED"
        health = self._health(channel_id)
        connection_policy = self.policies.connection(provider)
        connectivity = self._connectivity(
            enabled=enabled,
            configured=configured,
            excluded=coming_soon,
            health=health,
            policy=connection_policy,
        )

        definition = self.marketplace.get_definition(channel_id)
        if definition is None:
            definition = next(
                (
                    item
                    for item in self.marketplace.list_definitions()
                    if item.connector_type == provider
                ),
                None,
            )
        capabilities = set(definition.capabilities) if definition else set()
        product_supported = ChannelCapability.PRODUCTS_READ in capabilities
        order_supported = bool(
            capabilities
            & {
                ChannelCapability.ORDERS_READ,
                ChannelCapability.ORDERS_EVENTS_POLL,
                ChannelCapability.ORDERS_WEBHOOK_RECEIVE,
            }
        )

        connection_capability = self._connection_capability(
            provider,
            enabled=enabled,
            configured=configured,
            coming_soon=coming_soon,
            health=health,
            connectivity=connectivity,
            policy=connection_policy,
        )
        # Webhook evidence is computed first because product synchronization
        # composes its effective schedule mode from it. The two were previously
        # independent lookups, which is why an event-driven channel reported
        # "not scheduled" product sync while its webhook was verifiably
        # delivering.
        webhook = self._webhook_capability(
            channel_id,
            provider,
            enabled=enabled,
            configured=configured,
            coming_soon=coming_soon,
            instance=instance,
        )
        product_sync = self._product_sync_capability(
            channel_id,
            provider,
            supported=product_supported,
            enabled=enabled,
            configured=configured,
            coming_soon=coming_soon,
            webhook=webhook,
        )
        product_cache = self._product_cache_capability(
            channel_id,
            provider,
            supported=product_supported,
            enabled=enabled,
            configured=configured,
            coming_soon=coming_soon,
        )
        observation_confidence = self._observation_confidence_summary(
            channel_id,
            provider,
            supported=product_supported,
            enabled=enabled,
            configured=configured,
            coming_soon=coming_soon,
        )
        order_sync = self._order_sync_capability(
            channel_id,
            provider,
            supported=order_supported,
            enabled=enabled,
            configured=configured,
            coming_soon=coming_soon,
            instance=instance,
        )
        capability_model = {
            "connectionVerification": connection_capability,
            "productSynchronization": product_sync,
            "orderSynchronization": order_sync,
            "webhookProcessing": webhook,
            "productCache": product_cache,
            "providerAcquisition": self._not_applicable_capability(
                "source_capability_only"
            ),
        }

        readiness, reason = self._channel_readiness(
            coming_soon=coming_soon,
            enabled=enabled,
            configured=configured,
            connectivity=connectivity,
            product_sync=product_sync,
            product_cache=product_cache,
            order_sync=order_sync,
            webhook=webhook,
        )
        action = self._channel_action(
            reason,
            product_sync=product_sync,
            product_cache=product_cache,
            order_sync=order_sync,
            connection=connection_capability,
        )
        freshness = self._resource_freshness(capability_model.values())
        denominator_eligible = enabled and not coming_soon
        overall = self._resource_overall(readiness, connectivity["state"])
        latest = _max_iso(
            connection_capability.get("lastAttemptAt"),
            product_sync.get("lastAttemptAt"),
            order_sync.get("lastAttemptAt"),
            webhook.get("lastAttemptAt"),
        )
        return {
            "id": channel_id,
            "kind": "CHANNEL",
            "provider": provider,
            "displayName": display_name,
            "lifecycle": lifecycle,
            "enabled": enabled,
            "configured": configured,
            "denominatorEligible": denominator_eligible,
            "connectivity": connectivity,
            "readiness": {"state": readiness.value, "reasonCode": reason},
            "freshness": {"state": freshness.value},
            "capabilities": capability_model,
            # Distinct axis from "freshness" above -- freshness answers "has
            # any read completed recently" (channel-level, coarse);
            # observationConfidence answers "do we currently trust this
            # channel's cached prices" (per-row evidence, worst-value-wins
            # rollup, evidence-driven -- never a sticky flag). See
            # ADR_CHANNEL_READ_ARCHITECTURE.md.
            "observationConfidence": observation_confidence,
            "overallState": overall.value,
            "reasonCode": reason,
            "recommendedAction": action,
            "latestRelevantAt": latest,
            "advancedEvidence": self._channel_advanced_evidence(
                channel_id, health, product_sync, order_sync, observation_confidence
            ),
        }

    def _connection_capability(
        self,
        provider: str,
        *,
        enabled: bool,
        configured: bool,
        coming_soon: bool,
        health: DlConnectorHealth | None,
        connectivity: dict[str, Any],
        policy: CapabilityPolicy,
    ) -> dict[str, Any]:
        if coming_soon:
            support = CapabilitySupport.COMING_SOON
            freshness = FreshnessState.NOT_APPLICABLE
        elif not enabled:
            support = CapabilitySupport.SUPPORTED_DISABLED
            freshness = FreshnessState.NOT_ENABLED
        elif not configured:
            support = CapabilitySupport.NOT_CONFIGURED
            freshness = FreshnessState.NOT_ENABLED
        else:
            support = CapabilitySupport.SUPPORTED_ENABLED
            freshness = FreshnessState(connectivity["freshness"])
        checked_at = health.checked_at if health else None
        next_expected = self._next_expected(checked_at, policy)
        return self._capability(
            support=support,
            freshness=freshness,
            schedule=policy,
            last_attempt_at=checked_at,
            last_success_at=health.last_success_at if health else None,
            last_outcome=(
                OutcomeState.NEVER_RUN
                if health is None
                else OutcomeState.SUCCESSFUL
                if health.status in {"healthy", "degraded"}
                else OutcomeState.FAILED
            ),
            next_expected_at=next_expected,
            policy=policy,
            required=enabled and configured and not coming_soon,
            evidence_key="data_layer_health",
        )

    def _effective_product_sync_policy(
        self,
        provider: str,
        *,
        supported: bool,
        enabled: bool,
        configured: bool,
        coming_soon: bool,
        webhook: dict[str, Any] | None,
    ) -> CapabilityPolicy:
        """Compose the product-sync schedule mode from *all* real evidence.

        The connector's own ``product_sync`` environment policy only ever
        describes a polling schedule. For a provider that pushes product
        changes over webhooks, the absence of that poll is not "no schedule" —
        delivery is event-driven, and the poll (when configured) is a
        reconciliation safety net layered on top. Reporting only the polling
        axis is what produced the "Webhook: event driven / Product
        synchronization: not scheduled" contradiction.
        """

        policy = self.policies.product_sync(provider)
        if coming_soon or not supported or not enabled or not configured:
            return policy

        webhook_policy = self.policies.webhook(provider)
        if webhook_policy.mode != ScheduleMode.EVENT_DRIVEN:
            return policy
        if webhook is None or not webhook.get("configured"):
            # Webhook support exists for the provider, but this instance has no
            # configured secret: there is no event-driven delivery to compose.
            return policy
        if int(webhook.get("acceptedCount") or 0) <= 0:
            # Configuration alone is not evidence. Until the provider has
            # actually delivered at least one accepted (non-dead-letter)
            # receipt, event-driven delivery is a claim, not a fact.
            return policy

        if policy.mode == ScheduleMode.SCHEDULED:
            mode = ScheduleMode.EVENT_DRIVEN_WITH_RECONCILIATION
            ttl = policy.freshness_ttl_seconds
            interval = policy.interval_seconds
        else:
            mode = ScheduleMode.EVENT_DRIVEN
            ttl = self.policies.product_sync_event_driven_ttl_seconds(provider)
            interval = None
        return CapabilityPolicy(
            mode,
            True,
            interval,
            ttl,
            f"{policy.policy_source}+{webhook_policy.policy_source}",
            required_for_readiness=policy.required_for_readiness,
        )

    def _product_sync_capability(
        self,
        channel_id: str,
        provider: str,
        *,
        supported: bool,
        enabled: bool,
        configured: bool,
        coming_soon: bool,
        webhook: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        declared = self.policies.product_sync(provider)
        policy = self._effective_product_sync_policy(
            provider,
            supported=supported,
            enabled=enabled,
            configured=configured,
            coming_soon=coming_soon,
            webhook=webhook,
        )
        latest = self._latest_product_refresh(channel_id)
        last_success = self._last_successful_product_sync(channel_id)
        if coming_soon:
            support = CapabilitySupport.COMING_SOON
            freshness = FreshnessState.NOT_APPLICABLE
        elif not supported:
            support = CapabilitySupport.NOT_SUPPORTED
            freshness = FreshnessState.NOT_APPLICABLE
        elif not enabled:
            support = CapabilitySupport.SUPPORTED_DISABLED
            freshness = FreshnessState.NOT_ENABLED
        elif not configured:
            support = CapabilitySupport.NOT_CONFIGURED
            freshness = FreshnessState.NOT_ENABLED
        elif policy.mode in EVENT_DRIVEN_MODES:
            # Event-driven currency is judged against real product evidence.
            # `_scheduled_freshness` would answer NOT_SCHEDULED for anything
            # that is not literally SCHEDULED, which makes the tile useless
            # for exactly the channels that are working correctly.
            support = CapabilitySupport.SUPPORTED_ENABLED
            freshness = self._evidence_freshness(
                last_success, policy.freshness_ttl_seconds
            )
        else:
            support = CapabilitySupport.SUPPORTED_ENABLED
            freshness = self._scheduled_freshness(last_success, policy)

        # Reconciliation is derived from the *declared* polling policy, which
        # is a separate fact from event delivery. It is published as its own
        # sub-fact rather than being folded into `nextExpectedAt`.
        next_reconciliation = self._next_expected(
            self._refresh_attempt_at(latest) or last_success, declared
        )
        reconciliation = self._reconciliation_fact(
            support=support,
            mode=policy.mode,
            declared=declared,
            next_reconciliation_at=next_reconciliation,
        )
        result = self._capability(
            support=support,
            freshness=freshness,
            schedule=policy,
            last_attempt_at=self._refresh_attempt_at(latest),
            last_success_at=last_success,
            last_outcome=self._refresh_outcome(latest),
            next_expected_at=next_reconciliation,
            policy=policy,
            # Required for readiness when the operator has actually scheduled
            # automatic sync (an implicit freshness promise), when delivery is
            # event-driven (the provider is actively pushing changes, so stale
            # product data is a real operational problem), or when the
            # connector contract explicitly requires it regardless of
            # scheduling. Being merely SUPPORTED never implies REQUIRED.
            required=bool(
                supported
                and enabled
                and configured
                and (
                    policy.mode == ScheduleMode.SCHEDULED
                    or policy.mode in EVENT_DRIVEN_MODES
                    or policy.required_for_readiness
                )
            ),
            evidence_key="data_layer_refresh_job",
        )
        result["reconciliation"] = reconciliation
        return result

    @staticmethod
    def _reconciliation_fact(
        *,
        support: CapabilitySupport,
        mode: ScheduleMode,
        declared: CapabilityPolicy,
        next_reconciliation_at: datetime | None,
    ) -> dict[str, Any]:
        if support != CapabilitySupport.SUPPORTED_ENABLED:
            reconciliation = ReconciliationMode.DISABLED
        elif mode in {
            ScheduleMode.SCHEDULED,
            ScheduleMode.EVENT_DRIVEN_WITH_RECONCILIATION,
        }:
            reconciliation = ReconciliationMode.SCHEDULED
        elif mode == ScheduleMode.EVENT_DRIVEN or declared.mode == ScheduleMode.MANUAL:
            # Event-driven delivery with no reconciliation poll configured, or
            # an explicitly manual-by-design connector: a manual refresh is the
            # available reconciliation path.
            reconciliation = ReconciliationMode.MANUAL
        else:
            # Neither event delivery nor any schedule: nothing reconciles this
            # channel on its own.
            reconciliation = ReconciliationMode.DISABLED
        return {
            "mode": reconciliation.value,
            "nextReconciliationAt": (
                _iso(next_reconciliation_at)
                if reconciliation == ReconciliationMode.SCHEDULED
                else None
            ),
        }

    def _product_cache_capability(
        self,
        channel_id: str,
        provider: str,
        *,
        supported: bool,
        enabled: bool,
        configured: bool,
        coming_soon: bool,
    ) -> dict[str, Any]:
        policy = self.policies.product_cache(provider)
        latest = self._latest_product_refresh(channel_id)
        last_success = self._last_successful_product_sync(channel_id)
        count = self.db.query(DlProductCache).filter_by(connector_id=channel_id).count()
        if coming_soon:
            support = CapabilitySupport.COMING_SOON
            freshness = FreshnessState.NOT_APPLICABLE
        elif not supported:
            support = CapabilitySupport.NOT_SUPPORTED
            freshness = FreshnessState.NOT_APPLICABLE
        elif not enabled:
            support = CapabilitySupport.SUPPORTED_DISABLED
            freshness = FreshnessState.NOT_ENABLED
        elif not configured:
            support = CapabilitySupport.NOT_CONFIGURED
            freshness = FreshnessState.NOT_ENABLED
        else:
            support = CapabilitySupport.SUPPORTED_ENABLED
            freshness = self._evidence_freshness(
                last_success, policy.freshness_ttl_seconds
            )
        result = self._capability(
            support=support,
            freshness=freshness,
            schedule=policy,
            last_attempt_at=self._refresh_attempt_at(latest),
            last_success_at=last_success,
            last_outcome=self._refresh_outcome(latest),
            next_expected_at=None,
            policy=policy,
            required=supported and enabled and configured and not coming_soon,
            evidence_key="data_layer_product_cache",
        )
        result["cachedItemCount"] = count
        return result

    def _observation_confidence_summary(
        self,
        channel_id: str,
        provider: str,
        *,
        supported: bool,
        enabled: bool,
        configured: bool,
        coming_soon: bool,
    ) -> dict[str, Any]:
        """Channel-level, worst-value-wins rollup of per-row Observation
        Confidence. Recomputed live every projection (not trusted purely
        from the stored per-row snapshot, which decays silently) --
        RECOVERY_REQUIRED in particular can only be known by checking
        DlChannelEntityWork's current retry-exhaustion state, since a
        write-time snapshot has no entity-work context to consult."""
        if coming_soon or not supported or not enabled or not configured:
            return {
                "value": ObservationConfidence.UNKNOWN.value,
                "reasonCode": "not_applicable",
                "recoveryRequiredCount": 0,
                "computedAt": _iso(self.now),
            }

        total = self.db.query(DlProductCache).filter_by(connector_id=channel_id).count()
        if total == 0:
            return {
                "value": ObservationConfidence.UNKNOWN.value,
                "reasonCode": "never_observed",
                "recoveryRequiredCount": 0,
                "computedAt": _iso(self.now),
            }

        recovery_required_count = 0
        if self._table_exists(DlChannelEntityWork):
            recovery_required_count = (
                self.db.query(DlChannelEntityWork)
                .filter(
                    DlChannelEntityWork.connector_id == channel_id,
                    DlChannelEntityWork.status == "failed",
                    DlChannelEntityWork.attempt_count >= DlChannelEntityWork.max_attempts,
                )
                .count()
            )
        if recovery_required_count > 0:
            return {
                "value": ObservationConfidence.RECOVERY_REQUIRED.value,
                "reasonCode": "entity_work_exhausted_retries",
                "recoveryRequiredCount": recovery_required_count,
                "computedAt": _iso(self.now),
            }

        never_observed = (
            self.db.query(DlProductCache)
            .filter_by(connector_id=channel_id, observation_confidence=ObservationConfidence.UNKNOWN.value)
            .count()
        )
        if never_observed > 0:
            return {
                "value": ObservationConfidence.UNKNOWN.value,
                "reasonCode": "never_observed",
                "recoveryRequiredCount": 0,
                "computedAt": _iso(self.now),
            }

        ttl_seconds = self.policies.product_cache(provider).freshness_ttl_seconds or 86_400
        stale_cutoff = self.now - timedelta(seconds=ttl_seconds)
        decaying_values = (ObservationConfidence.LIKELY_FRESH.value, ObservationConfidence.CONFIRMED.value)
        stale_or_decayed = (
            self.db.query(DlProductCache)
            .filter(
                DlProductCache.connector_id == channel_id,
                (DlProductCache.observation_confidence == ObservationConfidence.STALE.value)
                | (
                    DlProductCache.observation_confidence.in_(decaying_values)
                    & ((DlProductCache.last_fetched_at.is_(None)) | (DlProductCache.last_fetched_at < stale_cutoff))
                ),
            )
            .count()
        )
        if stale_or_decayed > 0:
            return {
                "value": ObservationConfidence.STALE.value,
                "reasonCode": "beyond_channel_ttl",
                "recoveryRequiredCount": 0,
                "computedAt": _iso(self.now),
            }

        confirmed_count = (
            self.db.query(DlProductCache)
            .filter_by(connector_id=channel_id, observation_confidence=ObservationConfidence.CONFIRMED.value)
            .count()
        )
        if confirmed_count == total:
            return {
                "value": ObservationConfidence.CONFIRMED.value,
                "reasonCode": "zero_staleness_read",
                "recoveryRequiredCount": 0,
                "computedAt": _iso(self.now),
            }
        return {
            "value": ObservationConfidence.LIKELY_FRESH.value,
            "reasonCode": "within_channel_ttl",
            "recoveryRequiredCount": 0,
            "computedAt": _iso(self.now),
        }

    def _order_sync_capability(
        self,
        channel_id: str,
        provider: str,
        *,
        supported: bool,
        enabled: bool,
        configured: bool,
        coming_soon: bool,
        instance: IntegrationConnectorInstance | None,
    ) -> dict[str, Any]:
        checkpoints = self._order_checkpoints(channel_id)
        last_attempt = _max_dt(*(item.last_run_at for item in checkpoints))
        last_success = _max_dt(*(item.last_success_at for item in checkpoints))
        last_failure = _max_dt(*(item.last_failure_at for item in checkpoints))
        global_enabled = parse_config_bool(
            os.environ.get("FLOWHUB_ORDER_SYNC_ENABLED"), default=True
        )
        interval = self._order_interval(provider, checkpoints, instance)
        policy = (
            CapabilityPolicy(
                ScheduleMode.SCHEDULED,
                True,
                interval,
                max(interval * 3, 3_600),
                "order_sync_runner_policy",
            )
            if global_enabled and supported
            else CapabilityPolicy(
                ScheduleMode.NOT_ENABLED
                if supported
                else ScheduleMode.NOT_APPLICABLE,
                False,
                None,
                None,
                "order_sync_runner_policy",
            )
        )
        if coming_soon:
            support = CapabilitySupport.COMING_SOON
            freshness = FreshnessState.NOT_APPLICABLE
        elif not supported:
            support = CapabilitySupport.NOT_SUPPORTED
            freshness = FreshnessState.NOT_APPLICABLE
        elif not enabled or not global_enabled:
            support = CapabilitySupport.SUPPORTED_DISABLED
            freshness = FreshnessState.NOT_ENABLED
        elif not configured:
            support = CapabilitySupport.NOT_CONFIGURED
            freshness = FreshnessState.NOT_ENABLED
        else:
            support = CapabilitySupport.SUPPORTED_ENABLED
            freshness = self._scheduled_freshness(last_success, policy)
        if last_failure and (last_success is None or last_failure > last_success):
            outcome = OutcomeState.FAILED
        elif last_success:
            outcome = OutcomeState.SUCCESSFUL
        elif last_attempt:
            outcome = OutcomeState.UNKNOWN
        else:
            outcome = OutcomeState.NEVER_RUN
        next_run = min(
            (item.next_run_at for item in checkpoints if item.next_run_at),
            default=None,
        )
        return self._capability(
            support=support,
            freshness=freshness,
            schedule=policy,
            last_attempt_at=last_attempt,
            last_success_at=last_success,
            last_outcome=outcome,
            next_expected_at=next_run or self._next_expected(last_attempt, policy),
            policy=policy,
            required=supported and enabled and configured and global_enabled,
            evidence_key="order_sync_checkpoint",
        )

    def _webhook_capability(
        self,
        channel_id: str,
        provider: str,
        *,
        enabled: bool,
        configured: bool,
        coming_soon: bool,
        instance: IntegrationConnectorInstance | None,
    ) -> dict[str, Any]:
        supported = provider in {"tapsishop", "woocommerce"}
        webhook_secret_setting_key = "webhook_token" if provider == "tapsishop" else "webhook_secret"
        webhook_enabled = bool(
            instance and self._setting_configured(instance, webhook_secret_setting_key)
        )
        policy = self.policies.webhook(provider)
        receipts = (
            self.db.query(WebhookReceipt).filter_by(channel_id=channel_id, provider=provider).all()
            if supported and self._table_exists(WebhookReceipt)
            else []
        )
        last_received = _max_dt(*(item.received_at for item in receipts))
        last_processed = _max_dt(*(item.processed_at for item in receipts))
        queued = sum(
            1
            for item in receipts
            if item.processing_state in {"queued", "retry_scheduled"}
        )
        # Durably accepted delivery evidence. WooCommerce's activation ping is
        # acknowledged without persisting a receipt (see
        # `app/flowhub/api/v2/webhooks.py`), so handshake noise never reaches
        # this count; only real, signature-verified deliveries do.
        accepted = sum(1 for item in receipts if item.processing_state != "dead_letter")
        dead_letter_rows = (
            self.db.query(WebhookDeadLetter)
            .filter_by(channel_id=channel_id, provider=provider)
            .all()
            if supported and self._table_exists(WebhookDeadLetter)
            else []
        )
        dead_letters = len(dead_letter_rows)
        # A dead-letter row is permanent evidence and is never deleted. But it
        # is only *actionable* while its receipt is still parked in
        # `dead_letter`: once an admin replays it (processing_state -> queued)
        # or it reprocesses successfully (-> processed), there is nothing left
        # for the Owner to do. Counting every dead letter that ever existed is
        # what pinned a recovered channel at NEEDS_ATTENTION forever.
        unresolved_receipt_ids = {
            item.id for item in receipts if item.processing_state == "dead_letter"
        }
        actionable_dead_letters = sum(
            1 for row in dead_letter_rows if row.receipt_id in unresolved_receipt_ids
        )
        if coming_soon:
            support = CapabilitySupport.COMING_SOON
            freshness = FreshnessState.NOT_APPLICABLE
        elif not supported:
            support = CapabilitySupport.NOT_SUPPORTED
            freshness = FreshnessState.NOT_APPLICABLE
        elif not enabled or not webhook_enabled:
            support = CapabilitySupport.SUPPORTED_DISABLED
            freshness = FreshnessState.NOT_ENABLED
        elif not configured:
            support = CapabilitySupport.NOT_CONFIGURED
            freshness = FreshnessState.NOT_ENABLED
        else:
            support = CapabilitySupport.SUPPORTED_ENABLED
            freshness = self._evidence_freshness(
                last_received, policy.freshness_ttl_seconds
            )
        outcome = (
            OutcomeState.FAILED
            if actionable_dead_letters
            else OutcomeState.PARTIAL
            if queued
            else OutcomeState.SUCCESSFUL
            if last_processed
            else OutcomeState.NEVER_RUN
        )
        result = self._capability(
            support=support,
            freshness=freshness,
            schedule=policy,
            last_attempt_at=last_received,
            last_success_at=last_processed,
            last_outcome=outcome,
            next_expected_at=None,
            policy=policy,
            required=False,
            evidence_key="webhook_receipts",
        )
        result.update(
            {
                "configured": webhook_enabled,
                "receivedCount": len(receipts),
                "acceptedCount": accepted,
                "queuedCount": queued,
                # Total is retained evidence; actionable is what readiness acts on.
                "deadLetterCount": dead_letters,
                "actionableDeadLetterCount": actionable_dead_letters,
                "lastReceivedAt": _iso(last_received),
                "lastProcessedAt": _iso(last_processed),
            }
        )
        return result

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    def _sources(self) -> list[dict[str, Any]]:
        if not self._table_exists(SourceProfile):
            return []
        return [
            self._source(profile)
            for profile in self.db.query(SourceProfile)
            .filter(SourceProfile.status != "deleted")
            .order_by(SourceProfile.name.asc(), SourceProfile.id.asc())
            .all()
        ]

    def _source(self, profile: SourceProfile) -> dict[str, Any]:
        connector_id = profile.external_source_id
        instance = self.db.get(IntegrationConnectorInstance, connector_id) if connector_id else None
        provider = instance.connector_type if instance else profile.source_kind
        lifecycle = profile.status.upper()
        archived = profile.status in {"archived", "deleted"}
        disabled = profile.status == "disabled"
        enabled = bool(profile.status == "active" and (instance is None or instance.enabled))
        configured = self._configured(instance, provider) if instance else profile.source_kind != "external"
        health = self._health(connector_id) if connector_id else None
        connection_policy = self.policies.connection(provider)
        connectivity = self._connectivity(
            enabled=enabled,
            configured=configured,
            excluded=archived or disabled,
            health=health,
            policy=connection_policy,
        )
        connection = self._connection_capability(
            provider,
            enabled=enabled,
            configured=configured,
            coming_soon=False,
            health=health,
            connectivity=connectivity,
            policy=connection_policy,
        )
        acquisition = self._source_acquisition(profile)
        # A healthy provider is not sufficient for operational readiness.
        # Reuse the Source-owned identity projection so all consumers observe
        # the same persisted Mapping/evidence decision.
        identity_validation: dict[str, Any] | None = None
        if not archived and not disabled:
            source_service = SourceWorkspaceService(self.db)
            mapping = source_service.sources.latest_mapping(profile.id)
            if mapping is not None:
                identity_validation = source_service._mapping_identity_validation_shape(mapping)
        if archived:
            readiness = ReadinessState.ARCHIVED
            reason = "source_archived"
        elif disabled or not enabled:
            readiness = ReadinessState.DISABLED
            reason = "source_disabled"
        elif not configured:
            readiness = ReadinessState.BLOCKED
            reason = "source_configuration_incomplete"
        elif connectivity["state"] == ConnectivityState.UNHEALTHY.value:
            readiness = ReadinessState.BLOCKED
            reason = "source_connection_unhealthy"
        elif connectivity["state"] in {
            ConnectivityState.UNKNOWN.value,
            ConnectivityState.DEGRADED.value,
        }:
            readiness = ReadinessState.NEEDS_ATTENTION
            reason = "source_connection_needs_attention"
        elif identity_validation is not None and identity_validation["status"] != "pass":
            readiness = ReadinessState.BLOCKED
            reason = f"identity_validation_{identity_validation['status']}"
        else:
            readiness = ReadinessState.READY
            reason = "source_ready"
        action = self._basic_action(reason, connection)
        capabilities = {
            "connectionVerification": connection,
            "providerAcquisition": acquisition,
            "productSynchronization": self._not_applicable_capability(
                "channel_capability_only"
            ),
            "orderSynchronization": self._not_applicable_capability(
                "channel_capability_only"
            ),
            "webhookProcessing": self._not_applicable_capability(
                "channel_capability_only"
            ),
            "productCache": self._not_applicable_capability(
                "channel_capability_only"
            ),
        }
        overall = self._resource_overall(readiness, connectivity["state"])
        latest = _max_iso(
            connection.get("lastAttemptAt"), acquisition.get("lastAttemptAt")
        )
        return {
            "id": profile.id,
            "connectorId": connector_id,
            "kind": "SOURCE",
            "provider": provider,
            "displayName": profile.name,
            "lifecycle": lifecycle,
            "enabled": enabled,
            "configured": configured,
            "denominatorEligible": enabled,
            "connectivity": connectivity,
            "readiness": {"state": readiness.value, "reasonCode": reason},
            "identityValidation": identity_validation,
            "freshness": {
                "state": self._resource_freshness(capabilities.values()).value
            },
            "capabilities": capabilities,
            # Channel Read concept only -- Sources have no product cache to
            # hold confidence about. Present with a fixed NOT_APPLICABLE
            # shape (like productCache above) so consumers can read this key
            # uniformly across both resource kinds.
            "observationConfidence": {
                "value": ObservationConfidence.UNKNOWN.value,
                "reasonCode": "not_applicable",
                "recoveryRequiredCount": 0,
                "computedAt": _iso(self.now),
            },
            "overallState": overall.value,
            "reasonCode": reason,
            "recommendedAction": action,
            "latestRelevantAt": latest,
            "advancedEvidence": [
                {
                    "key": "source_lifecycle",
                    "label": "Source lifecycle",
                    "value": profile.status,
                    "recordedAt": _iso(profile.archived_at or profile.updated_at),
                },
                {
                    "key": "data_layer_health",
                    "label": "Connection health record",
                    "value": health.status if health else None,
                    "recordedAt": _iso(health.checked_at) if health else None,
                },
            ],
        }

    def _source_acquisition(self, profile: SourceProfile) -> dict[str, Any]:
        if not self._table_exists(AcquisitionRun):
            return self._not_scheduled_capability("source_acquisition_runs")
        latest = (
            self.db.query(AcquisitionRun)
            .filter(AcquisitionRun.source_id == profile.id)
            .order_by(AcquisitionRun.created_at.desc())
            .first()
        )
        last_success = (
            self.db.query(func.max(AcquisitionRun.terminal_at))
            .filter(
                AcquisitionRun.source_id == profile.id,
                AcquisitionRun.status == "succeeded",
            )
            .scalar()
        )
        policy = CapabilityPolicy(
            ScheduleMode.NOT_SCHEDULED,
            False,
            None,
            None,
            "source_acquisition_policy",
        )
        return self._capability(
            support=(
                CapabilitySupport.SUPPORTED_ENABLED
                if profile.status == "active"
                else CapabilitySupport.SUPPORTED_DISABLED
            ),
            freshness=(
                FreshnessState.NOT_SCHEDULED
                if profile.status == "active"
                else FreshnessState.NOT_ENABLED
            ),
            schedule=policy,
            last_attempt_at=(
                latest.started_at or latest.queued_at if latest is not None else None
            ),
            last_success_at=last_success,
            last_outcome=(
                OutcomeState.NEVER_RUN
                if latest is None
                else OutcomeState.SUCCESSFUL
                if latest.status == "succeeded"
                else OutcomeState.RUNNING
                if latest.status in {"queued", "running"}
                else OutcomeState.FAILED
            ),
            next_expected_at=None,
            policy=policy,
            required=False,
            evidence_key="source_acquisition_runs",
        )

    # ------------------------------------------------------------------
    # Background jobs and summaries
    # ------------------------------------------------------------------

    def _runner(self, resources: list[dict[str, Any]]) -> dict[str, Any]:
        event = (
            self.db.query(IntegrationConnectorEvent)
            .filter_by(
                connector_id="flowhub:order-sync-runner",
                event_name="order_sync_runner_heartbeat",
            )
            .order_by(IntegrationConnectorEvent.created_at.desc())
            .first()
        )
        required = any(
            item["denominatorEligible"]
            and item["configured"]
            and item["capabilities"]["connectionVerification"]["schedule"]["enabled"]
            for item in resources
        )
        ttl = self.policies.runner_heartbeat_ttl_seconds()
        metadata = event.metadata_json if event and isinstance(event.metadata_json, dict) else {}
        raw_state = str(metadata.get("state") or "unknown").lower()
        stale = bool(event and event.created_at < self.now - timedelta(seconds=ttl))
        queue_depth, stale_queue_depth = self._queue_depths()
        if event is None:
            state = RunnerState.UNKNOWN
            health = "NEEDS_ATTENTION" if required else "NOT_APPLICABLE"
        elif stale:
            state = RunnerState.FAILED
            health = "ERROR"
        elif raw_state == "running":
            state = RunnerState.RUNNING
            health = "HEALTHY"
        elif raw_state == "idle":
            # A live runner with genuinely executable work waiting is not idle.
            # Reporting IDLE alongside a non-zero queue depth is a
            # contradiction the Owner cannot act on.
            state = RunnerState.PENDING if queue_depth > 0 else RunnerState.IDLE
            health = "HEALTHY"
        elif raw_state in {"stopped", "disabled"}:
            state = RunnerState.DEGRADED if required else RunnerState.IDLE
            health = "NEEDS_ATTENTION" if required else "NOT_APPLICABLE"
        else:
            state = RunnerState.UNKNOWN
            health = "NEEDS_ATTENTION" if required else "NOT_APPLICABLE"

        successes = (
            self.db.query(IntegrationConnectorEvent)
            .filter(
                IntegrationConnectorEvent.event_name.in_(
                    (
                        "product_cache_refresh_completed",
                        "order_sync_reconciliation_completed",
                        "order_sync_snappshop_events_completed",
                        "order_sync_tapsishop_webhooks_completed",
                    )
                )
            )
            .order_by(IntegrationConnectorEvent.created_at.desc())
            .first()
        )
        failure = (
            self.db.query(IntegrationConnectorEvent)
            .filter(
                (IntegrationConnectorEvent.severity == "error")
                | IntegrationConnectorEvent.event_name.ilike("%failed%")
            )
            .order_by(IntegrationConnectorEvent.created_at.desc())
            .first()
        )
        return {
            "id": "flowhub:order-sync-runner",
            "displayName": "Integration background runner",
            "state": state.value,
            "health": health,
            "required": required,
            "lastHeartbeatAt": _iso(event.created_at) if event else None,
            "heartbeatTtlSeconds": ttl,
            "runnerId": metadata.get("runner_id") if event else None,
            "lastSuccessfulJobAt": _iso(successes.created_at) if successes else None,
            "queueDepth": queue_depth,
            "staleQueueDepth": stale_queue_depth,
            "lastFailureAt": _iso(failure.created_at) if failure else None,
            "lastFailureCode": failure.event_name if failure else None,
            "advancedEvidence": [
                {
                    "key": "runner_queue_depth",
                    "label": "Executable queued work",
                    "value": queue_depth,
                    "recordedAt": _iso(event.created_at) if event else None,
                },
                {
                    "key": "runner_stale_queue_depth",
                    "label": "Abandoned records past their execution lease",
                    "value": stale_queue_depth,
                    "recordedAt": None,
                },
            ],
        }

    def _queue_depths(self) -> tuple[int, int]:
        """Split queued work into executable versus abandoned/historical.

        The previous count summed every ``pending``/``running`` refresh job and
        every ``queued``/``retry_scheduled`` receipt, so records that no live
        runner will ever pick up — jobs whose execution lease already expired,
        receipts already past their retention window — inflated queue depth
        forever. Both halves are returned: abandoned records stay visible as
        evidence rather than being deleted from the projection.
        """

        lifecycle = RefreshJobLifecycle(self.db)
        executable = 0
        abandoned = 0
        if self._table_exists(DlRefreshJob):
            jobs = (
                self.db.query(DlRefreshJob)
                .filter(DlRefreshJob.status.in_(("pending", "running")))
                .all()
            )
            for job in jobs:
                if lifecycle.is_expired(job, self.now):
                    abandoned += 1
                else:
                    executable += 1
        if self._table_exists(WebhookReceipt):
            receipts = (
                self.db.query(WebhookReceipt)
                .filter(
                    WebhookReceipt.processing_state.in_(("queued", "retry_scheduled"))
                )
                .all()
            )
            for receipt in receipts:
                if (
                    receipt.retention_until is not None
                    and receipt.retention_until < self.now
                ):
                    abandoned += 1
                else:
                    executable += 1
        return executable, abandoned

    def _overall(
        self,
        resources: list[dict[str, Any]],
        jobs: list[dict[str, Any]],
        platform_state: str,
    ) -> OverallState:
        if str(platform_state).upper() in {"ERROR", "FAILED", "UNHEALTHY"}:
            return OverallState.ERROR
        eligible = [item for item in resources if item["denominatorEligible"]]
        if any(item["overallState"] == OverallState.ERROR.value for item in eligible):
            return OverallState.ERROR
        if any(job["health"] == "ERROR" and job["required"] for job in jobs):
            return OverallState.ERROR
        if any(item["overallState"] == OverallState.BLOCKED.value for item in eligible):
            return OverallState.BLOCKED
        if any(
            item["overallState"] == OverallState.NEEDS_ATTENTION.value
            for item in eligible
        ):
            return OverallState.NEEDS_ATTENTION
        if any(
            job["health"] == "NEEDS_ATTENTION" and job["required"] for job in jobs
        ):
            return OverallState.NEEDS_ATTENTION
        return OverallState.HEALTHY

    def _summary(
        self, resources: list[dict[str, Any]], overall: OverallState
    ) -> dict[str, Any]:
        channels = [item for item in resources if item["kind"] == "CHANNEL"]
        sources = [item for item in resources if item["kind"] == "SOURCE"]
        operational_channels = [item for item in channels if item["denominatorEligible"]]
        active_sources = [item for item in sources if item["denominatorEligible"]]
        return {
            "overallState": overall.value,
            "channels": {
                "ready": sum(
                    item["readiness"]["state"] == ReadinessState.READY.value
                    for item in operational_channels
                ),
                "operational": len(operational_channels),
                "needsAttention": sum(
                    item["readiness"]["state"]
                    == ReadinessState.NEEDS_ATTENTION.value
                    for item in operational_channels
                ),
                "blocked": sum(
                    item["readiness"]["state"] == ReadinessState.BLOCKED.value
                    for item in operational_channels
                ),
                "disabled": sum(
                    item["readiness"]["state"] == ReadinessState.DISABLED.value
                    for item in channels
                ),
                "comingSoon": sum(
                    item["readiness"]["state"]
                    == ReadinessState.COMING_SOON.value
                    for item in channels
                ),
            },
            "sources": {
                "ready": sum(
                    item["readiness"]["state"] == ReadinessState.READY.value
                    for item in active_sources
                ),
                "active": len(active_sources),
                "needsAttention": sum(
                    item["readiness"]["state"]
                    == ReadinessState.NEEDS_ATTENTION.value
                    for item in active_sources
                ),
                "blocked": sum(
                    item["readiness"]["state"] == ReadinessState.BLOCKED.value
                    for item in active_sources
                ),
                "disabled": sum(
                    item["readiness"]["state"] == ReadinessState.DISABLED.value
                    for item in sources
                ),
                "archived": sum(
                    item["readiness"]["state"] == ReadinessState.ARCHIVED.value
                    for item in sources
                ),
            },
        }

    def _recent_checks(
        self,
        resources: list[dict[str, Any]],
        jobs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = [
            {
                "id": item["id"],
                "kind": item["kind"],
                "displayName": item["displayName"],
                "provider": item["provider"],
                "lifecycle": item["lifecycle"],
                "connectivity": item["connectivity"]["state"],
                "readiness": item["readiness"]["state"],
                "freshness": item["freshness"]["state"],
                "state": item["overallState"],
                "reasonCode": item["reasonCode"],
                "recordedAt": item["latestRelevantAt"],
            }
            for item in resources
        ]
        rows.extend(
            {
                "id": item["id"],
                "kind": "BACKGROUND_JOB",
                "displayName": item["displayName"],
                "provider": "flowhub",
                "lifecycle": "ACTIVE" if item["required"] else "NOT_APPLICABLE",
                "connectivity": "NOT_APPLICABLE",
                "readiness": item["health"],
                "freshness": "FRESH" if item["health"] == "HEALTHY" else "STALE",
                "state": (
                    OverallState.HEALTHY.value
                    if item["health"] in {"HEALTHY", "NOT_APPLICABLE"}
                    else OverallState.ERROR.value
                    if item["health"] == "ERROR"
                    else OverallState.NEEDS_ATTENTION.value
                ),
                "reasonCode": f"runner_{item['state'].lower()}",
                "recordedAt": item["lastHeartbeatAt"],
            }
            for item in jobs
        )
        return sorted(
            rows,
            key=lambda item: item["recordedAt"] or "",
            reverse=True,
        )[:12]

    # ------------------------------------------------------------------
    # Derivation helpers
    # ------------------------------------------------------------------

    def _connectivity(
        self,
        *,
        enabled: bool,
        configured: bool,
        excluded: bool,
        health: DlConnectorHealth | None,
        policy: CapabilityPolicy,
    ) -> dict[str, Any]:
        if excluded or not enabled:
            state = ConnectivityState.NOT_APPLICABLE
            freshness = FreshnessState.NOT_APPLICABLE
        elif not configured:
            state = ConnectivityState.UNKNOWN
            freshness = FreshnessState.NOT_ENABLED
        elif health is None:
            state = ConnectivityState.UNKNOWN
            freshness = FreshnessState.NEVER_RUN
        else:
            freshness = self._evidence_freshness(
                health.checked_at, policy.freshness_ttl_seconds
            )
            if freshness == FreshnessState.STALE:
                state = ConnectivityState.UNKNOWN
            elif health.status == "healthy":
                state = ConnectivityState.HEALTHY
            elif health.status == "degraded":
                state = ConnectivityState.DEGRADED
            elif health.status == "unhealthy":
                state = ConnectivityState.UNHEALTHY
            else:
                state = ConnectivityState.UNKNOWN
        return {
            "state": state.value,
            "freshness": freshness.value,
            "lastVerifiedAt": _iso(health.last_success_at) if health else None,
            "lastCheckedAt": _iso(health.checked_at) if health else None,
            "errorCode": health.error_class if health else None,
        }

    def _channel_readiness(
        self,
        *,
        coming_soon: bool,
        enabled: bool,
        configured: bool,
        connectivity: dict[str, Any],
        product_sync: dict[str, Any],
        product_cache: dict[str, Any],
        order_sync: dict[str, Any],
        webhook: dict[str, Any],
    ) -> tuple[ReadinessState, str]:
        if coming_soon:
            return ReadinessState.COMING_SOON, "channel_coming_soon"
        if not enabled:
            return ReadinessState.DISABLED, "channel_disabled"
        if not configured:
            return ReadinessState.BLOCKED, "configuration_incomplete"
        if connectivity["state"] == ConnectivityState.UNHEALTHY.value:
            return ReadinessState.BLOCKED, "connection_unhealthy"
        if connectivity["state"] == ConnectivityState.DEGRADED.value:
            return ReadinessState.NEEDS_ATTENTION, "connection_degraded"
        if connectivity["state"] == ConnectivityState.UNKNOWN.value:
            reason = (
                "connection_evidence_stale"
                if connectivity["freshness"] == FreshnessState.STALE.value
                else "connection_never_verified"
            )
            return ReadinessState.NEEDS_ATTENTION, reason
        if product_sync["required"] and product_sync["freshness"] in {
            FreshnessState.STALE.value,
            FreshnessState.NEVER_RUN.value,
        }:
            return (
                ReadinessState.NEEDS_ATTENTION,
                "product_sync_stale"
                if product_sync["freshness"] == FreshnessState.STALE.value
                else "product_sync_never_run",
            )
        if product_cache["required"] and product_cache["lastOutcome"] in {
            OutcomeState.FAILED.value,
            OutcomeState.PARTIAL.value,
        }:
            return ReadinessState.NEEDS_ATTENTION, "product_cache_refresh_failed"
        if product_cache["required"] and product_cache["freshness"] == FreshnessState.STALE.value:
            # Prior evidence exists and has aged out: a manual cadence was
            # already established, so staleness is actionable regardless of
            # whether automatic scheduling is configured.
            return ReadinessState.NEEDS_ATTENTION, "product_cache_stale"
        if (
            product_cache["required"]
            and product_cache["freshness"] == FreshnessState.NEVER_RUN.value
            and product_sync["required"]
        ):
            # Never having run is only a readiness problem when product sync
            # is actually expected (scheduled, or explicitly required by
            # connector policy). Merely SUPPORTED-but-unscheduled must not
            # manufacture a false NEEDS_ATTENTION.
            return ReadinessState.NEEDS_ATTENTION, "product_cache_never_run"
        if order_sync["required"] and order_sync["freshness"] in {
            FreshnessState.STALE.value,
            FreshnessState.NEVER_RUN.value,
        }:
            return (
                ReadinessState.NEEDS_ATTENTION,
                "order_sync_stale"
                if order_sync["freshness"] == FreshnessState.STALE.value
                else "order_sync_never_run",
            )
        if (
            webhook["support"] == CapabilitySupport.SUPPORTED_ENABLED.value
            and webhook.get("actionableDeadLetterCount", 0) > 0
        ):
            return ReadinessState.NEEDS_ATTENTION, "webhook_dead_letters"
        if (
            webhook["support"] == CapabilitySupport.SUPPORTED_ENABLED.value
            and webhook.get("queuedCount", 0) > 0
        ):
            return ReadinessState.NEEDS_ATTENTION, "webhook_processing_delayed"
        return ReadinessState.READY, "channel_ready"

    def _channel_action(
        self,
        reason: str,
        *,
        product_sync: dict[str, Any],
        product_cache: dict[str, Any],
        order_sync: dict[str, Any],
        connection: dict[str, Any],
    ) -> dict[str, Any]:
        if reason in {"channel_coming_soon", "channel_disabled", "channel_ready"}:
            return _action("NO_ACTION_REQUIRED")
        if reason == "configuration_incomplete":
            return _action("COMPLETE_CHANNEL_CONFIGURATION")
        if reason in {"connection_unhealthy", "connection_degraded"}:
            return _action("TEST_CONNECTION_REVIEW_CREDENTIALS")
        if reason in {"connection_evidence_stale", "connection_never_verified"}:
            next_run = connection.get("nextExpectedAt")
            return (
                _action("NEXT_CONNECTION_CHECK_SCHEDULED", scheduled_at=next_run)
                if next_run
                else _action("TEST_CONNECTION")
            )
        if reason in {"product_sync_stale", "product_sync_never_run"}:
            return self._product_sync_action(product_sync)
        if reason in {
            "product_cache_stale",
            "product_cache_never_run",
            "product_cache_refresh_failed",
        }:
            return self._product_sync_action(product_sync)
        if reason in {"order_sync_stale", "order_sync_never_run"}:
            return _action(
                "NEXT_ORDER_SYNC_SCHEDULED",
                scheduled_at=order_sync.get("nextExpectedAt"),
            )
        if reason == "webhook_dead_letters":
            return _action("REVIEW_WEBHOOK_DEAD_LETTERS")
        if reason == "webhook_processing_delayed":
            return _action("REVIEW_WEBHOOK_QUEUE")
        return _action("REVIEW_DIAGNOSTICS")

    @staticmethod
    def _product_sync_action(product_sync: dict[str, Any]) -> dict[str, Any]:
        mode = product_sync["schedule"]["mode"]
        if mode == ScheduleMode.SCHEDULED.value:
            return _action(
                "NEXT_PRODUCT_SYNC_SCHEDULED",
                scheduled_at=product_sync.get("nextExpectedAt"),
            )
        if mode in {item.value for item in EVENT_DRIVEN_MODES}:
            reconciliation = product_sync.get("reconciliation") or {}
            if product_sync["lastOutcome"] in {
                OutcomeState.FAILED.value,
                OutcomeState.PARTIAL.value,
            }:
                # Delivery is event-driven and the last reconciliation/refresh
                # attempt actually failed. The action is to investigate and
                # retry that attempt, not to prescribe a manual full refresh as
                # though nothing had ever run.
                return _action(
                    "RETRY_RECONCILIATION",
                    scheduled_at=reconciliation.get("nextReconciliationAt"),
                )
            if reconciliation.get("nextReconciliationAt"):
                return _action(
                    "NEXT_PRODUCT_SYNC_SCHEDULED",
                    scheduled_at=reconciliation["nextReconciliationAt"],
                )
            return _action("REFRESH_PRODUCTS")
        required_for_readiness = product_sync["policy"].get("requiredForReadiness")
        if required_for_readiness and mode != ScheduleMode.MANUAL.value:
            # Required by connector policy but no schedule exists and manual
            # refresh isn't the declared design: this is a configuration gap,
            # not stale data waiting on an expected trigger.
            return _action("CONFIGURE_PRODUCT_SYNC_SCHEDULE")
        return _action("REFRESH_PRODUCTS")

    def _basic_action(
        self, reason: str, connection: dict[str, Any]
    ) -> dict[str, Any]:
        if reason in {"source_archived", "source_disabled", "source_ready"}:
            return _action("NO_ACTION_REQUIRED")
        if reason == "source_configuration_incomplete":
            return _action("COMPLETE_SOURCE_CONFIGURATION")
        if reason == "source_connection_unhealthy":
            return _action("TEST_CONNECTION_REVIEW_CREDENTIALS")
        next_run = connection.get("nextExpectedAt")
        return (
            _action("NEXT_CONNECTION_CHECK_SCHEDULED", scheduled_at=next_run)
            if next_run
            else _action("TEST_CONNECTION")
        )

    def _capability(
        self,
        *,
        support: CapabilitySupport,
        freshness: FreshnessState,
        schedule: CapabilityPolicy,
        last_attempt_at: datetime | None,
        last_success_at: datetime | None,
        last_outcome: OutcomeState,
        next_expected_at: datetime | None,
        policy: CapabilityPolicy,
        required: bool,
        evidence_key: str,
    ) -> dict[str, Any]:
        return {
            "support": support.value,
            "freshness": freshness.value,
            "schedule": schedule.shape(),
            "lastAttemptAt": _iso(last_attempt_at),
            "lastSuccessAt": _iso(last_success_at),
            "lastOutcome": last_outcome.value,
            "nextExpectedAt": _iso(next_expected_at),
            "required": required,
            "policy": {
                "freshnessTtlSeconds": policy.freshness_ttl_seconds,
                "source": policy.policy_source,
                "requiredForReadiness": policy.required_for_readiness,
            },
            "evidenceKey": evidence_key,
        }

    def _not_applicable_capability(self, evidence_key: str) -> dict[str, Any]:
        policy = CapabilityPolicy(
            ScheduleMode.NOT_APPLICABLE,
            False,
            None,
            None,
            "capability_contract",
        )
        return self._capability(
            support=CapabilitySupport.NOT_SUPPORTED,
            freshness=FreshnessState.NOT_APPLICABLE,
            schedule=policy,
            last_attempt_at=None,
            last_success_at=None,
            last_outcome=OutcomeState.NEVER_RUN,
            next_expected_at=None,
            policy=policy,
            required=False,
            evidence_key=evidence_key,
        )

    def _not_scheduled_capability(self, evidence_key: str) -> dict[str, Any]:
        policy = CapabilityPolicy(
            ScheduleMode.NOT_SCHEDULED,
            False,
            None,
            None,
            "legacy_missing_policy",
        )
        return self._capability(
            support=CapabilitySupport.SUPPORTED_ENABLED,
            freshness=FreshnessState.NOT_SCHEDULED,
            schedule=policy,
            last_attempt_at=None,
            last_success_at=None,
            last_outcome=OutcomeState.NEVER_RUN,
            next_expected_at=None,
            policy=policy,
            required=False,
            evidence_key=evidence_key,
        )

    def _scheduled_freshness(
        self, value: datetime | None, policy: CapabilityPolicy
    ) -> FreshnessState:
        if policy.mode != ScheduleMode.SCHEDULED or not policy.enabled:
            return FreshnessState.NOT_SCHEDULED
        return self._evidence_freshness(value, policy.freshness_ttl_seconds)

    def _evidence_freshness(
        self, value: datetime | None, ttl_seconds: int | None
    ) -> FreshnessState:
        if value is None:
            return FreshnessState.NEVER_RUN
        if ttl_seconds is None:
            return FreshnessState.FRESH
        return (
            FreshnessState.STALE
            if value < self.now - timedelta(seconds=ttl_seconds)
            else FreshnessState.FRESH
        )

    def _next_expected(
        self, value: datetime | None, policy: CapabilityPolicy
    ) -> datetime | None:
        if (
            policy.mode != ScheduleMode.SCHEDULED
            or not policy.enabled
            or policy.interval_seconds is None
        ):
            return None
        expected = (
            value + timedelta(seconds=policy.interval_seconds)
            if value is not None
            else self.now
        )
        return max(expected, self.now)

    def _resource_freshness(
        self, capabilities: Iterable[dict[str, Any]]
    ) -> FreshnessState:
        values = [
            FreshnessState(item["freshness"])
            for item in capabilities
            if item.get("required")
        ]
        for state in (FreshnessState.STALE, FreshnessState.NEVER_RUN):
            if state in values:
                return state
        if FreshnessState.FRESH in values:
            return FreshnessState.FRESH
        if FreshnessState.NOT_SCHEDULED in values:
            return FreshnessState.NOT_SCHEDULED
        if FreshnessState.NOT_ENABLED in values:
            return FreshnessState.NOT_ENABLED
        return FreshnessState.NOT_APPLICABLE

    @staticmethod
    def _resource_overall(
        readiness: ReadinessState, connectivity: str
    ) -> OverallState:
        # Lifecycle exclusion states take precedence over connection-health
        # coloring: an intentionally non-operational resource is never
        # HEALTHY, ERROR, BLOCKED, or NEEDS_ATTENTION.
        if readiness == ReadinessState.ARCHIVED:
            return OverallState.ARCHIVED
        if readiness == ReadinessState.COMING_SOON:
            return OverallState.COMING_SOON
        if readiness == ReadinessState.DISABLED:
            return OverallState.DISABLED
        if connectivity == ConnectivityState.UNHEALTHY.value:
            return OverallState.ERROR
        if readiness == ReadinessState.BLOCKED:
            return OverallState.BLOCKED
        if readiness == ReadinessState.NEEDS_ATTENTION:
            return OverallState.NEEDS_ATTENTION
        return OverallState.HEALTHY

    # ------------------------------------------------------------------
    # Evidence access
    # ------------------------------------------------------------------

    def _health(self, connector_id: str | None) -> DlConnectorHealth | None:
        if not connector_id or not self._table_exists(DlConnectorHealth):
            return None
        return (
            self.db.query(DlConnectorHealth)
            .filter_by(connector_id=connector_id)
            .order_by(DlConnectorHealth.checked_at.desc())
            .first()
        )

    def _latest_product_refresh(self, channel_id: str) -> DlRefreshJob | None:
        if not self._table_exists(DlRefreshJob):
            return None
        return (
            self.db.query(DlRefreshJob)
            .filter_by(connector_id=channel_id, entity_type="products")
            .order_by(DlRefreshJob.created_at.desc(), DlRefreshJob.id.desc())
            .first()
        )

    def _last_successful_product_sync(self, channel_id: str) -> datetime | None:
        if not self._table_exists(DlProductCache):
            return None
        cache = (
            self.db.query(func.max(DlProductCache.last_successful_read))
            .filter(DlProductCache.connector_id == channel_id)
            .scalar()
        )
        job = None
        if self._table_exists(DlRefreshJob):
            job = (
                self.db.query(func.max(DlRefreshJob.completed_at))
                .filter(
                    DlRefreshJob.connector_id == channel_id,
                    DlRefreshJob.entity_type == "products",
                    DlRefreshJob.status.in_(("completed", "completed_with_warnings")),
                )
                .scalar()
            )
        return _max_dt(cache, job)

    def _order_checkpoints(self, channel_id: str) -> list[OrderSyncCheckpoint]:
        if not self._table_exists(OrderSyncCheckpoint):
            return []
        return self.db.query(OrderSyncCheckpoint).filter_by(channel_id=channel_id).all()

    def _configured(
        self, instance: IntegrationConnectorInstance | None, provider: str
    ) -> bool:
        if instance is None:
            return False
        required = {
            "woocommerce": {"url", "key", "secret"},
            "snappshop": {"token", "agent_identifier", "vendor_id"},
            "tapsishop": {"token"},
            "technolife": {"api_key", "encryption_secret"},
            "digikala": {"access_token"},
            "nextcloud": {"url", "username", "password", "spreadsheet_path"},
        }.get(provider, set())
        settings = {item.key: item for item in instance.settings}
        return bool(required) and all(
            settings.get(key) is not None and settings[key].configured
            for key in required
        )

    @staticmethod
    def _setting_configured(
        instance: IntegrationConnectorInstance, key: str
    ) -> bool:
        row = next((item for item in instance.settings if item.key == key), None)
        return bool(row and row.configured)

    @staticmethod
    def _channel_display_name(
        instance: IntegrationConnectorInstance | None,
    ) -> str | None:
        if instance is None:
            return None
        custom = next(
            (item for item in instance.settings if item.key == "display_name"), None
        )
        value = str(custom.value_json or "").strip() if custom else ""
        return value or str(instance.name or "").strip() or None

    def _order_interval(
        self,
        provider: str,
        checkpoints: list[OrderSyncCheckpoint],
        instance: IntegrationConnectorInstance | None,
    ) -> int:
        values = [item.interval_seconds for item in checkpoints if item.interval_seconds]
        if values:
            return min(values)
        settings = {item.key: item.value_json for item in instance.settings} if instance else {}
        key = (
            "order_sync_poll_interval_seconds"
            if provider == "snappshop"
            else "order_sync_reconcile_interval_seconds"
        )
        default = 300 if provider == "snappshop" else 900
        return _positive_int(settings.get(key), default)

    @staticmethod
    def _refresh_attempt_at(refresh: DlRefreshJob | None) -> datetime | None:
        if refresh is None:
            return None
        return refresh.started_at or refresh.created_at

    @staticmethod
    def _refresh_outcome(refresh: DlRefreshJob | None) -> OutcomeState:
        if refresh is None:
            return OutcomeState.NEVER_RUN
        return {
            "completed": OutcomeState.SUCCESSFUL,
            "completed_with_warnings": OutcomeState.PARTIAL,
            "failed": OutcomeState.FAILED,
            "partial_failed": OutcomeState.PARTIAL,
            "running": OutcomeState.RUNNING,
            "pending": OutcomeState.RUNNING,
            "cancelled": OutcomeState.CANCELLED,
        }.get(refresh.status, OutcomeState.UNKNOWN)

    def _channel_advanced_evidence(
        self,
        channel_id: str,
        health: DlConnectorHealth | None,
        product_sync: dict[str, Any],
        order_sync: dict[str, Any],
        observation_confidence: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        evidence = [
            {
                "key": "data_layer_health",
                "label": "Connection health record",
                "value": health.status if health else None,
                "recordedAt": _iso(health.checked_at) if health else None,
            },
            {
                "key": "connector_capability",
                "label": "Connector capability",
                "value": product_sync["support"],
                "recordedAt": product_sync["lastAttemptAt"],
            },
            {
                "key": "integration_polling_policy",
                "label": "Polling schedule",
                "value": product_sync["schedule"]["mode"],
                "recordedAt": product_sync["lastAttemptAt"],
            },
            {
                "key": "order_sync_checkpoint",
                "label": "Order synchronization checkpoint",
                "value": order_sync["lastOutcome"],
                "recordedAt": order_sync["lastAttemptAt"],
            },
            {
                "key": "resource_identity",
                "label": "Resource identity",
                "value": channel_id,
                "recordedAt": None,
            },
        ]
        if observation_confidence is not None:
            evidence.append(
                {
                    "key": "observation_confidence",
                    "label": "Observation confidence",
                    "value": observation_confidence["value"],
                    "recordedAt": observation_confidence["computedAt"],
                }
            )
        return evidence

    def _table_exists(self, model: Any) -> bool:
        return bool(inspect(self.db.get_bind()).has_table(model.__tablename__))


def _action(code: str, *, scheduled_at: str | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "scheduledAt": scheduled_at,
        "actionable": code != "NO_ACTION_REQUIRED",
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _max_dt(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _max_iso(*values: str | None) -> str | None:
    present = [value for value in values if value]
    return max(present) if present else None


def _env_bool(name: str, default: bool) -> bool:
    return parse_config_bool(os.environ.get(name), default=default)


def _env_optional_positive_int(name: str) -> int | None:
    value = os.environ.get(name)
    if value in (None, ""):
        return None
    return _positive_int(value, 0) or None


def _env_positive_int(name: str, default: int) -> int:
    return _positive_int(os.environ.get(name), default)


def _env_nonnegative_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, "") or default))
    except (TypeError, ValueError):
        return default


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
