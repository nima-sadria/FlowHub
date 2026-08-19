"""Connector Strategy Resolver.

Workspace expresses intent as a provider-neutral ``ChannelReadRequest``
("refresh Channel state", "verify these selected products"). This module is
what decides *how* to fulfill that intent -- which concrete execution
mechanism to run -- based on connector capabilities, scope, and cache state.
Workspace never chooses a mechanism directly. See
docs/architecture/ADR_CHANNEL_READ_ARCHITECTURE.md.

This module is purely additive: it does not replace or call
``IncrementalReadEngine.determine_strategy()``, which keeps serving the
existing CHANNEL-scope manual/scheduled call sites unchanged. ``resolve()``
is a pure function -- no I/O, no side effects -- so callers own fetching
``has_cache`` and any confidence evidence beforehand.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.flowhub.read_engine.contracts import (
    ChannelReadRequest,
    ConnectorReadCapabilities,
    ReadReason,
    ReadScope,
    ReadStrategy,
)
from app.flowhub.read_engine.exceptions import IncrementalReadUnsupported

# Concrete execution mechanisms. The first three are the exact strings
# IncrementalReadEngine.determine_strategy() already produces today; LIGHT
# and DEEP scope introduce the other two.
MECHANISM_INITIAL_FULL_READ = "initial_full_read"
MECHANISM_MODIFIED_SINCE = "modified_since"
MECHANISM_METADATA_FILTER = "metadata_filter"
MECHANISM_ENTITY_READ = "entity_read"
MECHANISM_DEEP_RECONCILIATION = "deep_reconciliation"


@dataclass(frozen=True)
class ResolvedReadPlan:
    strategy: ReadStrategy
    scope: ReadScope
    mechanism: str
    identifiers: tuple[str, ...]
    reason: ReadReason


def resolve(
    request: ChannelReadRequest,
    capabilities: ConnectorReadCapabilities,
    *,
    has_cache: bool,
) -> ResolvedReadPlan:
    """Resolve a request to a concrete plan, or raise IncrementalReadUnsupported.

    Never silently escalates to a more expensive mechanism than the
    connector's advertised capabilities and the request's own scope allow.
    """
    if request.scope is ReadScope.PRODUCT:
        return _resolve_product_scope(request, capabilities)
    return _resolve_channel_scope(request, capabilities, has_cache=has_cache)


def _resolve_product_scope(
    request: ChannelReadRequest, capabilities: ConnectorReadCapabilities
) -> ResolvedReadPlan:
    if capabilities.supports_entity_read:
        return ResolvedReadPlan(
            strategy=ReadStrategy.LIGHT,
            scope=ReadScope.PRODUCT,
            mechanism=MECHANISM_ENTITY_READ,
            identifiers=request.identifiers,
            reason=request.reason,
        )
    if capabilities.supports_batch_read:
        # No dedicated single-entity endpoint, but the connector can still
        # fetch exactly the requested IDs through its batch mechanism --
        # still O(requested), never a full scan.
        return ResolvedReadPlan(
            strategy=ReadStrategy.LIGHT,
            scope=ReadScope.PRODUCT,
            mechanism=MECHANISM_METADATA_FILTER,
            identifiers=request.identifiers,
            reason=request.reason,
        )
    raise IncrementalReadUnsupported(
        "incremental_read_unsupported: connector cannot target specific entities"
    )


def _resolve_channel_scope(
    request: ChannelReadRequest,
    capabilities: ConnectorReadCapabilities,
    *,
    has_cache: bool,
) -> ResolvedReadPlan:
    if request.strategy is ReadStrategy.DEEP:
        if not capabilities.supports_deep_recovery:
            raise IncrementalReadUnsupported(
                "incremental_read_unsupported: connector does not support DEEP recovery"
            )
        return ResolvedReadPlan(
            strategy=ReadStrategy.DEEP,
            scope=ReadScope.CHANNEL,
            mechanism=MECHANISM_DEEP_RECONCILIATION,
            identifiers=(),
            reason=request.reason,
        )

    if request.strategy is ReadStrategy.FULL or not has_cache:
        if not capabilities.supports_full_snapshot:
            raise IncrementalReadUnsupported(
                "incremental_read_unsupported: connector cannot build a full snapshot"
            )
        return ResolvedReadPlan(
            strategy=ReadStrategy.FULL,
            scope=ReadScope.CHANNEL,
            mechanism=MECHANISM_INITIAL_FULL_READ,
            identifiers=(),
            reason=request.reason,
        )

    if capabilities.supports_modified_since or capabilities.supports_updated_after:
        return ResolvedReadPlan(
            strategy=ReadStrategy.LIGHT,
            scope=ReadScope.CHANNEL,
            mechanism=MECHANISM_MODIFIED_SINCE,
            identifiers=(),
            reason=request.reason,
        )
    if capabilities.supports_batch_read:
        return ResolvedReadPlan(
            strategy=ReadStrategy.LIGHT,
            scope=ReadScope.CHANNEL,
            mechanism=MECHANISM_METADATA_FILTER,
            identifiers=(),
            reason=request.reason,
        )
    raise IncrementalReadUnsupported(
        "incremental_read_unsupported: connector supports no incremental channel-scope mechanism"
    )
