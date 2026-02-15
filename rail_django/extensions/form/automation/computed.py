"""
Computed field utilities for Form API.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict


_TEMPLATE_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_.]+)\s*}}")


def _resolve_path(values: Dict[str, Any], path: str | None) -> Any:
    if not path:
        return None
    cursor: Any = values
    for token in str(path).split("."):
        if not token:
            continue
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(token)
    return cursor


def _evaluate_ast(node: ast.AST, values: Dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _evaluate_ast(node.body, values)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return values.get(node.id)
    if isinstance(node, ast.UnaryOp):
        operand = _evaluate_ast(node.operand, values)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.Not):
            return not operand
        raise ValueError("Unsupported unary operator")
    if isinstance(node, ast.BinOp):
        left = _evaluate_ast(node.left, values)
        right = _evaluate_ast(node.right, values)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return left**right
        raise ValueError("Unsupported binary operator")
    if isinstance(node, ast.BoolOp):
        items = [_evaluate_ast(item, values) for item in node.values]
        if isinstance(node.op, ast.And):
            return all(items)
        if isinstance(node.op, ast.Or):
            return any(items)
        raise ValueError("Unsupported boolean operator")
    if isinstance(node, ast.Compare):
        left = _evaluate_ast(node.left, values)
        result = True
        for op, comparator in zip(node.ops, node.comparators):
            right = _evaluate_ast(comparator, values)
            if isinstance(op, ast.Eq):
                result = result and (left == right)
            elif isinstance(op, ast.NotEq):
                result = result and (left != right)
            elif isinstance(op, ast.Gt):
                result = result and (left > right)
            elif isinstance(op, ast.GtE):
                result = result and (left >= right)
            elif isinstance(op, ast.Lt):
                result = result and (left < right)
            elif isinstance(op, ast.LtE):
                result = result and (left <= right)
            else:
                raise ValueError("Unsupported comparison operator")
            left = right
        return result
    raise ValueError("Unsupported expression node")


def compute_field(expression: str, values: Dict[str, Any]) -> Any:
    expr = str(expression or "").strip()
    if not expr:
        return None

    # If the expression is a plain dotted path, return the referenced value.
    if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.]*", expr):
        return _resolve_path(values, expr)

    # Handle string templates such as "{{firstName}} {{lastName}}".
    if "{{" in expr and "}}" in expr:
        return _TEMPLATE_PATTERN.sub(
            lambda match: str(_resolve_path(values, match.group(1)) or ""),
            expr,
        ).strip()

    # Safe subset evaluator for arithmetic and comparison expressions.
    try:
        parsed = ast.parse(expr, mode="eval")
        return _evaluate_ast(parsed, values)
    except Exception:
        return None
