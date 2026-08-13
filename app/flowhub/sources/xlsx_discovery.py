"""Bounded XLSX worksheet/header discovery over HTTP byte ranges.

This module deliberately reads workbook metadata without invoking the Source
acquisition executor or materialising a business Snapshot. Servers that do not
honour byte ranges fail closed; callers must never fall back to a full GET.
"""

from __future__ import annotations

import posixpath
import re
import struct
import zlib
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

from app.connectors.common.source_http import SourceHttpClient, SourceHttpError


class XlsxDiscoveryError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class XlsxDiscoveryPolicy:
    max_transfer_bytes: int = 8 * 1024 * 1024
    max_entry_bytes: int = 4 * 1024 * 1024
    max_uncompressed_entry_bytes: int = 16 * 1024 * 1024
    max_worksheets: int = 100
    max_columns: int = 200


@dataclass(frozen=True)
class _Entry:
    name: str
    method: int
    compressed_size: int
    uncompressed_size: int
    local_offset: int


class RangedXlsxDiscovery:
    def __init__(self, http: SourceHttpClient, *, policy: XlsxDiscoveryPolicy | None = None) -> None:
        self.http = http
        self.policy = policy or XlsxDiscoveryPolicy()
        self.transferred = 0

    async def discover(
        self,
        url: str,
        *,
        basic_auth: tuple[str, str],
    ) -> tuple[list[dict[str, Any]], str | None]:
        tail, total, headers = await self._suffix(url, 65_557, basic_auth)
        eocd_at = tail.rfind(b"PK\x05\x06")
        if eocd_at < 0 or len(tail) - eocd_at < 22:
            raise XlsxDiscoveryError("xlsx_directory_unavailable")
        _, _, _, _, entries_count, directory_size, directory_offset, _ = struct.unpack_from(
            "<4s4H2LH", tail, eocd_at
        )
        if entries_count > 20_000 or directory_size > self.policy.max_entry_bytes:
            raise XlsxDiscoveryError("xlsx_metadata_limit_exceeded")
        directory = await self._range(url, directory_offset, directory_offset + directory_size - 1, total, basic_auth)
        entries = self._directory_entries(directory)
        workbook = ElementTree.fromstring(await self._entry(url, total, entries, "xl/workbook.xml", basic_auth))
        relations = ElementTree.fromstring(await self._entry(url, total, entries, "xl/_rels/workbook.xml.rels", basic_auth))
        relation_targets = {
            str(item.attrib.get("Id") or ""): str(item.attrib.get("Target") or "")
            for item in relations
        }
        shared_strings = await self._shared_strings(url, total, entries, basic_auth)
        worksheets: list[dict[str, Any]] = []
        relationship_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        for sheet in workbook.findall(".//{*}sheet")[: self.policy.max_worksheets]:
            name = str(sheet.attrib.get("name") or "").strip()
            relationship_id = str(sheet.attrib.get(relationship_namespace) or "")
            target = relation_targets.get(relationship_id, "")
            if not name or not target:
                continue
            clean_target = target.lstrip("/")
            entry_name = posixpath.normpath(
                clean_target if clean_target.startswith("xl/") else posixpath.join("xl", clean_target)
            )
            if not entry_name.startswith("xl/worksheets/") or entry_name not in entries:
                continue
            xml = await self._entry(url, total, entries, entry_name, basic_auth)
            columns = self._header_columns(xml, shared_strings)
            worksheets.append({"name": name[:240], "rowCount": None, "columns": columns})
        if not worksheets:
            raise XlsxDiscoveryError("worksheet_metadata_unavailable")
        token = str(headers.get("etag") or "").strip().strip('"')[:255] or None
        return worksheets, token

    async def _suffix(self, url: str, size: int, auth: tuple[str, str]) -> tuple[bytes, int, dict[str, str]]:
        response = await self.http.request(
            "GET", url, headers={"Accept": "application/octet-stream", "Accept-Encoding": "identity", "Range": f"bytes=-{size}"}, basic_auth=auth
        )
        if response.status_code != 206:
            raise XlsxDiscoveryError("provider_range_reads_unsupported")
        content_range = str(response.headers.get("content-range") or "")
        match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+)", content_range, re.IGNORECASE)
        if not match:
            raise XlsxDiscoveryError("provider_range_response_invalid")
        response_start, response_end, total = map(int, match.groups())
        if response_end < response_start or response_end - response_start + 1 != len(response.content):
            raise XlsxDiscoveryError("provider_range_response_invalid")
        self._account(len(response.content))
        return response.content, total, dict(response.headers)

    async def _range(
        self, url: str, start: int, end: int, total: int, auth: tuple[str, str]
    ) -> bytes:
        if start < 0 or end < start or end >= total or end - start + 1 > self.policy.max_entry_bytes:
            raise XlsxDiscoveryError("xlsx_metadata_limit_exceeded")
        response = await self.http.request(
            "GET", url, headers={"Accept": "application/octet-stream", "Accept-Encoding": "identity", "Range": f"bytes={start}-{end}"}, basic_auth=auth
        )
        content_range = str(response.headers.get("content-range") or "")
        match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+)", content_range, re.IGNORECASE)
        if (
            response.status_code != 206
            or len(response.content) != end - start + 1
            or match is None
            or tuple(map(int, match.groups())) != (start, end, total)
        ):
            raise XlsxDiscoveryError("provider_range_response_invalid")
        self._account(len(response.content))
        return response.content

    def _directory_entries(self, content: bytes) -> dict[str, _Entry]:
        result: dict[str, _Entry] = {}
        offset = 0
        while offset + 46 <= len(content):
            fields = struct.unpack_from("<4s6H3I5H2I", content, offset)
            if fields[0] != b"PK\x01\x02":
                raise XlsxDiscoveryError("xlsx_directory_invalid")
            name_length, extra_length, comment_length = fields[10], fields[11], fields[12]
            end = offset + 46 + name_length + extra_length + comment_length
            if end > len(content):
                raise XlsxDiscoveryError("xlsx_directory_invalid")
            try:
                name = content[offset + 46 : offset + 46 + name_length].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise XlsxDiscoveryError("xlsx_directory_invalid") from exc
            result[name] = _Entry(name, fields[4], fields[8], fields[9], fields[16])
            offset = end
        return result

    async def _entry(
        self, url: str, total: int, entries: dict[str, _Entry], name: str, auth: tuple[str, str]
    ) -> bytes:
        entry = entries.get(name)
        if entry is None:
            raise XlsxDiscoveryError("xlsx_entry_missing")
        if entry.compressed_size > self.policy.max_entry_bytes or entry.uncompressed_size > self.policy.max_uncompressed_entry_bytes:
            raise XlsxDiscoveryError("xlsx_metadata_limit_exceeded")
        header = await self._range(url, entry.local_offset, entry.local_offset + 29, total, auth)
        values = struct.unpack("<4s5H3I2H", header)
        if values[0] != b"PK\x03\x04":
            raise XlsxDiscoveryError("xlsx_entry_invalid")
        data_start = entry.local_offset + 30 + values[9] + values[10]
        compressed = await self._range(url, data_start, data_start + entry.compressed_size - 1, total, auth)
        if entry.method == 0:
            value = compressed
        elif entry.method == 8:
            try:
                decompressor = zlib.decompressobj(-15)
                value = decompressor.decompress(
                    compressed, self.policy.max_uncompressed_entry_bytes + 1
                )
                if decompressor.unconsumed_tail or len(value) > self.policy.max_uncompressed_entry_bytes:
                    raise XlsxDiscoveryError("xlsx_metadata_limit_exceeded")
                value += decompressor.flush()
            except zlib.error as exc:
                raise XlsxDiscoveryError("xlsx_entry_invalid") from exc
        else:
            raise XlsxDiscoveryError("xlsx_compression_unsupported")
        if len(value) > self.policy.max_uncompressed_entry_bytes:
            raise XlsxDiscoveryError("xlsx_metadata_limit_exceeded")
        return value

    async def _shared_strings(
        self, url: str, total: int, entries: dict[str, _Entry], auth: tuple[str, str]
    ) -> list[str]:
        if "xl/sharedStrings.xml" not in entries:
            return []
        root = ElementTree.fromstring(await self._entry(url, total, entries, "xl/sharedStrings.xml", auth))
        return ["".join(node.text or "" for node in item.findall(".//{*}t")) for item in root.findall("{*}si")]

    def _header_columns(self, content: bytes, shared_strings: list[str]) -> list[dict[str, str]]:
        root = ElementTree.fromstring(content)
        row = root.find(".//{*}sheetData/{*}row")
        if row is None:
            return []
        columns: list[dict[str, str]] = []
        for cell in row.findall("{*}c")[: self.policy.max_columns]:
            reference = str(cell.attrib.get("r") or "")
            match = re.match(r"([A-Z]{1,3})", reference.upper())
            if not match:
                continue
            letter = match.group(1)
            cell_type = str(cell.attrib.get("t") or "")
            if cell_type == "inlineStr":
                value = "".join(node.text or "" for node in cell.findall(".//{*}t"))
            else:
                raw = cell.findtext("{*}v") or ""
                if cell_type == "s" and raw.isdigit() and int(raw) < len(shared_strings):
                    value = shared_strings[int(raw)]
                else:
                    value = raw
            columns.append({"id": letter, "letter": letter, "header": " ".join(value.strip().split())[:240]})
        return columns

    def _account(self, amount: int) -> None:
        self.transferred += amount
        if self.transferred > self.policy.max_transfer_bytes:
            raise XlsxDiscoveryError("xlsx_discovery_transfer_limit_exceeded")
