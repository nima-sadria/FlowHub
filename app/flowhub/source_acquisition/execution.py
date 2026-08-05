"""Authoritative orchestration for one Source acquisition attempt."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.connectors.common.source_http import SourceHttpClient, SourceHttpError
from app.flowhub.source_acquisition.errors import SourceAcquisitionError
from app.flowhub.source_acquisition.models import AcquisitionRun, SourceObservation
from app.flowhub.source_acquisition.schema_assessment import SourceSchemaAssessmentService
from app.flowhub.source_acquisition.service import SourceAcquisitionService
from app.flowhub.source_workspace.models import SourceMappingRevision
from app.flowhub.unified_workspace.domain import checksum, utcnow


@dataclass(frozen=True)
class ProviderCapture:
    """Validated provider output; secret material is deliberately absent."""

    result: str
    resource_identity: str | None = None
    content: bytes | None = field(default=None, repr=False)
    provenance: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    snapshot_references: list[dict[str, Any]] = field(default_factory=list)
    observed_at: datetime | None = None


class SourceAcquisitionProvider(Protocol):
    async def capture(self, http_client: SourceHttpClient) -> ProviderCapture: ...


class ProviderAcquisitionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AcquisitionExecutionResult:
    run: dict[str, Any]
    observation: dict[str, Any] | None
    assessment: dict[str, Any] | None
    capture: ProviderCapture | None = field(default=None, repr=False)


class SourceAcquisitionExecutor:
    """Runs provider work under a durable Run and commits facts atomically."""

    def __init__(self, db: Session, *, http_client: SourceHttpClient) -> None:
        self.db = db
        self.http_client = http_client
        self.runs = SourceAcquisitionService(db)

    async def request_and_execute(
        self,
        *,
        source_id: str,
        provider: SourceAcquisitionProvider,
        worker_id: str,
        lease_seconds: int,
        trigger_kind: str = "manual",
        resource_scope: str = "source",
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        actor_user_id: int | None = None,
        request_payload: dict[str, Any] | None = None,
        assess_schema: bool = True,
    ) -> AcquisitionExecutionResult:
        run = self.runs.request_run(
            source_id=source_id,
            trigger_kind=trigger_kind,
            resource_scope=resource_scope,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            actor_user_id=actor_user_id,
            request_payload=request_payload,
        )
        if run["status"] != "queued":
            return self._replayed_result(str(run["id"]))
        try:
            return await self.execute_run(
                str(run["id"]),
                provider=provider,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                assess_schema=assess_schema,
            )
        except SourceAcquisitionError as exc:
            if exc.code != "invalid_run_transition":
                raise
            # A concurrent replay may have claimed the same authoritative Run.
            return self._replayed_result(str(run["id"]))

    async def execute_run(
        self,
        run_id: str,
        *,
        provider: SourceAcquisitionProvider,
        worker_id: str,
        lease_seconds: int,
        assess_schema: bool = True,
    ) -> AcquisitionExecutionResult:
        self.runs.start_run(
            run_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        cancellation = self._acknowledge_if_requested(run_id, worker_id)
        if cancellation is not None:
            return AcquisitionExecutionResult(cancellation, None, None, None)

        try:
            capture = await provider.capture(self.http_client)
        except SourceHttpError as exc:
            return AcquisitionExecutionResult(
                self._fail_or_cancel(run_id, worker_id, exc.code), None, None, None
            )
        except ProviderAcquisitionError as exc:
            return AcquisitionExecutionResult(
                self._fail_or_cancel(run_id, worker_id, exc.code), None, None, None
            )
        except Exception:
            self.db.rollback()
            return AcquisitionExecutionResult(
                self._fail_or_cancel(run_id, worker_id, "provider_execution_failed"),
                None,
                None,
                None,
            )

        try:
            result, reused = self._authoritative_result(run_id, capture)
            if result == "not_modified":
                completed = self._succeed_without_observation(run_id, worker_id, result)
                if completed["status"] == "cancelled":
                    return AcquisitionExecutionResult(completed, None, None, capture)
                assessment = self._assess(reused) if assess_schema and reused is not None else None
                return AcquisitionExecutionResult(completed, reused, assessment, capture)
            if capture.resource_identity is None or capture.content is None:
                raise ProviderAcquisitionError("provider_response_invalid")
            completed = self.runs.complete_with_observation(
                run_id,
                worker_id=worker_id,
                result=result,
                resource_identity=capture.resource_identity,
                provenance=capture.provenance,
                evidence=capture.evidence,
                snapshot_references=capture.snapshot_references,
                observed_at=capture.observed_at,
            )
            run = completed["run"]
            observation = completed["observation"]
            if run["status"] == "cancelled":
                return AcquisitionExecutionResult(run, None, None, capture)
            assessment = self._assess(observation) if assess_schema else None
            return AcquisitionExecutionResult(run, observation, assessment, capture)
        except ProviderAcquisitionError as exc:
            return AcquisitionExecutionResult(
                self._fail_or_cancel(run_id, worker_id, exc.code), None, None, None
            )
        except SourceAcquisitionError as exc:
            self.db.rollback()
            if exc.code in {
                "worker_ownership_conflict",
                "lease_expired",
                "invalid_run_transition",
                "terminal_run_immutable",
                "run_not_found",
            }:
                raise
            return AcquisitionExecutionResult(
                self._fail_or_cancel(run_id, worker_id, "observation_persistence_failed"),
                None,
                None,
                None,
            )
        except Exception:
            self.db.rollback()
            return AcquisitionExecutionResult(
                self._fail_or_cancel(run_id, worker_id, "observation_persistence_failed"),
                None,
                None,
                None,
            )

    def _authoritative_result(
        self, run_id: str, capture: ProviderCapture
    ) -> tuple[str, dict[str, Any] | None]:
        if capture.result not in {"observed", "not_modified", "content_unchanged_reparse"}:
            raise ProviderAcquisitionError("provider_result_invalid")
        run = self.db.get(AcquisitionRun, run_id)
        if run is None:
            raise SourceAcquisitionError("run_not_found")
        latest = (
            self.db.query(SourceObservation)
            .filter(
                SourceObservation.source_id == run.source_id,
                SourceObservation.resource_scope == run.resource_scope,
            )
            .order_by(SourceObservation.observation_version.desc())
            .first()
        )
        latest_shape = self._observation_shape(latest) if latest is not None else None
        if capture.result == "not_modified":
            if latest is None:
                raise ProviderAcquisitionError("not_modified_without_observation")
            return "not_modified", latest_shape
        if latest is None:
            return "observed", None
        if (
            capture.resource_identity is not None
            and latest.resource_identity_hash
            != checksum({"resource_identity": capture.resource_identity})
        ):
            return "observed", None
        prior_hash = str((latest.provenance_json or {}).get("capture_sha256") or "")
        current_hash = str(capture.provenance.get("capture_sha256") or "")
        if not prior_hash or prior_hash != current_hash:
            return capture.result, None
        prior_contract = str((latest.provenance_json or {}).get("capture_contract") or "")
        current_contract = str(capture.provenance.get("capture_contract") or "")
        if prior_contract == current_contract:
            return "not_modified", latest_shape
        return "content_unchanged_reparse", None

    def _succeed_without_observation(
        self, run_id: str, worker_id: str, result: str
    ) -> dict[str, Any]:
        cancellation = self._acknowledge_if_requested(run_id, worker_id)
        if cancellation is not None:
            return cancellation
        try:
            return self.runs.succeed_run(run_id, worker_id=worker_id, result=result)
        except SourceAcquisitionError as exc:
            if exc.code != "cancellation_requested":
                raise
            return self.runs.acknowledge_cancellation(run_id, worker_id=worker_id)

    def _acknowledge_if_requested(
        self, run_id: str, worker_id: str
    ) -> dict[str, Any] | None:
        self.db.expire_all()
        row = self.db.get(AcquisitionRun, run_id)
        if row is not None and row.status == "running" and row.cancellation_requested_at is not None:
            return self.runs.acknowledge_cancellation(run_id, worker_id=worker_id)
        return None

    def _fail_or_cancel(self, run_id: str, worker_id: str, code: str) -> dict[str, Any]:
        cancellation = self._acknowledge_if_requested(run_id, worker_id)
        if cancellation is not None:
            return cancellation
        try:
            return self.runs.fail_run(run_id, worker_id=worker_id, failure_code=code)
        except SourceAcquisitionError as exc:
            if exc.code != "cancellation_requested":
                raise
            return self.runs.acknowledge_cancellation(run_id, worker_id=worker_id)

    def _assess(self, observation: dict[str, Any] | None) -> dict[str, Any] | None:
        if observation is None:
            return None
        mapping = (
            self.db.query(SourceMappingRevision)
            .filter(SourceMappingRevision.source_id == observation["sourceId"])
            .order_by(SourceMappingRevision.version.desc())
            .first()
        )
        try:
            return SourceSchemaAssessmentService(self.db).assess(
                observation_id=str(observation["id"]),
                mapping_revision_id=mapping.id if mapping is not None else None,
            )
        except Exception:
            self.db.rollback()
            return None

    def _replayed_result(self, run_id: str) -> AcquisitionExecutionResult:
        run = self.runs.get_run(run_id)
        observation = (
            self.db.query(SourceObservation)
            .filter(SourceObservation.acquisition_run_id == run_id)
            .one_or_none()
        )
        return AcquisitionExecutionResult(
            run,
            self._observation_shape(observation) if observation is not None else None,
            None,
            None,
        )

    def _observation_shape(self, row: SourceObservation | None) -> dict[str, Any] | None:
        if row is None:
            return None
        from app.flowhub.source_acquisition.observations import SourceObservationService

        return SourceObservationService(self.db).observation(row.id)
