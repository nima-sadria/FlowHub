"""Closed-contract persistence foundation for formula translator metadata and results.

Phase D2 intentionally adds only immutable/append-only persistence and checksum
helpers.  No formula parsing, evaluator, translator engine, or workbook
migration execution occurs in this module.
"""

from __future__ import annotations

