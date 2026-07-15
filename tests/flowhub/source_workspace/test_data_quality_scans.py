from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.source_workspace.models import (
    SourceDataQualityIssue,
    SourceDataQualityScan,
    SourceDataQualityScanSource,
)
from app.flowhub.source_workspace.service import SourceWorkspaceService
from app.flowhub.unified_workspace.domain import utcnow


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def _setup() -> tuple[Session, FlowHubUser, SourceWorkspaceService, dict[str, Any]]:
    db = _session()
    user = FlowHubUser(
        id=1,
        username="data-quality-owner",
        hashed_password="x",
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    service = SourceWorkspaceService(db)
    source = service.create_source(
        name="Synthetic pricing sheet",
        source_kind="flowhub_sheet",
        external_source_id=None,
        worksheet_mode="selected",
        worksheet_name="محصولات",
        data_start_row=2,
        user=user,
    )
    return db, user, service, source


def _query(
    service: SourceWorkspaceService,
    user: FlowHubUser,
    **overrides: Any,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "source_id": None,
        "channel_id": None,
        "worksheet": None,
        "category": None,
        "severity": None,
        "product": None,
        "mapping_state": None,
        "page": 1,
        "page_size": 100,
    }
    values.update(overrides)
    return service.data_quality(user=user, **values)


def _analysis(source_id: str, issues: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "source": {"id": source_id},
        "mapping": {"id": "mapping", "version": 1},
        "sheetRevision": {"id": "revision"},
        "candidates": [
            {
                "sourceRowKey": "row-ready",
                "sourceProduct": {"name": "Ready product"},
            }
        ],
        "issues": issues,
        "summary": {"sourceProducts": 1, "listings": 1, "blocked": len(issues)},
    }


def _issue(*, row: str, category: str, severity: str = "blocked") -> dict[str, Any]:
    return {
        "sourceRowKey": row,
        "sourceRowNumber": 3,
        "worksheetName": "محصولات",
        "channelId": None,
        "sourceProductName": f"Product {row}",
        "mappingState": "unmapped",
        "category": category,
        "severity": severity,
        "code": category.upper(),
        "summary": "Synthetic validation issue.",
        "recommendedAction": "Correct the synthetic row.",
        "technicalDetails": {"fixture": True},
    }


def test_data_quality_distinguishes_never_checked_from_a_healthy_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, user, service, source = _setup()
    never_checked = _query(service, user)
    assert never_checked["summary"]["state"] == "never_checked"
    assert never_checked["summary"]["checkedAt"] is None

    calls: list[str] = []

    async def evaluate(source_id: str, _: FlowHubUser) -> dict[str, Any]:
        calls.append(source_id)
        return _analysis(source_id, [])

    monkeypatch.setattr(service, "snapshot_candidates", evaluate)
    result = asyncio.run(service.scan_data_quality(user=user, source_id=source["id"]))
    assert calls == [source["id"]]
    assert result["summary"]["state"] == "healthy"
    assert result["summary"]["productsChecked"] == 1
    assert result["summary"]["sourcesChecked"] == 1
    assert result["summary"]["checkedAt"] is not None
    lifecycle = service.source_lifecycle(source["id"], user)
    assert lifecycle["action"] == "archive"
    assert lifecycle["protectedHistory"]["dataQualityScans"] == 1


def test_in_progress_scan_is_presented_as_checking_not_healthy() -> None:
    db, user, service, source = _setup()
    db.add_all(
        [
            SourceDataQualityScan(
                id="scan-checking",
                owner_user_id=user.id,
                source_id=source["id"],
                source_ids_json=[source["id"]],
                source_results_json={},
                status="checking",
            ),
            SourceDataQualityScanSource(
                scan_id="scan-checking",
                source_id=source["id"],
            ),
        ]
    )
    db.commit()

    report = _query(service, user, source_id=source["id"])
    assert report["summary"]["state"] == "checking"
    assert report["summary"]["scanId"] == "scan-checking"


def test_missing_column_configuration_is_an_issue_not_a_false_healthy_state() -> None:
    _, user, service, source = _setup()

    result = asyncio.run(service.scan_data_quality(user=user, source_id=source["id"]))
    report = _query(service, user, source_id=source["id"])

    assert result["summary"]["state"] == "issues_found"
    assert report["total"] == 1
    assert report["items"][0]["code"] == "SOURCE_MAPPING_REQUIRED"
    assert report["items"][0]["category"] == "mapping_not_configured"


def test_data_quality_persists_history_and_aggregates_before_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, user, service, source = _setup()
    issues = [
        _issue(row="row-1", category="invalid_price"),
        _issue(row="row-2", category="invalid_price", severity="warning"),
        _issue(row="row-3", category="missing_product_id"),
    ]

    async def evaluate(source_id: str, _: FlowHubUser) -> dict[str, Any]:
        return _analysis(source_id, issues)

    monkeypatch.setattr(service, "snapshot_candidates", evaluate)
    scan = asyncio.run(service.scan_data_quality(user=user, source_id=source["id"]))
    report = _query(
        service,
        user,
        source_id=source["id"],
        category="all",
        severity="all",
        mapping_state="all",
        page_size=1,
    )

    assert scan["summary"]["state"] == "issues_found"
    assert report["total"] == 3
    assert len(report["items"]) == 1
    assert report["counts"] == {"invalid_price": 2, "missing_product_id": 1}
    assert report["summary"]["totalIssues"] == 3
    assert report["summary"]["blockingIssues"] == 2
    assert report["summary"]["warnings"] == 1
    assert report["summary"]["affectedProducts"] == 3
    assert db.query(SourceDataQualityScan).count() == 1
    assert db.query(SourceDataQualityIssue).count() == 3
    assert {item.scan_id for item in db.query(SourceDataQualityIssue).all()} == {
        scan["summary"]["scanId"]
    }


def test_data_quality_preserves_long_persian_external_row_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, user, service, source = _setup()
    common_prefix = "گزارش فروش محصولات و قیمت گذاری کانال های فروشگاه مرکزی - "
    worksheets = (f"{common_prefix}تهران", f"{common_prefix}شیراز")
    row_keys = tuple(f"external:{worksheet}:1048576" for worksheet in worksheets)
    assert row_keys[0][:36] == row_keys[1][:36]
    assert row_keys[0] != row_keys[1]

    issues: list[dict[str, Any]] = []
    for worksheet, row_key in zip(worksheets, row_keys, strict=True):
        issue = _issue(row=row_key, category="invalid_price")
        issue["worksheetName"] = worksheet
        issues.append(issue)

    async def evaluate(source_id: str, _: FlowHubUser) -> dict[str, Any]:
        return _analysis(source_id, issues)

    monkeypatch.setattr(service, "snapshot_candidates", evaluate)
    scan = asyncio.run(service.scan_data_quality(user=user, source_id=source["id"]))
    report = _query(service, user, source_id=source["id"])

    assert scan["summary"]["totalIssues"] == 2
    assert {(item["worksheet"], item["sourceRowKey"]) for item in report["items"]} == set(
        zip(worksheets, row_keys, strict=True)
    )
    persisted = db.query(SourceDataQualityIssue).all()
    assert {(item.worksheet_name, item.source_row_key) for item in persisted} == set(
        zip(worksheets, row_keys, strict=True)
    )
    assert SourceDataQualityIssue.__table__.c.source_row_key.type.length == 512


def test_data_quality_orders_blocking_severities_before_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, user, service, source = _setup()
    issues = [
        _issue(row="row-warning", category="warning-issue", severity="warning"),
        _issue(row="row-error", category="error-issue", severity="error"),
        _issue(row="row-blocked", category="blocked-issue", severity="blocked"),
    ]

    async def evaluate(source_id: str, _: FlowHubUser) -> dict[str, Any]:
        return _analysis(source_id, issues)

    monkeypatch.setattr(service, "snapshot_candidates", evaluate)
    asyncio.run(service.scan_data_quality(user=user, source_id=source["id"]))
    report = _query(service, user, source_id=source["id"])

    assert [item["severity"] for item in report["items"]] == [
        "blocked",
        "error",
        "warning",
    ]


def test_latest_scan_scopes_issue_history_and_reports_resolved_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, user, service, source = _setup()
    responses = iter(
        [
            _analysis(source["id"], [_issue(row="row-1", category="invalid_price")]),
            _analysis(source["id"], []),
        ]
    )

    async def evaluate(_: str, __: FlowHubUser) -> dict[str, Any]:
        return next(responses)

    monkeypatch.setattr(service, "snapshot_candidates", evaluate)
    first = asyncio.run(service.scan_data_quality(user=user, source_id=source["id"]))
    second = asyncio.run(service.scan_data_quality(user=user, source_id=source["id"]))
    report = _query(service, user, source_id=source["id"])

    assert first["summary"]["state"] == "issues_found"
    assert second["summary"]["state"] == "healthy"
    assert second["summary"]["resolvedSinceLastRead"] == 1
    assert second["summary"]["trendSinceLastRead"] == -1
    assert report["items"] == []
    assert report["summary"]["scanId"] == second["summary"]["scanId"]
    assert db.query(SourceDataQualityIssue).count() == 1


def test_resolved_count_uses_issue_identity_when_total_count_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, user, service, source = _setup()
    responses = iter(
        [
            _analysis(source["id"], [_issue(row="row-1", category="invalid_price")]),
            _analysis(source["id"], [_issue(row="row-2", category="missing_product_id")]),
        ]
    )

    async def evaluate(_: str, __: FlowHubUser) -> dict[str, Any]:
        return next(responses)

    monkeypatch.setattr(service, "snapshot_candidates", evaluate)
    asyncio.run(service.scan_data_quality(user=user, source_id=source["id"]))
    second = asyncio.run(service.scan_data_quality(user=user, source_id=source["id"]))

    assert second["summary"]["totalIssues"] == 1
    assert second["summary"]["resolvedSinceLastRead"] == 1
    assert second["summary"]["trendSinceLastRead"] == 0


def test_more_than_one_thousand_unrelated_scans_do_not_hide_scope_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, user, service, source = _setup()
    unrelated = service.create_source(
        name="Unrelated Source",
        source_kind="flowhub_sheet",
        external_source_id=None,
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=1,
        user=user,
    )
    responses = iter(
        [
            _analysis(source["id"], [_issue(row="row-1", category="invalid_price")]),
            _analysis(source["id"], []),
        ]
    )

    async def evaluate(_: str, __: FlowHubUser) -> dict[str, Any]:
        return next(responses)

    monkeypatch.setattr(service, "snapshot_candidates", evaluate)
    first = asyncio.run(service.scan_data_quality(user=user, source_id=source["id"]))
    scans: list[SourceDataQualityScan] = []
    scopes: list[SourceDataQualityScanSource] = []
    for index in range(1_001):
        scan_id = f"unrelated-{index:04d}"
        scans.append(
            SourceDataQualityScan(
                id=scan_id,
                owner_user_id=user.id,
                source_id=unrelated["id"],
                source_ids_json=[unrelated["id"]],
                source_results_json={unrelated["id"]: {"issueCount": 0}},
                status="completed",
                checked_at=utcnow(),
            )
        )
        scopes.append(
            SourceDataQualityScanSource(
                scan_id=scan_id,
                source_id=unrelated["id"],
            )
        )
    db.add_all([*scans, *scopes])
    db.commit()

    second = asyncio.run(service.scan_data_quality(user=user, source_id=source["id"]))

    assert first["summary"]["totalIssues"] == 1
    assert second["summary"]["state"] == "healthy"
    assert second["summary"]["resolvedSinceLastRead"] == 1
    assert second["summary"]["trendSinceLastRead"] == -1


def test_failed_scan_is_durable_and_is_not_presented_as_no_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, user, service, source = _setup()

    async def fail(_: str, __: FlowHubUser) -> dict[str, Any]:
        raise RuntimeError("synthetic source read failure")

    monkeypatch.setattr(service, "snapshot_candidates", fail)
    with pytest.raises(RuntimeError, match="synthetic source read failure"):
        asyncio.run(service.scan_data_quality(user=user, source_id=source["id"]))

    persisted = db.query(SourceDataQualityScan).one()
    assert persisted.status == "failed"
    assert persisted.error_code == "RUNTIMEERROR"
    report = _query(service, user, source_id=source["id"])
    assert report["summary"]["state"] == "failed"
    assert report["summary"]["errorCode"] == "RUNTIMEERROR"


def test_global_scan_evaluates_each_active_source_once_and_ignores_disabled_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, user, service, first = _setup()
    second = service.create_source(
        name="Second active Source",
        source_kind="flowhub_sheet",
        external_source_id=None,
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=1,
        user=user,
    )
    disabled = service.create_source(
        name="Disabled Source",
        source_kind="flowhub_sheet",
        external_source_id=None,
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=1,
        user=user,
    )
    disabled_row = service.sources.get(disabled["id"])
    assert disabled_row is not None
    disabled_row.status = "disabled"
    db.commit()
    calls: list[str] = []

    async def evaluate(source_id: str, _: FlowHubUser) -> dict[str, Any]:
        calls.append(source_id)
        return _analysis(source_id, [])

    monkeypatch.setattr(service, "snapshot_candidates", evaluate)
    result = asyncio.run(service.scan_data_quality(user=user, source_id=None))

    assert sorted(calls) == sorted([first["id"], second["id"]])
    assert len(calls) == len(set(calls)) == 2
    assert result["summary"]["sourcesChecked"] == 2


def test_source_specific_scan_does_not_replace_the_global_overview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, user, service, first = _setup()
    second = service.create_source(
        name="Second active Source",
        source_kind="flowhub_sheet",
        external_source_id=None,
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=1,
        user=user,
    )

    async def global_evaluate(source_id: str, _: FlowHubUser) -> dict[str, Any]:
        issues = (
            [_issue(row="second-row", category="invalid_price")]
            if source_id == second["id"]
            else []
        )
        return _analysis(source_id, issues)

    monkeypatch.setattr(service, "snapshot_candidates", global_evaluate)
    global_scan = asyncio.run(service.scan_data_quality(user=user, source_id=None))

    async def healthy_first(source_id: str, _: FlowHubUser) -> dict[str, Any]:
        return _analysis(source_id, [])

    monkeypatch.setattr(service, "snapshot_candidates", healthy_first)
    source_scan = asyncio.run(service.scan_data_quality(user=user, source_id=first["id"]))
    global_report = _query(service, user)

    assert source_scan["summary"]["state"] == "healthy"
    assert source_scan["summary"]["resolvedSinceLastRead"] == 0
    assert source_scan["summary"]["trendSinceLastRead"] == 0
    assert global_report["summary"]["scanId"] == global_scan["summary"]["scanId"]
    assert global_report["summary"]["state"] == "issues_found"
    assert global_report["summary"]["totalIssues"] == 1
    assert global_report["items"][0]["sourceId"] == second["id"]


@pytest.mark.parametrize("filter_value", [None, "", "all", "ALL", " all "])
def test_all_filter_values_are_normalized(
    filter_value: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, user, service, source = _setup()

    async def evaluate(source_id: str, _: FlowHubUser) -> dict[str, Any]:
        return _analysis(source_id, [_issue(row="row-1", category="invalid_price")])

    monkeypatch.setattr(service, "snapshot_candidates", evaluate)
    asyncio.run(service.scan_data_quality(user=user, source_id=None))
    report = _query(
        service,
        user,
        channel_id=filter_value,
        worksheet=filter_value,
        category=filter_value,
        severity=filter_value,
        product=filter_value,
        mapping_state=filter_value,
    )
    assert report["total"] == 1
