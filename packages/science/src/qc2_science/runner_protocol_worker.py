"""Isolated interpreter for the bounded Runner Protocol JSON expression language.

This file intentionally does not import application, model, broker, network, or filesystem APIs.
Only declarative JSON expressions are accepted; protocol-supplied Python is never imported or run.
"""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

_MAX_REQUEST_BYTES = 65_536
_MAX_NODES = 128
_MAX_DEPTH = 32
_MAX_ITEMS = 32
_SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,95}$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]{0,35})(?:\.[0-9]{1,12})?$")
_BINARY = frozenset(
    {"add", "subtract", "multiply", "divide", "gt", "gte", "lt", "lte", "eq"}
)
_ALLOWED = _BINARY | frozenset({"input", "parameter", "decimal", "abs", "not", "and", "or"})


class _WorkerFault(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _set_resource_limits() -> bool:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
    except (ImportError, OSError, ValueError):
        return False
    return True


def _decimal(value: Any) -> Decimal:
    if not isinstance(value, str) or len(value) > 50 or not _DECIMAL.fullmatch(value):
        raise _WorkerFault("INVALID_DECIMAL")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise _WorkerFault("INVALID_DECIMAL") from exc
    if not result.is_finite():
        raise _WorkerFault("INVALID_DECIMAL")
    return result


def _named_values(value: Any) -> dict[str, Decimal]:
    if not isinstance(value, dict) or len(value) > _MAX_ITEMS:
        raise _WorkerFault("INVALID_REQUEST")
    result: dict[str, Decimal] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not _SLUG.fullmatch(key):
            raise _WorkerFault("INVALID_REQUEST")
        result[key] = _decimal(item)
    return result


def _evaluate(
    node: Any,
    inputs: dict[str, Decimal],
    parameters: dict[str, Decimal],
    *,
    max_steps: int,
) -> tuple[bool | Decimal, int]:
    steps = 0

    def visit(current: Any, depth: int) -> bool | Decimal:
        nonlocal steps
        steps += 1
        if steps > max_steps or steps > _MAX_NODES or depth > _MAX_DEPTH:
            raise _WorkerFault("RESOURCE_LIMIT_EXCEEDED")
        if not isinstance(current, dict) or not isinstance(current.get("op"), str):
            raise _WorkerFault("INVALID_EXPRESSION")

        op = current["op"]
        if op not in _ALLOWED:
            raise _WorkerFault("UNSUPPORTED_EXPRESSION")

        if op in {"input", "parameter"}:
            if set(current) != {"op", "name"}:
                raise _WorkerFault("INVALID_EXPRESSION")
            name = current["name"]
            if not isinstance(name, str) or not _SLUG.fullmatch(name):
                raise _WorkerFault("INVALID_EXPRESSION")
            values = inputs if op == "input" else parameters
            if name not in values:
                raise _WorkerFault("UNBOUND_NAME")
            return values[name]

        if op == "decimal":
            if set(current) != {"op", "value"}:
                raise _WorkerFault("INVALID_EXPRESSION")
            return _decimal(current["value"])

        if op in {"abs", "not"}:
            if set(current) != {"op", "value"}:
                raise _WorkerFault("INVALID_EXPRESSION")
            operand = visit(current["value"], depth + 1)
            if op == "abs":
                if not isinstance(operand, Decimal):
                    raise _WorkerFault("TYPE_MISMATCH")
                return abs(operand)
            if type(operand) is not bool:
                raise _WorkerFault("TYPE_MISMATCH")
            return not operand

        if op in {"and", "or"}:
            if set(current) != {"op", "items"}:
                raise _WorkerFault("INVALID_EXPRESSION")
            items = current["items"]
            if not isinstance(items, list) or not items or len(items) > _MAX_ITEMS:
                raise _WorkerFault("INVALID_EXPRESSION")
            for item in items:
                result = visit(item, depth + 1)
                if type(result) is not bool:
                    raise _WorkerFault("TYPE_MISMATCH")
                if op == "and" and not result:
                    return False
                if op == "or" and result:
                    return True
            return op == "and"

        if set(current) != {"op", "left", "right"}:
            raise _WorkerFault("INVALID_EXPRESSION")
        left = visit(current["left"], depth + 1)
        right = visit(current["right"], depth + 1)
        if not isinstance(left, Decimal) or not isinstance(right, Decimal):
            raise _WorkerFault("TYPE_MISMATCH")

        try:
            with localcontext() as context:
                context.prec = 48
                if op == "add":
                    return left + right
                if op == "subtract":
                    return left - right
                if op == "multiply":
                    return left * right
                if op == "divide":
                    if right == 0:
                        raise _WorkerFault("ARITHMETIC_ERROR")
                    return left / right
        except (ArithmeticError, InvalidOperation) as exc:
            raise _WorkerFault("ARITHMETIC_ERROR") from exc

        if op == "gt":
            return left > right
        if op == "gte":
            return left >= right
        if op == "lt":
            return left < right
        if op == "lte":
            return left <= right
        if op == "eq":
            return left == right
        raise _WorkerFault("UNSUPPORTED_EXPRESSION")

    result = visit(node, 1)
    return result, steps


def _run(request: Any) -> dict[str, Any]:
    if not _set_resource_limits():
        return {"ok": False, "code": "RESOURCE_LIMITS_UNAVAILABLE"}
    if not isinstance(request, dict) or set(request) != {
        "expression",
        "inputs",
        "parameters",
        "max_steps",
    }:
        return {"ok": False, "code": "INVALID_REQUEST"}
    max_steps = request["max_steps"]
    if type(max_steps) is not int or not 1 <= max_steps <= _MAX_NODES:
        return {"ok": False, "code": "INVALID_REQUEST"}
    try:
        inputs = _named_values(request["inputs"])
        parameters = _named_values(request["parameters"])
        result, steps = _evaluate(
            request["expression"], inputs, parameters, max_steps=max_steps
        )
        if type(result) is not bool:
            return {"ok": False, "code": "NON_BOOLEAN_RESULT", "steps": steps}
        return {"ok": True, "matched": result, "steps": steps}
    except _WorkerFault as exc:
        return {"ok": False, "code": exc.code}


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1)
        if len(raw) > _MAX_REQUEST_BYTES:
            response = {"ok": False, "code": "RESOURCE_LIMIT_EXCEEDED"}
        else:
            try:
                request = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                response = {"ok": False, "code": "INVALID_REQUEST"}
            else:
                response = _run(request)
    except BaseException:
        response = {"ok": False, "code": "WORKER_FAILURE"}
    sys.stdout.write(json.dumps(response, separators=(",", ":"), sort_keys=True))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
