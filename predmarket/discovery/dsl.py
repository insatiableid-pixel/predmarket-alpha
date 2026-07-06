"""Safe vectorized signal expression DSL.

The DSL parses a narrow Python-expression subset with ``ast`` and evaluates it
directly. It never calls ``eval`` or imports user code.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np


class DSLValidationError(ValueError):
    """Raised when a signal expression violates the safe DSL contract."""


FORBIDDEN_FEATURES = {
    "outcome",
    "resolved_ts",
    "resolution_ts",
    "target",
    "label",
    "p_model",
    "model_prob",
}

ALLOWED_FUNCTIONS = {
    "abs",
    "clip",
    "interaction",
    "lag",
    "log1p",
    "momentum",
    "rank",
    "sigmoid",
    "zscore",
}


class SafeSignalDSL:
    """Parse and evaluate leak-aware signal expressions over row dictionaries."""

    def __init__(self, feature_catalog: Iterable[str]):
        self.feature_catalog = {str(name) for name in feature_catalog}

    @staticmethod
    def discover_feature_catalog(rows: Sequence[dict[str, Any]]) -> list[str]:
        names: set[str] = set()
        for row in rows:
            for key, value in row.items():
                if key.endswith("_available_ts") or key in {
                    "feature_available_ts",
                    "_feature_available_ts",
                }:
                    continue
                if SafeSignalDSL._is_forbidden_feature(key):
                    continue
                if isinstance(value, bool) or isinstance(value, (int, float)):
                    if math.isfinite(float(value)):
                        names.add(str(key))
        return sorted(names)

    @staticmethod
    def _is_forbidden_feature(name: str) -> bool:
        lowered = name.lower()
        return (
            lowered in FORBIDDEN_FEATURES
            or "future" in lowered
            or lowered.startswith("__")
            or lowered.endswith("_future_ts")
            or lowered.startswith("resolved")
        )

    def canonicalize(self, expression: str) -> str:
        tree = self._parse(expression)
        return ast.dump(tree, annotate_fields=True, include_attributes=False)

    def complexity(self, expression: str) -> int:
        tree = self._parse(expression)
        return sum(1 for _ in ast.walk(tree))

    def referenced_features(self, expression: str) -> set[str]:
        tree = self._parse(expression)
        names = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id not in ALLOWED_FUNCTIONS
        }
        for name in names:
            if self._is_forbidden_feature(name):
                raise DSLValidationError(f"forbidden feature reference: {name}")
            if name not in self.feature_catalog:
                raise DSLValidationError(f"unknown feature reference: {name}")
        return names

    def validate(self, expression: str, rows: Sequence[dict[str, Any]]) -> set[str]:
        features = self.referenced_features(expression)
        for feature in features:
            support = 0
            for row in rows:
                if feature not in row:
                    raise DSLValidationError(f"feature unavailable in row: {feature}")
                value = row.get(feature)
                if not isinstance(value, (int, float, bool)) or not math.isfinite(float(value)):
                    raise DSLValidationError(f"non-numeric feature value: {feature}")
                self._validate_feature_as_of(feature, row)
                support += 1
            if support == 0:
                raise DSLValidationError(f"feature has no support: {feature}")
        return features

    def evaluate(self, expression: str, rows: Sequence[dict[str, Any]]) -> list[float]:
        if not rows:
            return []
        self.validate(expression, rows)
        tree = self._parse(expression)
        values = self._eval_node(tree.body, rows)
        arr = np.asarray(values, dtype=float)
        if arr.shape != (len(rows),):
            raise DSLValidationError("expression did not produce one value per row")
        if not np.all(np.isfinite(arr)):
            raise DSLValidationError("expression produced non-finite values")
        return [float(value) for value in arr]

    def _parse(self, expression: str) -> ast.Expression:
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise DSLValidationError(f"invalid signal expression: {exc}") from exc
        for node in ast.walk(tree):
            if isinstance(
                node,
                (
                    ast.Attribute,
                    ast.Subscript,
                    ast.Lambda,
                    ast.Dict,
                    ast.List,
                    ast.Tuple,
                    ast.Set,
                    ast.ListComp,
                    ast.SetComp,
                    ast.DictComp,
                    ast.GeneratorExp,
                    ast.Compare,
                    ast.BoolOp,
                    ast.IfExp,
                    ast.NamedExpr,
                    ast.Await,
                    ast.Yield,
                    ast.YieldFrom,
                ),
            ):
                raise DSLValidationError(f"unsupported syntax: {type(node).__name__}")
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS:
                    raise DSLValidationError("unsupported function call")
                if node.keywords:
                    raise DSLValidationError("keyword arguments are not supported")
            if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
                raise DSLValidationError("only numeric constants are supported")
        return tree

    def _eval_node(self, node: ast.AST, rows: Sequence[dict[str, Any]]) -> np.ndarray:
        if isinstance(node, ast.Constant):
            return np.full(len(rows), float(node.value), dtype=float)

        if isinstance(node, ast.Name):
            if node.id in ALLOWED_FUNCTIONS:
                raise DSLValidationError(f"function name used as value: {node.id}")
            return np.asarray([float(row[node.id]) for row in rows], dtype=float)

        if isinstance(node, ast.UnaryOp):
            value = self._eval_node(node.operand, rows)
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return value
            raise DSLValidationError("unsupported unary operator")

        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, rows)
            right = self._eval_node(node.right, rows)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / np.where(np.abs(right) < 1e-12, np.nan, right)
            if isinstance(node.op, ast.Pow):
                return np.power(left, np.clip(right, -8.0, 8.0))
            raise DSLValidationError("unsupported binary operator")

        if isinstance(node, ast.Call):
            args = [self._eval_node(arg, rows) for arg in node.args]
            return self._apply_function(node.func.id, args, len(rows))

        raise DSLValidationError(f"unsupported syntax: {type(node).__name__}")

    def _apply_function(self, name: str, args: list[np.ndarray], n_rows: int) -> np.ndarray:
        if name == "abs":
            self._check_arity(name, args, 1)
            return np.abs(args[0])
        if name == "clip":
            self._check_arity(name, args, 3)
            return np.clip(args[0], args[1], args[2])
        if name == "interaction":
            self._check_arity(name, args, 2)
            return args[0] * args[1]
        if name == "lag":
            if len(args) not in {1, 2}:
                raise DSLValidationError("lag expects one or two arguments")
            periods = int(round(float(args[1][0]))) if len(args) == 2 else 1
            return self._lag(args[0], periods)
        if name == "log1p":
            self._check_arity(name, args, 1)
            return np.log1p(np.maximum(args[0], -0.999999))
        if name == "momentum":
            if len(args) not in {1, 2}:
                raise DSLValidationError("momentum expects one or two arguments")
            periods = int(round(float(args[1][0]))) if len(args) == 2 else 1
            return args[0] - self._lag(args[0], periods)
        if name == "rank":
            self._check_arity(name, args, 1)
            return self._rank(args[0])
        if name == "sigmoid":
            self._check_arity(name, args, 1)
            return 1.0 / (1.0 + np.exp(-np.clip(args[0], -40.0, 40.0)))
        if name == "zscore":
            self._check_arity(name, args, 1)
            return self._zscore(args[0])
        raise DSLValidationError(f"unsupported function: {name}")

    @staticmethod
    def _check_arity(name: str, args: list[np.ndarray], expected: int) -> None:
        if len(args) != expected:
            raise DSLValidationError(f"{name} expects {expected} arguments")

    @staticmethod
    def _lag(values: np.ndarray, periods: int) -> np.ndarray:
        if periods < 1:
            raise DSLValidationError("lag periods must be positive")
        periods = min(periods, max(len(values) - 1, 1))
        lagged = np.empty_like(values, dtype=float)
        lagged[:periods] = values[0]
        lagged[periods:] = values[:-periods]
        return lagged

    @staticmethod
    def _rank(values: np.ndarray) -> np.ndarray:
        if len(values) == 1:
            return np.array([0.5], dtype=float)
        order = np.argsort(values, kind="mergesort")
        ranks = np.empty(len(values), dtype=float)
        ranks[order] = np.arange(len(values), dtype=float)
        return ranks / max(len(values) - 1, 1)

    @staticmethod
    def _zscore(values: np.ndarray) -> np.ndarray:
        sd = float(np.std(values))
        if sd <= 1e-12:
            return np.zeros(len(values), dtype=float)
        return (values - float(np.mean(values))) / sd

    @staticmethod
    def _validate_feature_as_of(feature: str, row: dict[str, Any]) -> None:
        as_of_ts = float(row.get("as_of_ts", 0.0))
        direct_key = f"{feature}_available_ts"
        available_ts = None
        if direct_key in row:
            available_ts = row[direct_key]
        feature_available_ts = row.get("feature_available_ts") or row.get("_feature_available_ts")
        if isinstance(feature_available_ts, dict) and feature in feature_available_ts:
            available_ts = feature_available_ts[feature]
        if available_ts is not None and float(available_ts) > as_of_ts:
            raise DSLValidationError(f"feature unavailable at as_of_ts: {feature}")
