"""Safe formula specs for machine-generated weak Kalshi signals."""

from __future__ import annotations

import ast
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any


class FormulaSecurityError(ValueError):
    """Raised when a formula attempts to leave the whitelisted expression DSL."""


@dataclass(frozen=True, slots=True)
class SignalFormulaSpec:
    name: str
    formula: str
    family_id: str
    output: str = "feature"
    input_fields: tuple[str, ...] = ()
    multiple_testing_family_id: str | None = None
    model_id: str | None = None
    version: str = "1.0"
    description: str = ""
    retired_signal_keys: tuple[str, ...] = field(default_factory=tuple)

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["input_fields"] = list(self.input_fields)
        row["retired_signal_keys"] = list(self.retired_signal_keys)
        return row


def validate_signal_formula_spec(spec: SignalFormulaSpec) -> list[str]:
    errors: list[str] = []
    if not spec.name.strip():
        errors.append("name is required")
    if spec.output not in {"feature", "score", "edge_filter", "probability_candidate"}:
        errors.append("output must be feature, score, edge_filter, or probability_candidate")
    if not spec.family_id.strip():
        errors.append("family_id is required")
    try:
        tree = ast.parse(spec.formula, mode="eval")
        SafeFormulaEvaluator({field: 1.0 for field in spec.input_fields}).validate(tree)
    except (FormulaSecurityError, SyntaxError, ValueError) as exc:
        errors.append(str(exc))
    return errors


def evaluate_formula(formula: str, row: Mapping[str, Any]) -> float:
    tree = ast.parse(formula, mode="eval")
    return SafeFormulaEvaluator(row).evaluate(tree)


class SafeFormulaEvaluator:
    def __init__(self, row: Mapping[str, Any]) -> None:
        self.row = row
        self.operators: dict[str, Callable[..., float]] = {
            "Abs": abs,
            "Clip": _clip,
            "Greater": lambda left, right: 1.0 if left > right else 0.0,
            "IfThenElse": lambda condition, left, right: left if bool(condition) else right,
            "Max": max,
            "Min": min,
            "Sqrt": math.sqrt,
        }

    def validate(self, tree: ast.Expression) -> None:
        self._eval(tree.body)

    def evaluate(self, tree: ast.Expression) -> float:
        value = self._eval(tree.body)
        if not math.isfinite(value):
            raise ValueError("formula returned non-finite value")
        return float(value)

    def _eval(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool | int | float):
                return float(node.value)
            raise FormulaSecurityError("only numeric and boolean constants are allowed")
        if isinstance(node, ast.Name):
            if node.id not in self.row:
                raise FormulaSecurityError(f"unknown field or operator: {node.id}")
            return _numeric_value(self.row[node.id], node.id)
        if isinstance(node, ast.Call):
            return self._eval_call(node)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
            value = self._eval(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            return self._eval_binop(node)
        if isinstance(node, ast.Compare):
            return self._eval_compare(node)
        raise FormulaSecurityError(f"unsupported expression: {node.__class__.__name__}")

    def _eval_call(self, node: ast.Call) -> float:
        if not isinstance(node.func, ast.Name):
            raise FormulaSecurityError("only direct whitelisted function calls are allowed")
        name = node.func.id
        if name not in self.operators:
            raise FormulaSecurityError(f"operator is not allowed: {name}")
        if node.keywords:
            raise FormulaSecurityError("keyword arguments are not allowed")
        args = [self._eval(arg) for arg in node.args]
        return float(self.operators[name](*args))

    def _eval_binop(self, node: ast.BinOp) -> float:
        left = self._eval(node.left)
        right = self._eval(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            return left**right
        raise FormulaSecurityError(f"binary operator is not allowed: {node.op.__class__.__name__}")

    def _eval_compare(self, node: ast.Compare) -> float:
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise FormulaSecurityError("chained comparisons are not allowed")
        left = self._eval(node.left)
        right = self._eval(node.comparators[0])
        op = node.ops[0]
        if isinstance(op, ast.Gt):
            return 1.0 if left > right else 0.0
        if isinstance(op, ast.GtE):
            return 1.0 if left >= right else 0.0
        if isinstance(op, ast.Lt):
            return 1.0 if left < right else 0.0
        if isinstance(op, ast.LtE):
            return 1.0 if left <= right else 0.0
        if isinstance(op, ast.Eq):
            return 1.0 if left == right else 0.0
        if isinstance(op, ast.NotEq):
            return 1.0 if left != right else 0.0
        raise FormulaSecurityError(f"comparison operator is not allowed: {op.__class__.__name__}")


def build_signal_formula_registry(
    specs: Sequence[SignalFormulaSpec],
    *,
    retired_signal_keys: set[str] | None = None,
) -> dict[str, Any]:
    retired = retired_signal_keys or set()
    rows: list[dict[str, Any]] = []
    blocked = 0
    for spec in specs:
        signal_key = signal_formula_key(spec)
        errors = validate_signal_formula_spec(spec)
        if signal_key in retired:
            errors.append("signal formula is retired")
        status = "formula_ready_for_falsification" if not errors else "formula_blocked"
        blocked += int(bool(errors))
        rows.append(
            {
                **spec.to_row(),
                "signal_formula_key": signal_key,
                "status": status,
                "errors": errors,
                "counts_toward_multiple_testing": status == "formula_ready_for_falsification",
            }
        )
    tested = sum(1 for row in rows if row["counts_toward_multiple_testing"])
    return {
        "schema_version": 1,
        "status": "signal_formula_registry_ready" if rows else "signal_formula_registry_empty",
        "research_only": True,
        "execution_enabled": False,
        "market_execution": False,
        "account_or_order_paths": False,
        "summary": {
            "formula_count": len(rows),
            "ready_formula_count": tested,
            "blocked_formula_count": blocked,
            "multiple_testing_hypothesis_count": tested,
        },
        "formulas": rows,
        "safety": {
            "research_only": True,
            "execution_enabled": False,
            "arbitrary_python_execution": False,
            "market_execution": False,
            "account_or_order_paths": False,
        },
    }


def signal_formula_key(spec: SignalFormulaSpec) -> str:
    return "|".join(
        [
            spec.family_id,
            spec.model_id or "formula",
            spec.multiple_testing_family_id or spec.family_id,
            spec.name,
            spec.version,
        ]
    )


def default_signal_formula_specs() -> tuple[SignalFormulaSpec, ...]:
    return (
        SignalFormulaSpec(
            name="model_market_probability_gap",
            formula="model_probability - market_probability",
            family_id="generic",
            output="score",
            input_fields=("model_probability", "market_probability"),
            multiple_testing_family_id="generic_probability_decay",
            description="Generic weak edge score from model probability minus crowd-implied probability.",
        ),
        SignalFormulaSpec(
            name="clipped_positive_gap",
            formula="Max(0, Clip(model_probability - market_probability, -1, 1))",
            family_id="generic",
            output="edge_filter",
            input_fields=("model_probability", "market_probability"),
            multiple_testing_family_id="generic_probability_decay",
            description="Positive-only clipped probability gap; still requires FDR before use.",
        ),
    )


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _numeric_value(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"field {name!r} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"field {name!r} must be finite")
    return number
