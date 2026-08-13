from __future__ import annotations

import asyncio
import io
import re

import openpyxl
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.connectors.common.source_http import SourceHttpResponse
from app.flowhub.sources.xlsx_discovery import RangedXlsxDiscovery, XlsxDiscoveryError
from app.flowhub.database import FlowHubBase
from app.flowhub.auth.models import FlowHubUser  # noqa: F401
from app.flowhub.source_workspace.models import SourceProfile  # noqa: F401
from app.flowhub.unified_workspace.models import WorkspaceChannel  # noqa: F401
from app.flowhub.data_layer.models import DlSourceReadReservation, DlSourceSnapshot, DlWorksheetDiscoveryCache
from app.flowhub.setup.service import AppConfigService
from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService


def _workbook_bytes() -> bytes:
    workbook = openpyxl.Workbook()
    retail = workbook.active
    retail.title = "Retail"
    retail.append(["Product Name", "Cost", "SKU", None, None, None, None, "Stock"])
    retail.append(["Mouse", 100, "M-1", None, None, None, None, 4])
    marketplace = workbook.create_sheet("Marketplace")
    marketplace.append(["Name", "Key", "Price"])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


class _RangeHttp:
    def __init__(self, content: bytes, *, honour_ranges: bool = True) -> None:
        self.content = content
        self.honour_ranges = honour_ranges
        self.requests: list[str] = []

    async def request(self, method: str, url: str, *, headers=None, basic_auth=None):
        assert method == "GET"
        assert basic_auth == ("user", "secret")
        value = str((headers or {}).get("Range") or "")
        self.requests.append(value)
        if not self.honour_ranges:
            return SourceHttpResponse(200, {}, self.content, url)
        suffix = re.fullmatch(r"bytes=-(\d+)", value)
        if suffix:
            size = min(int(suffix.group(1)), len(self.content))
            start = len(self.content) - size
            selected = self.content[start:]
            return SourceHttpResponse(206, {"content-range": f"bytes {start}-{len(self.content)-1}/{len(self.content)}", "etag": '"v1"'}, selected, url)
        match = re.fullmatch(r"bytes=(\d+)-(\d+)", value)
        assert match is not None
        start, end = int(match.group(1)), int(match.group(2))
        selected = self.content[start : end + 1]
        return SourceHttpResponse(206, {"content-range": f"bytes {start}-{end}/{len(self.content)}"}, selected, url)


def test_ranged_discovery_returns_real_headers_without_full_get() -> None:
    http = _RangeHttp(_workbook_bytes())
    worksheets, token = asyncio.run(
        RangedXlsxDiscovery(http).discover("https://nextcloud.invalid/file.xlsx", basic_auth=("user", "secret"))
    )
    assert token == "v1"
    assert [item["name"] for item in worksheets] == ["Retail", "Marketplace"]
    assert worksheets[0]["columns"] == [
        {"id": "A", "letter": "A", "header": "Product Name"},
        {"id": "B", "letter": "B", "header": "Cost"},
        {"id": "C", "letter": "C", "header": "SKU"},
        {"id": "H", "letter": "H", "header": "Stock"},
    ]
    assert http.requests
    assert all(value.startswith("bytes=") for value in http.requests)


def test_discovery_fails_closed_when_provider_ignores_ranges() -> None:
    http = _RangeHttp(_workbook_bytes(), honour_ranges=False)
    try:
        asyncio.run(RangedXlsxDiscovery(http).discover("https://nextcloud.invalid/file.xlsx", basic_auth=("user", "secret")))
    except XlsxDiscoveryError as error:
        assert error.code == "provider_range_reads_unsupported"
    else:  # pragma: no cover
        raise AssertionError("a full workbook response must never be accepted as discovery")


def test_remote_refresh_uses_only_discovery_allowance_and_creates_no_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    db = Session(engine)
    AppConfigService(db).set_many({
        "nextcloud.url": "https://nextcloud.example.com",
        "nextcloud.username": "user",
        "nextcloud.password": "secret",
        "nextcloud.spreadsheet_path": "/Reports/prices.xlsx",
    }, updated_by="test")

    class _Http:
        async def preflight(self, _url: str) -> None:
            return None

    class _Discovery:
        def __init__(self, _http: object) -> None:
            pass

        async def discover(self, _url: str, *, basic_auth: tuple[str, str]):
            assert basic_auth == ("user", "secret")
            return ([{"name": "Retail", "rowCount": None, "columns": [{"id": "A", "letter": "A", "header": "Name"}]}], "etag-1")

    reader = SpreadsheetSourceReadService(db)
    monkeypatch.setattr(reader, "_nextcloud_http_client", lambda: _Http())
    monkeypatch.setattr("app.flowhub.sources.spreadsheet_source.RangedXlsxDiscovery", _Discovery)
    result = asyncio.run(reader.refresh_worksheet_discovery(source_profile_id="source-1", user_id="7"))

    assert result["worksheets"][0]["columns"][0]["header"] == "Name"
    assert result["quota"]["usage"] == 1
    assert db.query(DlSourceReadReservation).count() == 0
    assert db.query(DlSourceSnapshot).count() == 0
    assert db.get(DlWorksheetDiscoveryCache, "source-1") is not None
    db.close()
    engine.dispose()
