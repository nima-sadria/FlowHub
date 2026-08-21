"""Framework-free domain contracts and policies for Unified Workspace."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


class EntryPoint(StrEnum):
    SOURCE = "source"
    MANUAL = "manual"


class ProductKind(StrEnum):
    SIMPLE = "simple"
    VARIABLE = "variable"
    VARIATION = "variation"


class MappingState(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    CONFLICT = "conflict"


class WorkspaceState(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class DraftState(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPLIED = "applied"


class ReviewState(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"
    STALE = "stale"


class ApplyState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PARTIALLY_APPLIED = "partially_applied"
    APPLIED = "applied"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    STALE = "stale"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class ApplyItemOutcome(StrEnum):
    """Authoritative lifecycle for a single external write attempt."""

    PENDING = "pending"
    DISPATCH_INTENT_RECORDED = "dispatch_intent_recorded"
    DISPATCHED = "dispatched"
    PROVIDER_ACCEPTED = "provider_accepted"
    VERIFIED_APPLIED = "verified_applied"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    RECOVERING = "recovering"


class CellStatus(StrEnum):
    UNCHANGED = "unchanged"
    EDITED = "edited"
    DRAFT_SAVED = "draft_saved"
    WARNING = "warning"
    ERROR = "error"
    READY = "ready"
    APPLYING = "applying"
    APPLIED = "applied"
    FAILED = "failed"
    READ_ONLY = "read_only"
    UNAVAILABLE = "unavailable"
    STALE_REVIEW = "stale_review"


class AvailabilitySignal(StrEnum):
    """Provider-neutral availability evidence contributed by one Source field."""

    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"


class SourceInstruction(StrEnum):
    """Keep Source meanings distinct; ``None`` is not a business contract."""

    SET = "SET"
    NO_INSTRUCTION = "NO_INSTRUCTION"
    UNAVAILABLE = "UNAVAILABLE"
    UNUSABLE = "UNUSABLE"
    INVALID = "INVALID"


class PriceChangeState(StrEnum):
    UNCHANGED = "UNCHANGED"
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    NO_VALID_PRICE = "NO_VALID_PRICE"
    NOT_EVALUATED = "NOT_EVALUATED"


class QuantityChangeState(StrEnum):
    UNMANAGED = "UNMANAGED"
    UNCHANGED = "UNCHANGED"
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    NOT_EVALUATED = "NOT_EVALUATED"


class StockStatusChangeState(StrEnum):
    UNCHANGED_IN_STOCK = "UNCHANGED_IN_STOCK"
    UNCHANGED_OUT_OF_STOCK = "UNCHANGED_OUT_OF_STOCK"
    BECOMES_IN_STOCK = "BECOMES_IN_STOCK"
    BECOMES_OUT_OF_STOCK = "BECOMES_OUT_OF_STOCK"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True, slots=True)
class NormalizedSourceField:
    """Exact, immutable business meaning of one observed Source cell.

    This intentionally sits below Workspace persistence.  It gives Source
    acquisition, Preview, and focused tests one canonical interpretation while
    retaining the raw lexeme as evidence.
    """

    instruction: SourceInstruction
    raw_lexeme: str | None
    target: str | None = None
    availability_signal: AvailabilitySignal | None = None
    reason_code: str | None = None
    warning_code: str | None = None
    blocker_code: str | None = None
    fix_applied: bool = False


def _decimal_text(value: Decimal) -> str:
    """Serialize exact canonical Decimal without exponent or redundant scale."""

    return format(value.normalize(), "f") if value != 0 else "0"


def _numeric_lexeme(raw: object) -> tuple[str | None, str | None]:
    """Return normalized ASCII numeric text or a precise lexical failure code.

    The accepted grammar is deliberately smaller than ``Decimal``: no signs,
    exponent, units, currency glyphs, or partially repaired text.  Persian and
    Arabic-Indic digits and their documented separators are normalized first.
    """

    if raw is None:
        return None, None
    if isinstance(raw, bool):
        return None, "BOOLEAN_NOT_NUMERIC"
    text = str(raw).strip()
    if not text:
        return None, None
    translation = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫",
        "01234567890123456789.",
    )
    text = text.translate(translation)
    if text.count(".") > 1 or ("." in text and "," in text and text.rfind(",") > text.rfind(".")):
        return None, "PRICE_MALFORMED"
    integer, separator, fraction = text.partition(".")
    if "," in integer:
        groups = integer.split(",")
        if not groups[0] or len(groups[0]) > 3 or any(
            len(group) != 3 or not group.isdigit() for group in groups[1:]
        ):
            return None, "PRICE_MALFORMED"
        integer = "".join(groups)
    if "," in fraction or not integer.isdigit() or (separator and (not fraction or not fraction.isdigit())):
        return None, "PRICE_MALFORMED"
    return integer + ("." + fraction if separator else ""), None


def _decimal_from_lexeme(raw: object) -> tuple[str | None, Decimal | None, str | None]:
    lexeme, failure = _numeric_lexeme(raw)
    if lexeme is None:
        return lexeme, None, failure
    try:
        value = Decimal(lexeme)
    except InvalidOperation:
        return lexeme, None, "PRICE_MALFORMED"
    if not value.is_finite():
        return lexeme, None, "PRICE_NON_FINITE"
    return lexeme, value, None


# ISO 4217 minor-unit (decimal-place) exponents. This is the canonical,
# versioned default monetary precision contract for any currency without an
# explicit Channel-declared override (`capabilities["monetaryPrecision"]`).
# RIAL/TOMAN are handled separately (always 0, see is_rial_or_toman below)
# and are not part of this table. Every other ISO 4217 currency not listed
# here uses the standard two-decimal default.
_ISO_4217_ZERO_DECIMAL_CURRENCIES = frozenset(
    {
        "BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG",
        "RWF", "UGX", "UYI", "VND", "VUV", "XAF", "XOF", "XPF",
    }
)
_ISO_4217_THREE_DECIMAL_CURRENCIES = frozenset(
    {"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"}
)
MONETARY_PRECISION_CONTRACT_VERSION = "iso4217-v1"


def default_monetary_precision(currency: str | None) -> int:
    """Return the ISO 4217 standard decimal-place count for `currency`."""

    code = canonical_text(currency).upper()
    if code in _ISO_4217_ZERO_DECIMAL_CURRENCIES:
        return 0
    if code in _ISO_4217_THREE_DECIMAL_CURRENCIES:
        return 3
    return 2


def normalize_direct_price(
    raw: object,
    *,
    currency: str | None,
    unit: str | None,
    monetary_precision: int | None,
    fix_zero_decimal_prices: bool | None = None,
    raw_scale_authoritative: bool = True,
    mapped: bool = True,
) -> NormalizedSourceField:
    """Apply the approved direct mapped Price contract without float coercion."""

    if not mapped:
        return NormalizedSourceField(SourceInstruction.NO_INSTRUCTION, None)
    raw_lexeme = None if raw is None else str(raw).strip()
    if raw is None or raw_lexeme == "":
        return NormalizedSourceField(
            SourceInstruction.UNAVAILABLE, raw_lexeme, availability_signal=AvailabilitySignal.OUT_OF_STOCK,
            reason_code="PRICE_UNAVAILABLE_BLANK",
        )
    if raw_lexeme.casefold() == "x":
        return NormalizedSourceField(
            SourceInstruction.UNAVAILABLE, raw_lexeme, availability_signal=AvailabilitySignal.OUT_OF_STOCK,
            reason_code="PRICE_UNAVAILABLE_X",
        )
    lexeme, value, failure = _decimal_from_lexeme(raw)
    if failure or value is None:
        return NormalizedSourceField(
            SourceInstruction.UNUSABLE, raw_lexeme, availability_signal=AvailabilitySignal.OUT_OF_STOCK,
            reason_code=failure or "PRICE_NOT_NUMERIC", warning_code="UNUSABLE_MAPPED_PRICE",
        )
    if value == 0:
        return NormalizedSourceField(
            SourceInstruction.UNAVAILABLE, raw_lexeme, availability_signal=AvailabilitySignal.OUT_OF_STOCK,
            reason_code="PRICE_UNAVAILABLE_ZERO",
        )
    if value < 0:
        return NormalizedSourceField(
            SourceInstruction.UNUSABLE, raw_lexeme, availability_signal=AvailabilitySignal.OUT_OF_STOCK,
            reason_code="PRICE_NEGATIVE", warning_code="UNUSABLE_MAPPED_PRICE",
        )
    currency_value, unit_value = canonical_text(currency).upper(), canonical_text(unit).upper()
    if not currency_value or not unit_value or monetary_precision is None or monetary_precision < 0:
        return NormalizedSourceField(
            SourceInstruction.INVALID, raw_lexeme, reason_code="MONETARY_PRECISION_CONTRACT_MISSING",
            blocker_code="MONETARY_PRECISION_CONTRACT_MISSING",
        )
    is_rial_or_toman = currency_value == "IRR" and unit_value in {"RIAL", "TOMAN"}
    if is_rial_or_toman:
        effective_fix = True if fix_zero_decimal_prices is None else fix_zero_decimal_prices
        has_decimal_form = "." in (lexeme or "")
        if not effective_fix and has_decimal_form and not raw_scale_authoritative:
            return NormalizedSourceField(
                SourceInstruction.INVALID, raw_lexeme, reason_code="SOURCE_PRICE_LEXEME_UNVERIFIABLE",
                blocker_code="SOURCE_PRICE_LEXEME_UNVERIFIABLE",
            )
        if value != value.to_integral_value():
            return NormalizedSourceField(
                SourceInstruction.UNUSABLE, raw_lexeme, availability_signal=AvailabilitySignal.OUT_OF_STOCK,
                reason_code="PRICE_FRACTION_NOT_ALLOWED", warning_code="UNUSABLE_MAPPED_PRICE",
            )
        if has_decimal_form and not effective_fix:
            return NormalizedSourceField(
                SourceInstruction.UNUSABLE, raw_lexeme, availability_signal=AvailabilitySignal.OUT_OF_STOCK,
                reason_code="PRICE_DECIMAL_LEXEME_NOT_ALLOWED", warning_code="UNUSABLE_MAPPED_PRICE",
            )
        return NormalizedSourceField(
            SourceInstruction.SET, raw_lexeme, target=_decimal_text(value),
            availability_signal=AvailabilitySignal.IN_STOCK,
            reason_code="PRICE_ZERO_DECIMAL_FIXED" if has_decimal_form else None,
            fix_applied=has_decimal_form,
        )
    scale_factor = Decimal(10) ** monetary_precision
    if value * scale_factor != (value * scale_factor).to_integral_value():
        return NormalizedSourceField(
            SourceInstruction.UNUSABLE, raw_lexeme, availability_signal=AvailabilitySignal.OUT_OF_STOCK,
            reason_code="PRICE_PRECISION_NOT_ALLOWED", warning_code="UNUSABLE_MAPPED_PRICE",
        )
    return NormalizedSourceField(
        SourceInstruction.SET, raw_lexeme, target=_decimal_text(value),
        availability_signal=AvailabilitySignal.IN_STOCK,
    )


def normalize_quantity(raw: object, *, mapped: bool = True) -> NormalizedSourceField:
    if not mapped:
        return NormalizedSourceField(SourceInstruction.NO_INSTRUCTION, None)
    raw_lexeme = None if raw is None else str(raw).strip()
    if raw is None or raw_lexeme == "":
        return NormalizedSourceField(
            SourceInstruction.NO_INSTRUCTION, raw_lexeme,
            availability_signal=AvailabilitySignal.IN_STOCK,
        )
    _, value, failure = _decimal_from_lexeme(raw)
    if failure or value is None or value < 0 or value != value.to_integral_value():
        return NormalizedSourceField(
            SourceInstruction.INVALID, raw_lexeme, reason_code="INVALID_QUANTITY",
            blocker_code="INVALID_QUANTITY",
        )
    return NormalizedSourceField(
        SourceInstruction.SET, raw_lexeme, target=_decimal_text(value),
        availability_signal=(AvailabilitySignal.OUT_OF_STOCK if value == 0 else AvailabilitySignal.IN_STOCK),
    )


def normalize_stock_status(raw: object, *, mapped: bool = True) -> NormalizedSourceField:
    if not mapped:
        return NormalizedSourceField(SourceInstruction.NO_INSTRUCTION, None)
    raw_lexeme = None if raw is None else str(raw).strip()
    if raw is None or raw_lexeme == "":
        return NormalizedSourceField(
            SourceInstruction.SET, raw_lexeme, target=AvailabilitySignal.IN_STOCK.value,
            availability_signal=AvailabilitySignal.IN_STOCK,
        )
    # Status intentionally rejects grouped values even though Price accepts them.
    if "," in raw_lexeme or isinstance(raw, bool):
        return NormalizedSourceField(SourceInstruction.INVALID, raw_lexeme, reason_code="INVALID_STOCK_STATUS", blocker_code="INVALID_STOCK_STATUS")
    _, value, failure = _decimal_from_lexeme(raw)
    if failure or value not in {Decimal(0), Decimal(1)}:
        return NormalizedSourceField(SourceInstruction.INVALID, raw_lexeme, reason_code="INVALID_STOCK_STATUS", blocker_code="INVALID_STOCK_STATUS")
    signal = AvailabilitySignal.OUT_OF_STOCK if value == 0 else AvailabilitySignal.IN_STOCK
    return NormalizedSourceField(SourceInstruction.SET, raw_lexeme, target=signal.value, availability_signal=signal)


def resolve_availability(*fields: NormalizedSourceField) -> tuple[AvailabilitySignal | None, tuple[str, ...]]:
    """Apply the approved blocker → OOS → IN → no-instruction precedence."""

    blockers = tuple(field.blocker_code for field in fields if field.blocker_code)
    if blockers:
        return None, blockers
    signals = {field.availability_signal for field in fields}
    if AvailabilitySignal.OUT_OF_STOCK in signals:
        return AvailabilitySignal.OUT_OF_STOCK, ()
    if AvailabilitySignal.IN_STOCK in signals:
        return AvailabilitySignal.IN_STOCK, ()
    return None, ()


class WorkspaceDomainError(ValueError):
    code = "WORKSPACE_DOMAIN_ERROR"


class ConcurrencyConflict(WorkspaceDomainError):
    code = "OPTIMISTIC_CONCURRENCY_CONFLICT"


class ImmutableRecordError(WorkspaceDomainError):
    code = "IMMUTABLE_RECORD"


class StaleReviewError(WorkspaceDomainError):
    code = "STALE_REVIEW"


class PermissionDenied(WorkspaceDomainError):
    code = "WORKSPACE_PERMISSION_DENIED"


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def canonical_text(value: object) -> str:
    # `value or ""` previously collapsed any falsy-but-present value -- most
    # importantly numeric identifier/quantity zero -- to blank, identical to
    # a truly absent value. Identity, price, and stock zero are meaningful
    # business values (see the Product Identity Authority ADR and the
    # Stock Quantity rules), so only None is treated as blank here.
    text = unicodedata.normalize("NFKC", "" if value is None else str(value))
    return " ".join(text.strip().split())


def stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def checksum(value: object) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Money:
    raw_amount: str
    currency: str
    unit: str
    original_currency: str
    original_unit: str
    normalized_amount: Decimal
    normalized_currency: str
    normalized_unit: str
    conversion_factor: Decimal
    conversion_rule: str
    conversion_context: str
    configuration_reference: str

    @classmethod
    def create(
        cls,
        raw_amount: object,
        *,
        currency: str,
        unit: str,
        normalized_currency: str,
        normalized_unit: str,
        conversion_factor: object,
        conversion_rule: str,
        conversion_context: str,
        configuration_reference: str,
    ) -> Money:
        currency_value = canonical_text(currency).upper()
        unit_value = canonical_text(unit).upper()
        if not currency_value or not unit_value:
            raise WorkspaceDomainError("Currency and unit must be explicit.")
        if currency_value in {"TMN", "TOMAN"}:
            raise WorkspaceDomainError("Toman is a unit, not an ISO currency code.")
        try:
            amount = Decimal(canonical_text(raw_amount).replace(",", ""))
            factor = Decimal(canonical_text(conversion_factor))
        except InvalidOperation as exc:
            raise WorkspaceDomainError(
                "Money amount and conversion factor must be numeric."
            ) from exc
        if not amount.is_finite() or not factor.is_finite() or factor <= 0:
            raise WorkspaceDomainError(
                "Money values must be finite and conversion factor must be positive."
            )
        return cls(
            raw_amount=canonical_text(raw_amount),
            currency=currency_value,
            unit=unit_value,
            original_currency=currency_value,
            original_unit=unit_value,
            normalized_amount=amount * factor,
            normalized_currency=canonical_text(normalized_currency).upper(),
            normalized_unit=canonical_text(normalized_unit).upper(),
            conversion_factor=factor,
            conversion_rule=canonical_text(conversion_rule),
            conversion_context=canonical_text(conversion_context),
            configuration_reference=canonical_text(configuration_reference),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "raw_amount": self.raw_amount,
            "currency": self.currency,
            "unit": self.unit,
            "original_currency": self.original_currency,
            "original_unit": self.original_unit,
            "normalized_amount": str(self.normalized_amount),
            "normalized_currency": self.normalized_currency,
            "normalized_unit": self.normalized_unit,
            "conversion_factor": str(self.conversion_factor),
            "conversion_rule": self.conversion_rule,
            "conversion_context": self.conversion_context,
            "configuration_reference": self.configuration_reference,
        }


@dataclass(frozen=True, slots=True)
class ChannelCapabilities:
    channel_id: str
    read_price: bool
    write_price: bool
    read_stock: bool
    write_stock: bool
    read_status: bool
    write_status: bool
    supports_bulk_update: bool
    supports_partial_update: bool
    supports_multiple_listings: bool
    supports_variations: bool
    requires_stock_management: bool
    maximum_batch_size: int
    rate_limit_per_minute: int | None
    health_state: str
    primary_identifier_type: str
    supported_statuses: tuple[str, ...]
    currency: str
    unit: str
    write_available: bool
    version: str
    mapping_required_fields: tuple[str, ...] = ("external_id",)

    def can_write(self, field: str) -> bool:
        return self.write_available and {
            "price": self.write_price,
            "stock": self.write_stock,
            "status": self.write_status,
        }.get(field, False)


@dataclass(frozen=True, slots=True)
class DraftChange:
    canonical_product_id: str
    listing_id: str
    channel_id: str
    field: str
    target_value: str
    currency: str | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        if self.field not in {"price", "stock", "status"}:
            raise WorkspaceDomainError(f"Unsupported editable field: {self.field}")
        if not all((self.canonical_product_id, self.listing_id, self.channel_id)):
            raise WorkspaceDomainError("Canonical product, listing, and channel are required.")
        if self.field in {"price", "stock"}:
            try:
                parsed = Decimal(canonical_text(self.target_value).replace(",", ""))
            except InvalidOperation as exc:
                raise WorkspaceDomainError(f"{self.field} must be numeric.") from exc
            if not parsed.is_finite() or parsed < 0:
                raise WorkspaceDomainError(f"{self.field} must be finite and non-negative.")
        if self.field == "price" and (not self.currency or not self.unit):
            raise WorkspaceDomainError("Price changes require explicit currency and unit.")

    def as_dict(self) -> dict[str, str | None]:
        return {
            "canonical_product_id": self.canonical_product_id,
            "listing_id": self.listing_id,
            "channel_id": self.channel_id,
            "field": self.field,
            "target_value": canonical_text(self.target_value),
            "currency": self.currency,
            "unit": self.unit,
        }


def validate_product_editable(product_type: str) -> None:
    if product_type == ProductKind.VARIABLE:
        raise WorkspaceDomainError(
            "Variable parent products are grouping-only and cannot be edited."
        )
    if product_type not in {ProductKind.SIMPLE, ProductKind.VARIATION}:
        raise WorkspaceDomainError("Unsupported product type.")


def deterministic_revision_checksum(changes: list[DraftChange], metadata: Mapping[str, Any]) -> str:
    ordered = sorted(
        (change.as_dict() for change in changes),
        key=lambda item: (
            str(item["canonical_product_id"]),
            str(item["listing_id"]),
            str(item["field"]),
        ),
    )
    return checksum({"changes": ordered, "metadata": dict(metadata)})


def values_equal(field: str, current: object, target: object) -> bool:
    if field in {"price", "stock"}:
        try:
            left = Decimal(canonical_text(current).replace(",", ""))
            right = Decimal(canonical_text(target).replace(",", ""))
        except InvalidOperation:
            return False
        return left.is_finite() and right.is_finite() and left == right
    if field == "status":
        canonical_status = {
            "instock": "in_stock",
            "outofstock": "out_of_stock",
            "in_stock": "in_stock",
            "out_of_stock": "out_of_stock",
        }
        return canonical_status.get(canonical_text(current).casefold()) == canonical_status.get(
            canonical_text(target).casefold()
        )
    return canonical_text(current).casefold() == canonical_text(target).casefold()


def finite_number(value: object) -> bool:
    try:
        return math.isfinite(float(canonical_text(value).replace(",", "")))
    except (TypeError, ValueError):
        return False
