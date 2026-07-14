"""Small deterministic spreadsheet formula engine.

The engine parses a deliberately constrained Excel-like grammar into Python's
AST, validates every node, and interprets it without ``eval``.  It has no I/O,
attribute access, arbitrary function calls, or executable language escape.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, DivisionByZero, InvalidOperation

FORMULA_ENGINE_VERSION = "flowhub-formula-1"
MAX_FORMULA_LENGTH = 2_000
MAX_DEPENDENCIES = 1_000
MAX_EVALUATION_STEPS = 10_000

_CELL = re.compile(r"(?<![A-Z0-9_\"'])\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})(?![A-Z0-9_\"'])", re.I)
_RANGE = re.compile(r"\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})\s*:\s*\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})", re.I)
_ALLOWED_FUNCTIONS = {"ROUND", "IF", "MIN", "MAX", "SUM", "CELL", "RANGE"}
FormulaScalar = Decimal | bool | str | None
FormulaValue = FormulaScalar | list[FormulaScalar]


class FormulaError(ValueError):
    """A stable, user-displayable calculation failure."""


@dataclass(frozen=True)
class FormulaResult:
    value: str | None
    dependencies: tuple[str, ...]
    error: str | None = None


def column_number(name: str) -> int:
    result = 0
    for character in name.upper():
        if character < "A" or character > "Z":
            raise FormulaError("INVALID_REFERENCE")
        result = result * 26 + ord(character) - 64
    return result


def column_name(number: int) -> str:
    if number < 1 or number > 18_278:
        raise FormulaError("INVALID_REFERENCE")
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def expand_range(start: str, end: str) -> tuple[str, ...]:
    start_match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", start.upper())
    end_match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", end.upper())
    if not start_match or not end_match:
        raise FormulaError("INVALID_REFERENCE")
    start_column, start_row = column_number(start_match[1]), int(start_match[2])
    end_column, end_row = column_number(end_match[1]), int(end_match[2])
    left, right = sorted((start_column, end_column))
    top, bottom = sorted((start_row, end_row))
    references = tuple(
        f"{column_name(column)}{row}"
        for row in range(top, bottom + 1)
        for column in range(left, right + 1)
    )
    if len(references) > MAX_DEPENDENCIES:
        raise FormulaError("DEPENDENCY_LIMIT")
    return references


def _translate(expression: str) -> str:
    text = expression.strip()
    if not text.startswith("="):
        raise FormulaError("FORMULA_PREFIX_REQUIRED")
    if len(text) > MAX_FORMULA_LENGTH:
        raise FormulaError("FORMULA_TOO_LONG")
    text = text[1:].strip()
    text = text.replace("^", "**").replace("<>", "!=")
    text = re.sub(r"(?<![<>!=])=(?!=)", "==", text)
    text = _RANGE.sub(lambda match: f'RANGE("{match[1].upper()}{match[2]}","{match[3].upper()}{match[4]}")', text)
    text = _CELL.sub(lambda match: f'CELL("{match[1].upper()}{match[2]}")', text)
    return text


class FormulaEvaluator:
    def __init__(self, resolver: Callable[[str], Decimal | str | None]) -> None:
        self._resolver = resolver
        self._dependencies: set[str] = set()
        self._steps = 0

    def evaluate(self, expression: str) -> FormulaResult:
        try:
            tree = ast.parse(_translate(expression), mode="eval")
            value = self._node(tree.body)
            normalized = self._serialize(value)
            return FormulaResult(normalized, tuple(sorted(self._dependencies)))
        except FormulaError as exc:
            return FormulaResult(None, tuple(sorted(self._dependencies)), str(exc))
        except (SyntaxError, InvalidOperation, DivisionByZero, ZeroDivisionError):
            return FormulaResult(None, tuple(sorted(self._dependencies)), "CALCULATION_ERROR")

    def _tick(self) -> None:
        self._steps += 1
        if self._steps > MAX_EVALUATION_STEPS:
            raise FormulaError("EVALUATION_LIMIT")

    def _node(self, node: ast.AST) -> FormulaValue:
        self._tick()
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return node.value
            if isinstance(node.value, (int, float)):
                return Decimal(str(node.value))
            if isinstance(node.value, str):
                return node.value
            raise FormulaError("UNSUPPORTED_LITERAL")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self._decimal(self._node(node.operand))
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
        ):
            left = self._decimal(self._node(node.left))
            right = self._decimal(self._node(node.right))
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise FormulaError("DIVISION_BY_ZERO")
                return left / right
            exponent = int(right)
            if right != exponent or abs(exponent) > 20:
                raise FormulaError("POWER_LIMIT")
            return left**exponent
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
            comparison_left = self._node(node.left)
            comparison_right = self._node(node.comparators[0])
            operation = node.ops[0]
            if isinstance(operation, ast.Gt):
                return self._decimal(comparison_left) > self._decimal(comparison_right)
            if isinstance(operation, ast.GtE):
                return self._decimal(comparison_left) >= self._decimal(comparison_right)
            if isinstance(operation, ast.Lt):
                return self._decimal(comparison_left) < self._decimal(comparison_right)
            if isinstance(operation, ast.LtE):
                return self._decimal(comparison_left) <= self._decimal(comparison_right)
            if isinstance(operation, ast.Eq):
                return comparison_left == comparison_right
            if isinstance(operation, ast.NotEq):
                return comparison_left != comparison_right
            raise FormulaError("UNSUPPORTED_COMPARISON")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id.upper()
            if name not in _ALLOWED_FUNCTIONS or node.keywords:
                raise FormulaError("UNSUPPORTED_FUNCTION")
            return self._call(name, [self._node(argument) for argument in node.args])
        raise FormulaError("UNSUPPORTED_EXPRESSION")

    def _call(
        self, name: str, arguments: list[FormulaValue]
    ) -> FormulaValue:
        if name == "CELL":
            if len(arguments) != 1 or not isinstance(arguments[0], str):
                raise FormulaError("INVALID_REFERENCE")
            reference = arguments[0].upper()
            self._dependencies.add(reference)
            if len(self._dependencies) > MAX_DEPENDENCIES:
                raise FormulaError("DEPENDENCY_LIMIT")
            return self._resolver(reference)
        if name == "RANGE":
            if len(arguments) != 2 or not all(isinstance(item, str) for item in arguments):
                raise FormulaError("INVALID_REFERENCE")
            references = expand_range(str(arguments[0]), str(arguments[1]))
            self._dependencies.update(references)
            if len(self._dependencies) > MAX_DEPENDENCIES:
                raise FormulaError("DEPENDENCY_LIMIT")
            return [self._resolver(reference) for reference in references]
        if name == "IF":
            if len(arguments) != 3:
                raise FormulaError("INVALID_ARGUMENT_COUNT")
            return arguments[1] if bool(arguments[0]) else arguments[2]
        if name == "ROUND":
            if len(arguments) not in {1, 2}:
                raise FormulaError("INVALID_ARGUMENT_COUNT")
            digits = int(self._decimal(arguments[1])) if len(arguments) == 2 else 0
            if digits < -12 or digits > 12:
                raise FormulaError("ROUND_LIMIT")
            quantum = Decimal(1).scaleb(-digits)
            return self._decimal(arguments[0]).quantize(quantum, rounding=ROUND_HALF_UP)
        values = [self._decimal(value) for value in self._flatten(arguments)]
        if not values:
            raise FormulaError("EMPTY_RANGE")
        if name == "SUM":
            return sum(values, Decimal(0))
        if name == "MIN":
            return min(values)
        if name == "MAX":
            return max(values)
        raise FormulaError("UNSUPPORTED_FUNCTION")

    @staticmethod
    def _flatten(
        values: Iterable[FormulaValue],
    ) -> Iterable[FormulaScalar]:
        for value in values:
            if isinstance(value, list):
                yield from value
            else:
                yield value

    @staticmethod
    def _decimal(value: FormulaValue) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, bool):
            return Decimal(1 if value else 0)
        if value is None or value == "":
            return Decimal(0)
        if isinstance(value, list):
            raise FormulaError("RANGE_NOT_ALLOWED_HERE")
        try:
            return Decimal(str(value).replace(",", "").strip())
        except InvalidOperation as exc:
            raise FormulaError("NON_NUMERIC_VALUE") from exc

    @staticmethod
    def _serialize(value: FormulaValue) -> str | None:
        if value is None:
            return None
        if isinstance(value, list):
            raise FormulaError("RANGE_RESULT_NOT_ALLOWED")
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, Decimal):
            normalized = format(value.normalize(), "f")
            return "0" if normalized in {"-0", ""} else normalized
        return str(value)


def calculate_sheet(values: dict[str, str | None]) -> dict[str, FormulaResult]:
    """Evaluate a sheet deterministically, including dependency and cycle checks."""

    results: dict[str, FormulaResult] = {}
    visiting: set[str] = set()

    def resolve(reference: str) -> Decimal | str | None:
        reference = reference.upper()
        if reference in visiting:
            raise FormulaError("CIRCULAR_REFERENCE")
        if reference in results:
            result = results[reference]
            if result.error:
                raise FormulaError(result.error)
            return result.value
        raw = values.get(reference)
        if raw is None:
            return None
        if not str(raw).lstrip().startswith("="):
            return str(raw)
        visiting.add(reference)
        result = FormulaEvaluator(resolve).evaluate(str(raw))
        visiting.remove(reference)
        results[reference] = result
        if result.error:
            raise FormulaError(result.error)
        return result.value

    for reference, raw in sorted(values.items()):
        if raw is not None and str(raw).lstrip().startswith("=") and reference not in results:
            try:
                resolve(reference)
            except FormulaError as exc:
                results.setdefault(reference, FormulaResult(None, (), str(exc)))
    return results
