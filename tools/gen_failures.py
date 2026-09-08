"""Deterministic cross-tool failure corpus generator (M2 P2 deliverable).

Emits `corpora/failures/smt/*.bpl` (z3-refuted / unknown / timeout programs)
and `corpora/failures/parse/*.bpl` (out-of-M1-subset programs), plus
`corpora/failures/expected.json` mapping entry (posix relative path) ->
`{file, backend, family, expected}`.

Required backends are z3 + boogie-parser (both always available in-repo); the
>=200 required-backend entries are the M2 exit-criterion corpus. The cvc5 arm
re-checks the `smt/*` entries through `Cvc5Backend` when `UVIL_CVC5` is set -
by construction verdicts for the designed refutation families must agree, so
no cvc5-specific entries are generated (generation stays deterministic with or
without cvc5 installed).

Verdict provenance mirrors tools/gen_corpus.py: refutation families are
"designed" (the negation is satisfiable by construction; the generator fails
if z3 disagrees) and unknown/timeout families record exactly what the pinned
z3 observed. Regeneration is idempotent and deterministic (fixed seed, stale
files removed, output committed).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from uvil.adapters.boogie.lower import import_module  # noqa: E402
from uvil.adapters.smt.backends import verdict_status  # noqa: E402
from uvil.check.core import SmtBackend  # noqa: E402

FAILURES_DIR = REPO_ROOT / "corpora" / "failures"
SMT_DIR = FAILURES_DIR / "smt"
PARSE_DIR = FAILURES_DIR / "parse"
EXPECTED_PATH = FAILURES_DIR / "expected.json"

SEED = 20260908
DEFAULT_BUDGET_MS = 2000
UNKNOWN_BUDGET_MS = 1000
TIMEOUT_BUDGET_MS = 300
TARGET_REQUIRED = 200

# family counts (required-backend entries): 60+40+10+4 smt + 90 parse = 204
COUNTS = {
    "refuted-linear": 60,
    "refuted-bound": 40,
    "unknown-nonlinear": 10,
    "timeout-fermat": 4,
    "parse-if": 20,
    "parse-call": 20,
    "parse-uninterp": 15,
    "parse-type": 20,
    "parse-stray": 15,
}
TIMEOUT_FAMILY = "timeout-fermat"


@dataclass(frozen=True)
class FailureProgram:
    name: str  # file stem
    subdir: str  # "smt" | "parse"
    source: str
    family: str
    backend: str  # "z3" | "boogie-parser"
    expected: str | None  # designed verdict/I7 kind, or None to observe with z3
    budget_ms: int = DEFAULT_BUDGET_MS


def build_failure_programs() -> list[FailureProgram]:
    """Families x deterministic instantiations (fixed seed, varying literals)."""
    programs: list[FailureProgram] = []

    # -- smt: refuted-linear (negation of a + a == 3 * a satisfiable for a >= N)
    for i in range(COUNTS["refuted-linear"]):
        n = i + 1
        programs.append(
            FailureProgram(
                f"gen_refuted_linear_{i:03d}",
                "smt",
                (
                    f"procedure p_ref_lin_{i}(a: int)\n"
                    f"  requires a >= {n}\n"
                    f"{{\n  assert a + a == 3 * a;\n}}\n"
                ),
                "refuted-linear",
                "z3",
                "refuted",
            )
        )

    # -- smt: refuted-bound (a witness below the bound always exists)
    for i in range(COUNTS["refuted-bound"]):
        n = i + 3
        programs.append(
            FailureProgram(
                f"gen_refuted_bound_{i:03d}",
                "smt",
                (
                    f"procedure p_ref_bnd_{i}(x: int)\n"
                    f"  requires 0 <= x && x <= {n}\n"
                    f"{{\n  assert x * x >= {n + 1};\n}}\n"
                ),
                "refuted-bound",
                "z3",
                "refuted",
            )
        )

    # -- smt: unknown-nonlinear (observed). Valid-but-hard integer goals (the
    # only consecutive perfect powers are 0 and 1, so the assertion is valid);
    # the pinned z3 cannot settle them within the 1000ms budget. Note: this
    # backend deterministically reports budget exhaustion as `timeout` (the
    # reason-unknown string contains "timeout"); a plain `unknown` verdict is
    # recorded the same way whenever the backend produces one. The corpus
    # invariant under test is: such obligations never discharge - they stay
    # open/timeout with a matching I7.
    for i in range(COUNTS["unknown-nonlinear"]):
        a, b = 7 + i, 8 + i
        programs.append(
            FailureProgram(
                f"gen_unknown_nonlinear_{i:03d}",
                "smt",
                (
                    f"procedure p_unknl_{i}(x: int, y: int)\n"
                    f"  requires x >= {a} && y >= {b}\n"
                    f"{{\n  assert x * x * x != y * y * y - 1;\n}}\n"
                ),
                "unknown-nonlinear",
                "z3",
                None,
                budget_ms=UNKNOWN_BUDGET_MS,
            )
        )

    # -- smt: timeout-fermat (valid, never decidable fast; slow marker)
    for i in range(COUNTS["timeout-fermat"]):
        k = i + 1
        programs.append(
            FailureProgram(
                f"gen_timeout_fermat_{i:03d}",
                "smt",
                (
                    f"procedure p_fermat_{i}(x: int, y: int, z: int)\n"
                    f"  requires x >= {k} && y >= {k} && z >= {k}\n"
                    "{\n"
                    "  assert x * x * x * x * x + y * y * y * y * y "
                    "!= z * z * z * z * z;\n"
                    "}\n"
                ),
                TIMEOUT_FAMILY,
                "z3",
                None,
                budget_ms=TIMEOUT_BUDGET_MS,
            )
        )

    # -- parse: `if` statements (straight-line + while only)
    for i in range(COUNTS["parse-if"]):
        n = i + 1
        programs.append(
            FailureProgram(
                f"gen_parse_if_{i:03d}",
                "parse",
                (
                    f"procedure p_if_{i}(x: int)\n"
                    f"{{\n  if x > {n} {{\n    assert x >= {n};\n  }}\n}}\n"
                ),
                "parse-if",
                "boogie-parser",
                "parse",
            )
        )

    # -- parse: call statements
    for i in range(COUNTS["parse-call"]):
        n = i + 1
        programs.append(
            FailureProgram(
                f"gen_parse_call_{i:03d}",
                "parse",
                (
                    f"procedure p_call_{i}(x: int)\n"
                    f"{{\n  call helper_{i}(x);\n  assert x >= {n};\n}}\n"
                    f"procedure helper_{i}(x: int)\n{{\n}}\n"
                ),
                "parse-call",
                "boogie-parser",
                "parse",
            )
        )

    # -- parse: uninterpreted function calls (definition-less functions)
    for i in range(COUNTS["parse-uninterp"]):
        programs.append(
            FailureProgram(
                f"gen_parse_uninterp_{i:03d}",
                "parse",
                (
                    f"function f_{i}(x: int) returns (int);\n"
                    f"procedure p_uninterp_{i}(x: int)\n"
                    f"{{\n  assert f_{i}(x) >= {i};\n}}\n"
                ),
                "parse-uninterp",
                "boogie-parser",
                "parse",
            )
        )

    # -- parse: unsupported types
    bad_types = ["multiset<int>", "bv8", "set<int>", "map<int,int>", "nat"]
    for i in range(COUNTS["parse-type"]):
        bad = bad_types[i % len(bad_types)]
        programs.append(
            FailureProgram(
                f"gen_parse_type_{i:03d}",
                "parse",
                (f"procedure p_type_{i}(v: {bad})\n{{\n  assert |v| >= {i};\n}}\n"),
                "parse-type",
                "boogie-parser",
                "parse",
            )
        )

    # -- parse: stray tokens (`;;` / dangling brace)
    for i in range(COUNTS["parse-stray"]):
        n = i + 1
        if i % 2 == 0:
            body = f"{{\n  assert x > {n};;\n}}\n"
        else:
            body = f"{{\n  assert x >= {n};\n}}\n}}\n"
        programs.append(
            FailureProgram(
                f"gen_parse_stray_{i:03d}",
                "parse",
                f"procedure p_stray_{i}(x: int)\n{body}",
                "parse-stray",
                "boogie-parser",
                "parse",
            )
        )

    return programs


def observe(program: FailureProgram) -> str:
    """Run the entry's backend; returns the observed status / I7 kind."""
    result = import_module(program.source, f"{program.name}.bpl")
    if program.backend == "boogie-parser":
        if not result.diagnostics:
            raise SystemExit(f"{program.name}: designed parse failure produced no diagnostics")
        return "parse"
    assert result.ok, [d.native_message for d in result.diagnostics]
    engine = SmtBackend("z3")
    statuses = {
        verdict_status(engine.run(obl, budget=program.budget_ms)) for obl in result.obligations
    }
    if len(statuses) > 1:
        raise SystemExit(f"{program.name}: mixed verdicts {statuses}")
    return statuses.pop()


def generate(target_dir: Path) -> dict[str, object]:
    """Deterministically (re)build failure programs + expected.json content."""
    expected: dict[str, dict[str, str]] = {}
    programs = build_failure_programs()
    for subdir in ("smt", "parse"):
        (target_dir / subdir).mkdir(parents=True, exist_ok=True)
        current = {f"{p.name}.bpl" for p in programs if p.subdir == subdir}
        for stale in (target_dir / subdir).glob("*.bpl"):
            if stale.name not in current:
                stale.unlink()

    for program in programs:
        out = target_dir / program.subdir / f"{program.name}.bpl"
        status = observe(program)
        if program.expected is not None and status != program.expected:
            raise SystemExit(
                f"{program.name}: designed {program.expected} but backend returned {status}"
            )
        out.write_text(program.source, encoding="utf-8")
        rel = out.relative_to(target_dir).as_posix()
        expected[rel] = {
            "file": rel,
            "backend": program.backend,
            "family": program.family,
            "expected": status,
        }

    return {
        "meta": {
            "seed": SEED,
            "z3_pin": "5.1.0",
            "budget_ms_default": DEFAULT_BUDGET_MS,
            "budget_ms_unknown": UNKNOWN_BUDGET_MS,
            "budget_ms_timeout": TIMEOUT_BUDGET_MS,
            "required_backends": ["z3", "boogie-parser"],
            "note": (
                "expected statuses / I7 kinds were observed with the pinned z3 at "
                "generation time; refutation families additionally match their "
                "by-construction verdicts. The cvc5 arm re-checks smt/* entries "
                "through Cvc5Backend when UVIL_CVC5 is set (tests skip if absent). "
                "Unknown/timeout-family entries never discharge: they stay open or "
                "timeout with a matching I7 (this backend reports budget "
                "exhaustion as timeout; plain unknown is recorded identically)."
            ),
        },
        "expected": expected,
    }


def main() -> int:
    payload = generate(FAILURES_DIR)
    n = len(payload["expected"])
    EXPECTED_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {EXPECTED_PATH} with {n} required-backend entries (target >= {TARGET_REQUIRED})")
    if n < TARGET_REQUIRED:
        raise SystemExit(f"failure corpus too small: {n} < {TARGET_REQUIRED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
