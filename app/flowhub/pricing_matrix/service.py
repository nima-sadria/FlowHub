"""Transactional application service for Pricing Matrix configuration."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.pricing_matrix.arithmetic import PRICING_ARITHMETIC_VERSION
from app.flowhub.pricing_matrix.contracts import (
    PricingGuardSet,
    PricingRule,
    RateMode,
    RoundingMode,
    RoundOrder,
)
from app.flowhub.pricing_matrix.errors import PricingMatrixError
from app.flowhub.pricing_matrix.models import (
    ChannelPricingPolicyHead,
    ProductGroupMember,
    ProductGroupRevision,
    PricingChannelConfigRevision,
    PricingPolicyLifecycleEvent,
    PricingPolicyRevision,
    PricingRuleEntry,
    WorkspacePricingBinding,
)
from app.flowhub.pricing_matrix.units import (
    UNIT_REGISTRY_VERSION,
    resolve_currency_unit,
    validate_rule_channel_compatibility,
)
from app.flowhub.unified_workspace.domain import checksum, utcnow
from app.flowhub.unified_workspace.models import CanonicalProduct, CurrencyProfile, WorkspaceChannel


def _id() -> str:
    return str(uuid.uuid4())


class PricingMatrixService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_policy_revision(
        self,
        *,
        payload: dict[str, Any],
        user: FlowHubUser,
    ) -> dict[str, Any]:
        policy_id = str(payload.get("policy_id") or _id())
        latest_number = (
            self.db.query(func.max(PricingPolicyRevision.revision_number))
            .filter(PricingPolicyRevision.policy_id == policy_id)
            .scalar()
            or 0
        )
        revision_number = int(latest_number) + 1
        round_order = str(payload["round_order"])
        rule_payloads = list(payload["rules"])
        if not rule_payloads:
            raise PricingMatrixError("policy_rules_required")

        scopes: set[tuple[str | None, str | None, str | None]] = set()
        prepared_rules: list[tuple[dict[str, Any], PricingRule, int]] = []
        for item in rule_payloads:
            channel_id = _optional_text(item.get("channel_id"))
            product_ref = _optional_text(item.get("product_ref"))
            group_id = _optional_text(item.get("product_group_revision_id"))
            if product_ref and group_id:
                raise PricingMatrixError("rule_scope_invalid")
            if channel_id and self.db.get(WorkspaceChannel, channel_id) is None:
                raise PricingMatrixError("channel_not_found")
            if group_id and self.db.get(ProductGroupRevision, group_id) is None:
                raise PricingMatrixError("product_group_revision_not_found")
            scope = (channel_id, product_ref, group_id)
            if scope in scopes:
                raise PricingMatrixError("rule_scope_duplicate")
            scopes.add(scope)
            guards = PricingGuardSet(**dict(item.get("guards") or {}))
            rule = PricingRule(
                rate_mode=RateMode(str(item["rate_mode"])),
                rate_value=item["rate_value"],
                fixed_addend_minor=item.get("fixed_addend_minor", 0),
                round_mode=RoundingMode(str(item.get("round_mode", "floor"))),
                round_step_minor=item.get("round_step_minor", 1),
                surcharge_minor=item.get("surcharge_minor", 0),
                round_order=RoundOrder(round_order),
                guards=guards,
            )
            prepared_rules.append((item, rule, _scope_rank(channel_id, product_ref, group_id)))

        policy_payload = {
            "policy_id": policy_id,
            "revision_number": revision_number,
            "name": str(payload["name"]).strip(),
            "computation_currency": str(payload["computation_currency"]).strip().upper(),
            "basis_strategy": "min",
            "round_order": round_order,
            "max_quote_age_days": int(payload["max_quote_age_days"]),
            "min_quote_count": int(payload["min_quote_count"]),
            "evaluation_timezone": str(payload["evaluation_timezone"]),
            "arithmetic_version": PRICING_ARITHMETIC_VERSION,
            "unit_registry_version": UNIT_REGISTRY_VERSION,
            "rules": [
                {
                    **item,
                    "guards": asdict(rule.guards),
                    "scope_rank": rank,
                }
                for item, rule, rank in prepared_rules
            ],
        }
        row = PricingPolicyRevision(
            id=_id(),
            policy_id=policy_id,
            revision_number=revision_number,
            name=policy_payload["name"],
            computation_currency=policy_payload["computation_currency"],
            basis_strategy="min",
            round_order=round_order,
            max_quote_age_days=policy_payload["max_quote_age_days"],
            min_quote_count=policy_payload["min_quote_count"],
            evaluation_timezone=policy_payload["evaluation_timezone"],
            arithmetic_version=PRICING_ARITHMETIC_VERSION,
            unit_registry_version=UNIT_REGISTRY_VERSION,
            checksum=checksum(policy_payload),
            created_by_user_id=user.id,
        )
        try:
            self.db.add(row)
            self.db.flush()
            for item, rule, rank in prepared_rules:
                rule_contract = {
                    "policy_revision_id": row.id,
                    "channel_id": _optional_text(item.get("channel_id")),
                    "product_ref": _optional_text(item.get("product_ref")),
                    "product_group_revision_id": _optional_text(
                        item.get("product_group_revision_id")
                    ),
                    "rate_mode": rule.rate_mode.value,
                    "rate_value": rule.rate_value,
                    "fixed_addend_minor": rule.fixed_addend_minor,
                    "round_mode": rule.round_mode.value,
                    "round_step_minor": rule.round_step_minor,
                    "surcharge_minor": rule.surcharge_minor,
                    "guards": asdict(rule.guards),
                    "scope_rank": rank,
                }
                self.db.add(
                    PricingRuleEntry(
                        id=_id(),
                        policy_revision_id=row.id,
                        channel_id=rule_contract["channel_id"],
                        product_ref=rule_contract["product_ref"],
                        product_group_revision_id=rule_contract["product_group_revision_id"],
                        rate_mode=rule.rate_mode.value,
                        rate_value=rule.rate_value,
                        fixed_addend_minor=rule.fixed_addend_minor,
                        round_mode=rule.round_mode.value,
                        round_step_minor=rule.round_step_minor,
                        surcharge_minor=rule.surcharge_minor,
                        guards_json=asdict(rule.guards),
                        scope_rank=rank,
                        checksum=checksum(rule_contract),
                    )
                )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.policy(row.id)

    def create_product_group_revision(
        self,
        *,
        payload: dict[str, Any],
        user: FlowHubUser,
    ) -> dict[str, Any]:
        product_group_id = str(payload.get("product_group_id") or _id())
        product_ids = sorted(set(str(item) for item in payload["canonical_product_ids"]))
        if len(product_ids) != len(payload["canonical_product_ids"]):
            raise PricingMatrixError("product_group_member_duplicate")
        known_ids = {
            item[0]
            for item in self.db.query(CanonicalProduct.id)
            .filter(CanonicalProduct.id.in_(product_ids))
            .all()
        }
        if len(known_ids) != len(product_ids):
            raise PricingMatrixError("canonical_product_not_found")
        revision_number = int(
            self.db.query(func.max(ProductGroupRevision.revision_number))
            .filter(ProductGroupRevision.product_group_id == product_group_id)
            .scalar()
            or 0
        ) + 1
        group_contract = {
            "product_group_id": product_group_id,
            "revision_number": revision_number,
            "name": str(payload["name"]).strip(),
            "canonical_product_ids": product_ids,
        }
        row = ProductGroupRevision(
            id=_id(),
            product_group_id=product_group_id,
            revision_number=revision_number,
            name=group_contract["name"],
            checksum=checksum(group_contract),
            created_by_user_id=user.id,
        )
        try:
            self.db.add(row)
            self.db.flush()
            self.db.add_all(
                [
                    ProductGroupMember(
                        id=_id(),
                        product_group_revision_id=row.id,
                        canonical_product_id=product_id,
                    )
                    for product_id in product_ids
                ]
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.product_group(row.id)

    def product_groups(self) -> list[dict[str, Any]]:
        rows = self.db.query(ProductGroupRevision).order_by(
            ProductGroupRevision.created_at.desc(), ProductGroupRevision.id.asc()
        )
        return [self._product_group_contract(row) for row in rows]

    def product_group(self, revision_id: str) -> dict[str, Any]:
        row = self.db.get(ProductGroupRevision, revision_id)
        if row is None:
            raise PricingMatrixError("product_group_revision_not_found")
        return self._product_group_contract(row)

    def policies(self) -> list[dict[str, Any]]:
        rows = self.db.query(PricingPolicyRevision).order_by(
            PricingPolicyRevision.created_at.desc(), PricingPolicyRevision.id.asc()
        )
        return [self._policy_contract(row, include_rules=False) for row in rows]

    def policy(self, revision_id: str) -> dict[str, Any]:
        row = self.db.get(PricingPolicyRevision, revision_id)
        if row is None:
            raise PricingMatrixError("policy_revision_not_found")
        return self._policy_contract(row, include_rules=True)

    def declare_unit(
        self,
        *,
        scope: str,
        scope_reference: str,
        currency: str,
        unit: str,
        user: FlowHubUser,
        connector_config_version: str = "unversioned",
        commit: bool = True,
    ) -> dict[str, Any]:
        if scope not in {"global", "source", "channel"}:
            raise PricingMatrixError("currency_scope_invalid")
        spec = resolve_currency_unit(currency, unit)
        reference = scope_reference if scope != "global" else "default"
        if scope == "channel" and self.db.get(WorkspaceChannel, reference) is None:
            from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

            UnifiedWorkspaceService(self.db)._seed_channels()
            if self.db.get(WorkspaceChannel, reference) is None:
                raise PricingMatrixError("channel_not_found")
        latest = (
            self.db.query(CurrencyProfile)
            .filter_by(scope=scope, scope_reference=reference)
            .order_by(CurrencyProfile.version.desc())
            .first()
        )
        if latest and (latest.currency, latest.unit) == (spec.currency, spec.unit):
            profile = latest
        else:
            version = latest.version + 1 if latest else 1
            profile_contract = {
                "scope": scope,
                "scope_reference": reference,
                "currency": spec.currency,
                "unit": spec.unit,
                "normalization_currency": spec.currency,
                "normalization_unit": spec.canonical_unit,
                "conversion_factor": str(spec.canonical_factor),
                "conversion_rule": UNIT_REGISTRY_VERSION,
                "version": version,
            }
            profile = CurrencyProfile(
                id=_id(),
                scope=scope,
                scope_reference=reference,
                currency=spec.currency,
                unit=spec.unit,
                normalization_currency=spec.currency,
                normalization_unit=spec.canonical_unit,
                conversion_factor=Decimal(spec.canonical_factor),
                conversion_rule=UNIT_REGISTRY_VERSION,
                checksum=checksum(profile_contract),
                version=version,
                enabled=True,
            )
            self.db.add(profile)
            self.db.flush()

        channel_config: PricingChannelConfigRevision | None = None
        if scope == "channel":
            latest_config = (
                self.db.query(PricingChannelConfigRevision)
                .filter_by(channel_id=reference)
                .order_by(PricingChannelConfigRevision.revision_number.desc())
                .first()
            )
            if latest_config and (
                latest_config.currency_profile_id == profile.id
                and latest_config.connector_config_version == connector_config_version
            ):
                channel_config = latest_config
            else:
                config_version = latest_config.revision_number + 1 if latest_config else 1
                config_contract = {
                    "channel_id": reference,
                    "revision_number": config_version,
                    "currency_profile_id": profile.id,
                    "currency": spec.currency,
                    "currency_unit": spec.unit,
                    "unit_registry_version": UNIT_REGISTRY_VERSION,
                    "connector_config_version": connector_config_version,
                }
                channel_config = PricingChannelConfigRevision(
                    id=_id(),
                    channel_id=reference,
                    revision_number=config_version,
                    currency_profile_id=profile.id,
                    currency=spec.currency,
                    currency_unit=spec.unit,
                    unit_registry_version=UNIT_REGISTRY_VERSION,
                    connector_config_version=connector_config_version,
                    checksum=checksum(config_contract),
                    created_by_user_id=user.id,
                )
                self.db.add(channel_config)
            if self.db.get(ChannelPricingPolicyHead, reference) is None:
                self.db.add(ChannelPricingPolicyHead(channel_id=reference, head_version=0))
        try:
            if commit:
                self.db.commit()
            else:
                self.db.flush()
        except Exception:
            self.db.rollback()
            raise
        return {
            "scope": scope,
            "scopeReference": reference,
            "currency": profile.currency,
            "unit": profile.unit,
            "canonicalCurrency": profile.normalization_currency,
            "canonicalUnit": profile.normalization_unit,
            "canonicalFactor": int(profile.conversion_factor),
            "currencyProfileId": profile.id,
            "version": profile.version,
            "channelConfigRevisionId": channel_config.id if channel_config else None,
            "unitRegistryVersion": UNIT_REGISTRY_VERSION,
        }

    def unit_declaration(self, scope: str, scope_reference: str) -> dict[str, Any]:
        reference = scope_reference if scope != "global" else "default"
        row = (
            self.db.query(CurrencyProfile)
            .filter_by(scope=scope, scope_reference=reference)
            .order_by(CurrencyProfile.version.desc())
            .first()
        )
        if row is None:
            return {
                "scope": scope,
                "scopeReference": reference,
                "status": "unresolved",
                "currency": None,
                "unit": None,
            }
        return {
            "scope": scope,
            "scopeReference": reference,
            "status": "resolved",
            "currency": row.currency,
            "unit": row.unit,
            "canonicalCurrency": row.normalization_currency,
            "canonicalUnit": row.normalization_unit,
            "canonicalFactor": int(row.conversion_factor),
            "currencyProfileId": row.id,
            "version": row.version,
        }

    def activate(
        self,
        *,
        channel_id: str,
        policy_revision_id: str,
        expected_head_version: int,
        reason: str,
        user: FlowHubUser,
    ) -> dict[str, Any]:
        policy = self.db.get(PricingPolicyRevision, policy_revision_id)
        if policy is None:
            raise PricingMatrixError("policy_revision_not_found")
        config = (
            self.db.query(PricingChannelConfigRevision)
            .filter_by(channel_id=channel_id)
            .order_by(PricingChannelConfigRevision.revision_number.desc())
            .first()
        )
        if config is None:
            raise PricingMatrixError("channel_unit_unresolved")
        if config.currency != policy.computation_currency:
            raise PricingMatrixError("channel_computation_currency_mismatch")
        spec = resolve_currency_unit(config.currency, config.currency_unit)
        rules = self.db.query(PricingRuleEntry).filter(
            PricingRuleEntry.policy_revision_id == policy.id,
            or_(PricingRuleEntry.channel_id.is_(None), PricingRuleEntry.channel_id == channel_id),
        )
        if not rules.count():
            raise PricingMatrixError("channel_policy_rule_missing")
        for entry in rules:
            validate_rule_channel_compatibility(
                round_step_minor=entry.round_step_minor,
                surcharge_minor=entry.surcharge_minor,
                round_order=policy.round_order,
                channel_spec=spec,
            )
        return self._append_lifecycle_event(
            channel_id=channel_id,
            event_kind="activate",
            policy_revision_id=policy.id,
            channel_config_revision_id=config.id,
            expected_head_version=expected_head_version,
            reason=reason,
            user=user,
        )

    def deactivate(
        self,
        *,
        channel_id: str,
        expected_head_version: int,
        reason: str,
        user: FlowHubUser,
    ) -> dict[str, Any]:
        head = self.db.get(ChannelPricingPolicyHead, channel_id)
        if head is None or head.effective_activation_id is None:
            raise PricingMatrixError("pricing_policy_not_activated")
        return self._append_lifecycle_event(
            channel_id=channel_id,
            event_kind="deactivate",
            policy_revision_id=None,
            channel_config_revision_id=None,
            expected_head_version=expected_head_version,
            reason=reason,
            user=user,
        )

    def head(self, channel_id: str) -> dict[str, Any]:
        head = self.db.get(ChannelPricingPolicyHead, channel_id)
        if head is None:
            return {
                "channelId": channel_id,
                "headVersion": 0,
                "currentEventId": None,
                "effectiveActivationId": None,
                "status": "inactive",
            }
        event = self.db.get(PricingPolicyLifecycleEvent, head.current_event_id)
        return {
            "channelId": channel_id,
            "headVersion": head.head_version,
            "currentEventId": head.current_event_id,
            "effectiveActivationId": head.effective_activation_id,
            "status": "active" if head.effective_activation_id else "inactive",
            "policyRevisionId": event.policy_revision_id if event else None,
            "channelConfigRevisionId": event.channel_config_revision_id if event else None,
            "updatedAt": head.updated_at.isoformat(),
        }

    def lifecycle_events(self, channel_id: str) -> list[dict[str, Any]]:
        if self.db.get(WorkspaceChannel, channel_id) is None:
            raise PricingMatrixError("channel_not_found")
        rows = (
            self.db.query(PricingPolicyLifecycleEvent)
            .filter_by(channel_id=channel_id)
            .order_by(PricingPolicyLifecycleEvent.occurred_at.asc(), PricingPolicyLifecycleEvent.id.asc())
            .all()
        )
        return [
            {
                "id": item.id,
                "channelId": item.channel_id,
                "eventKind": item.event_kind,
                "predecessorEventId": item.predecessor_event_id,
                "effectiveActivationId": item.effective_activation_id,
                "policyRevisionId": item.policy_revision_id,
                "channelConfigRevisionId": item.channel_config_revision_id,
                "supersedesActivationId": item.supersedes_activation_id,
                "actorUserId": item.actor_user_id,
                "reason": item.reason,
                "occurredAt": item.occurred_at.isoformat(),
            }
            for item in rows
        ]

    def bind_workspace_channels(
        self,
        *,
        workspace_id: str,
        channel_ids: list[str],
        evaluated_at: Any,
        execution_policy_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Pin the effective pricing decision without weakening per-Channel isolation."""

        bindings: list[WorkspacePricingBinding] = []
        issues: dict[str, str] = {}
        for channel_id in sorted(set(channel_ids)):
            existing = (
                self.db.query(WorkspacePricingBinding)
                .filter_by(workspace_id=workspace_id, channel_id=channel_id)
                .one_or_none()
            )
            if existing is not None:
                issue = self._binding_issue(existing)
                if issue:
                    issues[channel_id] = issue
                else:
                    bindings.append(existing)
                continue

            head = self.db.get(ChannelPricingPolicyHead, channel_id)
            if head is None or head.effective_activation_id is None:
                issues[channel_id] = "policy_not_activated"
                continue
            event = self.db.get(PricingPolicyLifecycleEvent, head.effective_activation_id)
            if (
                event is None
                or event.event_kind != "activate"
                or event.policy_revision_id is None
                or event.channel_config_revision_id is None
            ):
                issues[channel_id] = "pricing_activation_invalid"
                continue
            latest_config = self._latest_channel_config(channel_id)
            if latest_config is None:
                issues[channel_id] = "channel_unit_unresolved"
                continue
            if latest_config.id != event.channel_config_revision_id:
                issues[channel_id] = "channel_config_outdated"
                continue
            binding = WorkspacePricingBinding(
                id=_id(),
                workspace_id=workspace_id,
                channel_id=channel_id,
                policy_revision_id=event.policy_revision_id,
                pricing_policy_activation_id=event.id,
                channel_config_revision_id=latest_config.id,
                execution_policy_snapshot_json=dict(execution_policy_snapshot),
                workspace_pricing_evaluated_at=evaluated_at,
            )
            self.db.add(binding)
            bindings.append(binding)
        self.db.flush()
        return {
            "bindings": [self._binding_contract(item) for item in bindings],
            "issues": issues,
        }

    def verify_workspace_channels(
        self, *, workspace_id: str, channel_ids: list[str]
    ) -> dict[str, str]:
        issues: dict[str, str] = {}
        for channel_id in sorted(set(channel_ids)):
            binding = (
                self.db.query(WorkspacePricingBinding)
                .filter_by(workspace_id=workspace_id, channel_id=channel_id)
                .one_or_none()
            )
            if binding is None:
                issues[channel_id] = "pricing_binding_missing"
                continue
            issue = self._binding_issue(binding)
            if issue:
                issues[channel_id] = issue
        return issues

    def workspace_bindings(self, workspace_id: str) -> list[dict[str, Any]]:
        rows = (
            self.db.query(WorkspacePricingBinding)
            .filter_by(workspace_id=workspace_id)
            .order_by(WorkspacePricingBinding.channel_id.asc())
            .all()
        )
        return [self._binding_contract(item) for item in rows]

    def _binding_issue(self, binding: WorkspacePricingBinding) -> str | None:
        head = self.db.get(ChannelPricingPolicyHead, binding.channel_id)
        if head is None or head.effective_activation_id is None:
            return "pricing_policy_deactivated"
        if head.effective_activation_id != binding.pricing_policy_activation_id:
            return "pricing_decision_outdated"
        event = self.db.get(PricingPolicyLifecycleEvent, head.effective_activation_id)
        if event is None or event.policy_revision_id != binding.policy_revision_id:
            return "pricing_activation_invalid"
        latest_config = self._latest_channel_config(binding.channel_id)
        if latest_config is None:
            return "channel_unit_unresolved"
        if latest_config.id != binding.channel_config_revision_id:
            return "channel_config_outdated"
        return None

    def _latest_channel_config(
        self, channel_id: str
    ) -> PricingChannelConfigRevision | None:
        return (
            self.db.query(PricingChannelConfigRevision)
            .filter_by(channel_id=channel_id)
            .order_by(PricingChannelConfigRevision.revision_number.desc())
            .first()
        )

    @staticmethod
    def _binding_contract(binding: WorkspacePricingBinding) -> dict[str, Any]:
        return {
            "id": binding.id,
            "workspaceId": binding.workspace_id,
            "channelId": binding.channel_id,
            "policyRevisionId": binding.policy_revision_id,
            "pricingPolicyActivationId": binding.pricing_policy_activation_id,
            "channelConfigRevisionId": binding.channel_config_revision_id,
            "executionPolicySnapshot": binding.execution_policy_snapshot_json,
            "workspacePricingEvaluatedAt": (
                binding.workspace_pricing_evaluated_at.isoformat()
                if binding.workspace_pricing_evaluated_at is not None
                else None
            ),
        }

    def _append_lifecycle_event(
        self,
        *,
        channel_id: str,
        event_kind: str,
        policy_revision_id: str | None,
        channel_config_revision_id: str | None,
        expected_head_version: int,
        reason: str,
        user: FlowHubUser,
    ) -> dict[str, Any]:
        head = self.db.get(ChannelPricingPolicyHead, channel_id)
        if head is None:
            if self.db.get(WorkspaceChannel, channel_id) is None:
                raise PricingMatrixError("channel_not_found")
            head = ChannelPricingPolicyHead(channel_id=channel_id, head_version=0)
            self.db.add(head)
            self.db.flush()
        if head.head_version != expected_head_version:
            raise PricingMatrixError("pricing_policy_head_conflict")
        event_id = _id()
        previous_activation = head.effective_activation_id
        event = PricingPolicyLifecycleEvent(
            id=event_id,
            channel_id=channel_id,
            event_kind=event_kind,
            predecessor_event_id=head.current_event_id,
            effective_activation_id=event_id if event_kind == "activate" else None,
            policy_revision_id=policy_revision_id,
            channel_config_revision_id=channel_config_revision_id,
            supersedes_activation_id=previous_activation,
            actor_user_id=user.id,
            reason=reason.strip(),
        )
        try:
            self.db.add(event)
            self.db.flush()
            updated = (
                self.db.query(ChannelPricingPolicyHead)
                .filter(
                    ChannelPricingPolicyHead.channel_id == channel_id,
                    ChannelPricingPolicyHead.head_version == expected_head_version,
                )
                .update(
                    {
                        ChannelPricingPolicyHead.current_event_id: event_id,
                        ChannelPricingPolicyHead.effective_activation_id: (
                            event_id if event_kind == "activate" else None
                        ),
                        ChannelPricingPolicyHead.head_version: expected_head_version + 1,
                        ChannelPricingPolicyHead.updated_at: utcnow(),
                    },
                    synchronize_session=False,
                )
            )
            if updated != 1:
                raise PricingMatrixError("pricing_policy_head_conflict")
            self.db.commit()
            self.db.expire_all()
        except Exception:
            self.db.rollback()
            raise
        return self.head(channel_id)

    def _policy_contract(
        self, row: PricingPolicyRevision, *, include_rules: bool
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": row.id,
            "policyId": row.policy_id,
            "revisionNumber": row.revision_number,
            "name": row.name,
            "computationCurrency": row.computation_currency,
            "basisStrategy": row.basis_strategy,
            "roundOrder": row.round_order,
            "maxQuoteAgeDays": row.max_quote_age_days,
            "minQuoteCount": row.min_quote_count,
            "evaluationTimezone": row.evaluation_timezone,
            "arithmeticVersion": row.arithmetic_version,
            "unitRegistryVersion": row.unit_registry_version,
            "checksum": row.checksum,
            "createdAt": row.created_at.isoformat(),
        }
        if include_rules:
            rules = self.db.query(PricingRuleEntry).filter_by(policy_revision_id=row.id).order_by(
                PricingRuleEntry.scope_rank.asc(), PricingRuleEntry.id.asc()
            )
            body["rules"] = [
                {
                    "id": item.id,
                    "channelId": item.channel_id,
                    "productRef": item.product_ref,
                    "productGroupRevisionId": item.product_group_revision_id,
                    "rateMode": item.rate_mode,
                    "rateValue": item.rate_value,
                    "fixedAddendMinor": item.fixed_addend_minor,
                    "roundMode": item.round_mode,
                    "roundStepMinor": item.round_step_minor,
                    "surchargeMinor": item.surcharge_minor,
                    "guards": item.guards_json,
                    "scopeRank": item.scope_rank,
                }
                for item in rules
            ]
        return body

    def _product_group_contract(self, row: ProductGroupRevision) -> dict[str, Any]:
        members = (
            self.db.query(ProductGroupMember.canonical_product_id)
            .filter_by(product_group_revision_id=row.id)
            .order_by(ProductGroupMember.canonical_product_id.asc())
            .all()
        )
        return {
            "id": row.id,
            "productGroupId": row.product_group_id,
            "revisionNumber": row.revision_number,
            "name": row.name,
            "canonicalProductIds": [item[0] for item in members],
            "checksum": row.checksum,
            "createdAt": row.created_at.isoformat(),
        }


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _scope_rank(channel_id: str | None, product_ref: str | None, group_id: str | None) -> int:
    if channel_id and product_ref:
        return 1
    if channel_id and group_id:
        return 2
    if channel_id:
        return 3
    if product_ref:
        return 4
    if group_id:
        return 5
    return 6
