from __future__ import annotations

import pytest

from app.connectors.common.current_state import (
    CurrentStateIdentity,
    CurrentStateRequest,
    CurrentStateResult,
    CurrentStateStrategy,
    TransportRecorder,
    unsupported_current_state,
)


def test_current_state_request_requires_unique_stable_entity_keys():
    with pytest.raises(ValueError, match="unique"):
        CurrentStateRequest(
            channel_id="channel:main",
            entities=(
                CurrentStateIdentity(key="listing-1", external_id="1"),
                CurrentStateIdentity(key="listing-1", external_id="2"),
            ),
            required_fields=frozenset({"price"}),
        )


def test_transport_report_exposes_request_batch_retry_and_bottleneck_evidence():
    recorder = TransportRecorder(
        strategy=CurrentStateStrategy.BATCH_BY_ID,
        purpose="verification",
        entities_requested=20,
    )
    recorder.record_stage(stage="rate_limit_wait", duration_ms=4)
    recorder.record_batch()
    recorder.record_request(stage="provider_read", duration_ms=12)
    recorder.record_request(
        stage="provider_read",
        duration_ms=18,
        retry=True,
        failed=True,
    )

    report = recorder.finish(entities_returned=19)

    assert report.requests_issued == 2
    assert report.batches_issued == 1
    assert report.retries == 1
    assert report.failed_requests == 1
    assert report.slowest_request_ms == 18
    assert report.provider_response_ms == 30
    assert report.bottleneck_stage == "provider_read"
    assert report.as_dict()["entities_returned"] == 19
    assert report.operation_id.startswith("csr_")


def test_current_state_result_rejects_missing_per_entity_evidence():
    recorder = TransportRecorder(
        strategy=CurrentStateStrategy.BATCH_BY_ID,
        purpose="verification",
        entities_requested=1,
    )

    with pytest.raises(ValueError, match="one record or error"):
        CurrentStateResult(
            records={},
            errors={},
            transport=recorder.finish(entities_returned=0),
        )


def test_unsupported_strategy_keeps_one_error_per_entity_without_remote_requests():
    request = CurrentStateRequest(
        channel_id="tapsishop:main",
        entities=(
            CurrentStateIdentity(key="listing-1", external_id="1"),
            CurrentStateIdentity(key="listing-2", external_id="2"),
        ),
        required_fields=frozenset({"price", "stock"}),
    )

    result = unsupported_current_state(request, message="read-back unavailable")

    assert set(result.errors) == {"listing-1", "listing-2"}
    assert result.transport.strategy is CurrentStateStrategy.UNSUPPORTED
    assert result.transport.requests_issued == 0
