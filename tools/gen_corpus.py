"""Deterministic corpus generator: parameterized Boogie families -> obligations.

Emits `corpora/boogie/generated/<name>.bpl` programs plus
`corpora/boogie/expected.json` mapping obligation identity -> expected status
for the whole corpus (curated + generated). Regeneration is idempotent and
deterministic: the same seed (and the pinned z3) always produce the same files
and the same identity set - covered by a property test.

Verdict provenance: "designed" families have verdicts by construction (proved
identities, false assertions) and the generator fails if z3 disagrees within
its budget; "observed" families (nonlinear unknown / timeout inducers) record
exactly what the pinned z3 returns, so the corpus verifies solver stability.

One assert per procedure (the M0 obligation-identity tuple
`(spec, semantics_model, program_fragment, profile_version)` is per-procedure;
one assert keeps identities collision-free). Every instantiation places its
literals inside the spec or fragment so identities stay distinct.
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from uvil.adapters.boogie.lower import ImportResult, import_module  # noqa: E402
from uvil.check.core import SmtBackend  # noqa: E402
from uvil.adapters.smt.backends import verdict_status  # noqa: E402
from uvil.store import obligation_identity  # noqa: E402

CORPUS_DIR = REPO_ROOT / "corpora" / "boogie"
GENERATED_DIR = CORPUS_DIR / "generated"
EXPECTED_PATH = CORPUS_DIR / "expected.json"

SEED = 20260908
DEFAULT_BUDGET_MS = 2000
TIMEOUT_BUDGET_MS = 300
TARGET_OBLIGATIONS = 500


@dataclass(frozen=True)
class CorpusProgram:
    name: str
    source: str
    family: str
    expected: str | None  # designed status, or None to observe with z3
    budget_ms: int = DEFAULT_BUDGET_MS


def _procedure(name: str, params: str, requires: list[str], body_assert: str) -> str:
    reqs = "".join(f"  requires {r}\n" for r in requires)
    return f"procedure {name}({params})\n{reqs}{{\n  assert {body_assert};\n}}\n"


def build_generated_programs() -> list[CorpusProgram]:
    """Families x deterministic instantiations (seeded literal pools)."""
    rng = random.Random(SEED)
    programs: list[CorpusProgram] = []

    def triple(count: int, lo: int, hi: int) -> list[tuple[int, int, int]]:
        return [(rng.randint(lo, hi), rng.randint(lo, hi), rng.randint(lo, hi)) for _ in range(count)]

    # 1. arithmetic commutativity, anchored by a bound literal
    for i, (a, b, k) in enumerate(triple(60, -1000, 1000)):
        programs.append(
            CorpusProgram(
                f"gen_arith_comm_{i:03d}",
                _procedure("p", "a: int, b: int", [f"a >= {a} && b >= {b}"], "a + b == b + a"),
                family="arith-comm",
                expected="discharged",
            )
        )
        del k

    # 2. distributivity with a range anchor
    for i, (a, b, c) in enumerate(triple(50, -100, 100)):
        programs.append(
            CorpusProgram(
                f"gen_distrib_{i:03d}",
                _procedure(
                    "p", "a: int, b: int, c: int", [f"c <= {c} && c >= {c}"],
                    "(a + b) * c == a * c + b * c",
                ),
                family="distrib",
                expected="discharged",
            )
        )

    # 3. square of a sum
    for i, (x, y, _) in enumerate(triple(40, -50, 50)):
        del _
        programs.append(
            CorpusProgram(
                f"gen_sq_sum_{i:03d}",
                _procedure(
                    "p", "x: int, y: int", [f"x >= {x} && y >= {y}"],
                    "(x + y) * (x + y) == x * x + 2 * x * y + y * y",
                ),
                family="sq-sum",
                expected="discharged",
            )
        )

    # 4. abs/clamp bounds
    for i, (x, k, _) in enumerate(triple(40, 1, 500)):
        del x, _
        programs.append(
            CorpusProgram(
                f"gen_abs_bound_{i:03d}",
                _procedure("p", "x: int", [f"x >= -{k} && x <= {k}"], f"(if x < 0 then -x else x) <= {k}"),
                family="abs-bound",
                expected="discharged",
            )
        )

    # 5. min/max via ite
    for i, (a, b, m) in enumerate(triple(40, 0, 300)):
        programs.append(
            CorpusProgram(
                f"gen_minmax_{i:03d}",
                _procedure(
                    "p", "a: int, b: int", [f"a <= {a + m} && b <= {b + m}"],
                    f"(if a < b then a else b) <= {max(a, b) + m}",
                ),
                family="minmax",
                expected="discharged",
            )
        )

    # 6. div/mod identity (Euclidean, positive divisor)
    for i, (a, b, _) in enumerate(triple(40, 1, 200)):
        del _
        programs.append(
            CorpusProgram(
                f"gen_divmod_{i:03d}",
                _procedure("p", "a: int, b: int", [f"b == {b}"], f"a / b * b + a % b == a"),
                family="divmod",
                expected="discharged",
            )
        )

    # 7. refutable linear (negation satisfiable by construction)
    for i, (a, b, _) in enumerate(triple(60, 1, 100)):
        del b, _
        programs.append(
            CorpusProgram(
                f"gen_refut_linear_{i:03d}",
                _procedure("p", "a: int", [f"a >= {a}"], "a + a == 3 * a"),
                family="refut-linear",
                expected="refuted",
            )
        )

    # 8. refutable bounded (a witness below the bound always exists)
    for i, (n, _, _) in enumerate(triple(30, 3, 60)):
        del _;
        programs.append(
            CorpusProgram(
                f"gen_refut_bound_{i:03d}",
                _procedure("p", "x: int", [f"0 <= x && x <= {n}"], f"x * x >= {n + 1}"),
                family="refut-bound",
                expected="refuted",
            )
        )

    # 9. array store/select at the stored index
    for i, (j, v, _) in enumerate(triple(40, 0, 90)):
        del _
        programs.append(
            CorpusProgram(
                f"gen_arr_store_sel_{i:03d}",
                _procedure("p", "a: [int]int", [], f"a[{j} := {v}][{j}] == {v}"),
                family="arr-store-sel",
                expected="discharged",
            )
        )

    # 10. array store/select away from the index
    for i, (idx, j, v) in enumerate(triple(40, 0, 90)):
        if idx == j:
            j = (j + 1) % 91
        programs.append(
            CorpusProgram(
                f"gen_arr_store_other_{i:03d}",
                _procedure("p", "a: [int]int", [f"{idx} != {j}"], f"a[{idx} := {v}][{j}] == a[{j}]"),
                family="arr-store-other",
                expected="discharged",
            )
        )

    # 11. quantified array bounds -> instance
    for i, (n, _, _) in enumerate(triple(35, 1, 40)):
        del _;
        programs.append(
            CorpusProgram(
                f"gen_arr_quant_{i:03d}",
                _procedure(
                    "p",
                    "a: [int]int, n: int",
                    [f"n >= {n}", "forall i: int :: 0 <= i && i < n ==> a[i] >= 0"],
                    f"a[{n} - 1] >= 0",
                ),
                family="arr-quant",
                expected="discharged",
            )
        )

    # 12. sequence nth/length reasoning (seq.update has no SMT-LIB rendering)
    for i, (idx, _, k) in enumerate(triple(30, 0, 60)):
        programs.append(
            CorpusProgram(
                f"gen_seq_nth_{i:03d}",
                _procedure(
                    "p", "s: seq<int>",
                    [f"|s| > {idx}",
                     "forall j: int :: 0 <= j && j < |s| ==> s[j] >= 0"],
                    f"s[{idx}] >= 0 && |s| >= {k % 2}",
                ),
                family="seq-nth",
                expected="discharged",
            )
        )

    # 13. loop invariants join the context (boogie-m1 approximation)
    for i, (n, _, _) in enumerate(triple(30, 1, 100)):
        del _;
        src = (
            f"procedure loop_sum_{i}(n: int)\n"
            f"  requires n >= {n}\n"
            f"{{\n"
            f"  var i: int;\n"
            f"  assume i == 0;\n"
            f"  while i < n\n"
            f"    invariant i >= 0\n"
            f"  {{\n"
            f"    i := i + 1;\n"
            f"  }}\n"
            f"  assert i >= 0;\n"
            f"}}\n"
        )
        programs.append(CorpusProgram(f"gen_loop_inv_{i:03d}", src, family="loop-inv", expected="discharged"))

    # 14. observed: nonlinear integer unknowns (records z3's actual verdict)
    for i, (x, y, _) in enumerate(triple(4, 7, 13)):
        del _
        programs.append(
            CorpusProgram(
                f"gen_nonlinear_{i:03d}",
                _procedure("p", "x: int, y: int", [f"x >= {x} && y >= {y}"], "x * x * x == y * y * y + 1"),
                family="nonlinear-unknown",
                expected=None,
            )
        )

    # 15. observed + slow: Fermat n=5 shape (valid but never decidable fast);
    # z3 must prove unsatisfiability of x^5+y^5==z^5 over positive ints
    programs.append(
        CorpusProgram(
            "gen_timeout_000",
            _procedure(
                "p", "x: int, y: int, z: int", ["x >= 1 && y >= 1 && z >= 1"],
                "x * x * x * x * x + y * y * y * y * y != z * z * z * z * z",
            ),
            family="timeout",
            expected=None,
            budget_ms=TIMEOUT_BUDGET_MS,
        )
    )

    return programs


# Curated programs checked in next to generated/ (hand-written, one family each).
CURATED: dict[str, dict[str, object]] = {
    "arith_identities.bpl": {"family": "arith-comm", "expected": "discharged"},
    "min_max_abs.bpl": {"family": "abs-bound", "expected": "discharged"},
    "clamp.bpl": {"family": "abs-bound", "expected": "discharged"},
    "div_mod.bpl": {"family": "divmod", "expected": "discharged"},
    "refutable_linear.bpl": {"family": "refut-linear", "expected": "refuted"},
    "refutable_bounds.bpl": {"family": "refut-bound", "expected": "refuted"},
    "array_bounds_select.bpl": {"family": "arr-quant", "expected": "discharged"},
    "array_store_select.bpl": {"family": "arr-store-other", "expected": "discharged"},
    "quantified_ranges.bpl": {"family": "arr-quant", "expected": "discharged"},
    "seq_ops.bpl": {"family": "seq-update", "expected": "discharged"},
    "loop_sum.bpl": {"family": "loop-inv", "expected": "discharged"},
    "loop_count.bpl": {"family": "loop-inv", "expected": "discharged"},
    "loop_invariant_weaker.bpl": {"family": "loop-inv", "expected": "refuted"},
    "mod_reasoning.bpl": {"family": "divmod", "expected": "discharged"},
    "negatives.bpl": {"family": "arith-comm", "expected": "discharged"},
    "vacuity_case.bpl": {"family": "vacuity", "expected": "discharged"},
    "by_block.bpl": {"family": "assert-by", "expected": "discharged"},
    "havoc_case.bpl": {"family": "havoc", "expected": "refuted"},
    "functions_inlined.bpl": {"family": "functions", "expected": "discharged"},
    "axioms_case.bpl": {"family": "axioms", "expected": "discharged"},
    "unknown_nonlinear.bpl": {"family": "nonlinear-unknown", "expected": None},
    "timeout_case.bpl": {"family": "timeout", "expected": None, "budget_ms": TIMEOUT_BUDGET_MS},
}


def identities_for(result: ImportResult) -> dict[str, str]:
    """Obligation identity -> procedure name (procedures carry exactly one assert)."""
    out: dict[str, str] = {}
    for proc in result.procedures.values():
        assert len(proc.obligations) == 1, (
            f"corpus discipline violated: procedure {proc.name} has "
            f"{len(proc.obligations)} asserts (one per procedure required)"
        )
        obl = proc.obligations[0]
        obl_id = obligation_identity(
            spec=obl.spec_ref,
            semantics_model=obl.semantics_model,
            program_fragment=proc.program.fragment or proc.name,
            profile_version=obl.target_profile.rsplit("@", 1)[-1],
        )
        out[obl_id] = proc.name
    return out


def observe(program: CorpusProgram) -> str:
    """Run z3 on every obligation; returns the observed I4 status (all must agree)."""
    result = import_module(program.source, f"{program.name}.bpl")
    assert result.ok, [d.native_message for d in result.diagnostics]
    engine = SmtBackend("z3")
    statuses = {verdict_status(engine.run(obl, budget=program.budget_ms)) for obl in result.obligations}
    if len(statuses) > 1:
        raise SystemExit(f"{program.name}: mixed verdicts {statuses}")
    return statuses.pop()


def generate(target_dir: Path) -> dict[str, object]:
    """Deterministically (re)build generated programs + expected.json content."""
    expected: dict[str, dict[str, str]] = {}
    generated_dir = target_dir / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    programs = build_generated_programs()
    current_names = {f"{p.name}.bpl" for p in programs}

    # idempotency: stale files from earlier seeds must not survive regeneration
    for stale in generated_dir.glob("*.bpl"):
        if stale.name not in current_names:
            stale.unlink()

    for path in sorted(target_dir.glob("*.bpl")):
        entry = CURATED.get(path.name)
        if entry is None:
            raise SystemExit(f"curated file missing from CURATED manifest: {path.name}")
        family, designed = str(entry["family"]), entry["expected"]
        budget = int(entry.get("budget_ms", DEFAULT_BUDGET_MS))
        source = path.read_text(encoding="utf-8")
        result = import_module(source, path.name)
        assert result.ok, [d.native_message for d in result.diagnostics]
        status = observe(CorpusProgram(path.name, source, family, None, budget))
        if designed is not None and status != str(designed):
            raise SystemExit(f"{path.name}: designed {designed} but z3 returned {status}")
        for obl_id, proc_name in identities_for(result).items():
            expected[obl_id] = {
                "file": path.name,
                "family": family,
                "expected": status,
                "proc": proc_name,
            }

    seen_ids: set[str] = set()
    for program in programs:
        out = target_dir / "generated" / f"{program.name}.bpl"
        result = import_module(program.source, out.name)
        assert result.ok, [d.native_message for d in result.diagnostics]
        ids = identities_for(result)
        if seen_ids & set(ids):
            # duplicate content under a different name: skip entirely so the
            # manifest and the files on disk stay 1:1
            out.unlink(missing_ok=True)
            continue
        status = observe(program)
        if program.expected is not None and status != program.expected:
            raise SystemExit(f"{program.name}: designed {program.expected} but z3 returned {status}")
        out.write_text(program.source, encoding="utf-8")
        for obl_id, proc_name in ids.items():
            seen_ids.add(obl_id)
            expected[obl_id] = {
                "file": f"generated/{out.name}",
                "family": program.family,
                "expected": status,
                "proc": proc_name,
            }

    return {
        "meta": {
            "seed": SEED,
            "z3_pin": "5.1.0",
            "budget_ms_default": DEFAULT_BUDGET_MS,
            "budget_ms_timeout": TIMEOUT_BUDGET_MS,
            "note": (
                "expected statuses were observed with the pinned z3 at generation "
                "time; designed families additionally match their by-construction "
                "verdicts. timeout-family entries never discharge (scheduler-"
                "dependent whether z3 reports timeout or plain unknown)."
            ),
        },
        "expected": expected,
    }


def main() -> int:
    payload = generate(CORPUS_DIR)
    n = len(payload["expected"])
    EXPECTED_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {EXPECTED_PATH} with {n} obligation identities (target >= {TARGET_OBLIGATIONS})")
    if n < TARGET_OBLIGATIONS:
        raise SystemExit(f"corpus too small: {n} < {TARGET_OBLIGATIONS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
