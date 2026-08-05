from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from functools import wraps

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.connectors.common.source_http import SourceHttpClient, SourceHttpError
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.source_acquisition.execution import (
    ProviderAcquisitionError,
    ProviderCapture,
    SourceAcquisitionExecutor,
)
from app.flowhub.source_acquisition.errors import SourceAcquisitionError
from app.flowhub.source_acquisition.models import AcquisitionRun, SourceObservation
from app.flowhub.source_acquisition.observations import SourceObservationService
from app.flowhub.source_acquisition.service import SourceAcquisitionService
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.unified_workspace import models as _unified_workspace_models  # noqa: F401


def async_test(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))

    return wrapper


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def _source(db: Session, source_id: str = "source-one") -> SourceProfile:
    user = db.get(FlowHubUser, 1)
    if user is None:
        user = FlowHubUser(
            id=1,
            username="owner",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.flush()
    source = SourceProfile(
        id=source_id,
        name=source_id,
        source_kind="external",
        external_source_id=f"external-{source_id}",
        worksheet_mode="selected",
        worksheet_name="Products",
        data_start_row=2,
        status="active",
        version=1,
        owner_user_id=user.id,
    )
    db.add(source)
    db.commit()
    return source


def _capture(*, content: bytes = b"workbook", contract: str = "parse-v1") -> ProviderCapture:
    digest = hashlib.sha256(content).hexdigest()
    return ProviderCapture(
        result="observed",
        resource_identity="nextcloud:fileid:42",
        content=content,
        provenance={
            "provider": "nextcloud",
            "capture_contract": contract,
            "capture_sha256": digest,
        },
        evidence=[
            {
                "kind": "capture_manifest",
                "reference": f"sha256:{digest}",
                "metadata": {"bytes": len(content)},
            },
            {
                "kind": "schema_headers",
                "reference": f"sha256:{digest}:headers",
                "metadata": {"headers": ["SKU", "Price"]},
            },
        ],
        snapshot_references=[
            {
                "kind": "raw_capture",
                "reference": f"sha256:{digest}",
                "checksum": digest,
                "metadata": {"format": "xlsx"},
            }
        ],
    )


class FakeProvider:
    def __init__(self, result: ProviderCapture | Exception) -> None:
        self.result = result
        self.calls = 0

    async def capture(self, _http_client: SourceHttpClient) -> ProviderCapture:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _executor(db: Session) -> SourceAcquisitionExecutor:
    return SourceAcquisitionExecutor(db, http_client=SourceHttpClient())


@async_test
async def test_successful_execution_commits_observation_before_run_success() -> None:
    db = _session()
    source = _source(db)
    provider = FakeProvider(_capture())

    result = await _executor(db).request_and_execute(
        source_id=source.id,
        provider=provider,
        worker_id="worker-a",
        lease_seconds=60,
        idempotency_key="acquire-1",
        request_payload={"operation": "acquire"},
    )

    assert provider.calls == 1
    assert result.run["status"] == "succeeded"
    assert result.run["result"] == "observed"
    assert result.observation is not None
    assert result.observation["acquisitionRunId"] == result.run["id"]
    assert result.assessment is not None
    assert result.assessment["schemaStatus"] == "no_mapping"


@async_test
async def test_same_capture_reuses_observation_and_changed_contract_reparses() -> None:
    db = _session()
    source = _source(db)
    executor = _executor(db)
    first = await executor.request_and_execute(
        source_id=source.id,
        provider=FakeProvider(_capture()),
        worker_id="worker-a",
        lease_seconds=60,
        idempotency_key="first",
        request_payload={"operation": "acquire"},
    )
    unchanged = await executor.request_and_execute(
        source_id=source.id,
        provider=FakeProvider(_capture()),
        worker_id="worker-a",
        lease_seconds=60,
        idempotency_key="second",
        request_payload={"operation": "acquire"},
    )
    reparsed = await executor.request_and_execute(
        source_id=source.id,
        provider=FakeProvider(_capture(contract="parse-v2")),
        worker_id="worker-a",
        lease_seconds=60,
        idempotency_key="third",
        request_payload={"operation": "acquire"},
    )
    relocated = await executor.request_and_execute(
        source_id=source.id,
        provider=FakeProvider(
            replace(_capture(contract="parse-v2"), resource_identity="nextcloud:fileid:99")
        ),
        worker_id="worker-a",
        lease_seconds=60,
        idempotency_key="fourth",
        request_payload={"operation": "acquire"},
    )

    assert unchanged.run["result"] == "not_modified"
    assert unchanged.observation is not None
    assert unchanged.observation["id"] == first.observation["id"]
    assert reparsed.run["result"] == "content_unchanged_reparse"
    assert reparsed.observation is not None
    assert reparsed.observation["id"] != first.observation["id"]
    assert reparsed.observation["observationVersion"] == 2
    assert relocated.run["result"] == "observed"
    assert relocated.observation["observationVersion"] == 3


@async_test
@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (SourceHttpError("unsafe_destination"), "unsafe_destination"),
        (SourceHttpError("read_timeout"), "read_timeout"),
        (SourceHttpError("response_too_large"), "response_too_large"),
        (ProviderAcquisitionError("provider_authentication_failed"), "provider_authentication_failed"),
        (ProviderAcquisitionError("provider_response_invalid"), "provider_response_invalid"),
    ],
)
async def test_normalized_failure_never_creates_observation(
    failure: Exception, code: str
) -> None:
    db = _session()
    source = _source(db)
    result = await _executor(db).request_and_execute(
        source_id=source.id,
        provider=FakeProvider(failure),
        worker_id="worker-a",
        lease_seconds=60,
        request_payload={"operation": "acquire", "secret": "not-persisted"},
    )

    assert result.run["status"] == "failed"
    assert result.run["failureCode"] == code
    assert db.query(SourceObservation).count() == 0
    persisted = db.get(AcquisitionRun, str(result.run["id"]))
    assert persisted is not None
    assert "not-persisted" not in str(persisted.failure_code)


@async_test
async def test_observation_persistence_failure_rolls_back_and_fails_run(monkeypatch) -> None:
    db = _session()
    source = _source(db)

    def fail_stage(*_args, **_kwargs):
        raise RuntimeError("database detail containing secret")

    monkeypatch.setattr(SourceObservationService, "_stage_observation", fail_stage)
    result = await _executor(db).request_and_execute(
        source_id=source.id,
        provider=FakeProvider(_capture()),
        worker_id="worker-a",
        lease_seconds=60,
        request_payload={"operation": "acquire"},
    )

    assert result.run["status"] == "failed"
    assert result.run["failureCode"] == "observation_persistence_failed"
    assert db.query(SourceObservation).count() == 0
    assert "secret" not in str(result.run)


@async_test
async def test_invalid_observation_metadata_fails_run_without_leaking_secret() -> None:
    db = _session()
    source = _source(db)
    invalid = replace(
        _capture(), provenance={"capture_contract": "v1", "authorization": "Bearer hidden"}
    )
    result = await _executor(db).request_and_execute(
        source_id=source.id,
        provider=FakeProvider(invalid),
        worker_id="worker-a",
        lease_seconds=60,
        request_payload={"operation": "acquire"},
    )

    assert result.run["status"] == "failed"
    assert result.run["failureCode"] == "observation_persistence_failed"
    assert "hidden" not in str(result.run)
    assert db.query(SourceObservation).count() == 0


@async_test
async def test_cancellation_requested_during_provider_wins_completion_race() -> None:
    db = _session()
    source = _source(db)

    class CancellingProvider(FakeProvider):
        async def capture(self, http_client: SourceHttpClient) -> ProviderCapture:
            run = db.query(AcquisitionRun).filter(AcquisitionRun.status == "running").one()
            SourceAcquisitionService(db).request_cancellation(
                run.id, requester_user_id=1
            )
            return await super().capture(http_client)

    result = await _executor(db).request_and_execute(
        source_id=source.id,
        provider=CancellingProvider(_capture()),
        worker_id="worker-a",
        lease_seconds=60,
        request_payload={"operation": "acquire"},
    )

    assert result.run["status"] == "cancelled"
    assert db.query(SourceObservation).count() == 0


@async_test
async def test_cancelled_queued_run_never_calls_provider() -> None:
    db = _session()
    source = _source(db)
    runs = SourceAcquisitionService(db)
    run = runs.request_run(
        source_id=source.id,
        trigger_kind="manual",
        request_payload={"operation": "acquire"},
    )
    runs.request_cancellation(str(run["id"]), requester_user_id=1)
    provider = FakeProvider(_capture())

    with pytest.raises(SourceAcquisitionError, match="invalid_run_transition"):
        await _executor(db).execute_run(
            str(run["id"]),
            provider=provider,
            worker_id="worker-a",
            lease_seconds=60,
        )
    assert provider.calls == 0
    assert db.query(SourceObservation).count() == 0


@async_test
async def test_not_modified_without_prior_observation_fails_closed() -> None:
    db = _session()
    source = _source(db)
    result = await _executor(db).request_and_execute(
        source_id=source.id,
        provider=FakeProvider(ProviderCapture(result="not_modified")),
        worker_id="worker-a",
        lease_seconds=60,
        request_payload={"operation": "acquire"},
    )

    assert result.run["status"] == "failed"
    assert result.run["failureCode"] == "not_modified_without_observation"
    assert db.query(SourceObservation).count() == 0


@async_test
async def test_idempotent_replay_and_concurrent_replay_do_not_call_provider_twice() -> None:
    db = _session()
    source = _source(db)
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingProvider(FakeProvider):
        async def capture(self, http_client: SourceHttpClient) -> ProviderCapture:
            self.calls += 1
            started.set()
            await release.wait()
            return self.result  # type: ignore[return-value]

    provider = BlockingProvider(_capture())
    executor = _executor(db)
    kwargs = {
        "source_id": source.id,
        "provider": provider,
        "worker_id": "worker-a",
        "lease_seconds": 60,
        "idempotency_key": "same-intent",
        "request_payload": {"operation": "acquire"},
    }
    first_task = asyncio.create_task(executor.request_and_execute(**kwargs))
    await started.wait()
    replay = await executor.request_and_execute(**kwargs)
    assert replay.run["status"] == "running"
    release.set()
    first = await first_task
    terminal_replay = await executor.request_and_execute(**kwargs)

    assert first.run["status"] == "succeeded"
    assert terminal_replay.run["id"] == first.run["id"]
    assert provider.calls == 1
    assert db.query(AcquisitionRun).count() == 1


@async_test
async def test_retry_is_linked_and_creates_only_its_own_observation() -> None:
    db = _session()
    source = _source(db)
    executor = _executor(db)
    failed = await executor.request_and_execute(
        source_id=source.id,
        provider=FakeProvider(SourceHttpError("connection_failed")),
        worker_id="worker-a",
        lease_seconds=60,
        request_payload={"operation": "acquire"},
    )
    retry = SourceAcquisitionService(db).retry_run(
        str(failed.run["id"]), idempotency_key="retry-1"
    )
    completed = await executor.execute_run(
        str(retry["id"]),
        provider=FakeProvider(_capture()),
        worker_id="worker-b",
        lease_seconds=60,
    )

    assert failed.run["status"] == "failed"
    assert completed.run["status"] == "succeeded"
    assert completed.run["parentRunId"] == failed.run["id"]
    assert completed.observation is not None
    assert completed.observation["acquisitionRunId"] == completed.run["id"]
    assert db.query(SourceObservation).count() == 1


@async_test
async def test_source_and_scope_isolation() -> None:
    db = _session()
    source_one = _source(db, "source-one")
    source_two = _source(db, "source-two")
    executor = _executor(db)
    results = []
    for source, scope, key in (
        (source_one, "sheet:a", "one"),
        (source_one, "sheet:b", "two"),
        (source_two, "sheet:a", "three"),
    ):
        results.append(
            await executor.request_and_execute(
                source_id=source.id,
                resource_scope=scope,
                provider=FakeProvider(replace(_capture(), resource_identity=f"{source.id}:{scope}")),
                worker_id="worker-a",
                lease_seconds=60,
                idempotency_key=key,
                request_payload={"operation": "acquire"},
            )
        )

    assert len({item.run["id"] for item in results}) == 3
    assert len({item.observation["id"] for item in results if item.observation}) == 3
