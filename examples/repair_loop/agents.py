"""Deterministic rule-based repair stubs (interface-only demonstrations).

The standardized arm's single agent (`StubRepairer`) consumes ONLY the
common-JSON feedback dict + source text - no z3 sexpr parsing, no parser
internals. It targets named corpus families:

- wrong-constant refutations (`assert a + a == K;` with a pinning `requires
  a == N;`): the I6 valuation supplies the witness, the asserted constant is
  replaced by the witnessed value (witness `a=N` => `K := 2*N` for
  `a + a == K`) - a provable claim.
- out-of-subset programs (the `parse-*` corpus families): the I7 kind + loc +
  native message locate the offending line; the repair rewrites it into
  `assume` form (e.g. `call f();` -> `assume true;`, `if` statements ->
  assume-guarded form) and de-scopes the program's claims. Success by
  de-scoping is an interface demonstration, not real repair power.

The native arm's agents (`NativeZ3Repairer`, `NativeBoogieRepairer`) are the
bespoke per-backend equivalents: they parse raw z3 model sexprs / raw parser
error text instead of the common JSON.
"""

from __future__ import annotations

import re
from typing import Any


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _eval_linear(expr: str, values: dict[str, int]) -> int | None:
    """Evaluate `t1 + t2`, `t1 * t2`, or a bare name under the witness values."""
    expr = expr.strip()
    if re.fullmatch(r"-?\d+", expr):
        return int(expr)
    if expr in values:
        return values[expr]
    patterns = [
        (r"(.+?)\s*\+\s*(.+)", lambda a, b: a + b),
        (r"(.+?)\s*\*\s*(.+)", lambda a, b: a * b),
    ]
    for pattern, op in patterns:
        m = re.fullmatch(pattern, expr)
        if m:
            a = _eval_linear(m.group(1), values)
            b = _eval_linear(m.group(2), values)
            if a is not None and b is not None:
                return op(a, b)
    return None


class LiteralAdjusterRepairer:
    """Wrong-constant refutation repairer: consumes the I6 valuation only."""

    def repair(self, source: str, feedback: dict[str, Any]) -> str | None:
        for cex in feedback.get("counterexamples", []):
            if cex.get("kind") != "valuation":
                continue
            values: dict[str, int] = {}
            for name, term in (cex.get("valuation") or {}).items():
                if term.get("op") == "const" and term.get("args"):
                    scalar = term["args"][0]
                    if isinstance(scalar, int):
                        values[name] = scalar
            if not values:
                continue
            for m in re.finditer(r"assert\s+(.+?)\s*==\s*(-?\d+)\s*;", source):
                witnessed = _eval_linear(m.group(1), values)
                if witnessed is None or int(m.group(2)) == witnessed:
                    continue
                start, end = m.span(2)
                return source[:start] + str(witnessed) + source[end:]
        return None


class SubsetRepairer:
    """Out-of-subset repairer: consumes the I7 kind + loc + native message.

    One edit per iteration; the loop re-imports and re-reports until the
    program is inside the accepted subset with no remaining claims.
    """

    def repair(self, source: str, feedback: dict[str, Any]) -> str | None:
        for diag in feedback.get("diagnostics", []):
            if diag.get("kind") != "parse":
                continue
            message = diag.get("native_message") or ""
            loc = diag.get("loc") or {}
            line_no = loc.get("line")
            if line_no is None:
                repaired = self._repair_unlocated(source, message)
            else:
                repaired = self._repair_located(source, line_no - 1)
            if repaired is not None:
                return repaired
        return None

    def _repair_located(self, source: str, idx: int) -> str | None:
        lines = source.splitlines()
        if not (0 <= idx < len(lines)):
            return None
        line = lines[idx]
        stripped = line.strip()
        if stripped.startswith("call "):
            lines[idx] = _indent(line) + "assume true;"
        elif stripped.startswith("if ") and stripped.endswith("{"):
            lines[idx] = _indent(line) + f"assume {stripped[3:-1].strip()};"
            for j in range(idx + 1, len(lines)):
                if lines[j].strip() == "}":
                    del lines[j]
                    break
        elif stripped.startswith("procedure ") and ":" in stripped:
            m = re.search(r"\((\w+):\s*([^)]+)\)", line)
            if m is None or re.fullmatch(r"int|bool|real", m.group(2).strip()):
                return None
            name = m.group(1)
            lines[idx] = line[: m.start(2)] + "int" + line[m.end(2) :]
            for j, other in enumerate(lines):
                if f"|{name}|" in other:
                    lines[j] = _indent(other) + "assume true;"
        else:
            return None
        return _descope_asserts("\n".join(lines))

    def _repair_unlocated(self, source: str, message: str) -> str | None:
        lines = source.splitlines()
        if "uninterpreted function" in message:
            for i, line in enumerate(lines):
                if line.strip().startswith("function "):
                    del lines[i]
                    return "\n".join(lines) + "\n"
            return None
        m = re.search(r"unknown function '(\w+)'", message)
        if m:
            for i, line in enumerate(lines):
                if re.search(rf"\b{m.group(1)}\s*\(", line) and "function" not in line:
                    lines[i] = _indent(line) + "assume true;"
                    return _descope_asserts("\n".join(lines))
        return None


def _descope_asserts(source: str) -> str:
    """De-scope every remaining claim: `assert E;` -> `assume E;`."""
    out = [re.sub(r"\bassert\b", "assume", line) for line in source.splitlines()]
    return "\n".join(out) + "\n"


class StubRepairer:
    """The standardized arm's single agent: one object, every target family.

    Dispatches on the I7/I6 kinds inside the common JSON - the same object
    repairs z3 refutations and Boogie-parser failures unchanged.
    """

    def __init__(self) -> None:
        self._literal = LiteralAdjusterRepairer()
        self._subset = SubsetRepairer()

    def repair(self, source: str, feedback: dict[str, Any]) -> str | None:
        return self._literal.repair(source, feedback) or self._subset.repair(source, feedback)


class NativeZ3Repairer:
    """Bespoke z3-path agent: regex-parses the raw SMT-LIB model sexprs."""

    def repair(self, source: str, feedback: dict[str, Any]) -> str | None:
        model = feedback.get("z3_model")
        if not model:
            return None
        values: dict[str, int] = {}
        # raw sexprs wrap values across lines: `(define-fun a () Int\n  1)`
        for name, value in re.findall(r"\(define-fun (\w+) \(\) Int\s+(-?\d+)\)", model):
            values[name] = int(value)
        if not values:
            return None
        for m in re.finditer(r"assert\s+(.+?)\s*==\s*(-?\d+)\s*;", source):
            witnessed = _eval_linear(m.group(1), values)
            if witnessed is None or int(m.group(2)) == witnessed:
                continue
            start, end = m.span(2)
            return source[:start] + str(witnessed) + source[end:]
        return None


class NativeBoogieRepairer:
    """Bespoke parser-path agent: works from raw parser error text."""

    def repair(self, source: str, feedback: dict[str, Any]) -> str | None:
        for error in feedback.get("boogie_errors", []):
            message = error.get("message") or ""
            lines = source.splitlines()

            # definition-less/uninterpreted functions: the raw error names the
            # function but carries no verbatim line - regex the message
            m = re.search(r"uninterpreted function '(\w+)'", message)
            if m is not None:
                for i, line in enumerate(lines):
                    if line.strip().startswith(f"function {m.group(1)}"):
                        del lines[i]
                        return "\n".join(lines) + "\n"
                continue
            m = re.search(r"unknown function '(\w+)'", message)
            if m is not None:
                for i, line in enumerate(lines):
                    if re.search(rf"\b{m.group(1)}\s*\(", line) and "function" not in line:
                        lines[i] = _indent(line) + "assume true;"
                        return _descope_asserts("\n".join(lines))
                continue

            # everything else: locate the offending line via the verbatim text
            verbatim = message.splitlines()[-1].strip() if message else ""
            idx = next(
                (i for i, line in enumerate(lines) if verbatim and line.strip() == verbatim),
                None,
            )
            if idx is None:
                continue
            line = lines[idx]
            stripped = line.strip()
            if stripped.startswith("call "):
                lines[idx] = _indent(line) + "assume true;"
            elif stripped.startswith("if ") and stripped.endswith("{"):
                lines[idx] = _indent(line) + f"assume {stripped[3:-1].strip()};"
                for j in range(idx + 1, len(lines)):
                    if lines[j].strip() == "}":
                        del lines[j]
                        break
            elif stripped.startswith("procedure "):
                m = re.search(r"\((\w+):\s*([^)]+)\)", line)
                if m is None or re.fullmatch(r"int|bool|real", m.group(2).strip()):
                    continue
                name = m.group(1)
                lines[idx] = line[: m.start(2)] + "int" + line[m.end(2) :]
                for j, other in enumerate(lines):
                    if f"|{name}|" in other:
                        lines[j] = _indent(other) + "assume true;"
            else:
                continue
            return _descope_asserts("\n".join(lines))
        return None
