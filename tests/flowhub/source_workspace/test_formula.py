from __future__ import annotations

from app.flowhub.source_workspace.formula import FormulaEvaluator, calculate_sheet


def test_formula_arithmetic_functions_ranges_and_dependencies() -> None:
    values = {
        "B2": "100",
        "C2": "20",
        "D2": "=B2*(1+C2/100)",
        "E2": "=ROUND(D2,0)",
        "F2": "=IF(E2>0,MAX(B2:E2),0)",
        "G2": "=SUM(B2:C2)",
    }
    results = calculate_sheet(values)
    assert results["D2"].value == "120"
    assert results["E2"].value == "120"
    assert results["F2"].value == "120"
    assert results["G2"].value == "120"
    assert results["D2"].dependencies == ("B2", "C2")


def test_formula_detects_cycle_division_by_zero_and_invalid_input() -> None:
    results = calculate_sheet({"A1": "=B1", "B1": "=A1", "C1": "=1/0"})
    assert results["A1"].error == "CIRCULAR_REFERENCE"
    assert results["B1"].error == "CIRCULAR_REFERENCE"
    assert results["C1"].error == "DIVISION_BY_ZERO"
    assert FormulaEvaluator(lambda _: None).evaluate("=__import__('os')").error == "UNSUPPORTED_FUNCTION"
    assert FormulaEvaluator(lambda _: None).evaluate("=A1.__class__").error == "UNSUPPORTED_EXPRESSION"


def test_formula_resource_limits_are_fail_closed() -> None:
    result = FormulaEvaluator(lambda _: "1").evaluate("=SUM(A1:A1001)")
    assert result.error == "DEPENDENCY_LIMIT"
